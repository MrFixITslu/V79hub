#!/usr/bin/env python3
"""Guarded Acer swap-off window for in-memory private runtime contract check.

Only the local operator runs this. Restores swap only after the checker has
exited and all v3 disposable RAM/container residue is absent. No server access.
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

CHECKER_SHA="a9a9941c78551d3659386e46d978348d8fec8f7338dd51ad7ab39af343fb3cc8"
SWAP="/swapfile"
HEADROOM=4*1024**3
PHASE="PREFLIGHT"
class Stop(Exception): pass
def need(ok,reason):
 if not ok:raise Stop(reason)
def available():
 for row in Path("/proc/meminfo").read_text().splitlines():
  if row.startswith("MemAvailable:"):return int(row.split()[1])*1024
 raise Stop("MEMORY_STATUS_UNAVAILABLE")
def swaps(content=None):
 lines=(Path("/proc/swaps").read_text() if content is None else content).splitlines()[1:]
 result={}
 for row in lines:
  fields=row.split()
  need(len(fields)>=5,"SWAP_STATUS_INVALID")
  result[fields[0]]=int(fields[3])*1024
 return result
def call(args,timeout=90):
 try:return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):raise Stop("LOCAL_COMMAND_FAILED") from None
def clean():
 result=call(["docker","ps","-a","--format","{{.Names}}"])
 need(result.returncode==0,"DOCKER_INVENTORY_UNAVAILABLE")
 names=[n for n in result.stdout.decode().splitlines() if n.startswith("v79-v3-")]
 return not names and not list(Path("/dev/shm").glob("v79-v3-*"))
def preflight(checker):
 need(socket.gethostname().split(".")[0]=="firelion-Aspire-A315-51","ACER_HOST_REQUIRED")
 need(os.geteuid()!=0 and not os.getenv("DOCKER_HOST") and not os.getenv("DOCKER_CONTEXT"),
      "ACER_LOCAL_USER_ONLY")
 need(checker.is_file() and not checker.is_symlink() and
      hashlib.sha256(checker.read_bytes()).hexdigest()==CHECKER_SHA,"CHECKER_SHA_DRIFT")
 current=swaps()
 need(set(current)=={SWAP},"SWAP_SET_DRIFT")
 need(available()>=current[SWAP]+HEADROOM,"PRE_SWAPOFF_MEMORY_LOW")
 need(clean(),"PRIVATE_REHEARSAL_RESIDUE")
 need(call(["sudo","-n","-v"]).returncode==0,"CACHED_SUDO_REQUIRED")
def run(checker):
 global PHASE
 preflight(checker)
 off=False;rc=None
 try:
  PHASE="DISABLE_ACER_SWAP"
  p=call(["sudo","-n","swapoff",SWAP],timeout=240)
  off=SWAP not in swaps()
  need(p.returncode==0 and off and not swaps(),"SWAP_OFF_NOT_VERIFIED")
  need(available()>=HEADROOM,"AFTER_SWAPOFF_MEMORY_LOW")
  print("ACER_DISK_SWAP=OFF_VERIFIED",flush=True)
  PHASE="CANDIDATE_PRIVATE_CONTRACT"
  rc=subprocess.run(["python3","-B",str(checker),"--run"],
                    stdout=None,stderr=None).returncode
 finally:
  PHASE="VERIFY_PRIVATE_CLEANUP"
  if off:
   if clean():
    PHASE="RESTORE_ACER_SWAP"
    p=call(["sudo","-n","swapon",SWAP],timeout=90)
    need(p.returncode==0 and set(swaps())=={SWAP},"SWAP_RESTORE_FAILED")
    print("ACER_SWAP=RESTORED",flush=True)
   else:
    print("ACER_SWAP=LEFT_OFF_PRIVATE_RESIDUE_REQUIRES_REVIEW",flush=True)
    raise Stop("CLEANUP_UNPROVEN_SWAP_LEFT_OFF")
 need(rc==0,"CANDIDATE_CONTRACT_GATE_HOLD")
 PHASE="DONE"
 print("CANDIDATE_CONTRACT_WINDOW=PASS_CHECK_AND_SWAP_RESTORED")
class Tests(unittest.TestCase):
 def test_swap_parser(self):
  self.assertEqual(swaps("Filename Type Size Used Priority\n/swapfile file 2000 800 -1\n"),
                   {"/swapfile":800*1024})
 def test_wrong_host_no_commands(self):
  with patch("socket.gethostname",return_value="wrong"),patch(__name__+".call") as command:
   with self.assertRaises(Stop):preflight(Path("/missing"))
   command.assert_not_called()
 def test_residue_keeps_swap_off(self):
  fake=subprocess.CompletedProcess([],0)
  with patch(__name__+".preflight",return_value=None),\
       patch(__name__+".swaps",return_value={}),\
       patch(__name__+".available",return_value=HEADROOM+1),\
       patch(__name__+".clean",return_value=False),\
       patch(__name__+".call",return_value=fake) as invoked,\
       patch("subprocess.run",return_value=fake):
   with contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaises(Stop):run(Path("/synthetic"))
   self.assertEqual(invoked.call_count,1)
   self.assertEqual(invoked.call_args.args[0],["sudo","-n","swapoff",SWAP])
def main():
 need(len(sys.argv) in (2,3) and sys.argv[1] in ("--self-test","--run"),"MODE_REQUIRED")
 if sys.argv[1]=="--self-test":
  r=unittest.TextTestRunner(verbosity=1).run(
     unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if r.wasSuccessful() else 1
 need(len(sys.argv)==3,"CHECKER_PATH_REQUIRED")
 run(Path(sys.argv[2]));return 0
if __name__=="__main__":
 try:sys.exit(main())
 except Stop as e:
  print("STOP_PHASE="+PHASE+" STOP_REASON="+str(e));sys.exit(3)
 except Exception as e:
  print("STOP_PHASE="+PHASE+" STOP_REASON=REDACTED_"+type(e).__name__);sys.exit(3)
