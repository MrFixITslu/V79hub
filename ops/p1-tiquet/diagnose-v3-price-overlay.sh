#!/usr/bin/env bash
# Read-only V79 P1 release v3 diagnostics. Prints field paths only, never values.
set -euo pipefail
ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 firelion@v79sl 'python3 -' <<'PY'
import json, os, pathlib, subprocess, sys

def stop(why):
    print('STOP='+why)
    sys.exit(1)

def cmd(parts, cwd=None):
    p=subprocess.run(parts,cwd=cwd,text=True,capture_output=True,timeout=30,check=False)
    return json.loads(p.stdout) if p.returncode==0 else None

me=cmd(['docker','inspect','v79-tiquet-manager'])
if not me: stop('LIVE_INSPECT_UNAVAILABLE')
live=me[0]
labels=live['Config'].get('Labels') or {}
project=labels.get('com.docker.compose.project','')
service=labels.get('com.docker.compose.service','')
wd=labels.get('com.docker.compose.project.working_dir','')
files=labels.get('com.docker.compose.project.config_files','').split(',')
if service!='v79-tiquet-manager' or not project or not wd or not os.path.isdir(wd) or any(not f.startswith('/') or not os.path.isfile(f) for f in files):
    stop('COMPOSE_METADATA_INVALID')
release=pathlib.Path.home()/'v79-p1-tiquet-live-release-20261016'
price=release/'runtime-price-freeze.yml'
if not price.is_file() or price.is_symlink() or price.stat().st_size>4096:
    stop('PRESERVED_OVERLAY_MISSING_OR_UNSAFE')
args=['--project-directory',wd,'-p',project]
for file in files: args+=['-f',file]

def config(add):
    return cmd(['docker','compose',*args,*add,'config','--format','json'], wd)

before=config([])
after=config(['-f',str(price)])
if not before or not after: stop('ORIGINAL_OR_OVERLAY_PARSE_FAILED')
if service not in before.get('services',{}) or service not in after.get('services',{}):stop('SERVICE_MISSING')

actual=dict(z.split('=',1) for z in live['Config']['Env'] if '=' in z)
keys={'PLAN_PRICE_STARTER','PLAN_PRICE_PRO','PLAN_PRICE_ENTERPRISE'}
expected=json.loads(json.dumps(before['services'][service]))
expected.setdefault('environment',{}).update({k:actual.get(k) for k in keys})

# Prints only changed field keys: never prices, secrets, hashes or contents.
def diff(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        for key in sorted(set(a)|set(b)):
            yield from diff(a.get(key),b.get(key),f'{path}.{key}' if path else str(key))
    elif isinstance(a,list) and isinstance(b,list):
        if a!=b: yield path+'[]'
    elif a!=b:
        yield path

raw_diff=list(diff(before['services'][service],after['services'][service]))
unexpected=list(diff(expected,after['services'][service]))
other=[name for name in before['services'] if name not in after.get('services',{}) or (name!=service and before['services'][name]!=after['services'][name])]
other+= [name for name in after['services'] if name not in before['services']]
post_env=after['services'][service].get('environment') or {}
env_diff=sorted(k for k,v in post_env.items() if actual.get(k)!=v)
print('MODE=READ_ONLY_NO_PRODUCTION_CHANGES')
print('PRESERVED_V3_RELEASE_ARTIFACT=EXISTS')
print('LIVE_TIQUET_RUNNING='+str(live['State'].get('Running',False)).upper())
print('V3_PRICE_OVERLAY=PARSE_PASS')
print('ACTUAL_OVERLAY_SERVICE_DIFF_KEYS='+(','.join(raw_diff[:35]) or 'NONE'))
print('UNEXPECTED_OVERLAY_SERVICE_DIFF_KEYS='+(','.join(unexpected[:35]) or 'NONE'))
print('UNEXPECTED_OVERLAY_SERVICE_DIFF_COUNT='+str(len(unexpected)))
print('OTHER_SERVICE_CHANGES='+(','.join(other[:12]) or 'NONE'))
print('AFTER_OVERLAY_RUNTIME_ENV_DIFF_KEYS='+(','.join(env_diff[:35]) or 'NONE'))
print('AFTER_OVERLAY_RUNTIME_ENV_DIFF_COUNT='+str(len(env_diff)))
print('DIAG_COMPLETE=NO_CHANGES')
PY
