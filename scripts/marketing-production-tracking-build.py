#!/usr/bin/env python3
"""Build/test receipt tracking + Hub status/cleanup images without live deployment."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import tempfile

HUB=('V79hub','045d68a61257c758f2f6ca229d050e4e7a7df618','d1157d636ede68b5981a4c69306f1d29cf58041c','8d82b21a4defe47a3d377a57dcd648b3c9818fea')
MARKETING=('V79Marketing','de806c5c8db2d798ecb94621e3e1b04e9d7c8592','15595d37621996d866100e6a57297e5406006b2c','b7934c03f0e3fd91f826af52e68b62422ef55616')
EXISTING_BUILD=Path('/home/firelion/v79-g3-tracking-build-1qcu4yh_')
NODE_BASE='public.ecr.aws/docker/library/node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402'
LIVE={
 'v79-hub':'sha256:ac3f3262476deeba190a362a6782e02836fff2a7d701ab219a60be7f8caaba0e',
 'v79marketing-app':'sha256:e34d3c22f325c7fef78bc79bf96aa3386c10a45a7d2fd3e4e5081d39e9d4e0e8',
 'v79-business-agent':'sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f',
 'v79-hub-postgres':'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24',
 'v79-tiquet-manager':'sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b',
 'tiquet-postgres':'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685'}
MARKETING_FILES={'server.ts','src/App.tsx','src/components/ContentCalendar.tsx','src/lib/db.ts','src/lib/productionAdapters.ts',
 'src/lib/productionStore.ts','src/lib/productionWorkflow.ts','src/lib/productionTracking.ts','src/lib/publicationLinks.ts','src/lib/publisher.ts','src/types.ts'}


def require(ok,message):
 if not ok:raise RuntimeError(message)


def run(args,*,data=None,visible=False,timeout=60):
 result=subprocess.run(args,input=data,capture_output=not visible,timeout=timeout)
 require(result.returncode==0,'Command failed; sensitive output withheld')
 return result.stdout


def snapshot():
 result={}
 for name,image in LIVE.items():
  meta=json.loads(run(['docker','inspect',name]))[0]
  require(meta['Image']==image and meta['State']['Running'] and meta['State'].get('Health',{}).get('Status')=='healthy','Live image/health differs: '+name)
  if name in ('v79-hub','v79marketing-app'):
   env=dict(v.split('=',1) for v in meta['Config']['Env'])
   require(env.get('V79_MARKETING_PRODUCTION_ENABLED')=='1','Generation flag differs')
   if name=='v79marketing-app':require(env.get('V79_MARKETING_PRODUCTION_PUBLISH_ENABLED')=='1','Publication flag differs')
  result[name]={'id':meta['Id'],'image':meta['Image'],'startedAt':meta['State']['StartedAt'],
   'runtimeSha256':hashlib.sha256(json.dumps({k:meta[k] for k in ('Config','HostConfig','Mounts')},sort_keys=True).encode()).hexdigest(),
   'networks':sorted(meta['NetworkSettings']['Networks'])}
 return result


def isolated(image,args,environment=()):
 command=['docker','run','--rm','--network','none','--read-only','--user','node','--cap-drop','ALL',
  '--security-opt','no-new-privileges','--memory','768m','--cpus','2','--tmpfs','/tmp:rw,nosuid,nodev,size=256m']
 for value in environment:command+=['--env',value]
 return command+['--entrypoint','node',image]+list(args)


def verify_source(path,spec):
 repo,commit,tree,base=spec
 require(run(['git','-C',str(path),'rev-parse','HEAD']).decode().strip()==commit and run(['git','-C',str(path),'rev-parse','HEAD^{tree}']).decode().strip()==tree,'Pinned checkout/tree differs')
 run(['git','-C',str(path),'diff','--quiet','HEAD','--'])
 require(not run(['git','-C',str(path),'ls-files','--others','--exclude-standard']).strip(),'Unexpected untracked source files')
 changed=run(['git','-C',str(path),'diff','--name-only',base,commit]).decode().splitlines()
 allowed={'src/components/MarketingProductionPanel.tsx'} if repo=='V79hub' else MARKETING_FILES
 require(all(p in allowed or p.startswith(('tests/','docs/','scripts/')) for p in changed),'Source changes exceed UI/receipt-tracking scope')
 for filename in ('package.json','package-lock.json'):
  require(run(['git','-C',str(path),'show',base+':'+filename])==(path/filename).read_bytes(),'Dependencies changed beyond receipt-tracking scope')


def checkout(root,spec):
 repo,commit,tree,base=spec;path=root/repo;path.mkdir()
 run(['git','init','--quiet',str(path)])
 for sha in (commit,base):run(['git','-C',str(path),'fetch','--depth','1','https://github.com/MrFixITslu/'+repo+'.git',sha],timeout=180)
 run(['git','-C',str(path),'checkout','--quiet','--detach',commit])
 require(run(['git','-C',str(path),'rev-parse','HEAD']).decode().strip()==commit and run(['git','-C',str(path),'rev-parse','HEAD^{tree}']).decode().strip()==tree,'Pinned checkout/tree differs')
 verify_source(path,spec)
 for directory,dirs,files in os.walk(path,followlinks=False):
  dirs[:]=[n for n in dirs if n!='.git'];Path(directory).chmod(0o755)
  for name in dirs+files:
   child=Path(directory)/name;require(not child.is_symlink(),'Unexpected source symlink')
   if child.is_file():child.chmod(0o755 if child.stat().st_mode&0o111 else 0o644)
 return path


def build(root,spec):
 repo,commit,tree,_=spec;path=checkout(root,spec);tag=('v79-hub' if repo=='V79hub' else 'v79-marketing')+'-tracking:'+commit[:12]
 print('STAGE=build-'+repo,flush=True)
 run(['docker','build','--build-arg','NODE_BASE='+NODE_BASE,'--label','org.opencontainers.image.revision='+commit,'--tag',tag,str(path)],visible=True,timeout=1800)
 return verify_image(root,spec,path,tag)


def verify_image(root,spec,path,tag,expected_image=None):
 repo,commit,tree,_=spec
 meta=json.loads(run(['docker','image','inspect',tag]))[0];image=meta['Id']
 require(expected_image is None or image==expected_image,'Existing immutable candidate image differs')
 require(meta['Config']['Labels'].get('org.opencontainers.image.revision')==commit and 'NODE_ENV=production' in meta['Config']['Env'],'Candidate source/environment differs')
 print('STAGE=network-isolated-tests-'+repo,flush=True)
 if repo=='V79hub':
  run(isolated(image,['--test','tests/marketing-production-panel.test.mjs','tests/marketing-production-routes.test.mjs','tests/workforce-action-routes.test.mjs','tests/workforce-actions.test.mjs'],['NODE_ENV=test','NODE_OPTIONS=--import=./tests/isolated-env.mjs']),visible=True,timeout=180)
 else:
  # The deployed image keeps dev dependencies pruned. A separate disposable
  # verification image restores only lockfile-bound test dependencies.
  require('RUN npm install -g npm@11.9.0' in (path/'Dockerfile').read_text(),'Candidate npm toolchain differs')
  dockerfile=root/'marketing-verification-npm11.Dockerfile'
  dockerfile.write_text('FROM '+tag+'\nUSER root\nRUN apk add --no-cache python3 make g++\nRUN npm install -g npm@11.9.0\nCOPY package.json package-lock.json ./\nRUN npm ci --include=dev --no-audit --no-fund\nCOPY . .\nUSER node\n')
  verify_tag='v79-marketing-tracking-tests:'+commit[:12]
  run(['docker','build','--file',str(dockerfile),'--tag',verify_tag,str(path)],visible=True,timeout=1800)
  verify=json.loads(run(['docker','image','inspect',verify_tag]))[0]['Id']
  run(isolated(verify,['node_modules/vitest/vitest.mjs','run','--config','tests/vitest-isolated.config.mts','--configLoader','runner'],
   ['NODE_ENV=test','DATABASE_PATH=/tmp/marketing-tests.sqlite','JWT_SECRET=synthetic-isolated-test-key-32-characters','V79_MARKETING_SEED_DEMO=1','V79_ENABLE_SIMULATED_PUBLISHER=1']),visible=True,timeout=300)
  run(isolated(image,['dist/production-renderer-smoke.mjs']),visible=True,timeout=180)
  program="const fs=require('node:fs'),c=require('node:crypto'),m=JSON.parse(fs.readFileSync('/app/dist/server.cjs.map')),out={};for(let i=0;i<m.sources.length;i++)if(!m.sources[i].includes('node_modules')&&typeof m.sourcesContent?.[i]==='string')out[m.sources[i]]=c.createHash('sha256').update(m.sourcesContent[i]).digest('hex');console.log(JSON.stringify(out));"
  hashes=json.loads(run(isolated(image,['-e',program])))
  for filename in ('server.ts','src/lib/productionTracking.ts','src/lib/publicationLinks.ts','src/lib/productionWorkflow.ts','src/lib/productionStore.ts','src/lib/publisher.ts','src/lib/db.ts'):
   require(hashes.get('../'+filename)==hashlib.sha256((path/filename).read_bytes()).hexdigest(),'Compiled runtime source differs: '+filename)
 require(json.loads(run(['docker','image','inspect',tag]))[0]['Id']==image,'Candidate tag changed during isolated tests')
 return {'commit':commit,'tree':tree,'image':image,'tag':tag,'sourceScopeVerified':True,'isolatedTestsPassed':True}


def main():
 os.umask(0o077)
 require(socket.gethostname().split('.')[0]=='v79sl' and os.getuid()==1000 and pwd.getpwuid(os.getuid()).pw_name=='firelion','Run as firelion on v79sl')
 before=snapshot();require(shutil.disk_usage('/home/firelion').free>8*1024**3,'Insufficient image build space')
 root=Path(tempfile.mkdtemp(prefix='v79-g3-tracking-build-',dir='/home/firelion'));print('BUILD_DIRECTORY='+str(root),flush=True)
 candidates={spec[0]:build(root,spec) for spec in (HUB,MARKETING)}
 require(snapshot()==before,'Live runtime changed during builds; inspect before deployment')
 write_receipt(root,before,candidates)


def write_receipt(root,before,candidates,reused=False):
 receipt={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'deploymentPerformed':False,'liveRuntime':before,'candidates':candidates,
  'publicationEnabled':True,'cleanupPerformed':False,'testEnvironment':'test','runtimeSourceVerified':True,'reusedExistingImages':reused}
 with (root/'tracking-build-receipt.json').open('x') as output:
  json.dump(receipt,output,indent=2);output.write('\n');output.flush();os.fsync(output.fileno())
 print('TRACKING_STATUS_LINKS_AND_CLEANUP_CANDIDATES_BUILD_AND_ISOLATED_TESTS_PASS')
 for repo,candidate in candidates.items():print(repo+'_IMAGE='+candidate['image'])
 print('BUILD_RECEIPT='+str(root/'tracking-build-receipt.json'))
 print('LIVE_CONTAINERS_PUBLICATION_APPROVALS_AND_CUSTOMER_DATA_UNCHANGED')
 print('FRESH_COPIED_STATE_RECOVERY_AND_DEPLOYMENT_PENDING')


def verify_existing():
 os.umask(0o077)
 require(socket.gethostname().split('.')[0]=='v79sl' and os.getuid()==1000 and pwd.getpwuid(os.getuid()).pw_name=='firelion','Run as firelion on v79sl')
 root=EXISTING_BUILD
 require(root.is_dir() and not root.is_symlink() and root.stat().st_uid==os.getuid() and root.stat().st_mode&0o077==0,'Existing private build directory differs')
 require(not (root/'tracking-build-receipt.json').exists(),'Build already verified; inspect its receipt')
 before=snapshot();candidates={}
 expected={'V79hub':'sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06',
  'V79Marketing':'sha256:32641b8f302b4ec38a56167ee6df9d5e0a185bf017431fa86f5bb9f462f7eaf3'}
 print('BUILD_DIRECTORY='+str(root),flush=True)
 print('STAGE=verify-existing-immutable-images-and-checkouts',flush=True)
 for spec in (HUB,MARKETING):
  repo,commit,_,_=spec;path=root/repo
  require(path.is_dir() and not path.is_symlink(),'Existing checkout differs')
  verify_source(path,spec)
  tag=('v79-hub' if repo=='V79hub' else 'v79-marketing')+'-tracking:'+commit[:12]
  candidates[repo]=verify_image(root,spec,path,tag,expected[repo])
 require(snapshot()==before,'Live runtime changed during verification; inspect before deployment')
 write_receipt(root,before,candidates,reused=True)


if __name__=='__main__':
 try:
  if globals().get('VERIFY_EXISTING_BUILD') is True:verify_existing()
  else:main()
 except (Exception,KeyboardInterrupt) as exc:
  print('STOP: '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__))
  print('NO_LIVE_RECREATION_UPLOAD_OR_CAMPAIGN_CLEANUP_ATTEMPTED')
  raise SystemExit(1)
