#!/usr/bin/env python3
"""Read-only Vision79 v3 production contract audit. No deployment capability.

Audits current live Hub/Compose and checks that low-level Docker bind/mount
declarations reproduce the actual mounts. Does NOT prove candidate parity,
real owner MFA/SSO, or authorize production replacement. No secrets emitted.
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

HUB = "v79-hub"
COMPOSE_SHA = "2fc119a387df933ff2fcfb8c33d07445160ba281511f05e937ef48beaa4e5083"
IMAGES = {
    "v79-hub": "sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4",
    "v79-hub-postgres": "sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
    "v79-tiquet-manager": "sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0",
    "tiquet-postgres": "sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
    "v79-business-agent": "sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b",
}

class Stop(Exception): pass

def need(ok, reason):
    if not ok: raise Stop(reason)

def command(args, cwd=None):
    try:
        p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=45)
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("READ_ONLY_COMMAND_UNAVAILABLE") from None
    need(p.returncode == 0 and len(p.stdout) <= 16 * 1024 * 1024,
         "READ_ONLY_COMMAND_FAILED")
    return p.stdout

def one(args):
    try: rows = json.loads(command(args))
    except (ValueError, UnicodeDecodeError):
        raise Stop("PRIVATE_INSPECTION_INVALID") from None
    need(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict),
         "INSPECTION_SHAPE_DRIFT")
    return rows[0]

def environment(entries):
    result = {}
    for item in entries or []:
        need(isinstance(item, str) and "=" in item, "ENVIRONMENT_SHAPE_DRIFT")
        k, v = item.split("=", 1)
        need(k and k not in result, "ENVIRONMENT_DUPLICATE_KEY")
        result[k] = v
    return result

def fingerprint(row):
    # Private values are hashed locally, never printed or retained.
    snapshot = {
        "id": row.get("Id"),
        "image": row.get("Image"),
        "config": row.get("Config"),
        "host_config": row.get("HostConfig"),
        "mounts": row.get("Mounts"),
        "networks": (row.get("NetworkSettings") or {}).get("Networks")
    }
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

def resolve_source(item, rendered):
    kind = item.get("type")
    source = item.get("source")
    if kind == "volume":
        need(isinstance(source, str) and source, "VOLUME_SOURCE_MISSING")
        return ((rendered.get("volumes") or {}).get(source) or {}).get("name", source)
    need(kind == "bind" and isinstance(source, str) and source.startswith("/"),
         "UNSUPPORTED_MOUNT_SOURCE")
    return source

def compose_mounts(service, rendered):
    expected = {}
    for item in service.get("volumes") or []:
        need(isinstance(item, dict), "COMPOSE_MOUNT_SHAPE")
        target = item.get("target")
        need(isinstance(target, str) and target.startswith("/") and target not in expected,
             "COMPOSE_MOUNT_TARGET_INVALID")
        kind = item.get("type")
        need(kind in ("bind", "volume"), "UNSUPPORTED_COMPOSE_MOUNT")
        expected[target] = (kind, resolve_source(item, rendered),
                            not bool(item.get("read_only", False)))
    return expected

def actual_mounts(row):
    result = {}
    for item in row.get("Mounts") or []:
        dest = item.get("Destination")
        kind = item.get("Type")
        need(isinstance(dest, str) and dest not in result and kind in ("bind", "volume"),
             "UNSUPPORTED_RUNTIME_MOUNT")
        source = item.get("Name") if kind == "volume" else item.get("Source")
        need(isinstance(source, str) and source, "RUNTIME_MOUNT_SOURCE_INVALID")
        result[dest] = (kind, source, bool(item.get("RW")))
    return result

def host_declared_mounts(row, actual):
    host = row.get("HostConfig") or {}
    declarations = {}
    for bind in host.get("Binds") or []:
        need(isinstance(bind, str), "BIND_SHAPE_INVALID")
        parts = bind.split(":")
        need(2 <= len(parts) <= 3, "UNSUPPORTED_BIND_FORMAT")
        source, target = parts[:2]
        mode = parts[2] if len(parts) == 3 else ""
        flags = mode.split(",") if mode else []
        need(not ("ro" in flags and "rw" in flags), "BIND_MODE_CONFLICT")
        need(target.startswith("/") and target not in declarations and source,
             "BIND_TARGET_OR_SOURCE_INVALID")
        kind = "bind" if source.startswith("/") else "volume"
        declarations[target] = (kind, source, "ro" not in flags)
    for mount in host.get("Mounts") or []:
        need(isinstance(mount, dict), "HOST_MOUNT_SHAPE_INVALID")
        target = mount.get("Target") or mount.get("Destination")
        kind = mount.get("Type")
        source = mount.get("Source")
        need(isinstance(target, str) and target.startswith("/") and target not in declarations
             and kind in ("bind", "volume") and isinstance(source, str) and source,
             "HOST_MOUNT_DECLARATION_INVALID")
        declarations[target] = (kind, source, not bool(mount.get("ReadOnly", False)))
    need(declarations == actual, "HOST_BINDS_OR_MOUNTS_DRIFT")
    return len(host.get("Binds") or []), len(host.get("Mounts") or [])

def validate(hub, hub_image, rendered):
    need(hub.get("Image") == IMAGES[HUB] and hub_image.get("Id") == IMAGES[HUB],
         "LIVE_HUB_IMAGE_DRIFT")
    need(hub.get("State", {}).get("Status") == "running" and
         hub.get("State", {}).get("Health", {}).get("Status") == "healthy",
         "LIVE_HUB_UNHEALTHY")
    service = (rendered.get("services") or {}).get(HUB)
    need(isinstance(service, dict), "COMPOSE_SERVICE_MISSING")
    ref = service.get("image")
    need(ref is None or ref in ([IMAGES[HUB]] + (hub_image.get("RepoTags") or []) +
                                 (hub_image.get("RepoDigests") or [])), "COMPOSE_IMAGE_DRIFT")
    cfg = service.get("environment") or {}
    need(isinstance(cfg, dict), "COMPOSE_ENV_INVALID")
    env_expected = environment((hub_image.get("Config") or {}).get("Env"))
    env_expected.update({k: str(v) for k, v in cfg.items() if v is not None})
    need(environment((hub.get("Config") or {}).get("Env")) == env_expected,
         "RESOLVED_ENVIRONMENT_DRIFT")
    expected = compose_mounts(service, rendered)
    actual = actual_mounts(hub)
    need(expected == actual, "COMPOSE_MOUNTS_DRIFT")
    binds, mounts = host_declared_mounts(hub, actual)
    networks = ((hub.get("NetworkSettings") or {}).get("Networks") or {})
    declared = service.get("networks") or {}
    if isinstance(declared, list): declared = {n: {} for n in declared}
    need(isinstance(declared, dict), "COMPOSE_NETWORK_SHAPE")
    actual_names = set(networks)
    expected_names = {((rendered.get("networks") or {}).get(n) or {}).get("name", n)
                      for n in declared}
    need(actual_names == expected_names, "COMPOSE_NETWORK_DRIFT")
    host = hub.get("HostConfig") or {}
    need(not host.get("PortBindings"), "UNEXPECTED_PORT_PUBLICATION")
    need(host.get("Privileged") is False, "PRIVILEGED_RUNTIME_REJECTED")
    need(not host.get("PidMode") or host.get("PidMode") != "host",
         "HOST_PID_NAMESPACE_REJECTED")
    need(bool(host.get("ReadonlyRootfs")) == bool(service.get("read_only", False)),
         "ROOT_FILESYSTEM_MODE_DRIFT")
    restart = service.get("restart")
    if restart is not None:
        need((host.get("RestartPolicy") or {}).get("Name") == restart,
             "RESTART_POLICY_DRIFT")
    return {"environment_keys":len(env_expected), "mount_destinations":len(actual),
            "host_bind_entries":binds, "host_mount_entries":mounts,
            "network_count":len(actual_names),
            "runtime_fingerprint_sha256":fingerprint(hub)}

def collect():
    need(socket.gethostname().split(".")[0] == "v79sl", "SERVER_HOST_REQUIRED")
    need(os.geteuid() != 0 and not os.getenv("DOCKER_HOST") and not os.getenv("DOCKER_CONTEXT"),
         "LOCAL_USER_AND_DOCKER_REQUIRED")
    need(command(["docker","context","show"]).strip() == b"default" and
         command(["docker","info","--format","{{.Name}}"]).strip() == b"v79sl",
         "SERVER_DOCKER_REQUIRED")
    containers = {n: one(["docker","inspect","--type","container",n]) for n in IMAGES}
    for name, row in containers.items():
        need(row.get("Image") == IMAGES[name] and
             (row.get("State") or {}).get("Status") == "running" and
             ((row.get("State") or {}).get("Health") or {}).get("Status") == "healthy",
             "LIVE_SERVICE_BASELINE_DRIFT")
    hub = containers[HUB]
    labels = (hub.get("Config") or {}).get("Labels") or {}
    files = (labels.get("com.docker.compose.project.config_files") or "").split(",")
    need(len(files) == 1 and Path(files[0]).is_absolute() and
         Path(files[0]).name == "hub-candidate.json", "COMPOSE_CHAIN_DRIFT")
    p = Path(files[0])
    need(p.is_file() and not p.is_symlink() and p.stat().st_size < 2_000_000,
         "COMPOSE_FILE_INVALID")
    need(hashlib.sha256(p.read_bytes()).hexdigest() == COMPOSE_SHA, "COMPOSE_SOURCE_DRIFT")
    project = labels.get("com.docker.compose.project")
    working = labels.get("com.docker.compose.project.working_dir")
    need(isinstance(project,str) and project and isinstance(working,str) and
         Path(working).is_absolute(), "COMPOSE_PROJECT_INVALID")
    try:
        rendered = json.loads(command(["docker","compose","--project-directory",working,
                                       "--project-name",project,"-f",str(p),
                                       "config","--format","json"],cwd=working))
    except (ValueError, UnicodeDecodeError):
        raise Stop("COMPOSE_RENDER_INVALID") from None
    image = one(["docker","inspect","--type","image",IMAGES[HUB]])
    checks = validate(hub, image, rendered)
    again = one(["docker","inspect","--type","container",HUB])
    need(fingerprint(again) == checks["runtime_fingerprint_sha256"] and
         hashlib.sha256(p.read_bytes()).hexdigest() == COMPOSE_SHA,
         "BASELINE_CHANGED_DURING_AUDIT")
    return {"schema":"vision79-v3-deep-runtime-readonly",
            "result":"PASS_LIVE_RUNTIME_COMPOSE_AUDIT",
            "checks":checks,"candidate_image_on_server_verified":False,
            "candidate_full_runtime_parity_verified":False,
            "real_owner_mfa_sso_verified":False,
            "production_changes":"NONE","release_gate":"HOLD"}

class Tests(unittest.TestCase):
    def fixture(self):
        image = IMAGES[HUB]
        m = {"Destination":"/app/data","Type":"bind",
             "Source":"/safe/mock-data","RW":True}
        row = {
          "Id":"a"*64, "Image":image,
          "State":{"Status":"running","Health":{"Status":"healthy"}},
          "Config":{"Env":["SECRET=private-value"],"Labels":{}},
          "HostConfig":{"Binds":["/safe/mock-data:/app/data:rw"],"Mounts":[],
                        "PortBindings":None,"Privileged":False,"ReadonlyRootfs":False,
                        "PidMode":"","RestartPolicy":{"Name":"unless-stopped"}},
          "Mounts":[m],"NetworkSettings":{"Networks":{"proxy_network":{}}}
        }
        image_meta = {"Id":image,"Config":{"Env":["SECRET=private-value"]},
                      "RepoTags":["hub:current"]}
        rendered={"services":{HUB:{"image":"hub:current","restart":"unless-stopped",
           "environment":{},"volumes":[{"type":"bind","source":"/safe/mock-data",
                                     "target":"/app/data"}],
           "networks":{"proxy":{}}}},"networks":{"proxy":{"name":"proxy_network"}}}
        return row,image_meta,rendered

    def test_reject_wrong_host_without_docker(self):
        with patch("socket.gethostname",return_value="other"),patch(__name__+".command") as c:
            with self.assertRaises(Stop): collect()
            c.assert_not_called()

    def test_reject_drifted_host_bind(self):
        row,image,rendered = self.fixture()
        row["HostConfig"]["Binds"]=["/wrong:/app/data:rw"]
        with self.assertRaises(Stop):validate(row,image,rendered)

    def test_reject_missing_mount_declaration(self):
        row,image,rendered = self.fixture()
        row["HostConfig"]["Binds"]=[]
        with self.assertRaises(Stop):validate(row,image,rendered)

    def test_reject_extra_host_mount(self):
        row,image,rendered = self.fixture()
        row["HostConfig"]["Mounts"]=[{"Type":"bind","Source":"/extra",
                                    "Target":"/extra","ReadOnly":False}]
        with self.assertRaises(Stop):validate(row,image,rendered)

    def test_reject_privileged(self):
        row,image,rendered=self.fixture()
        row["HostConfig"]["Privileged"]=True
        with self.assertRaises(Stop):validate(row,image,rendered)

    def test_reject_secret_exposure(self):
        row,image,rendered=self.fixture()
        check=validate(row,image,rendered)
        self.assertNotIn("private-value",json.dumps(check))
        self.assertEqual(check["host_bind_entries"],1)

    def test_reject_env_drift(self):
        row,image,rendered=self.fixture()
        row["Config"]["Env"]=["SECRET=wrong"]
        with self.assertRaises(Stop):validate(row,image,rendered)

    def test_reject_network_drift(self):
        row,image,rendered=self.fixture()
        row["NetworkSettings"]["Networks"]={"different":{}}
        with self.assertRaises(Stop):validate(row,image,rendered)

def main():
    need(len(sys.argv)==2 and sys.argv[1] in ("--self-test","--run"),"MODE_REQUIRED")
    if sys.argv[1]=="--self-test":
        r=unittest.TextTestRunner(verbosity=1).run(
             unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
        return 0 if r.wasSuccessful() else 1
    print(json.dumps(collect(),sort_keys=True));return 0

if __name__=="__main__":
    try:sys.exit(main())
    except Stop as e:
        print(json.dumps({"result":"STOP","reason":str(e),"production_changes":"NONE",
                          "release_gate":"HOLD"}));sys.exit(3)
    except Exception as e:
        print(json.dumps({"result":"STOP","reason":"REDACTED_"+type(e).__name__,
                          "production_changes":"NONE","release_gate":"HOLD"}));sys.exit(3)
