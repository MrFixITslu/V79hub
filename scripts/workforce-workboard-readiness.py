#!/usr/bin/env python3
"""Read-only metadata readiness; no credential values, files or Docker objects changed."""
import json,os,socket,subprocess
from pathlib import Path
IMAGE='sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698'
if socket.gethostname()!='v79sl':raise SystemExit('STOP=RUN_ON_V79SL')
p=subprocess.run(['docker','inspect','v79-hub'],capture_output=True,text=True,timeout=20)
if p.returncode:raise SystemExit('STOP=HUB_METADATA_UNAVAILABLE')
hub=json.loads(p.stdout)[0]
if hub['Image']!=IMAGE or hub['State'].get('Health',{}).get('Status')!='healthy':raise SystemExit('STOP=HUB_IMAGE_OR_HEALTH_CHANGED')
env=dict(item.split('=',1) for item in hub['Config'].get('Env',[]) if '=' in item)
target=env.get('V79_COO_GITHUB_TOKEN_FILE','/run/secrets/v79-coo-github-token')
mount=next((item for item in hub['Mounts'] if item['Destination']==target),None)
print('MODE=READ_ONLY_METADATA_NO_TOKEN_READ')
print('WORKBOARD_ENABLED='+('YES' if env.get('V79_COO_WORKBOARD_ENABLED')=='1' else 'NO'))
print('REPORTS_ENABLED='+('YES' if env.get('V79_WORKFORCE_REPORTS_ENABLED')=='1' else 'NO'))
print('TOKEN_MOUNT='+('READ_ONLY' if mount and not mount['RW'] else 'MISSING_OR_UNSAFE'))
file=Path.home()/'.v79-secrets/coo-github-readonly.token'
if file.exists() or file.is_symlink():
 s=file.lstat()
 safe=not file.is_symlink() and file.is_file() and s.st_mode&0o077==0 and 16<=s.st_size<=512
 print('DEDICATED_HOST_TOKEN_METADATA='+('PRIVATE_REGULAR_FILE' if safe else 'UNSAFE'))
else:print('DEDICATED_HOST_TOKEN_METADATA=NOT_PROVISIONED')
print('TOKEN_VALUES_PRINTED=NO')
print('PRODUCTION_CHANGES=NONE')
