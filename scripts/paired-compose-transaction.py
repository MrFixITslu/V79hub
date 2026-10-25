#!/usr/bin/env python3
"""Guarded Compose image-only transaction and durable manual rollback.

This module is called only after a separately verified preparation step. It has
no production CLI, image download/load, backup restore or migration command.
Sealed models and original inspect records remain usable while apps are down.
"""
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time


class Refused(ValueError):
    pass


def module(filename):
    spec=importlib.util.spec_from_file_location(filename.replace('-','_'),Path(__file__).with_name(filename+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def environment(values):
    pairs=[v.split('=',1) for v in values]
    if any(len(p)!=2 for p in pairs) or len({p[0] for p in pairs})!=len(pairs):
        raise Refused('RUNTIME_ENVIRONMENT_INVALID')
    return dict(pairs)


def seal_plan(root,plan):
    fd=module('paired-release-context').private_directory(Path(root))
    raw=json.dumps(plan,sort_keys=True,separators=(',',':')).encode()
    try:
        out=os.open('transaction.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        with os.fdopen(out,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.fsync(fd)
    finally:os.close(fd)
    return hashlib.sha256(raw).hexdigest()


def load_plan(root,expected_sha256):
    import stat
    if not re.fullmatch('[0-9a-f]{64}',expected_sha256 or ''):raise Refused('PLAN_EXTERNAL_DIGEST_REQUIRED')
    directory=module('paired-release-context').private_directory(Path(root))
    try:
        fd=os.open('transaction.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(fd,'rb') as f:
            before=os.fstat(f.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid!=os.geteuid()
                    or before.st_mode&0o077 or before.st_size>16*1024**2):raise Refused('PLAN_FILE_UNSAFE')
            raw=f.read(16*1024**2+1);after=os.fstat(f.fileno())
            for field in ('st_ino','st_dev','st_size','st_mtime_ns','st_ctime_ns'):
                if getattr(before,field)!=getattr(after,field):raise Refused('PLAN_CHANGED_DURING_READ')
    finally:os.close(directory)
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise Refused('PLAN_EXTERNAL_DIGEST_MISMATCH')
    return json.loads(raw)


def runtime_matches(before,after,entry,which,*,selinux_enabled):
    """Full HostConfig/storage plus effective process/env/labels/network checks.

    Only image inheritance differences reviewed during preparation, generated
    Docker hostname/Compose bookkeeping and assigned endpoint IDs can vary.
    """
    expected_id=entry[which+'_image']['Id']
    if after['Image']!=expected_id:raise Refused('ACTUAL_IMAGE_IDENTITY_CHANGED')
    first,second=copy.deepcopy(before),copy.deepcopy(after)
    # Moby adaptContainerSettings defaults absent OomKillDisable to false.
    # verifyPlatformContainerResources may discard false back to nil on cgroup2.
    # Both keep the OOM killer enabled; true must remain strictly different.
    # Primary implementation: moby/moby v28.0.4 daemon/daemon_unix.go.
    for row in (first,second):
        if row['HostConfig'].get('OomKillDisable') is None:
            row['HostConfig']['OomKillDisable']=False
    module('paired-mount-contract').verify_host_storage(first,second,selinux_enabled=selinux_enabled)
    old,new=copy.deepcopy(before['Config']),copy.deepcopy(after['Config'])
    old['Image']=new['Image']=expected_id
    for config,row in ((old,before),(new,after)):
        if (not entry['model']['services'][entry['service']].get('hostname')
                and config.get('Hostname')==row['Id'][:12]):
            config['Hostname']='<generated-container-id>'
    old_env=environment(old.pop('Env',[]) or []);new_env=environment(new.pop('Env',[]) or [])
    configured=entry['model']['services'][entry['service']].get('environment') or {}
    if which=='candidate':
        # Only these reviewed removed base-tool metadata keys may disappear.
        for key in entry.get('removed_metadata',[]):
            if key not in ('NODE_VERSION','YARN_VERSION') or key in configured:
                raise Refused('UNREVIEWED_IMAGE_ENVIRONMENT_CHANGE')
            old_env.pop(key,None)
    if old_env!=new_env:raise Refused('ACTUAL_ENVIRONMENT_CHANGED')
    old_labels=old.pop('Labels',{}) or {};new_labels=new.pop('Labels',{}) or {}
    explicit=entry['model']['services'][entry['service']].get('labels') or {}
    previous=entry['rollback_image']['Config'].get('Labels') or {}
    selected=entry[which+'_image']['Config'].get('Labels') or {}
    for key in set(previous)|set(selected):
        if key not in explicit:
            if key in selected:old_labels[key]=selected[key]
            else:old_labels.pop(key,None)
    generated={
        'com.docker.compose.project.config_files':str(entry[which+'_file']),
        'com.docker.compose.image':expected_id,
        'com.docker.compose.version':entry['compose_version'],
        'com.docker.compose.project.environment_file':'/dev/null',
    }
    for key,value in generated.items():
        if new_labels.get(key)!=value:raise Refused('COMPOSE_BOOKKEEPING_IDENTITY_CHANGED')
        old_labels.pop(key,None);new_labels.pop(key,None)
    config_hash=new_labels.pop('com.docker.compose.config-hash',None)
    old_labels.pop('com.docker.compose.config-hash',None)
    if not isinstance(config_hash,str) or not re.fullmatch('[0-9a-f]{64}',config_hash):
        raise Refused('COMPOSE_CONFIG_HASH_MISSING')
    # Compose's generated dependency label reflects --no-deps, while the sealed
    # full model retains every dependency. Reserved labels are not app settings.
    if new_labels.pop('com.docker.compose.depends_on',None) not in (None,''):
        raise Refused('COMPOSE_NO_DEPS_LABEL_CHANGED')
    old_labels.pop('com.docker.compose.depends_on',None)
    # compose v2.38.2 convergence.go records the exact replaced container ID.
    replacement=new_labels.pop('com.docker.compose.replace',None)
    if replacement!=entry.get('_replaced_id'):
        raise Refused('COMPOSE_REPLACED_CONTAINER_ID_CHANGED')
    old_labels.pop('com.docker.compose.replace',None)
    if old_labels!=new_labels:
        fields=sorted(k for k in set(old_labels)|set(new_labels) if old_labels.get(k)!=new_labels.get(k))
        raise Refused('APPLICATION_LABELS_CHANGED:'+','.join(fields))
    if old!=new:
        fields=sorted(k for k in set(old)|set(new) if old.get(k)!=new.get(k))
        raise Refused('ACTUAL_CONFIG_FIELDS_CHANGED:'+','.join(fields))
    networks_before=before.get('NetworkSettings',{}).get('Networks',{})
    networks_after=after.get('NetworkSettings',{}).get('Networks',{})
    # A created-but-never-started container may not yet have endpoint IDs.
    if after['State'].get('Running'):
        if set(networks_before)!=set(networks_after):raise Refused('ACTUAL_NETWORK_SCOPE_CHANGED')
        for name,endpoint in networks_before.items():
            actual=networks_after[name]
            for key in ('NetworkID','IPAMConfig','Links','DriverOpts'):
                a,b=endpoint.get(key),actual.get(key)
                if key in ('IPAMConfig','DriverOpts'):a,b=a or {},b or {}
                if a!=b:raise Refused('ACTUAL_NETWORK_OPTIONS_CHANGED')
            def aliases(row,ep):
                return sorted(set(ep.get('Aliases') or [])-{row['Id'],row['Id'][:12]})
            if aliases(before,endpoint)!=aliases(after,actual):raise Refused('ACTUAL_NETWORK_ALIASES_CHANGED')
            service=entry['model']['services'][entry['service']]
            if service.get('mac_address') and endpoint.get('MacAddress')!=actual.get('MacAddress'):
                raise Refused('CONFIGURED_MAC_ADDRESS_CHANGED')
    return True


def protected_fingerprint(row):
    return digest({'Id':row['Id'],'Image':row['Image'],'Config':row['Config'],
        'HostConfig':row['HostConfig'],'Mounts':sorted(row.get('Mounts') or [],key=lambda m:m['Destination']),
        'Networks':row.get('NetworkSettings',{}).get('Networks'),
        'Status':row['State']['Status'],'StartedAt':row['State'].get('StartedAt')})


class ComposeBackend:
    def __init__(self,root,plan):
        self.root=Path(root);self.plan=plan
        fd=module('paired-release-context').private_directory(self.root)
        os.close(fd)

    def call(self,args,*,timeout=90):
        try:p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                             timeout=timeout,env={**os.environ,'COMPOSE_PARALLEL_LIMIT':'1'})
        except (OSError,subprocess.TimeoutExpired):raise Refused('COMMAND_OUTCOME_REQUIRES_ROLLBACK') from None
        if p.returncode:raise Refused('COMMAND_FAILED_REDACTED')
        return p.stdout

    def inspect(self,name,*,allow_missing=False):
        try:p=subprocess.run(['docker','inspect',name],capture_output=True,timeout=30)
        except (OSError,subprocess.TimeoutExpired):raise Refused('INSPECTION_UNAVAILABLE') from None
        if p.returncode:
            if allow_missing and b'no such' in p.stderr.lower():return None
            raise Refused('INSPECTION_FAILED_REDACTED')
        return json.loads(p.stdout)[0]

    def supervised(self):
        if not self.plan.get('requires_supervision'):return
        try:
            path=self.root/'supervision.json';info=path.lstat()
            if (path.is_symlink() or not path.is_file() or info.st_uid!=os.geteuid()
                    or info.st_nlink!=1 or info.st_mode&0o077 or info.st_size>128):
                raise ValueError()
            heartbeat=json.loads(path.read_bytes())['monotonic']
            if not isinstance(heartbeat,(int,float)) or not 0<=time.monotonic()-heartbeat<=30:
                raise ValueError()
        except Exception:raise Refused('OWNER_SUPERVISION_LEASE_LOST') from None

    def protected(self):
        names=self.call(['docker','ps','--all','--format','{{.Names}}']).decode().splitlines()
        expected=self.plan['protected']
        if set(names)-set(self.plan['apps'])!=set(expected):
            raise Refused('CONTAINER_INVENTORY_CHANGED')
        for name,row in expected.items():
            now=self.inspect(row['Id'])
            if protected_fingerprint(now)!=protected_fingerprint(row):
                raise Refused('UNRELATED_CONTAINER_RUNTIME_CHANGED')
            if name in ('v79-business-agent','v79-hub-postgres','tiquet-postgres'):
                if now['State'].get('Health',{}).get('Status')!='healthy':
                    raise Refused('PROTECTED_CORE_HEALTH_CHANGED')

    def journal(self,event,name=None):
        # Append-only intent survives ambiguous CLI failure and process restart.
        # No configuration or secret values are written to the public journal.
        data=json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         'event':event,'app':name},sort_keys=True).encode()+b'\n'
        fd=os.open(self.root/'events.jsonl',os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'ab') as f:f.write(data);f.flush();os.fsync(f.fileno())
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)

    def check_files(self):
        for entry in self.plan['apps'].values():
            for which in ('candidate','rollback'):
                path=Path(entry[which+'_file'])
                st=path.lstat()
                if (path.parent!=self.root or path.is_symlink() or not path.is_file()
                        or st.st_uid!=os.geteuid() or st.st_mode&0o077
                        or hashlib.sha256(path.read_bytes()).hexdigest()!=entry[which+'_sha256']):
                    raise Refused('SEALED_MODEL_FILE_CHANGED')

    def eligible(self,name,*,allow_missing=False):
        entry=self.plan['apps'][name];row=self.inspect(name,allow_missing=allow_missing)
        if row is None:return
        if row['Image'] not in {entry['candidate_image']['Id'],entry['rollback_image']['Id']}:
            raise Refused('FOREIGN_IMAGE_NO_MUTATION')
        labels=row['Config'].get('Labels') or {}
        if labels.get('com.docker.compose.project')!=entry['project'] or labels.get('com.docker.compose.service')!=entry['service']:
            raise Refused('FOREIGN_COMPOSE_IDENTITY_NO_MUTATION')
        if row['Id']!=entry['baseline']['Id'] and labels.get('com.docker.compose.project.config_files') not in (
                str(entry['candidate_file']),str(entry['rollback_file'])):
            raise Refused('FOREIGN_REPLACEMENT_CONTAINER_NO_MUTATION')

    def switch(self,name,which):
        if which=='candidate':self.supervised()
        self.check_files();self.protected();self.eligible(name,allow_missing=which=='rollback')
        entry=self.plan['apps'][name]
        previous=self.inspect(name,allow_missing=which=='rollback')
        entry['_replaced_id']=None if previous is None else previous['Id']
        args=['docker','compose','--env-file','/dev/null','--project-directory',
              entry['directory'],'--project-name',entry['project'],'-f',entry[which+'_file']]
        # Up supports --no-deps and --no-start. Create's dependency behavior and
        # unsupported --no-deps spelling must not recreate a database by accident.
        self.call([*args,'up','--no-start','--no-deps','--no-build','--pull','never',
                   '--force-recreate',entry['service']],timeout=180)
        row=self.inspect(name)
        if row['State'].get('Running'):raise Refused('UNEXPECTED_START_BEFORE_RUNTIME_GATE')
        self.verify(name,which,row)
        self.protected()
        if which=='candidate':self.supervised()
        self.call(['docker','start',row['Id']])
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            if which=='candidate':self.supervised()
            now=self.inspect(row['Id']);self.verify(name,which,now)
            if now['State'].get('Running') and now['State'].get('Health',{}).get('Status')=='healthy':
                self.protected();return
            if now['State'].get('Status') in ('exited','dead','removing'):
                raise Refused('SELECTED_APP_STARTUP_FAILED')
            time.sleep(2)
        raise Refused('SELECTED_APP_HEALTH_TIMEOUT')

    def verify(self,name,which,row=None):
        entry=self.plan['apps'][name]
        return runtime_matches(entry['baseline'],row or self.inspect(name),entry,which,
                               selinux_enabled=self.plan['selinux_enabled'])

    def healthy(self,name,which):
        if which=='candidate':self.supervised()
        row=self.inspect(name);self.verify(name,which,row)
        if not row['State'].get('Running') or row['State'].get('Health',{}).get('Status')!='healthy':
            raise Refused('EXPECTED_APP_NOT_HEALTHY')


