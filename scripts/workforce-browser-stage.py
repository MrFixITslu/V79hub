#!/usr/bin/env python3
"""Start only a private, disposable synthetic Hub for owner browser acceptance."""
import json,os,secrets,socket,subprocess,tempfile,time,urllib.request,uuid
from pathlib import Path
IMAGE='sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698'
EXPECTED={'v79-hub':'sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06','v79-business-agent':'sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f','v79-tiquet-manager':'sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42'}
def run(args):
 p=subprocess.run(args,text=True,capture_output=True,timeout=60)
 if p.returncode:raise RuntimeError('Staging command failed; private details withheld')
 return p.stdout.strip()
def baseline():
 rows=json.loads(run(['docker','inspect',*EXPECTED]))
 if any(r['Image']!=EXPECTED[r['Name'].lstrip('/')] or r['State'].get('Health',{}).get('Status')!='healthy' for r in rows):raise RuntimeError('Live baseline changed')
def private(path,text):
 with path.open('x') as f:os.chmod(path,0o600);f.write(text)
def main():
 os.umask(0o077)
 if socket.gethostname()!='v79sl':raise RuntimeError('Run on v79sl only')
 baseline()
 with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
 stage=Path(tempfile.mkdtemp(prefix='v79-workforce-browser-stage.',dir=Path.home()))
 token=uuid.uuid4().hex[:16];name='v79-workforce-qa-'+token;network=name+'-internal'
 password=secrets.token_urlsafe(24)
 env={'NODE_ENV':'production','PORT':'3040','DATA_DIR':'/app/data','APP_URL':'http://localhost:13079','V79_HUB_STORE_BACKEND':'json','V79_HUB_ADMIN_USERNAME':'admin','V79_HUB_ADMIN_PASSWORD':password,'V79_HUB_ADMIN_EMAIL':'vision79slu@gmail.com','V79_REQUIRE_ADMIN_MFA':'1','V79_HUB_SECURITY_KEY':secrets.token_hex(32),'V79_PLATFORM_SHARED_SECRET':secrets.token_hex(32),'V79_WORKFORCE_REPORTS_ENABLED':'1','V79_COO_WORKBOARD_ENABLED':'0','V79_WORKFORCE_ACTIONS_ENABLED':'0','V79_MARKETING_PRODUCTION_ENABLED':'0','WIPAY_ENABLED':'0','RESEND_API_KEY':'','V79_AGENT_API_TOKEN':''}
 for key in ['POS_BASE_URL','FFPRO_INTERNAL_URL','TIQUET_INTERNAL_URL','ACADEMY_INTERNAL_URL','MARKETING_INTERNAL_URL','LASERTAG_INTERNAL_URL','WEBSITE_INTERNAL_URL','GAMES_INTERNAL_URL','V79_AGENT_INTERNAL_URL']:env[key]='http://127.0.0.1:9'
 private(stage/'synthetic.env',''.join(k+'='+v+'\n' for k,v in env.items()))
 private(stage/'browser-login.txt','STAGING ONLY — NOT YOUR LIVE PASSWORD\nUsername: admin\nPassword: '+password+'\nUse a separate temporary MFA enrollment entry for staging.\n')
 cid=None;network_created=False;success=False
 try:
  run(['docker','network','create','--internal','--label','v79.workforce.browser='+token,network]);network_created=True
  cid=run(['docker','create','--name',name,'--label','v79.workforce.browser='+token,'--network',network,'--publish',f'127.0.0.1:{port}:3040','--env-file',str(stage/'synthetic.env'),'--read-only','--security-opt','no-new-privileges','--memory','768m','--cpus','1','--pids-limit','192','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','--tmpfs','/app/data:rw,nosuid,nodev,size=64m','--mount','type=bind,src='+str(Path.home()/'.local/share/v79-workforce-operations/reports')+',dst=/run/v79-workforce-reports,readonly',IMAGE])
  row=json.loads(run(['docker','inspect',cid]))[0]
  mounts=row['Mounts'];binds=[m for m in mounts if m['Type']=='bind']
  if len(binds)!=1 or binds[0]['Destination']!='/run/v79-workforce-reports' or binds[0]['RW']:raise RuntimeError('Report mount isolation failed')
  if any(m['Type'] not in ['bind','tmpfs'] for m in mounts):raise RuntimeError('Unexpected staging volume')
  net=json.loads(run(['docker','network','inspect',network]))[0]
  if not net.get('Internal'):raise RuntimeError('Staging network is not internal')
  ports=row['HostConfig'].get('PortBindings',{})
  if ports!={'3040/tcp':[{'HostIp':'127.0.0.1','HostPort':str(port)}]}:raise RuntimeError('Staging bind is not loopback-only')
  run(['docker','start',cid])
  for attempt in range(60):
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=2) as response:
     if response.status==200:break
   except Exception:
    if attempt==59:raise RuntimeError('Private staging startup unavailable')
    time.sleep(1)
  try:
   urllib.request.urlopen(f'http://127.0.0.1:{port}/api/agent/workforce-briefings',timeout=3)
   raise RuntimeError('Anonymous report access unexpectedly succeeded')
  except urllib.error.HTTPError as error:
   if error.code not in [401,403]:raise RuntimeError('Unexpected anonymous report response')
  baseline()
  private(stage/'stage.json',json.dumps({'schema':1,'container':cid,'name':name,'network':network,'token':token,'port':port,'image':IMAGE,'productionDeployed':False},indent=2))
  cleanup='''#!/usr/bin/env python3
import json,subprocess
from pathlib import Path
meta=json.loads(Path(__file__).with_name('stage.json').read_text())
for command,obj in [(['docker','inspect',meta['container']],'container'),(['docker','network','inspect',meta['network']],'network')]:
 p=subprocess.run(command,text=True,capture_output=True)
 if p.returncode:continue
 row=json.loads(p.stdout)[0]
 labels=row['Config']['Labels'] if obj=='container' else row['Labels']
 if labels.get('v79.workforce.browser')!=meta['token']:raise SystemExit('STOP_LABEL_MISMATCH')
 subprocess.run(['docker','rm','-f',meta['container']] if obj=='container' else ['docker','network','rm',meta['network']],check=True,stdout=subprocess.DEVNULL)
print('PRIVATE_STAGING_CLEANUP=PASS')
'''
  private(stage/'cleanup.py',cleanup)
  success=True
  print('PRIVATE_BROWSER_STAGE=READY')
  print('ANONYMOUS_REPORT_ACCESS=DENIED')
  print('PRODUCTION_DATABASE_MOUNTED=NO')
  print('EXTERNAL_NETWORK=DISABLED')
  print('LIVE_IMAGE_AND_HEALTH_RECHECK=PASS')
  print('STAGE_DIRECTORY='+str(stage))
  print('LOGIN_FILE='+str(stage/'browser-login.txt'))
  print('TUNNEL_COMMAND=ssh -N -L 13079:127.0.0.1:'+str(port)+' firelion@v79sl')
  print('BROWSER_URL=http://localhost:13079')
  print('PRODUCTION_DEPLOYED=NO')
 finally:
  if not success:
   if cid:run(['docker','rm','-f',cid])
   if network_created:run(['docker','network','rm',network])
if __name__=='__main__':
 try:main()
 except Exception as error:
  print('PRIVATE_BROWSER_STAGE=FAILED')
  print('REASON='+str(error) if isinstance(error,RuntimeError) else 'REASON='+type(error).__name__)
  raise SystemExit(1)
