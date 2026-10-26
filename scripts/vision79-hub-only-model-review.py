#!/usr/bin/env python3
"""V79 V8 -> Vision79 visual: read-only single-Hub candidate and rollback model review.

NO deployment, files written, container lifecycle changes, secrets printed or release authorization.
Runs on Dell only with the existing nonroot Docker-capable operator identity.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys

REV="5b8db879b60a3eeb583b40ec8bda725dcb7c8201"
LIVE={
"v79-hub": ("e02a3b4b40c521257582c1456acb5f9f3949dd22d9b1145de3c2aec77d3aba5c","sha256:66caa099adf1321b72a90b22f8125981e5a6d99b5920cebae0454541cccd9fa7"),
"v79-tiquet-manager": ("2ab5154f800733e4e090ab40f4d16f0c6b054986fd013b7483b8b1d2937ce982","sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0"),
"v79-business-agent": ("b7e559c1cdd6ca73ad4625c94ce39334558f3ae891dd4bc7accfd9ed7a478d28","sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b"),
"v79-hub-postgres": ("5b97b804ed9590a0fd54e86f4a610aae5200131f956549189b0e4aeeab1ec75c","sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24"),
"tiquet-postgres": ("8e4d1093faf710f555795a70caf57b67da8dc71b29555ee0d681c5c47e3b1140","sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685")
}
MODELS={
"v79-hub":(
"/home/firelion/.v79-hardened-pair-releases/pair-20261026T003607Z-6e6006791f34/manifest-v79-hub-candidate.json",
"e785277a3970476c214fade92763fac7a41a9151ece7365c67c8cb2b439023c6"),
"v79-tiquet-manager":(
"/home/firelion/.v79-hardened-pair-releases/pair-20261026T003607Z-6e6006791f34/manifest-v79-tiquet-manager-candidate.json",
"e8f21d2c797c5f8edf012ba47d9122b8ed142b7256282204925ec071c19c9010")
}
CHECKPOINT="release-20261026T102542Z-def4da1b"
CHECKPOINT_IMAGES={name:ident[1] for name,ident in LIVE.items()}
MOUNTS={
"v79-hub": {"/app/data":("bind",True), "/run/secrets/v79-agent-token":("bind",False),
 "/run/secrets/v79-coo-github-token":("bind",False),"/run/secrets/v79-readonly-platform-token":("bind",False),
 "/run/secrets/v79-workforce-token":("bind",False),"/run/v79-google":("volume",False),
 "/run/v79-workforce-reports":("bind",False)},
"v79-tiquet-manager":{"/app/data":("volume",True),"/app/uploads":("volume",True)},
"v79-business-agent":{"/run/secrets/v79-agent-token":("bind",False)}
}
TIMERS=("v79-g2-approved-task-worker.timer","v79-workforce-morning.timer","v79-workforce-evening.timer")

class Halt(Exception):
    pass

def need(ok,reason):
    if not ok:raise Halt(reason)

def safe_call(cmd,data=None,timeout=40):
    try:p=subprocess.run(cmd,input=data,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):raise Halt("READ_ONLY_COMMAND_UNAVAILABLE") from None
    need(p.returncode==0,"READ_ONLY_COMMAND_REFUSED")
    return p.stdout

def inspect(name):
    result=json.loads(safe_call(["docker","inspect",name]))
    need(len(result)==1,"DOCKER_INSPECT_AMBIGUOUS")
    return result[0]

def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def checked_input(path,expected_hash):
    p=Path(path);st=p.lstat()
    need(stat.S_ISREG(st.st_mode) and not p.is_symlink() and
         st.st_uid in (0,os.getuid()) and st.st_size<2*1024*1024 and
         not st.st_mode&0o002,"SEALED_COMPOSE_INPUT_UNSAFE")
    need(file_hash(p)==expected_hash,"SEALED_COMPOSE_CHANGED")
    return json.loads(p.read_bytes())

def candidate_model(original,service,image):
    need(isinstance(original,dict) and isinstance(original.get("services"),dict) and
         service in original["services"],"SEALED_MODEL_STRUCTURE_UNEXPECTED")
    model=copy.deepcopy(original)
    model["services"][service]["image"]=image
    need(model["services"][service]["image"]==image,"CANDIDATE_IMAGE_PATCH_FAILED")
    changed=copy.deepcopy(model)
    changed["services"][service]["image"]=original["services"][service]["image"]
    need(changed==original,"NOT_EXACT_IMAGE_ONLY_CHANGE")
    return model

def check_live():
    need(socket.gethostname()=="v79sl" and os.getuid()!=0 and str(Path.home())=="/home/firelion",
         "EXPECTED_NONROOT_DELL_ONLY")
    need(not os.environ.get("DOCKER_HOST") and not os.environ.get("DOCKER_CONTEXT"),
         "DOCKER_REMOTE_OVERRIDE_REFUSED")
    ctx=json.loads(safe_call(["docker","context","inspect"]))
    need(len(ctx)==1 and ctx[0]["Endpoints"]["docker"]["Host"] in
         ("unix:///var/run/docker.sock","unix:///run/docker.sock"),"NOT_LOCAL_DOCKER")
    need(safe_call(["docker","info","--format","{{.Name}}"]).strip()==b"v79sl",
         "DOCKER_DAEMON_CHANGED")
    version=safe_call(["docker","compose","version","--short"]).decode().strip().removeprefix("v")
    need(version=="5.6.0","COMPOSE_VERSION_UNREHEARSED")
    results={}
    for name,(identifier,image) in LIVE.items():
        row=inspect(name)
        need(row["Id"]==identifier and row["Image"]==image and row["State"]["Running"] and
             row["State"]["Health"]["Status"]=="healthy",
             "PINNED_LIVE_CONTAINER_CHANGED")
        results[name]=row
        if name in MOUNTS:
            actual={m["Destination"]:(m["Type"],m["RW"]) for m in row.get("Mounts",[])}
            need(actual==MOUNTS[name],"MOUNT_SCOPE_CHANGED")
    for name,(path,checksum) in MODELS.items():
        row=results[name]
        need(row["Config"]["Labels"].get("com.docker.compose.project.config_files")==path,
             "SINGLE_SEALED_COMPOSE_IDENTITY_CHANGED")
        model=checked_input(path,checksum)
        need(row["Config"]["Labels"].get("com.docker.compose.service")==name,
             "SERVICE_IDENTITY_CHANGED")
        service=model["services"][name]
        need("image" in service and inspect(service["image"])["Id"]==row["Image"],
             "SEALED_MODEL_IMAGE_DIFFERS_FROM_RUNNING")
    for timer in TIMERS:
        need(safe_call(["systemctl","--user","is-active",timer]).strip()==b"active",
             "WORKFORCE_TIMER_CHANGED")
    cp=Path.home()/".v79-release-checkpoints"/CHECKPOINT/"checkpoint"/"manifest.json"
    obj=checked_checkpoint(cp)
    need(obj.get("images")==CHECKPOINT_IMAGES,
         "RECOVERY_CHECKPOINT_WRONG_IMAGES")
    return results

def checked_checkpoint(path):
    p=Path(path);st=p.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and
         not st.st_mode&0o077 and st.st_nlink==1 and not p.is_symlink(),
         "RECOVERY_MANIFEST_UNSAFE")
    item=json.loads(p.read_bytes())
    need(item.get("audit")=="V79_RELEASE_WINDOW_CHECKPOINT_V1" and
         item.get("apps_resumed_same_ids")==True and len(item.get("files",[]))==15,
         "RECOVERY_MANIFEST_INVALID")
    return item

def main():
    live=check_live()
    candidate=inspect("vision79-hub-visual:"+REV)
    need(candidate["Config"]["Labels"].get("org.opencontainers.image.revision")==REV,
         "CANDIDATE_IMAGE_REVISION_MISMATCH")
    need(candidate["Id"]!=live["v79-hub"]["Image"],"CANDIDATE_EQUALS_RUNNING_IMAGE")
    old_img=inspect(live["v79-hub"]["Image"])
    prior={v.split("=",1)[0]:v.split("=",1)[1] for v in old_img["Config"].get("Env",[]) if "=" in v}
    proposed={v.split("=",1)[0]:v.split("=",1)[1] for v in candidate["Config"].get("Env",[]) if "=" in v}
    differences={k for k in prior.keys()|proposed.keys() if prior.get(k)!=proposed.get(k)}
    need(differences <= {"NODE_VERSION","YARN_VERSION"},
         "NEW_IMAGE_UNREVIEWED_PROCESS_ENV_DEFAULTS")
    old,oldhash=MODELS["v79-hub"]
    model=checked_input(old,oldhash)
    patched=candidate_model(model,"v79-hub",candidate["Id"])
    need(patched["services"]["v79-hub"]["image"]==candidate["Id"],
         "IMAGE_SUBSTITUTION_FAILED")
    baseline_model=candidate_model(model,"v79-hub",live["v79-hub"]["Image"])
    args=["docker","compose","--env-file","/dev/null",
          "--project-name",live["v79-hub"]["Config"]["Labels"]["com.docker.compose.project"],
          "--project-directory",live["v79-hub"]["Config"]["Labels"]["com.docker.compose.project.working_dir"],
          "-f","-","config","--format","json"]
    # Validate both models only in-memory: never write their secrets to a file or output.
    for kind,entry,identity in (("rollback",baseline_model,live["v79-hub"]["Image"]),
                                ("candidate",patched,candidate["Id"])):
        out=json.loads(safe_call(args,json.dumps(entry).encode()))
        need(out["services"]["v79-hub"]["image"]==identity,"COMPOSE_RENDER_IMAGE_CHANGED")
        need(set(out["services"])==set(entry["services"]),"COMPOSE_RENDER_SERVICE_SCOPE_CHANGED")
        print("COMPOSE_"+kind.upper()+"_READ_ONLY_RENDER=PASS")
    print("LIVE_HUB_IMAGE="+live["v79-hub"]["Image"])
    print("CANDIDATE_HUB_IMAGE="+candidate["Id"])
    print("REVIEWED_IMAGE_DEFAULT_CHANGES="+",".join(sorted(differences)))
    print("PROTECTED_CONTAINERS_AND_MOUNTS=PASS_5_OF_5")
    print("OFFHOST_CHECKPOINT_MANIFEST=PINNED_TO_CURRENT_IMAGES")
    print("WORKFORCE_TIMERS=PASS_3_OF_3")
    print("HUB_ONLY_IMAGE_DELTA=PASS")
    print("PROFILE_AND_ROLLBACK_REHEARSAL=NOT_YET_PERFORMED")
    print("PRODUCTION_CHANGES=NONE")

if __name__=="__main__":
    try:main()
    except BaseException as error:
        if isinstance(error,SystemExit):raise
        reason=str(error) if isinstance(error,Halt) and re.fullmatch(r"[A-Z0-9_]+",str(error)) else "READ_ONLY_PREFLIGHT_REFUSED"
        print("NO_GO="+reason)
        print("PRODUCTION_CHANGES=NONE")
        sys.exit(2)