def stopped_profiles(backend):
    """Create exact process/host profiles with synthetic sources; never start.

    Published-port declarations are preserved, but no process/socket starts.
    Every real bind/volume source is replaced before creating the container.
    Resource deletion is limited to exact nonce-owned never-started probes.
    """
    import uuid
    nonce='v79profile'+uuid.uuid4().hex[:16]
    print('STOPPED_PROFILE_SCOPE='+nonce,flush=True)
    directory=backend.root/nonce;directory.mkdir(mode=0o700)
    created=[];volumes=[];verified=0
    backend.protected();backend.check_files()
    try:
        for name,entry in backend.plan['apps'].items():
            for which in ('candidate','rollback'):
                backend.supervised()
                model=json.loads(Path(entry[which+'_file']).read_bytes())
                service=model['services'][entry['service']]
                probe=nonce+'-'+str(verified);project=probe
                service['container_name']=probe
                expected=copy.deepcopy(entry['baseline'])
                expected['Config']['Labels']['com.docker.compose.project']=project
                expected['Name']='/'+probe
                replacements={}
                declared=service.get('volumes') or []
                if not all(isinstance(v,dict) for v in declared):raise Refused('PROFILE_LONG_MOUNT_MODEL_REQUIRED')
                targets={v['target']:(v,'source') for v in declared}
                # Preserve Compose's own file-secret/config codec, replacing
                # only the source. Targets follow compose v2.38.2 create.go.
                for kind,prefix in (('secrets','/run/secrets/'),('configs','/')):
                    for reference in service.get(kind) or []:
                        if not isinstance(reference,dict) or 'source' not in reference:
                            raise Refused('PROFILE_LONG_SECRET_CONFIG_MODEL_REQUIRED')
                        definition=(model.get(kind) or {}).get(reference['source']) or {}
                        if not definition.get('file') or definition.get('external'):
                            raise Refused('PROFILE_FILE_SECRET_CONFIG_SOURCE_REQUIRED')
                        target=reference.get('target') or reference['source']
                        if not target.startswith('/'):target=prefix+target
                        if target in targets:raise Refused('PROFILE_DUPLICATE_MOUNT_TARGET')
                        targets[target]=(definition,'file')
                if set(targets)!={m['Destination'] for m in expected.get('Mounts') or []}:
                    raise Refused('PROFILE_MOUNT_SCOPE_UNACCOUNTED')
                for index,mount in enumerate(expected.get('Mounts') or []):
                    spec,source_key=targets[mount['Destination']]
                    if mount['Type']=='bind':
                        original=mount['Source'];source=directory/(probe+'-bind-'+str(index))
                        if Path(original).is_dir():source.mkdir(mode=0o700)
                        elif Path(original).is_file():source.write_bytes(b'synthetic-profile-only');source.chmod(0o600)
                        else:raise Refused('PROFILE_BIND_SOURCE_TYPE_UNAVAILABLE')
                        replacements[original]=str(source);mount['Source']=str(source);spec[source_key]=str(source)
                    elif mount['Type']=='volume':
                        if mount.get('Driver')!='local':raise Refused('PROFILE_VOLUME_DRIVER_UNSUPPORTED')
                        volume=probe+'-volume-'+str(index)
                        backend.call(['docker','volume','create','--label','v79.profile.scope='+nonce,volume])
                        volumes.append(volume)
                        metadata=json.loads(backend.call(['docker','volume','inspect',volume]))[0]
                        replacements[mount['Name']]=volume
                        mount['Name']=volume;mount['Source']=metadata['Mountpoint']
                        if source_key!='source':raise Refused('PROFILE_VOLUME_SOURCE_CODEC_INVALID')
                        key=spec[source_key];model.setdefault('volumes',{})[key]={'name':volume,'external':True}
                    else:raise Refused('PROFILE_MOUNT_TYPE_UNSUPPORTED')
                host=expected['HostConfig']
                if host.get('Binds'):
                    host['Binds']=[replacements.get(value.split(':',1)[0],value.split(':',1)[0])+':'+value.split(':',1)[1]
                                   for value in host['Binds']]
                for mount in host.get('Mounts') or []:
                    mount['Source']=replacements.get(mount['Source'],mount['Source'])
                for key,network in list((model.get('networks') or {}).items()):
                    if 'name' not in network:raise Refused('PROFILE_NETWORK_NAME_REQUIRED')
                    model['networks'][key]={'name':network['name'],'external':True}
                path=directory/(probe+'.json')
                path.write_text(json.dumps(model));path.chmod(0o600)
                current=copy.deepcopy(entry);current[which+'_file']=str(path)
                current['model']=model;current['project']=project;current['baseline']=expected
                args=['docker','compose','--env-file','/dev/null','--project-directory',entry['directory'],
                      '--project-name',project,'-f',str(path),'up','--no-start','--no-deps',
                      '--no-build','--pull','never',entry['service']]
                # Remember the exact intended name before the potentially
                # ambiguous create call, so finally can reconcile it safely.
                created.append((probe,project,entry[which+'_image']['Id']))
                backend.call(args,timeout=180)
                row=backend.inspect(probe)
                if row['State'].get('Running') or not str(row['State'].get('StartedAt','0001')).startswith('0001'):
                    raise Refused('PROFILE_UNEXPECTED_PROCESS_START')
                runtime_matches(expected,row,current,which,selinux_enabled=backend.plan['selinux_enabled'])
                verified+=1
    finally:
        cleanup_failed=False
        for probe,project,image in reversed(created):
            try:
                row=backend.inspect(probe,allow_missing=True)
                if row is None:continue
                if (row['Image']!=image or row['Name']!='/'+probe
                        or row['Config']['Labels'].get('com.docker.compose.project')!=project
                        or row['State'].get('Running')
                        or not str(row['State'].get('StartedAt','0001')).startswith('0001')):
                    raise Refused('PROFILE_CLEANUP_OWNERSHIP_OR_STATE_CHANGED')
                backend.call(['docker','rm',row['Id']])
                if backend.inspect(probe,allow_missing=True) is not None:raise Refused('PROFILE_CONTAINER_REMAINS')
            except BaseException:cleanup_failed=True
        for volume in reversed(volumes):
            try:
                info=json.loads(backend.call(['docker','volume','inspect',volume]))[0]
                if (info['Name']!=volume or (info.get('Labels') or {}).get('v79.profile.scope')!=nonce):
                    raise Refused('PROFILE_VOLUME_OWNERSHIP_CHANGED')
                backend.call(['docker','volume','rm',volume])
            except BaseException:cleanup_failed=True
        if cleanup_failed:raise Refused('PROFILE_OWNED_CLEANUP_INCOMPLETE')
        backend.protected()
    return {'status':'PASS_STOPPED_EXACT_PROFILES_SYNTHETIC_MOUNTS_ONLY',
            'profiles_verified':verified,'application_processes_started':False,
            'live_application_data_mounted':False,'temporary_resource_cleanup_verified':True}


