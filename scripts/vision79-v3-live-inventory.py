#!/usr/bin/env python3
"""Read-only Vision79 v3 production inventory. No deployment capability.

--self-test uses synthetic metadata; --run permits inspection only on v79sl.
Config.Env, raw labels, host mount sources, command arguments and health logs
are never emitted. This inventory is not a sealed runtime/rollback plan.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

APPROVED_VISUAL_SOURCE = "114841271d4f8b9c4b63df6aedfd55bde2e82f40"
SERVICES = ("v79-hub", "v79-hub-postgres", "v79-tiquet-manager", "tiquet-postgres", "v79-business-agent")
TIMERS = ("v79-g2-approved-task-worker.timer", "v79-workforce-evening.timer", "v79-workforce-morning.timer")
HEX = re.compile(r"^sha256:[0-9a-f]{64}$")
class Stop(Exception): pass

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def invoke(args):
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("READ_ONLY_COMMAND_UNAVAILABLE_OR_TIMEOUT") from None
    if len(result.stdout) > 16 * 1024 * 1024:
        raise Stop("INSPECT_RESPONSE_TOO_LARGE")
    return result

def inspect(kind, name):
    result = invoke(["docker", "inspect", "--type", kind, name])
    if result.returncode:
        raise Stop("DOCKER_INSPECTION_UNAVAILABLE")
    try: rows = json.loads(result.stdout)
    except (ValueError, TypeError): raise Stop("INSPECT_JSON_INVALID") from None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise Stop("INSPECT_SHAPE_INVALID")
    return rows[0]

def safe_service(meta, image):
    cfg, state = meta.get("Config") or {}, meta.get("State") or {}
    labels = cfg.get("Labels") or {}
    image_id = meta.get("Image")
    if not isinstance(image_id, str) or not HEX.fullmatch(image_id) or image.get("Id") != image_id:
        raise Stop("IMAGE_IDENTITY_INVALID")
    container_id = meta.get("Id", "")
    if not re.fullmatch(r"[0-9a-f]{64}", container_id): raise Stop("CONTAINER_IDENTITY_INVALID")
    # An inventory of nonsecret shape only. Do NOT claim full runtime parity.
    shape = {
        "network_mode": (meta.get("HostConfig") or {}).get("NetworkMode"),
        "restart_policy": (meta.get("HostConfig") or {}).get("RestartPolicy"),
        "port_bindings": (meta.get("HostConfig") or {}).get("PortBindings"),
        "read_only_rootfs": (meta.get("HostConfig") or {}).get("ReadonlyRootfs"),
        "mount_destinations": sorted(({"destination": m.get("Destination"), "type": m.get("Type"), "writable": m.get("RW")} for m in meta.get("Mounts") or []), key=lambda m:str(m["destination"])),
        "network_names": sorted((meta.get("NetworkSettings") or {}).get("Networks") or {}),
    }
    compose = labels.get("com.docker.compose.project.config_files") or ""
    revision = ((image.get("Config") or {}).get("Labels") or {}).get("org.opencontainers.image.revision", "")
    revision = revision if isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision) else "UNKNOWN"
    return {
        "container_id": container_id, "image_id": image_id,
        "image_revision_label": revision,
        "status": state.get("Status", "unknown"), "health": (state.get("Health") or {}).get("Status", "not_configured"),
        "restart_count": meta.get("RestartCount"),
        "compose_file_count": len(compose.split(",")) if compose else 0,
        "compose_stack_label_sha256": fingerprint(compose),
        "nonsecret_runtime_shape_sha256": fingerprint(shape),
        "mount_destinations": shape["mount_destinations"], "network_names": shape["network_names"],
        "private_full_runtime_comparison_required": True,
    }

def collect():
    if socket.gethostname().split(".")[0] != "v79sl": raise Stop("WRONG_HOST_NO_INSPECTION_PERFORMED")
    if os.getenv("DOCKER_HOST") or os.getenv("DOCKER_CONTEXT"): raise Stop("DOCKER_OVERRIDE_REFUSED")
    services, images = {}, {}
    for name in SERVICES:
        meta = inspect("container", name)
        image_id = meta.get("Image")
        if not isinstance(image_id, str) or not HEX.fullmatch(image_id): raise Stop("IMAGE_IDENTITY_INVALID")
        if image_id not in images: images[image_id] = inspect("image", image_id)
        services[name] = safe_service(meta, images[image_id])
    timers = {}
    for name in TIMERS:
        result = invoke(["systemctl", "is-active", name])
        value = result.stdout.decode("utf-8", errors="replace").strip()
        timers[name] = value if value in {"active", "inactive", "failed", "activating", "deactivating", "unknown"} else "unverified"
    return {
        "schema": "vision79-v3-readonly-inventory", "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "approved_visual_source": APPROVED_VISUAL_SOURCE, "owner_visual_approval": "APPROVED",
        "services": services, "workforce_timer_states": timers,
        "running_services_observed": all(s["status"] == "running" for s in services.values()),
        "production_changes": "NONE", "release_gate": "HOLD_PENDING_RELEASE_EVIDENCE",
        "candidate_image_built": False, "checkpoint_verified": False, "real_mfa_sso_verified": False,
        "required_next": ["review current identity and private full runtime parity", "fresh encrypted offhost checkpoint", "build immutable Hub candidate from clean Git source", "isolated boot and rollback rehearsal", "real private-session MFA and Hub-to-Tiquet SSO acceptance", "seal guarded Hub-only cutover and rollback"],
    }

class SafetyTests(unittest.TestCase):
    def fixture(self):
        image_id = "sha256:" + "b" * 64
        meta = {"Id":"a"*64,"Image":image_id,"Config":{"Env":["SECRET=do-not-disclose"],"Cmd":["private-argument"],"Labels":{"secret-label":"private-label","com.docker.compose.project.config_files":"/private/one.yml,/private/two.yml"}},"State":{"Status":"running","Health":{"Status":"healthy","Log":[{"Output":"private-health-log"}]}},"HostConfig":{"Binds":["/secret-source:/app/data"]},"Mounts":[{"Source":"/secret-source","Destination":"/app/data","Type":"bind","RW":True}],"NetworkSettings":{"Networks":{"proxy_network":{}}}}
        return meta,{"Id":image_id,"Config":{"Env":["SECRET=hidden-image"],"Labels":{}}}
    def test_no_private_values_in_output(self):
        out=json.dumps(safe_service(*self.fixture()))
        for secret in ["do-not-disclose","private-argument","private-label","private-health-log","secret-source","hidden-image","/private/one.yml"]: self.assertNotIn(secret,out)
        self.assertIn('"private_full_runtime_comparison_required": true',out)
    def test_image_mismatch_rejected(self):
        meta,image=self.fixture();image['Id']='sha256:'+'c'*64
        with self.assertRaises(Stop): safe_service(meta,image)
    def test_wrong_host_makes_no_commands(self):
        with patch('socket.gethostname',return_value='other'),patch(__name__+'.invoke') as call:
            with self.assertRaises(Stop): collect()
            call.assert_not_called()
    def test_override_makes_no_commands(self):
        with patch('socket.gethostname',return_value='v79sl'),patch.dict(os.environ,{'DOCKER_HOST':'tcp://other'}),patch(__name__+'.invoke') as call:
            with self.assertRaises(Stop): collect()
            call.assert_not_called()
    def test_only_readonly_commands_and_no_release_claim(self):
        meta,image=self.fixture();seen=[]
        def fake(args):
            seen.append(args)
            if args[:3]==['docker','inspect','--type']:
                return subprocess.CompletedProcess(args,0,json.dumps([meta if args[3]=='container' else image]).encode())
            if args[:2]==['systemctl','is-active']: return subprocess.CompletedProcess(args,0,b'active\n')
            raise AssertionError('Unexpected command '+repr(args))
        with patch('socket.gethostname',return_value='v79sl'),patch.dict(os.environ,{'DOCKER_HOST':'','DOCKER_CONTEXT':''}),patch(__name__+'.invoke',side_effect=fake): result=collect()
        self.assertEqual(result['production_changes'],'NONE');self.assertFalse(result['candidate_image_built']);self.assertEqual(len(result['services']),5)
        self.assertEqual(sum(c[:2]==['systemctl','is-active'] for c in seen),3)

def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--self-test',action='store_true');group.add_argument('--run',action='store_true');args=parser.parse_args()
    if args.self_test:
        result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(SafetyTests))
        if result.wasSuccessful(): print('READ_ONLY_PREFLIGHT_SELF_TEST=PASS_5')
        return 0 if result.wasSuccessful() else 1
    try:
        print(json.dumps(collect(),indent=2,sort_keys=True));return 0
    except Stop as exc:
        print(json.dumps({'production_changes':'NONE','release_gate':'HOLD','reason':str(exc)}));return 3
    except Exception:
        print(json.dumps({'production_changes':'NONE','release_gate':'HOLD','reason':'READ_ONLY_INVENTORY_FAILED_REDACTED'}));return 3
if __name__=='__main__': sys.exit(main())
