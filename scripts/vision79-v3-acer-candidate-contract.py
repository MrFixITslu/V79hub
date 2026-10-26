#!/usr/bin/env python3
"""Acer-only, read-only candidate-vs-encrypted-live-runtime metadata gate.

Decrypts the previously verified offhost snapshot into process memory only.
Requires all disk-backed swap disabled (a separate guarded window manages that).
Does not run containers, contact production, output private settings, or deploy.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path("/home/firelion/v79-v3-offhost-we7b0lir")
COPY=ROOT/"v3-20261026T194538Z-gnm710en"
RECEIPT_SHA="35a9b4d41b5c42a8c6653e1c1985ebdae49ce77432d57c94ff68c82172173df5"
AUDIT_SHA="2e63990c22d31d0998d90b575f7490a5fc09917c839f6a54f68e317cdfffaa57"
APPROVED="114841271d4f8b9c4b63df6aedfd55bde2e82f40"
CANDIDATE="sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
PRIOR="sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4"
NAMES={"v79-hub","v79-hub-postgres","v79-tiquet-manager","tiquet-postgres","v79-business-agent"}
CIPHERTEXT="live-runtime.json.gpg"
class Stop(Exception): pass
def need(ok,code):
 if not ok:raise Stop(code)
def digest(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for block in iter(lambda:f.read(131072),b""):h.update(block)
 return h.hexdigest()
def call(args,timeout=45):
 try:p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):raise Stop("LOCAL_COMMAND_FAILED") from None
 need(p.returncode==0 and len(p.stdout)<8*1024*1024,"LOCAL_COMMAND_FAILED")
 return p.stdout
def one(args):
 try: rows=json.loads(call(args))
 except (ValueError,TypeError,UnicodeError):raise Stop("IMAGE_INSPECT_INVALID") from None
 need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),"IMAGE_INSPECT_SHAPE")
 return rows[0]
def env(rows):
 result={}
 for item in rows or []:
  need(isinstance(item,str) and "=" in item,"ENV_ENTRY_INVALID")
  key,value=item.split("=",1)
  need(key and key not in result,"ENV_DUPLICATE")
  result[key]=value
 return result
def runtime_fingerprint(row):
 # Identical to approved live deep-audit calculation. Includes private fields
 # but ONLY returns a SHA-256 digest; private JSON never leaves memory.
 snapshot={"id":row.get("Id"),"image":row.get("Image"),"config":row.get("Config"),
           "host_config":row.get("HostConfig"),"mounts":row.get("Mounts"),
           "networks":(row.get("NetworkSettings") or {}).get("Networks")}
 value=json.dumps(snapshot,sort_keys=True,separators=(",",":")).encode()
 return hashlib.sha256(value).hexdigest()
def read_snapshot(path):
 p=None
 try:
  p=subprocess.Popen(["gpg","--batch","--no-tty","--quiet","--decrypt",str(path)],
                     stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  blocks=[];size=0
  while True:
   block=p.stdout.read(131072)
   if not block:break
   size+=len(block)
   need(size<=16*1024*1024,"RUNTIME_PRIVATE_MEMORY_LIMIT")
   blocks.append(block)
  need(p.wait(timeout=60)==0,"RUNTIME_DECRYPT_FAILED")
  try:records=json.loads(b"".join(blocks))
  except (ValueError,UnicodeDecodeError):raise Stop("RUNTIME_JSON_INVALID") from None
  need(isinstance(records,list) and len(records)==5,"RUNTIME_CONTAINER_COUNT_DRIFT")
  names={r.get("Name","").lstrip("/") for r in records}
  need(names==NAMES and len(names)==5,"RUNTIME_CONTAINER_SET_DRIFT")
  return {r["Name"].lstrip("/"):r for r in records}
 finally:
  if p is not None:
   if p.stdout and not p.stdout.closed:p.stdout.close()
   if p.poll() is None:p.kill()
   p.wait()
def compare(hub,prior,candidate):
 need(hub.get("Image")==PRIOR and prior.get("Id")==PRIOR
  and candidate.get("Id")==CANDIDATE,"APPROVED_IMAGE_PIN_DRIFT")
 need(runtime_fingerprint(hub)==AUDIT_SHA,"LIVE_SNAPSHOT_NOT_CURRENT_AUDIT")
 cfg=hub.get("Config") or {}
 live_env=env(cfg.get("Env"))
 need(len(live_env)==85,"LIVE_ENVIRONMENT_KEY_COUNT_DRIFT")
 need(live_env.get("V79_REQUIRE_ADMIN_MFA")=="1","LIVE_ADMIN_MFA_FLAG_MISSING")
 need(len(hub.get("Mounts") or [])==7,"LIVE_MOUNT_COUNT_DRIFT")
 host=hub.get("HostConfig") or {}
 need(len(host.get("Binds") or [])==4 and len(host.get("Mounts") or [])==3,
      "LIVE_HOST_MOUNT_DECLARATION_DRIFT")
 need(len((hub.get("NetworkSettings") or {}).get("Networks") or {})==2,
      "LIVE_NETWORK_COUNT_DRIFT")
 need(not host.get("PortBindings"),"LIVE_PORTS_EXPOSED")
 need((candidate.get("Config") or {}).get("Labels",{}).get("org.opencontainers.image.revision")==APPROVED,
      "CANDIDATE_REVISION_DRIFT")
 candidate_cfg=candidate.get("Config") or {}
 candidate_defaults=env(candidate_cfg.get("Env"))
 missing=sorted(set(candidate_defaults)-set(live_env))
 conflicts=sorted(k for k,v in candidate_defaults.items()
                  if k in live_env and live_env[k]!=v)
 # The live environment is intentionally not copied into a Docker command here.
 # New image defaults must not silently disappear in a future replacement.
 need(not missing,"NEW_CANDIDATE_DEFAULT_ENV_KEYS_NEED_REVIEW")
 image_volumes=set((candidate_cfg.get("Volumes") or {}).keys())
 mounted={m.get("Destination") for m in hub.get("Mounts") or []}
 need(image_volumes.issubset(mounted),"UNMAPPED_NEW_IMAGE_VOLUME")
 return {"schema":"vision79-v3-candidate-offhost-contract",
         "result":"PASS_CANDIDATE_METADATA_AND_LIVE_SNAPSHOT_MATCH",
         "live_baseline_fingerprint_match":True,
         "approved_source_image_match":True,
         "environment_keys":len(live_env),"mount_destinations":len(mounted),
         "candidate_default_keys":len(candidate_defaults),
         "candidate_default_value_changes":len(conflicts),
         "candidate_user_matches_prior":candidate_cfg.get("User")==((prior.get("Config") or {}).get("User")),
         "candidate_entrypoint_matches_prior":candidate_cfg.get("Entrypoint")==((prior.get("Config") or {}).get("Entrypoint")),
         "candidate_command_matches_prior":candidate_cfg.get("Cmd")==((prior.get("Config") or {}).get("Cmd")),
         "candidate_image_on_server_verified":False,
         "full_production_runtime_parity_verified":False,
         "real_owner_mfa_sso_verified":False,
         "production_changes":"NONE","release_gate":"HOLD"}
def preflight():
 need(socket.gethostname().split(".")[0]=="firelion-Aspire-A315-51","ACER_HOST_REQUIRED")
 need(os.geteuid()!=0 and not os.getenv("DOCKER_HOST") and not os.getenv("DOCKER_CONTEXT"),
      "ACER_LOCAL_USER_ONLY")
 need(call(["docker","context","show"]).strip()==b"default" and
      call(["docker","info","--format","{{.Name}}"]).strip()==b"firelion-Aspire-A315-51",
      "ACER_LOCAL_DOCKER_REQUIRED")
 swaps=Path("/proc/swaps").read_text().splitlines()
 need(len(swaps)==1,"ACTIVE_SWAP_REFUSED")
 receipt=COPY/"receipt.json";proof=ROOT/"offhost-verification.json";cfile=COPY/CIPHERTEXT
 need(all(p.is_file() and not p.is_symlink() for p in (receipt,proof,cfile)),
      "OFFHOST_RECOVERY_ARTIFACTS_MISSING")
 need(digest(receipt)==RECEIPT_SHA,"RECOVERY_RECEIPT_DRIFT")
 r=json.loads(receipt.read_text());p=json.loads(proof.read_text())
 need(p.get("server_receipt_sha256")==RECEIPT_SHA and
      p.get("offhost_ciphertext_hashes")=="PASS_14" and
      p.get("decryption_and_structure")=="PASS_14","OFFHOST_PROOF_DRIFT")
 need(digest(cfile)==r.get("encrypted_sha256",{}).get(CIPHERTEXT),
      "PRIVATE_CIPHERTEXT_HASH_DRIFT")
 return cfile
def run():
 cfile=preflight()
 records=read_snapshot(cfile)
 prior=one(["docker","image","inspect",PRIOR])
 candidate=one(["docker","image","inspect",CANDIDATE])
 return compare(records["v79-hub"],prior,candidate)
class Tests(unittest.TestCase):
 def image(self,key):
  return {"Id":key,"Config":{"Env":["NODE_ENV=production","PATH=/usr/local/bin"],
          "Labels":{"org.opencontainers.image.revision":APPROVED}}}
 def hub(self):
  row={"Image":PRIOR,"Config":{"Env":["V79_REQUIRE_ADMIN_MFA=1"]+
       ["K"+str(i)+"=v" for i in range(84)]},
       "Mounts":[{"Destination":"/app/"+str(i)} for i in range(7)],
       "HostConfig":{"Binds":["x"]*4,"Mounts":[{}]*3,"PortBindings":None},
       "NetworkSettings":{"Networks":{"proxy":{},"hub":{}}}}
  return row
 def test_wrong_host_rejected_before_docker(self):
  with patch("socket.gethostname",return_value="other"),patch(__name__+".call") as c:
   with self.assertRaises(Stop):preflight()
   c.assert_not_called()
 def test_duplicate_env_rejected(self):
  with self.assertRaises(Stop):env(["A=one","A=two"])
 def test_secret_never_in_output(self):
  h=self.hub();h["Config"]["Env"][1]="K0=PRIVATE_SECRET"
  before=runtime_fingerprint(h)
  with patch(__name__+".AUDIT_SHA",before):
   candidate=self.image(CANDIDATE);candidate["Config"]["Env"]=["NODE_ENV=production"]
   with self.assertRaises(Stop):compare(h,self.image(PRIOR),candidate)
  self.assertNotIn("PRIVATE_SECRET",before)
 def test_fingerprint_rejects_drift(self):
  with self.assertRaises(Stop):compare(self.hub(),self.image(PRIOR),self.image(CANDIDATE))
 def test_missing_image_env_rejected(self):
  h=self.hub();sha=runtime_fingerprint(h)
  candidate=self.image(CANDIDATE);candidate["Config"]["Env"]=["KNEW=yes"]
  with patch(__name__+".AUDIT_SHA",sha):
   with self.assertRaises(Stop):compare(h,self.image(PRIOR),candidate)
 def test_check_no_swap_without_decrypt(self):
  with patch("socket.gethostname",return_value="firelion-Aspire-A315-51"),\
       patch("os.geteuid",return_value=1000),patch(__name__+".call",return_value=b"default"),\
       patch("pathlib.Path.read_text",return_value="Filename Type Size Used Priority\n/swapfile file 100 50 -1\n"):
   with self.assertRaises(Stop):preflight()

def main():
 need(len(sys.argv)==2 and sys.argv[1] in ("--self-test","--run"),"MODE_REQUIRED")
 if sys.argv[1]=="--self-test":
  results=unittest.TextTestRunner(verbosity=1).run(
          unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if results.wasSuccessful() else 1
 print(json.dumps(run(),sort_keys=True));return 0
if __name__=="__main__":
 try:sys.exit(main())
 except Stop as e:
  print(json.dumps({"result":"STOP","reason":str(e),"release_gate":"HOLD",
                    "production_changes":"NONE"}));sys.exit(3)
 except Exception as e:
  print(json.dumps({"result":"STOP","reason":"REDACTED_"+type(e).__name__,
                    "release_gate":"HOLD","production_changes":"NONE"}));sys.exit(3)