def rollback(backend,names):
    """Attempt every touched app even if one rollback fails; never delete data."""
    failures=[]
    for name in reversed(list(names)):
        try:
            backend.journal('ROLLBACK_INTENT',name)
            backend.switch(name,'rollback')
            backend.healthy(name,'rollback')
            backend.journal('ROLLBACK_HEALTHY',name)
        except BaseException:
            backend.journal('ROLLBACK_FAILED',name);failures.append(name)
    if failures:
        backend.journal('ROLLBACK_INCOMPLETE')
        raise Refused('ROLLBACK_INCOMPLETE_OPERATOR_REQUIRED')
    backend.protected();backend.journal('ORIGINAL_PAIR_RESTORED')
    return {'status':'PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED',
            'application_data_restored':False,'release_decision':'HOLD'}


def deploy(backend):
    """Record intent before each destructive call; rollback on ambiguous outcome."""
    touched=[]
    backend.protected();backend.check_files()
    for name in backend.plan['apps']:backend.eligible(name)
    try:
        for name in backend.plan['apps']:
            backend.journal('CANDIDATE_INTENT',name);touched.append(name)
            backend.switch(name,'candidate');backend.healthy(name,'candidate')
            backend.journal('CANDIDATE_HEALTHY',name)
        for name in backend.plan['apps']:backend.healthy(name,'candidate')
        backend.protected();backend.journal('PAIR_HEALTHY_ACCEPTANCE_PENDING')
        return {'status':'PASS_DEPLOYED_HEALTHY_ACCEPTANCE_PENDING',
                'release_decision':'HOLD','supervised_acceptance_complete':False}
    except BaseException as error:
        backend.journal('CANDIDATE_FAILED',touched[-1] if touched else None)
        result=rollback(backend,touched)
        result['candidate_deployment_failed']=True
        result['candidate_failure_reason']=(str(error) if type(error).__name__=='Refused'
            and re.fullmatch('[A-Z][A-Za-z0-9_:,.]+',str(error)) else 'CANDIDATE_EXECUTION_INTERRUPTED_OR_FAILED')
        return result
