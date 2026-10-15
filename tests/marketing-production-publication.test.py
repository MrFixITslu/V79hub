"""Publication activation: exact flag scope, custody and no effects on retry."""
import copy
import datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load():
    spec=importlib.util.spec_from_file_location('publication',ROOT/'scripts/marketing-production-enable-publication.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    ns={'__name__':'test_support'};exec(compile(module.REMOTE_PROGRAM,'<publication-test>','exec'),ns)
    return module,ns

def runtime(ns,enabled=False):
    labels={'com.docker.compose.project.config_files':','.join(ns['FILES']),'com.docker.compose.project':ns['PROJECT'],
            'com.docker.compose.service':ns['SERVICE'],'com.docker.compose.project.working_dir':ns['DIRECTORY'],
            'com.docker.compose.config-hash':'before','org.opencontainers.image.revision':'preserved'}
    meta={'Id':'a'*64,'Image':ns['IMAGE'],'Config':{'Image':ns['IMAGE'],'Hostname':'a'*12,'User':'node','WorkingDir':'/app',
        'Cmd':['node','dist/server.cjs'],'Env':['NODE_ENV=production',ns['FLAG']+'=0','V79_MARKETING_PRODUCTION_ENABLED=1',
        'V79_MARKETING_PRODUCTION_OWNER_ORG_ID=founder','AUDIT_KEY=synthetic-preserved'],'Labels':labels},
        'HostConfig':{'Memory':805306368,'Binds':['one:/one:ro','two:/two:rw']},'Mounts':[{'Destination':'/app/data','RW':True}],
        'NetworkSettings':{'Networks':{'proxy_network':{}}},'State':{'Running':True,'Health':{'Status':'healthy'}}}
    if enabled:
        meta['Id']='b'*64;meta['Config']['Hostname']='b'*12
        meta['Config']['Env']=[v.replace(ns['FLAG']+'=0',ns['FLAG']+'=1') for v in meta['Config']['Env']]
        labels['com.docker.compose.project.config_files']+=','+str(ns['ROOT']/'publication.yml');labels['com.docker.compose.config-hash']='after'
        meta['HostConfig']['Binds'].reverse()
    return meta

class PublicationTests(unittest.TestCase):
    def test_only_publication_flag_changes_in_resolved_config_and_runtime(self):
        _,ns=load();old={'services':{ns['SERVICE']:{'image':ns['IMAGE'],'environment':{ns['FLAG']:'0','audit':'same'},'cpus':1},'db':{'image':'same'}}}
        new=copy.deepcopy(old);new['services'][ns['SERVICE']]['environment'][ns['FLAG']]='1';ns['parity'](old,new)
        for field in ('image','environment','cpus','unrelated'):
            bad=copy.deepcopy(new)
            if field=='environment':bad['services'][ns['SERVICE']][field]['audit']='changed'
            elif field=='unrelated':bad['services']['db']['image']='changed'
            else:bad['services'][ns['SERVICE']][field]='changed'
            with self.assertRaises(RuntimeError):ns['parity'](old,bad)
        ns['h']={'healthy':lambda m:True,'env_map':lambda xs:dict(v.split('=',1) for v in xs),'mounts':lambda m:m['Mounts']}
        before,after=runtime(ns),runtime(ns,True);ns['runtime_parity'](before,after,None)
        for field in ('Cmd','User','WorkingDir','Env','Hostname','Image'):
            bad=copy.deepcopy(after);bad['Config'][field]=['CHANGED=1'] if field=='Env' else 'changed'
            with self.assertRaises(RuntimeError):ns['runtime_parity'](before,bad,None)
        for change in (lambda x:x['HostConfig'].update(Memory=1),lambda x:x['HostConfig']['Binds'].append('socket:/var/run/docker.sock:rw'),lambda x:x['Mounts'][0].update(RW=False),lambda x:x['NetworkSettings']['Networks'].update(extra={})):
            bad=copy.deepcopy(after);change(bad)
            with self.assertRaises(RuntimeError):ns['runtime_parity'](before,bad,None)

    def test_signed_guard_rejects_approved_running_and_uncertain_effects(self):
        _,ns=load();spec=importlib.util.spec_from_file_location('cutover',ROOT/'scripts/marketing-production-panel-cutover.py')
        support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
        captured=[];ns['support']={'MARKETING_STATE':support.MARKETING_STATE}
        ns['h']={'run':lambda args,**kw:captured.append((args,kw['data'])) or b'digest'};ns['signed_state']()
        args,probe=captured[0];self.assertEqual(args[:3],['docker','exec','-i'])
        harness=r"""
const vm=require('node:vm'),crypto=require('node:crypto'),assert=require('node:assert/strict'),key='x'.repeat(64),id='44289786-2583-4bf1-9db2-99eca95dfd96';
let status='awaiting_owner',tamper=false,closed=false;
class DB{pragma(){}prepare(){return {get(){const state={paused:true,seenRequests:[],jobs:[{status:'awaiting_owner',deliveries:[{status}]}]};
const canonical=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
return {envelope:JSON.stringify({state,hmac:tamper?'0'.repeat(64):crypto.createHmac('sha256',key).update('v79-marketing-production-v1\n'+id+'\n'+canonical(state)).digest('hex')})};}};}close(){closed=true;}}
const run=()=>vm.runInNewContext(PROBE,{require:n=>n==='better-sqlite3'?DB:require(n),process:{env:{V79_MARKETING_PRODUCTION_AUDIT_KEY:key}},Buffer,console:{log(){}},Date});
for(status of ['awaiting_owner','rejected','cancelled','blocked'])run();
for(status of ['approved','running','uncertain']){closed=false;assert.throws(run);assert.ok(closed);}
status='awaiting_owner';tamper=true;assert.throws(run,/Ledger integrity/);
"""
        result=subprocess.run(['node','--input-type=commonjs','-'],input=('const PROBE='+json.dumps(probe.decode())+';'+harness).encode(),capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode())

    def test_activation_and_failure_paths_never_retry_or_change_other_services(self):
        for failure in (None,'custody','state','scope','restart','post-runtime','post-data'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                _,ns=load();ns['ROOT']=Path(directory);root=ns['ROOT'];calls=[];switched=False
                before=runtime(ns);after=runtime(ns,True)
                values={name:copy.deepcopy(before) for name in ns['NAMES']};values['v79-hub']['Image']=ns['HUB_IMAGE']
                config={'services':{ns['SERVICE']:{'image':ns['IMAGE'],'environment':{ns['FLAG']:'0'}}}}
                candidate=copy.deepcopy(config);candidate['services'][ns['SERVICE']]['environment'][ns['FLAG']]='1'
                baseline={'hub':'protected','marketing':'customer-provider-data','campaigns':'signed-state'}
                source={'/protected/env':'preserved'}
                digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()
                def write_json(path,value):
                    with Path(path).open('x') as out:json.dump(value,out)
                (root/'publication.yml').write_text('flag-only')
                encrypted={'backup.gpg':'cipher-hash'};clear={'backup.gpg':'plain-hash'}
                manifest={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runtimeHashes':ns['runtime_hashes'](values) if ns['h'] else {},'sourceHashes':source,
                    'protected':baseline,'originalResolvedHash':digest(config),'desiredResolvedHash':digest(candidate),
                    'encryptedBackups':encrypted,'plaintextHashes':clear,'overlayHash':'overlay-hash'}
                def file_hash(path,*_):
                    path=Path(path)
                    return 'manifest-hash' if path.name=='manifest.json' else 'overlay-hash' if path.name=='publication.yml' else 'cipher-hash'
                def snapshot():
                    result=copy.deepcopy(values)
                    if switched:
                        result[ns['MARKETING']]=copy.deepcopy(after)
                        if failure=='post-runtime':result['v79-hub']['Id']='changed'
                    return result
                def protected():return {**baseline,'marketing':'changed'} if failure in ('state','post-data') and (failure=='state' or switched) else baseline
                def run(args,**kwargs):
                    nonlocal switched
                    calls.append(args)
                    if 'up' in args:
                        self.assertTrue((root/'switch-attempted.json').is_file());switched=True
                        self.assertEqual(args[-1],ns['SERVICE']);self.assertIn('--no-deps',args);self.assertIn('--no-build',args);self.assertEqual(args[args.index('--pull')+1],'never')
                        if failure=='restart':raise RuntimeError('Synthetic restart timeout')
                    return b''
                ns['h']={'file_hash':file_hash,'fingerprint':digest,'stable_runtime':lambda x:x,'write_json':write_json,'run':run,
                    'healthy':lambda x:True,'env_map':lambda xs:dict(v.split('=',1) for v in xs),'mounts':lambda x:x['Mounts']}
                manifest['runtimeHashes']=ns['runtime_hashes'](values)
                write_json(root/'manifest.json',manifest)
                ns.update(snapshot=snapshot,check_disabled=lambda _:config,source_hashes=lambda _:source,protected=protected,
                    resolve=lambda _:candidate,probe_enabled=lambda:calls.append(['boundary-probes']))
                if failure=='scope':candidate['services'][ns['SERVICE']]['image']='changed'
                payload={'manifestSha256':'manifest-hash','encryptedBackups':encrypted,'plaintextHashes':clear,'acerCopy':'/acer/private-copy'}
                if failure=='custody':payload['plaintextHashes']={}
                with redirect_stdout(io.StringIO()):
                    if failure:
                        with self.assertRaises(RuntimeError):ns['activate'](payload)
                    else:ns['activate'](payload)
                    # Any uncertain or completed switch is never recreated by rerun.
                    if switched:
                        with self.assertRaises(RuntimeError):ns['activate'](payload)
                self.assertEqual(sum('up' in c for c in calls),int(failure not in ('custody','state','scope')))
                self.assertEqual((root/'deployed.json').exists(),failure is None)
                if failure is None:
                    record=json.loads((root/'deployed.json').read_text());self.assertTrue(record['exactOwnerApprovalRequired']);self.assertTrue(record['noApprovalsCreated']);self.assertFalse(record['automaticRetryOrRollback'])

    def test_acer_does_not_activate_when_decryption_fails(self):
        module,_=load()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data={name:b'encrypted' for name in module.ENCRYPTED}
            manifest={'encryptedBackups':{n:hashlib.sha256(b).hexdigest() for n,b in data.items()},'plaintextHashes':{n:'plain' for n in data}}
            body=json.dumps(manifest).encode();(root/'manifest.json').write_bytes(body)
            for name,blob in data.items():(root/name).write_bytes(blob)
            prepared={**manifest,'directory':'/home/firelion/v79-g3-publication-v1','manifestSha256':hashlib.sha256(body).hexdigest()}
            calls=[]
            with patch.object(module.socket,'gethostname',return_value='firelion-Aspire-A315-51'),patch.object(module.tempfile,'mkdtemp',return_value=directory),patch.object(module,'remote',side_effect=lambda payload,**kw:calls.append(payload) or prepared),patch.object(module.subprocess,'run'),patch.object(module,'decrypt_hash',side_effect=RuntimeError('Synthetic bad decryption')),redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):module.main()
            self.assertEqual(calls,[{'phase':'prepare'}])

if __name__=='__main__':unittest.main()
