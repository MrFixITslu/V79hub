#!/usr/bin/env python3
"""Guarded Acer swap-off window for one private-data paired boot rehearsal.

Only the operator can execute this. It changes Acer swap state, never server
state. Swap is re-enabled only after every disposable container and RAM scratch
directory is absent. If cleanup is uncertain, it stays off for manual review.
"""
import hashlib
import contextlib
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

BOOT_SHA='382e01857fe06b217b8e77c8ce2452b01ba590c48d5abff0bd0beab5e3218f55'
SWAP='/swapfile'
PRE_BYTES=4*1024**3
AFTER_BYTES=4*1024**3
PHASE='PREFLIGHT'
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def mem_available():
 for row in Path('/proc/meminfo').read_text().splitlines():
  if row.startswith('MemAvailable:'):return int(row.split()[1])*1024
 raise Stop('MEMORY_STATUS_UNAVAILABLE')
def swaps(content=None):
 rows=(Path('/proc/swaps').read_text() if content is None else content).splitlines()[1:]
 result={}
 for row in rows:
  fields=row.split()
  need(len(fields)>=5,'SWAP_STATUS_INVALID')
  result[fields[0]]=int(fields[3])*1024
 return result
def result(args,timeout=60):
 try:return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):raise Stop('LOCAL_COMMAND_UNAVAILABLE') from None
def clean():
 p=result(['docker','ps','-a','--format','{{.Names}}'])
 need(p.returncode==0,'DOCKER_INVENTORY_UNAVAILABLE')
 names=[v for v in p.stdout.decode().splitlines() if v.startswith('v79-v3-')]
 scratch=list(Path('/dev/shm').glob('v79-v3-*'))
 return not names and not scratch
def check_boot(path):
 need(path.is_file() and not path.is_symlink(),'BOOT_SCRIPT_MISSING')
 h=hashlib.sha256(path.read_bytes()).hexdigest()
 need(h==BOOT_SHA,'BOOT_SCRIPT_HASH_DRIFT')
def preflight(path):
 need(socket.gethostname().split('.')[0]=='firelion-Aspire-A315-51','ACER_HOST_REQUIRED')
 need(os.geteuid()!=0 and not os.getenv('DOCKER_HOST') and not os.getenv('DOCKER_CONTEXT'),'LOCAL_USER_ONLY')
 check_boot(path)
 current=swaps()
 need(set(current)=={SWAP},'SWAP_DEVICE_SET_DRIFT')
 need(mem_available()>=current[SWAP]+PRE_BYTES,'MEMORY_HEADROOM_TOO_LOW')
 need(clean(),'EXISTING_REHEARSAL_RESIDUE')
 need(result(['sudo','-n','-v']).returncode==0,'SUDO_CREDENTIAL_REQUIRED')
 return current[SWAP]
def run(path):
 global PHASE
 preflight(path)
 disabled=False
 boot_rc=None
 try:
  PHASE='DISABLE_ACER_SWAP'
  off=result(['sudo','-n','swapoff',SWAP],timeout=240)
  disabled=SWAP not in swaps()
  need(off.returncode==0 and disabled and not swaps(),'SWAP_NOT_FULLY_DISABLED')
  need(mem_available()>=AFTER_BYTES,'POST_SWAPOFF_MEMORY_HEADROOM_LOW')
  print('ACER_DISK_SWAP=OFF_VERIFIED',flush=True)
  PHASE='ISOLATED_PAIRED_BOOT'
  boot_rc=subprocess.run(['python3','-B',str(path),'--run']).returncode
 finally:
  PHASE='VERIFY_CLEANUP_BEFORE_SWAP'
  if disabled:
   if clean():
    PHASE='RESTORE_ACER_SWAP'
    on=result(['sudo','-n','swapon',SWAP],timeout=90)
    need(on.returncode==0 and set(swaps())=={SWAP},'SWAP_REENABLE_FAILED')
    print('ACER_SWAP=RESTORED',flush=True)
   else:
    print('ACER_SWAP=LEFT_OFF_REHEARSAL_RESIDUE_REQUIRES_MANUAL_REVIEW',flush=True)
    raise Stop('CLEANUP_NOT_PROVEN_SWAP_LEFT_OFF')
 need(boot_rc==0,'ISOLATED_PAIRED_BOOT_DID_NOT_PASS')
 PHASE='DONE'
 print('GUARDED_SWAP_WINDOW=PASS_REHEARSAL_AND_SWAP_RESTORED')
class Tests(unittest.TestCase):
 def test_swap_parser(self):
  self.assertEqual(swaps('Filename Type Size Used Priority\n/swapfile file 2097152 1024000 -1\n'),
                   {'/swapfile':1024000*1024})
 def test_wrong_host_no_change(self):
  with patch('socket.gethostname',return_value='wrong'),patch(__name__+'.result') as command:
   with self.assertRaises(Stop):preflight(Path('/missing'))
   command.assert_not_called()
 def test_residue_never_reenables_swap(self):
  fake=subprocess.CompletedProcess([],0)
  with patch(__name__+'.preflight',return_value=1),patch(__name__+'.swaps',return_value={}),\
       patch(__name__+'.mem_available',return_value=AFTER_BYTES+1),\
       patch(__name__+'.clean',return_value=False),patch(__name__+'.result',return_value=fake) as command,\
       patch('subprocess.run',return_value=fake):
   with contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaises(Stop):run(Path('/synthetic'))
   self.assertEqual(command.call_count,1)
   self.assertEqual(command.call_args.args[0],['sudo','-n','swapoff',SWAP])
def main():
 need(len(sys.argv) in (2,3) and sys.argv[1] in ('--self-test','--run'),'MODE_REQUIRED')
 if sys.argv[1]=='--self-test':
  r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if r.wasSuccessful() else 1
 need(len(sys.argv)==3,'BOOT_SCRIPT_ARGUMENT_REQUIRED')
 run(Path(sys.argv[2]));return 0
if __name__=='__main__':
 try:sys.exit(main())
 except Stop as e:print('STOP_PHASE='+PHASE+' STOP_REASON='+str(e));sys.exit(3)
 except Exception as e:print('STOP_PHASE='+PHASE+' STOP_REASON=REDACTED_'+type(e).__name__);sys.exit(3)
