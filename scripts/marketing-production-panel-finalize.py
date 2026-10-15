#!/usr/bin/env python3
"""On Acer: verify backups, then finalize the already-live UI deployment record."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess

LOCAL = Path('/home/firelion/v79-g3-ui-recovery-jqtxjxnc')
ENCRYPTED = ('hub-pg.dump.gpg','hub-data.tar.gpg','hub-runtime-and-config.json.gpg')
IMAGE = 'sha256:ac3f3262476deeba190a362a6782e02836fff2a7d701ab219a60be7f8caaba0e'

REMOTE_PROGRAM = r'''
import copy,datetime,hashlib,json,sys,urllib.request

def fingerprint(v):
 return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def normalized_host(v):
 v=copy.deepcopy(v)
 if isinstance(v.get('Binds'),list):v['Binds']=sorted(v['Binds'])
 return v

try:
 payload=json.load(sys.stdin)
 url='https://raw.githubusercontent.com/MrFixITslu/V79hub/abb89d1ff263ab1699be44f76cbed2e1db8c4689/scripts/marketing-production-panel-cutover.py'
 with urllib.request.urlopen(url,timeout=30) as response:code=response.read(1048577)
 if hashlib.sha256(code).hexdigest()!='e5e291d0270ba7b4725a118cc034086520ae70c51a05de938f0b6bdcff2c85a1':raise RuntimeError('Pinned support integrity differs')
 ns={'__name__':'finalize_ui_record_only'};exec(compile(code,'<verified-ui-record-support>','exec'),ns)
 h=ns['load_helper'](ns['HELPERS'][1]);ns['helper']=h;root=ns['WORK'];require=ns['require']
 require(root.is_dir() and not root.is_symlink(),'Cutover directory differs')
 require((root/'switch-attempted.json').is_file() and not (root/'deployed.json').exists(),'No pending deployment to finalize; inspect receipts')
 require(h['file_hash'](root/'manifest.json',True)==payload['manifestSha256'],'Pre-switch manifest differs from owner copy')
 manifest=json.loads((root/'manifest.json').read_text());failure=json.loads((root/'failure.json').read_text())
 require(failure.get('stage')=='verify-live-ui-runtime-and-protected-state' and failure.get('liveSwitchAttempted') is True and failure.get('automaticRetryOrRollback') is False,'Recorded outcome differs from reviewed verification stop')
 require(manifest['candidateImage']==ns['IMAGE'] and manifest['originalStack']==ns['FILES'] and manifest['publicationEnabled'] is False,'Recorded image/scope differs')
 for name,digest in manifest['encryptedBackups'].items():
  require(payload['encryptedBackupHashes'].get(name)==digest==h['file_hash'](root/name,True),'Recovery copy or encrypted backup differs')
 build=ns['BUILD']/'ui-build-receipt.json';require(h['file_hash'](build,True)==manifest['buildReceiptSha256'],'Passed test receipt changed')
 build_doc=json.loads(build.read_text());require(build_doc['candidate']['image']==ns['IMAGE'] and build_doc['isolatedTestsPassed'] is True and build_doc['testEnvironment']=='test','Passed isolated image tests differ')
 current=h['inspect']('v79-hub');require(h['healthy'](current) and current['Image']==ns['IMAGE'] and current['Config']['Image']==ns['IMAGE'] and current['Id']!=payload['beforeHubId'],'Live tested UI image or health differs')
 config=copy.deepcopy(current['Config']);labels=config.pop('Labels');config.pop('Image')
 explicit=payload['configuredHostname']
 require(config.get('Hostname')==(explicit if explicit is not None else current['Id'][:12]),'Live hostname differs')
 config.pop('Hostname');config['Env']=sorted(config.get('Env',[]))
 require(fingerprint(config)==payload['applicationConfigSha256'],'Application environment, keys, command or user changed')
 require(fingerprint(normalized_host(current['HostConfig']))==payload['normalizedHostSha256'],'Resources or bind entries changed beyond list order')
 require(fingerprint(h['mounts'](current))==payload['mountsSha256'] and sorted(current['NetworkSettings']['Networks'])==payload['networks'],'Mount contents/permissions or network membership changed')
 require(labels.get('com.docker.compose.project.config_files')==','.join(ns['FILES']+[str(root/'ui-image.yml')]) and labels.get('org.opencontainers.image.revision')==ns['COMMIT'],'Live Compose/image provenance differs')
 for key in ('com.docker.compose.project.config_files','com.docker.compose.config-hash','com.docker.compose.image','org.opencontainers.image.revision'):labels.pop(key,None)
 require(fingerprint(labels)==payload['preservedLabelsSha256'],'Unapproved application labels changed')
 require(fingerprint(ns['resolve'](ns['FILES']+[root/'ui-image.yml']))==payload['desiredResolvedSha256'],'Image-only resolved configuration differs')
 for path,digest in {**manifest['sourceFileHashes'],**manifest['mountedSecretFileHashes']}.items():require(h['file_hash'](path)==digest,'Original Compose or token file changed')
 for name,digest in payload['unrelatedRuntimeHashes'].items():
  meta=h['inspect'](name);require(h['healthy'](meta) and fingerprint(h['stable_runtime'](meta))==digest,'Unrelated service changed')
 marketing=h['inspect']('v79marketing-app');env=h['env_map'](marketing['Config']['Env'])
 require(env.get('V79_MARKETING_PRODUCTION_ENABLED')=='1' and env.get('V79_MARKETING_PRODUCTION_PUBLISH_ENABLED')=='0','Marketing generation/publication flags changed')
 h['probe_live']()
 require(h['protected_state']('v79-hub-postgres')==manifest['hubProtectedStateSha256'],'Accounts, billing or accepted G2 task changed')
 require(h['sqlite_state']('v79marketing-app')['digest']==manifest['marketingProtectedStateSha256'] and ns['semantic_marketing']()==manifest['signedMarketingPackagesSha256'],'Marketing customer/provider records or signed campaigns changed')
 served=h['run'](['docker','exec','v79-hub','node','--input-type=module','-'],data=b"const r=await fetch('http://127.0.0.1:3040/');if(!r.ok||!(await r.text()).includes('index-CHQuh9Xa.js'))throw Error('UI asset differs');console.log('PINNED_UI_ASSET_SERVED_PASS');")
 require(b'PINNED_UI_ASSET_SERVED_PASS' in served,'Pinned UI was not served')
 h['write_json'](root/'deployed.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'image':ns['IMAGE'],'hubContainerId':current['Id'],'healthy':True,'publicationEnabled':False,'protectedStatePreserved':True,'campaignPackagesPreserved':True,'onlyHubRecreated':True,'automaticRetryOrRollback':False,'finalizedWithoutRestart':True,'verifiedDifference':'Exact HostConfig.Binds entries reordered only','offhostCopy':payload['acerCopy'],'ownerRanThreeChecksumAndFullStreamDecryptionChecks':True,'liveRuntimeSha256':fingerprint(h['stable_runtime'](current))})
 print('HUB_UI_LOGO_AND_AUTOMATIC_STATUS_FIX_DEPLOYED_HEALTHY')
 print('EXACT_BIND_ENTRIES_PRESERVED_DOCKER_ORDER_DIFFERENCE_VERIFIED')
 print('ACCOUNTS_BILLING_G2_AND_MARKETING_CAMPAIGNS_PRESERVED')
 print('ALL_OTHER_SERVICES_UNCHANGED_PUBLICATION_DISABLED')
 print('DEPLOYMENT_RECORD_FINALIZED_WITHOUT_RESTART_OR_ROLLBACK')
except Exception as exc:
 print('STOP: deployment record was not finalized; '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__))
 sys.exit(1)
'''


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def normalized_host(value):
    result=copy.deepcopy(value)
    if isinstance(result.get('Binds'),list):result['Binds']=sorted(result['Binds'])
    return result


def main():
    os.umask(0o077)
    if socket.gethostname().split('.')[0]!='firelion-Aspire-A315-51':raise RuntimeError('Run directly on the Acer laptop')
    if not LOCAL.is_dir() or LOCAL.is_symlink():raise RuntimeError('Verified Acer recovery copy not found')
    hashes={}
    for line in (LOCAL/'encrypted-checksums.sha256').read_text().splitlines():
        digest,name=line.split(None,1);hashes[name.strip()]=digest
    document=None
    for name in ENCRYPTED:
        if hashlib.sha256((LOCAL/name).read_bytes()).hexdigest()!=hashes.get(name):raise RuntimeError('Encrypted checksum mismatch')
        if name=='hub-runtime-and-config.json.gpg':
            decrypted=subprocess.run(['gpg','--quiet','--decrypt',str(LOCAL/name)],stdout=subprocess.PIPE,check=True)
            if len(decrypted.stdout)>8388608:raise RuntimeError('Snapshot size bound')
            document=json.loads(decrypted.stdout)
        else:subprocess.run(['gpg','--quiet','--decrypt',str(LOCAL/name)],stdout=subprocess.DEVNULL,check=True)
        print('OFFHOST_DECRYPT_PASS='+name,flush=True)
    before=document['runtime']['v79-hub'];config=copy.deepcopy(before['Config']);labels=config.pop('Labels');config.pop('Image');config.pop('Hostname');config['Env']=sorted(config.get('Env',[]))
    for key in ('com.docker.compose.project.config_files','com.docker.compose.config-hash','com.docker.compose.image','org.opencontainers.image.revision'):labels.pop(key,None)
    desired=copy.deepcopy(document['resolved']);desired['services']['v79-hub']['image']=IMAGE
    mounts=sorted([{k:m.get(k) for k in ('Type','Name','Source','Destination','Driver','Mode','RW','Propagation')} for m in before['Mounts']],key=lambda m:m['Destination'])
    unrelated={}
    for name,meta in document['runtime'].items():
        if name=='v79-hub':continue
        stable={k:meta[k] for k in ('Id','Image','Config','HostConfig','Mounts')};stable.update(StartedAt=meta['State']['StartedAt'],networks=sorted(meta['NetworkSettings']['Networks']));unrelated[name]=fingerprint(stable)
    payload={'beforeHubId':before['Id'],'applicationConfigSha256':fingerprint(config),'normalizedHostSha256':fingerprint(normalized_host(before['HostConfig'])),'mountsSha256':fingerprint(mounts),'networks':sorted(before['NetworkSettings']['Networks']),'preservedLabelsSha256':fingerprint(labels),'desiredResolvedSha256':fingerprint(desired),'configuredHostname':document['resolved']['services']['v79-hub'].get('hostname'),'unrelatedRuntimeHashes':unrelated,'encryptedBackupHashes':{name:hashes[name] for name in ENCRYPTED},'manifestSha256':hashlib.sha256((LOCAL/'manifest.json').read_bytes()).hexdigest(),'acerCopy':str(LOCAL)}
    subprocess.run(['ssh','firelion@v79sl','python3 -B -c '+shlex.quote(REMOTE_PROGRAM)],input=json.dumps(payload).encode(),check=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('STOP: finalization failed; '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__))
        raise SystemExit(1)
