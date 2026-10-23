"""Execute real guard with synthetic sudo/swap/Git/host/auditor commands."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
STUB='''#!/usr/bin/python3
import os,sys,pathlib,subprocess,json
name=pathlib.Path(sys.argv[0]).name
home=pathlib.Path(os.environ['HOME']);args=sys.argv[1:]
with (home/'calls').open('a') as f:f.write(json.dumps([name,*args])+'\\n')
state=home/'swap-state'
if name=='hostname':print('firelion-Aspire-A315-51')
elif name=='id':print('1000')
elif name=='stat':print('1000')
elif name=='swapon':
    if '--show=USED' in args:print('0')
    else:print(state.read_text(),end='')
elif name=='sudo':
    if args[0]=='swapoff':state.write_text('')
    elif args[0]=='swapon':state.write_text('/swapfile\\n')
elif name=='git':
    if 'show' in args:
        sys.stdout.buffer.write(pathlib.Path(os.environ['AUDIT_SOURCE']).read_bytes() if os.environ.get('BAD_SOURCE')!='1' else b'changed')
    elif args[0]=='hash-object':sys.exit(subprocess.call(['/usr/bin/git',*args]))
    else:sys.exit(7)
elif name=='python3':sys.exit(int(os.environ['AUDIT_EXIT']))
else:sys.exit(8)
'''
class GuardTests(unittest.TestCase):
    def run_guard(self,status,bad=False):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);tools=home/'bin';tools.mkdir();runtime=home/'runtime';runtime.mkdir(mode=0o700)
            (home/'v79-r1-src.PnZUGsH9/repo/.git').mkdir(parents=True)
            (home/'swap-state').write_text('/swapfile\n')
            for name in ['hostname','id','stat','swapon','sudo','git','python3']:
                p=tools/name;p.write_text(STUB);p.chmod(0o700)
            env=dict(os.environ,HOME=str(home),XDG_RUNTIME_DIR=str(runtime),PATH=str(tools)+':'+os.environ['PATH'],AUDIT_SOURCE=str(ROOT/'scripts/p1-current-offhost-archive-audit.py'),AUDIT_EXIT=str(status),BAD_SOURCE='1' if bad else '0')
            r=subprocess.run(['bash',str(ROOT/'scripts/p1-current-offhost-archive-audit-guard.sh')],env=env,capture_output=True,text=True,timeout=20)
            calls=[json.loads(x) for x in (home/'calls').read_text().splitlines()]
            return r,(home/'swap-state').read_text(),calls
    def test_success_restores_only_original_swapfile(self):
        r,state,calls=self.run_guard(0)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(state,'/swapfile\n')
        self.assertIn('R1_SWAP_RESTORED=YES',r.stdout)
        self.assertEqual([x for x in calls if x[:2]==['sudo','swapon']],[['sudo','swapon','/swapfile']])
    def test_audit_failure_preserves_failure_and_restores_swap(self):
        r,state,calls=self.run_guard(1)
        self.assertEqual(r.returncode,1,r.stdout+r.stderr);self.assertEqual(state,'/swapfile\n');self.assertIn('R1_SWAP_RESTORED=YES',r.stdout)
    def test_changed_source_never_reaches_sudo_or_auditor(self):
        r,state,calls=self.run_guard(0,True)
        self.assertNotEqual(r.returncode,0);self.assertIn('AUDITOR_SOURCE_HASH_CHANGED',r.stdout)
        self.assertFalse(any(x[0] in ('sudo','python3') for x in calls));self.assertEqual(state,'/swapfile\n')
if __name__=='__main__':unittest.main()
