#!/usr/bin/env python3
"""Only executes the fixed G2 approved-work-item endpoint. No release claims."""
import json,os,re,sys,urllib.request
from pathlib import Path
URL='https://hub.v79sl.com/internal/workforce/execute-work-item'
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise RuntimeError('Redirect refused')
def run_once(config,opener=None):
 if set(config)!={'schema','tokenFile'} or config['schema']!=1:raise ValueError('Invalid worker configuration')
 file=Path(config['tokenFile']);s=file.lstat()
 if not file.is_absolute() or file.is_symlink() or not file.is_file() or s.st_mode&0o077 or not 32<=s.st_size<=512:raise ValueError('Unsafe worker token')
 token=file.read_text().strip()
 if not 32<=len(token)<=256 or re.search(r'\s',token):raise ValueError('Invalid worker credential')
 request=urllib.request.Request(URL,data=b'{}',method='POST',headers={'Content-Type':'application/json','X-V79-Workforce-Token':token,'Accept':'application/json','User-Agent':'V79-approved-task-worker'})
 transport=opener or urllib.request.build_opener(NoRedirect())
 with transport.open(request,timeout=20) as response:
  if response.status!=200:raise RuntimeError('Unexpected worker status')
  raw=response.read(65537)
  if len(raw)>65536:raise RuntimeError('Oversized worker response')
  body=json.loads(raw)
 if not isinstance(body,dict) or set(body)!={'job'}:raise RuntimeError('Unexpected worker envelope')
 job=body['job']
 if job is None:return {'state':'idle','operation':'create_work_item'}
 if not isinstance(job,dict) or job.get('operation')!='create_work_item' or job.get('status')!='succeeded':raise RuntimeError('Unexpected operation result')
 if not isinstance(job.get('digest'),str) or not re.fullmatch('[0-9a-f]{64}',job['digest']):raise RuntimeError('Missing approved job digest')
 return {'state':'succeeded','operation':'create_work_item','approvedDigest':job['digest']}
def main():
 os.umask(0o077)
 if len(sys.argv)!=2:raise ValueError('Provide private configuration path')
 config_file=Path(sys.argv[1]);root=config_file.parent;blocked=root/'uncertain.json'
 if blocked.exists():print('TASK_WORKER=BLOCKED_PENDING_OPERATOR_RECONCILIATION');return
 try:
  s=config_file.lstat()
  if config_file.is_symlink() or s.st_mode&0o077:raise ValueError('Unsafe configuration')
  result=run_once(json.loads(config_file.read_text()))
  temporary=root/'status.tmp'
  with temporary.open('w') as f:os.chmod(temporary,0o600);json.dump(result,f);f.flush();os.fsync(f.fileno())
  os.replace(temporary,root/'status.json')
  print('TASK_WORKER='+result['state'].upper())
 except Exception:
  # No automatic retry after an unknown POST outcome or missing receipt.
  with blocked.open('x') as f:os.chmod(blocked,0o600);json.dump({'state':'uncertain','action':'inspect_signed_queue_before_reset'},f)
  print('TASK_WORKER=UNCERTAIN_RECONCILIATION_REQUIRED');raise SystemExit(1)
if __name__=='__main__':main()
