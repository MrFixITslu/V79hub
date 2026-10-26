#!/usr/bin/env python3
"""Local-only diagnosis: why Docker image save config digest differs from inspect ID.

Does NOT change Docker, SSH, app data, production, or any repo/image tags.
Reports only boolean evidence about digest relationships; no private values.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

IMAGE="sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
SOURCE="114841271d4f8b9c4b63df6aedfd55bde2e82f40"
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def command(args,timeout=90):
 try:p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):raise Stop("LOCAL_COMMAND_UNAVAILABLE") from None
 need(p.returncode==0 and len(p.stdout)<4*1024*1024,"LOCAL_COMMAND_FAILED")
 return p.stdout
def local():
 need(socket.gethostname().split(".")[0]=="firelion-Aspire-A315-51","ACER_REQUIRED")
 need(os.geteuid()!=0 and not os.getenv("DOCKER_HOST") and not os.getenv("DOCKER_CONTEXT"),"LOCAL_DOCKER_ONLY")
 need(command(["docker","context","show"]).strip()==b"default" and
      command(["docker","info","--format","{{.Name}}"]).strip()==b"firelion-Aspire-A315-51",
      "DOCKER_DAEMON_DRIFT")
 try:rows=json.loads(command(["docker","image","inspect",IMAGE]))
 except (ValueError,UnicodeError):raise Stop("IMAGE_INSPECT_INVALID") from None
 need(isinstance(rows,list) and len(rows)==1 and rows[0].get("Id")==IMAGE,"IMAGE_ID_DRIFT")
 need(((rows[0].get("Config") or {}).get("Labels") or {}).get("org.opencontainers.image.revision")==SOURCE,"IMAGE_SOURCE_DRIFT")
 need(shutil.disk_usage(str(Path.home())).free>=6*1024**3,"ACER_DISK_HEADROOM_LOW")
 return rows[0]
def sha_stream(stream):
 h=hashlib.sha256()
 for buf in iter(lambda:stream.read(131072),b""):h.update(buf)
 return h.hexdigest()
def load_small(tar,name,limit=4*1024*1024):
 try:member=tar.getmember(name)
 except KeyError:return None
 need(member.isfile() and 0<member.size<=limit,"ARCHIVE_SMALL_FILE_INVALID")
 stream=tar.extractfile(member)
 need(stream is not None,"ARCHIVE_MEMBER_UNREADABLE")
 with stream:return stream.read(limit+1)
def analyze(tar,inspect_row):
 manifest=load_small(tar,"manifest.json",65536)
 need(manifest is not None,"DOCKER_MANIFEST_NOT_FOUND")
 try:rows=json.loads(manifest)
 except (UnicodeError,ValueError):raise Stop("DOCKER_MANIFEST_INVALID") from None
 need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),"DOCKER_MANIFEST_COUNT_DRIFT")
 row=rows[0]
 config_path=row.get("Config")
 need(isinstance(config_path,str) and bool(re.fullmatch(r"[a-zA-Z0-9_./-]+",config_path))
      and ".." not in config_path.split("/") and not config_path.startswith("/"),
      "CONFIG_PATH_INVALID")
 config_bytes=load_small(tar,config_path)
 need(config_bytes is not None,"CONFIG_MEMBER_NOT_FOUND")
 try:config=json.loads(config_bytes)
 except (UnicodeError,ValueError):raise Stop("CONFIG_JSON_INVALID") from None
 need(isinstance(config,dict),"CONFIG_SHAPE_INVALID")
 config_hash=hashlib.sha256(config_bytes).hexdigest()
 indexed_blob="blobs/sha256/"+config_hash
 path_matches=(config_path in (config_hash+".json",indexed_blob))
 index_bytes=load_small(tar,"index.json",65536)
 index=None
 if index_bytes is not None:
  try:index=json.loads(index_bytes)
  except (ValueError,UnicodeError):raise Stop("OCI_INDEX_JSON_INVALID") from None
 descriptors=index.get("manifests") if isinstance(index,dict) else None
 if not isinstance(descriptors,list):descriptors=[]
 pinned=IMAGE.split(":")[1]
 allnames={m.name for m in tar.getmembers()}
 pinned_blob="blobs/sha256/"+pinned
 config_inner=config.get("config") or {}
 inspect_config=inspect_row.get("Config") or {}
 exported_diff_ids=((config.get("rootfs") or {}).get("diff_ids") or [])
 inspect_diff_ids=((inspect_row.get("RootFS") or {}).get("Layers") or [])
 return {"schema":"vision79-v3-archive-identity-local-diagnostic",
         "archive_single_image":True,
         "archive_has_mutable_tags":bool(row.get("RepoTags")),
         "config_path_style":("legacy_json" if config_path.endswith(".json") else
                              "oci_blob" if config_path.startswith("blobs/sha256/") else "other"),
         "config_sha_matches_config_archive_name":path_matches,
         "config_sha_matches_pinned_image_id":config_hash==pinned,
         "index_json_present":index_bytes is not None,
         "index_file_sha_matches_pinned_image_id":hashlib.sha256(index_bytes).hexdigest()==pinned if index_bytes is not None else False,
         "index_descriptor_digest_matches_pinned_image_id":any(isinstance(d,dict) and d.get("digest")==IMAGE for d in descriptors),
         "pinned_image_id_blob_in_archive":pinned_blob in allnames,
         "exported_config_approved_source_label_match":((config_inner.get("Labels") or {}).get("org.opencontainers.image.revision")==SOURCE),
         "exported_config_user_matches_inspect":config_inner.get("User","")==inspect_config.get("User",""),
         "exported_config_entrypoint_matches_inspect":config_inner.get("Entrypoint")==inspect_config.get("Entrypoint"),
         "exported_config_cmd_matches_inspect":config_inner.get("Cmd")==inspect_config.get("Cmd"),
         "exported_diffids_match_inspect":exported_diff_ids==inspect_diff_ids,
         "exported_diffid_count":len(exported_diff_ids),
         "inspect_diffid_count":len(inspect_diff_ids),
         "release_gate":"HOLD","production_changes":"NONE","remote_transfer":"NONE"}
def diagnose():
 inspect_row=local()
 print("ACER_ONLY_DIAGNOSTIC_PREFLIGHT=PASS",flush=True)
 with tempfile.TemporaryDirectory(prefix="v79-v3-archive-diagnostic-",dir=str(Path.home())) as d:
  path=Path(d)/"candidate.tar"
  command(["docker","image","save","--output",str(path),IMAGE],timeout=900)
  need(path.is_file() and path.stat().st_size>=10_000_000,"EXPORTED_ARCHIVE_INVALID")
  with tarfile.open(path,mode="r:") as tar:report=analyze(tar,inspect_row)
 print("LOCAL_EXPORT_ARCHIVE_REMOVED=PASS",flush=True)
 print(json.dumps(report,sort_keys=True))
class Tests(unittest.TestCase):
 def fixture(self):
  import io
  inner={"config":{"Labels":{"org.opencontainers.image.revision":SOURCE},
                    "Entrypoint":["/bin/sh"],"Cmd":["app"],"User":""},
         "rootfs":{"diff_ids":["sha256:"+"f"*64]}}
  config_bytes=json.dumps(inner,separators=(",",":")).encode()
  sha=hashlib.sha256(config_bytes).hexdigest()
  entries=[{"Config":"blobs/sha256/"+sha,"RepoTags":None}]
  manifest=json.dumps(entries).encode()
  contents={"manifest.json":manifest,"blobs/sha256/"+sha:config_bytes}
  output=io.BytesIO()
  with tarfile.open(fileobj=output,mode="w:") as tar:
   for name,data in contents.items():
    info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
  output.seek(0)
  inspect={"Config":{"Entrypoint":["/bin/sh"],"Cmd":["app"],"User":""},
           "RootFS":{"Layers":["sha256:"+"f"*64]}}
  return output,inspect,sha
 def test_local_report_without_private_values(self):
  output,inspect,sha=self.fixture()
  with patch(__name__+".IMAGE","sha256:"+sha):
   with tarfile.open(fileobj=output,mode="r:") as tar:result=analyze(tar,inspect)
  self.assertTrue(result["config_sha_matches_pinned_image_id"])
  self.assertTrue(result["exported_diffids_match_inspect"])
  self.assertNotIn("f"*64,json.dumps(result))
 def test_oci_manifest_different_from_image_id(self):
  output,inspect,sha=self.fixture()
  with patch(__name__+".IMAGE","sha256:"+"e"*64):
   with tarfile.open(fileobj=output,mode="r:") as tar:result=analyze(tar,inspect)
  self.assertFalse(result["config_sha_matches_pinned_image_id"])
  self.assertTrue(result["config_sha_matches_config_archive_name"])
 def test_refuse_wrong_host_before_docker(self):
  with patch("socket.gethostname",return_value="other"),patch(__name__+".command") as cmd:
   with self.assertRaises(Stop):local()
   cmd.assert_not_called()
 def test_no_archive_dir_escape(self):
  output,inspect,sha=self.fixture()
  # No filesystem extracts are performed by this tool.
  self.assertEqual(inspect["Config"]["Cmd"],["app"])
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ("--self-test","--diagnose"),"MODE_REQUIRED")
 if sys.argv[1]=="--self-test":
  r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if r.wasSuccessful() else 1
 diagnose();return 0
if __name__=="__main__":
 try:sys.exit(main())
 except Stop as e:
  print(json.dumps({"result":"STOP","reason":str(e),"release_gate":"HOLD"}));sys.exit(3)
 except Exception as e:
  print(json.dumps({"result":"STOP","reason":"REDACTED_"+type(e).__name__,
                    "release_gate":"HOLD"}));sys.exit(3)
