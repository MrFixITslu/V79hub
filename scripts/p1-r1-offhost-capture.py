#!/usr/bin/env python3
"""V79 P1-R1 encrypted off-host capture, initiated ONLY on the Acer laptop.

--plan: read-only inventory, no output files.
--capture --approve-live-reads: streamed production READS, Acer-only encrypted writes.
--verify DIR: decrypt to validators over pipes, never to disk; no production access.
Neither operation is a full-app restore or independent release signoff.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile

HOST = "firelion@v79sl"
RECIPIENT = "484CF39CE37A02884497AD9C41A17102D2842ECE"
HUB = "sha256:d0dfba263dbfec8a08e6c46995c2172daf234206fe8d0f6484bb98b938cd3c65"
TIQUET = "sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42"
HUB_PG = "sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24"
TIQUET_PG = "sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685"
ROLLBACK_HUB = "sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698"
IMAGE_IDS = {"v79-hub": HUB, "v79-tiquet-manager": TIQUET,
             "v79-hub-postgres": HUB_PG, "tiquet-postgres": TIQUET_PG}
SOURCE_REVISION = "ui-overlay-b1c2a24e903509d4037d0166bc31813fcf25e228"
HUB_COMPOSE_HASHES = (
    "186175ec20d10f817a9468b305fed86a6b0b4ae7cd380659e574df95ef688261",
    "8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74",
    "fddb7d2a6934dfa65a5ce05358ca71a6769eebdff8c7def760eb070adac2b4c5",
    "44e177b5c5cd8138ea42139bd6cbd5d82452a2a83585db88ef4f50e74519bd34",
    "51cb2fb1629f1900a363aed090a1066d27f1ed2b97a63372b951d85bcd07591f",
    None,  # Source v3 printed only 63 hex chars for layer 6: require fresh read-only re-pin.
    "c532df563e257d2077705d48b39f0071d5fed88fcb2e9ca2874c46cba4b125c5",
    "108845250715cfb91c8db538cfafc34e189ff938fc0a56a4cbb724e8f883f168",
    "50e68e1f530e3cfac48111d2947e4ce2059e4795a4bfcd2388efd4e668d8020a",
    "d79b99f9b0c9d7e4cd88d49bdddf37a9e841f69f398590a0b8529b8143fdb48c",
    "fad2932985052a31d8ecfc9a9ba64575f5835917766515e434e25814f83dc133",
    "31f94cb30d6ce0b6be4df7d02baf0616f09c8e728eec7021b8d44671eac95e79",
    "8eda5018b4fcb591640492f6c44f8d63c446cff6ffa61aac985de19277933ff8",
)
VALID_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
# The only reviewed Hub secret-file bind destinations from its base Compose.
# No wildcard /run/secrets allowlisting.
HUB_SECRET_DESTINATIONS = (
    "/run/secrets/v79-agent-token",
    "/run/secrets/v79-workforce-token",
    "/run/secrets/v79-readonly-platform-token",
    "/run/secrets/v79-coo-github-token",
)
# The report volume is a known read-only directory, not a token file.
HUB_REPORT_DESTINATIONS = (
    "/run/v79-workforce-reports",
)

# Passed to python3 -B - over SSH STDIN. No shell-interpreted source or secrets.
REMOTE_PROBE = r'''
import hashlib,json,os,pathlib,re,stat,subprocess,sys
pins=json.loads(sys.argv[1])
images=pins["images"]
def call(*cmd):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=35)
 if p.returncode:raise RuntimeError("DOCKER_READ_FAILED")
 return json.loads(p.stdout)
def inspect(names):
 rows=call("docker","inspect",*names)
 out={str(r.get("Name","")).removeprefix("/"):r for r in rows}
 if set(out)!=set(names):raise RuntimeError("CONTAINER_SET_CHANGED")
 for name in names:
  r=out[name]
  if r.get("Image")!=images[name] or r.get("State",{}).get("Status")!="running" or r.get("State",{}).get("Health",{}).get("Status")!="healthy":
   raise RuntimeError("PIN_OR_HEALTH_CHANGED")
 return out
def flags(env):
 d={}
 for v in env:
  k,_,value=v.partition("=")
  if k in ("V79_REQUIRE_ADMIN_MFA","V79_ENTITLEMENT_RECHECK_ENABLED","V79_ALLOW_LEGACY_AUTH"):d[k]=value
 return d
def secure_file(p):
 if not p.startswith("/") or "\n" in p or "\r" in p or ".." in pathlib.PurePath(p).parts:raise RuntimeError("BAD_CONFIG_PATH")
 path=pathlib.Path(p)
 if path.is_symlink():raise RuntimeError("CONFIG_SYMLINK")
 st=path.stat()
 if not stat.S_ISREG(st.st_mode) or st.st_size>2097152:raise RuntimeError("CONFIG_FILE_UNSAFE")
 return hashlib.sha256(path.read_bytes()).hexdigest()
def configs(container):
 labels=container.get("Config",{}).get("Labels") or {}
 csv=labels.get("com.docker.compose.project.config_files") or ""
 paths=csv.split(",") if csv else []
 if not paths or len(paths)>40 or len(paths)!=len(set(paths)):raise RuntimeError("COMPOSE_CHAIN_INVALID")
 working=labels.get("com.docker.compose.project.working_dir") or ""
 if not working.startswith("/") or ".." in pathlib.PurePath(working).parts:raise RuntimeError("WORKING_DIR_INVALID")
 env=working.rstrip("/")+"/.env"
 if not os.path.isfile(env):raise RuntimeError("DEPLOY_ENV_FILE_MISSING")
 files=paths+[env]
 digests=[secure_file(p) for p in files]
 return {"files":files,"digests":digests,"composeCount":len(paths)}
def mounts(container,name):
 out=[]
 reviewed_hub_secrets=(
  "/run/secrets/v79-agent-token",
  "/run/secrets/v79-workforce-token",
  "/run/secrets/v79-readonly-platform-token",
  "/run/secrets/v79-coo-github-token",
 )
 reviewed_hub_reports=("/run/v79-workforce-reports",)
 for m in container.get("Mounts",[]):
  target=m.get("Destination")
  if m.get("Type") not in ("bind","volume") or not isinstance(target,str) or any(z in target for z in ("\n","\r")) or ".." in pathlib.PurePath(target).parts or target.endswith("/"):
   raise RuntimeError("UNREVIEWED_APP_MOUNT")
  if target.startswith("/app/"):
   pass
  elif name=="v79-hub" and target in (*reviewed_hub_secrets,*reviewed_hub_reports) and m.get("Type")=="bind" and m.get("RW") is False:
   pass
  else:raise RuntimeError("UNREVIEWED_APP_MOUNT")
  if target in out:raise RuntimeError("DUPLICATE_MOUNT_TARGET")
  out.append(target)
 if "/app/data" not in out or (name=="v79-tiquet-manager" and "/app/uploads" not in out):
  raise RuntimeError("REQUIRED_APP_MOUNT_MISSING")
 if len(out)>20:raise RuntimeError("TOO_MANY_MOUNTS")
 return out
def checked_mount_content(container,targets):
 # Metadata-only read through existing container; no token content is shown,
 # read, copied, or written to disk by --plan.
 for dest in targets:
  if dest in ("/run/secrets/v79-agent-token",
              "/run/secrets/v79-workforce-token",
              "/run/secrets/v79-readonly-platform-token",
              "/run/secrets/v79-coo-github-token"):
   checker='test -f "$1" && test ! -L "$1" && test -r "$1"'
   reason="REVIEWED_TOKEN_FILE_UNAVAILABLE"
  elif dest=="/run/v79-workforce-reports":
   checker='test -d "$1" && test ! -L "$1" && test -r "$1"'
   reason="REVIEWED_REPORT_DIRECTORY_UNAVAILABLE"
  else:continue
  p=subprocess.run(["docker","exec","-u","0",container,"sh","-c",
                    checker,"p1-r1-filetype-check",dest],
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                   timeout=20)
  if p.returncode:raise RuntimeError(reason)
try:
 if os.uname().nodename!="v79sl":raise RuntimeError("WRONG_REMOTE_HOST")
 core=inspect(list(images))
 hub=core["v79-hub"];tiquet=core["v79-tiquet-manager"]
 hf=flags(hub.get("Config",{}).get("Env") or [])
 tf=flags(tiquet.get("Config",{}).get("Env") or [])
 if hf.get("V79_REQUIRE_ADMIN_MFA") not in ("1","true"):raise RuntimeError("MFA_MISSING")
 if tf.get("V79_ENTITLEMENT_RECHECK_ENABLED")!="1" or tf.get("V79_ALLOW_LEGACY_AUTH")!="0":raise RuntimeError("TIQUET_SECURITY_CHANGED")
 hub_config=configs(hub)
 tiquet_config=configs(tiquet)
 if len(hub_config["digests"][:-1])!=13 or any(old is not None and got!=old for got,old in zip(hub_config["digests"][:-1],pins["hub_composes"])):raise RuntimeError("HUB_COMPOSE_DRIFT")
 rev=call("docker","image","inspect",images["v79-hub"])[0].get("Config",{}).get("Labels",{}).get("org.opencontainers.image.revision")
 if rev!=pins["revision"]:raise RuntimeError("HUB_SOURCE_LABEL_DRIFT")
 for ident in [*images.values(),pins["rollback"]]:
  info=call("docker","image","inspect",ident)
  if len(info)!=1 or info[0].get("Id")!=ident:raise RuntimeError("IMAGE_ARCHIVE_SOURCE_MISSING")
 hub_mounts=mounts(hub,"v79-hub")
 tiquet_mounts=mounts(tiquet,"v79-tiquet-manager")
 checked_mount_content("v79-hub",hub_mounts)
 result={
  "images":images,
  "rollback":pins["rollback"],
  "sourceRevision":rev,
  "configs":{"hub":hub_config,"tiquet":tiquet_config},
  "mounts":{"v79-hub":hub_mounts,"v79-tiquet-manager":tiquet_mounts}
 }
 print(json.dumps(result,separators=(",",":"),sort_keys=True))
except Exception as e:
 msg=str(e)
 print("STOP="+msg if re.fullmatch(r"[A-Z0-9_]+",msg) else "STOP=REMOTE_PREFLIGHT_FAILED",file=sys.stderr)
 sys.exit(1)
'''


class Abort(Exception):
    pass


def require(statement, reason):
    if not statement:
        raise Abort(reason)


def local_safe():
    require(socket.gethostname() != "v79sl", "RUN_ONLY_ON_ACER")
    for tool in ("ssh", "gpg", "tar", "pg_restore", "python3"):
        require(shutil.which(tool), "LOCAL_TOOL_MISSING")
    require(os.getuid() != 0, "REFUSE_ROOT_LAPTOP_EXECUTION")


def ssh_command(args):
    return ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=12", HOST, shlex.join(args)]


def pins():
    return {"images": IMAGE_IDS, "rollback": ROLLBACK_HUB,
            "hub_composes": list(HUB_COMPOSE_HASHES), "revision": SOURCE_REVISION}


def probe():
    arg = json.dumps(pins(), separators=(",", ":"))
    p = subprocess.run(ssh_command(["python3", "-B", "-", arg]), input=REMOTE_PROBE.encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=100)
    if p.returncode:
        safe_codes = re.findall(r"STOP=([A-Z0-9_]+)", p.stderr.decode("utf-8", "replace")[:2048])
        raise Abort("REMOTE_" + safe_codes[-1] if safe_codes else "REMOTE_PLAN_UNAVAILABLE_OR_DRIFT")
    try:
        result = json.loads(p.stdout)
    except ValueError:
        raise Abort("REMOTE_PLAN_INVALID") from None
    validate_plan(result)
    return result


def validate_plan(data):
    require(isinstance(data, dict) and data.get("images") == IMAGE_IDS, "LIVE_IMAGE_MISMATCH")
    require(data.get("rollback") == ROLLBACK_HUB and data.get("sourceRevision") == SOURCE_REVISION,
            "LIVE_RELEASE_DRIFT")
    require(isinstance(data.get("configs"), dict) and set(data["configs"]) == {"hub", "tiquet"},
            "CONFIG_PLAN_INCOMPLETE")
    for name in ("hub", "tiquet"):
        c = data["configs"][name]
        require(isinstance(c.get("files"), list) and isinstance(c.get("digests"), list)
                and len(c["files"]) == len(c["digests"])
                and c.get("composeCount") == len(c["files"]) - 1
                and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in c["digests"]),
                "CONFIG_PLAN_INVALID")
    require(len(data["configs"]["hub"]["digests"][:-1]) == 13 and
            all(expected is None or actual == expected for actual, expected in
                zip(data["configs"]["hub"]["digests"][:-1], HUB_COMPOSE_HASHES)),
            "HUB_COMPOSE_BASELINE_MISMATCH")
    require(data["configs"]["hub"]["composeCount"] == 13, "HUB_COMPOSE_COUNT_MISMATCH")
    mounts = data.get("mounts")
    require(isinstance(mounts, dict) and set(mounts) == {"v79-hub", "v79-tiquet-manager"},
            "APP_MOUNT_PLAN_INCOMPLETE")
    for name, targets in mounts.items():
        require(isinstance(targets, list) and "/app/data" in targets and
                (name != "v79-tiquet-manager" or "/app/uploads" in targets) and
                len(set(targets)) == len(targets) and len(targets) <= 20 and
                all(isinstance(v, str) and
                    (v.startswith("/app/") or
                     (name == "v79-hub" and
                      v in (*HUB_SECRET_DESTINATIONS, *HUB_REPORT_DESTINATIONS))) and
                    not v.endswith("/") and ".." not in Path(v).parts and
                    "\n" not in v and "\r" not in v for v in targets),
                "APP_MOUNT_PLAN_INVALID")


def streams_for(plan):
    streams = [
        ("hub-pg.dump.gpg", ["docker", "exec", "v79-hub-postgres", "sh", "-c",
                             'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'], "pg"),
        ("tiquet-pg.dump.gpg", ["docker", "exec", "tiquet-postgres", "sh", "-c",
                                'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'], "pg"),
    ]
    for alias in ("hub", "tiquet"):
        c = plan["configs"][alias]
        rel = [v.lstrip("/") for v in c["files"]]
        streams.append((alias + "-config.tar.gpg",
                        ["tar", "-C", "/", "-czf", "-", "--", *rel], "tgz"))
    for container, mounts in plan["mounts"].items():
        alias = "hub" if container == "v79-hub" else "tiquet"
        for index, destination in enumerate(mounts, 1):
            # Known Hub token file mounts only: require a regular file, not
            # a symlink or placeholder device. Stream straight into Acer GPG.
            if destination in HUB_SECRET_DESTINATIONS:
                require(container == "v79-hub", "SECRET_MOUNT_ASSIGNED_TO_WRONG_APP")
                reader = ["docker", "exec", "-u", "0", container, "sh", "-c",
                          'test -f "$1" && test ! -L "$1" && exec tar -C / -czf - -- "$2"',
                          "v79-read-only-secret", destination, destination.lstrip("/")]
            elif destination in HUB_REPORT_DESTINATIONS:
                require(container == "v79-hub", "REPORTS_MOUNT_ASSIGNED_TO_WRONG_APP")
                # A directory must remain a directory. Do not capture a
                # replaced symlink or a misconfigured sensitive file.
                reader = ["docker", "exec", "-u", "0", container, "sh", "-c",
                          'test -d "$1" && test ! -L "$1" && exec tar -C / -czf - -- "$2"',
                          "v79-read-only-report", destination, destination.lstrip("/")]
            else:
                reader = ["docker", "exec", "-u", "0", container, "tar", "-C", "/", "-czf",
                          "-", "--", destination.lstrip("/")]
            streams.append(("%s-mount-%02d.tar.gpg" % (alias, index), reader, "tgz"))
    streams.extend([
        ("runtime-inspect.json.gpg", ["docker", "inspect", *IMAGE_IDS], "json"),
        ("exact-images-and-rollback.tar.gpg",
         ["docker", "image", "save", *IMAGE_IDS.values(), ROLLBACK_HUB], "tar")
    ])
    require(len({x[0] for x in streams}) == len(streams), "DUPLICATE_STREAM_NAME")
    return streams


def key_ready():
    for opt in ("--list-keys", "--list-secret-keys"):
        p = subprocess.run(["gpg", "--batch", opt, RECIPIENT],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        require(p.returncode == 0, "OFFHOST_GPG_KEY_NOT_READY")


def safe_base(base):
    base = Path(base).expanduser().absolute()
    require(not base.is_symlink(), "OFFHOST_DIRECTORY_SYMLINK")
    if not base.exists():
        base.mkdir(mode=0o700, parents=False)
    st = base.stat()
    require(base.is_dir() and st.st_uid == os.getuid() and st.st_mode & 0o077 == 0,
            "OFFHOST_DIRECTORY_PERMISSIONS")
    require(shutil.disk_usage(base).free >= 8 * 1024**3, "OFFHOST_DISK_SPACE_TOO_LOW")
    return base


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_private_json(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(value, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")


def encrypt_stream(command, output):
    part = output.with_suffix(output.suffix + ".partial")
    # Never pipe raw plaintext into a file, terminal, shell trace, or logging.
    remote = subprocess.Popen(ssh_command(command), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        encrypted = subprocess.Popen(
            ["gpg", "--batch", "--yes", "--quiet", "--trust-model", "always",
             "--encrypt", "--recipient", RECIPIENT, "--output", str(part)],
            stdin=remote.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        remote.stdout.close()
        try:
            encrypted_rc = encrypted.wait(timeout=1800)
            remote_rc = remote.wait(timeout=30)
        except subprocess.TimeoutExpired:
            encrypted.kill()
            remote.kill()
            encrypted.wait()
            remote.wait()
            raise Abort("BACKUP_STREAM_TIMEOUT") from None
        require(remote_rc == 0 and encrypted_rc == 0 and part.is_file() and
                part.stat().st_size > 100, "BACKUP_STREAM_INCOMPLETE")
        part.rename(output)
    finally:
        if remote.poll() is None:
            remote.kill()
            remote.wait()


def verify_one(path, kind):
    decrypt = subprocess.Popen(["gpg", "--batch", "--quiet", "--decrypt", str(path)],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    validator = {
        "pg": ["pg_restore", "--list"],
        "tgz": ["tar", "-tzf", "-"],
        "tar": ["tar", "-tf", "-"],
        "json": ["python3", "-c",
                 "import json,sys; d=json.load(sys.stdin); assert isinstance(d,list) and len(d)==4"]
    }[kind]
    try:
        check = subprocess.Popen(validator, stdin=decrypt.stdout, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        decrypt.stdout.close()
        try:
            result = check.wait(timeout=1800)
            decrypted = decrypt.wait(timeout=30)
        except subprocess.TimeoutExpired:
            check.kill()
            decrypt.kill()
            check.wait()
            decrypt.wait()
            raise Abort("DECRYPT_OR_VALIDATOR_TIMEOUT") from None
        require(result == 0 and decrypted == 0, "ENCRYPTED_ARCHIVE_VALIDATION_FAILED")
    finally:
        if decrypt.poll() is None:
            decrypt.kill()
            decrypt.wait()


def verify_set(root):
    root = Path(root).expanduser().absolute()
    require(root.is_dir() and not root.is_symlink() and root.stat().st_mode & 0o077 == 0,
            "OFFHOST_SET_PERMISSIONS")
    marker = root / "CAPTURE_INCOMPLETE"
    require(not marker.exists(), "CAPTURE_MARKED_INCOMPLETE")
    receipt = root / "ciphertext-manifest.json"
    require(receipt.is_file() and not receipt.is_symlink(), "MANIFEST_MISSING")
    data = json.loads(receipt.read_text())
    require(data.get("schema") == 1 and data.get("images") == IMAGE_IDS and
            data.get("status") == "CAPTURED_NOT_RESTORED" and
            isinstance(data.get("files"), list) and len(data["files"]) >= 6,
            "MANIFEST_INVALID")
    names = set()
    expected_names = {
        "hub-pg.dump.gpg": "pg",
        "tiquet-pg.dump.gpg": "pg",
        "hub-config.tar.gpg": "tgz",
        "tiquet-config.tar.gpg": "tgz",
        "runtime-inspect.json.gpg": "json",
        "exact-images-and-rollback.tar.gpg": "tar",
    }
    mounts = data.get("appMountDestinations")
    require(isinstance(mounts, dict) and set(mounts) == {"v79-hub", "v79-tiquet-manager"},
            "MANIFEST_MOUNT_INVENTORY_MISSING")
    for container, destinations in mounts.items():
        require(isinstance(destinations, list) and len(destinations) <= 20
                and len(destinations) == len(set(destinations))
                and "/app/data" in destinations
                and (container != "v79-tiquet-manager" or "/app/uploads" in destinations)
                and all(isinstance(v, str) and
                        (v.startswith("/app/") or
                         (container == "v79-hub" and
                          v in (*HUB_SECRET_DESTINATIONS, *HUB_REPORT_DESTINATIONS))) and
                        not v.endswith("/") and ".." not in Path(v).parts and
                        "\n" not in v and "\r" not in v for v in destinations),
                "MANIFEST_APP_MOUNT_SET_INVALID")
        prefix = "hub" if container == "v79-hub" else "tiquet"
        for index, _ in enumerate(destinations, 1):
            expected_names[prefix + "-mount-%02d.tar.gpg" % index] = "tgz"
    require(len(data["files"]) == len(expected_names), "MANIFEST_COMPONENT_COUNT_MISMATCH")
    for entry in data["files"]:
        name, kind = entry.get("name"), entry.get("type")
        require(isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*\.(?:dump|tar|json)\.gpg", name)
                and name not in names and kind in ("pg", "tgz", "tar", "json"),
                "MANIFEST_ENTRY_INVALID")
        require(expected_names.get(name) == kind, "MANIFEST_UNEXPECTED_OR_WRONG_COMPONENT_TYPE")
        names.add(name)
        path = root / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_mode & 0o077 == 0
                and path.stat().st_size == entry.get("bytes") and sha_file(path) == entry.get("sha256"),
                "ENCRYPTED_CIPHERTEXT_HASH_MISMATCH")
        verify_one(path, kind)
    require(names == set(expected_names), "MANIFEST_REQUIRED_COMPONENT_MISSING")
    print("OFFHOST_CIPHERTEXT_SHA_AND_DECRYPT_STRUCTURE=PASS")
    print("VERIFIED_STREAMS=" + str(len(names)))
    print("CURRENT_FULL_APP_RESTORE=NOT_PERFORMED")
    print("RELEASE_GATE=NO_GO")


def run_capture(plan, base):
    key_ready()
    base = safe_base(base)
    stream_list = streams_for(plan)
    root = Path(tempfile.mkdtemp(prefix="p1-r1-current-release-", dir=base))
    os.chmod(root, 0o700)
    marker = root / "CAPTURE_INCOMPLETE"
    with os.fdopen(os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        f.write("Never use for release until all source and ciphertext checks finish.\n")
    print("ACER_RECOVERY_SET=" + str(root), flush=True)
    files = []
    try:
        for i, (name, cmd, kind) in enumerate(stream_list, 1):
            require(re.fullmatch(r"[a-z0-9][a-z0-9-]*\.(?:dump|tar|json)\.gpg", name), "BAD_STREAM_NAME")
            print("CAPTURE_STEP=%d/%d %s" % (i, len(stream_list), name), flush=True)
            outfile = root / name
            encrypt_stream(cmd, outfile)
            files.append({"name": name, "type": kind, "bytes": outfile.stat().st_size,
                          "sha256": sha_file(outfile)})
        after = probe()
        require(after == plan, "LIVE_RUNTIME_OR_CONFIGURATION_CHANGED_DURING_BACKUP")
        manifest = {"schema": 1, "status": "CAPTURED_NOT_RESTORED", "images": IMAGE_IDS,
                    "rollbackHub": ROLLBACK_HUB, "sourceRevision": SOURCE_REVISION,
                    "hubComposeSHA256Ordered": plan["configs"]["hub"]["digests"][:-1],
                    "tiquetComposeSHA256Ordered": plan["configs"]["tiquet"]["digests"][:-1],
                    "appMountDestinations": plan["mounts"], "files": files,
                    "fullAppRestoreVerified": False, "customerBetaAuthorized": False}
        write_private_json(root / "ciphertext-manifest.json", manifest)
        marker.unlink()
        print("ENCRYPTED_OFFHOST_CAPTURE=PASS_STREAMS_ONLY")
        print("STREAM_COUNT=" + str(len(files)))
        print("DECRYPT_STRUCTURE_VALIDATION=NOT_YET_RUN")
        print("ISOLATED_RESTORE=NOT_PERFORMED")
        print("RELEASE_GATE=NO_GO")
    except Exception:
        print("BACKUP=INCOMPLETE_DO_NOT_USE_FOR_RELEASE")
        print("INCOMPLETE_SET_PRESERVED=" + str(root))
        raise


def self_test():
    require(len(HUB_COMPOSE_HASHES) == 13 and HUB_COMPOSE_HASHES[5] is None and
            all(x is None or re.fullmatch(r"[0-9a-f]{64}", x) for x in HUB_COMPOSE_HASHES),
            "BROKEN_HASH_BASELINE")
    assert all(VALID_SHA.fullmatch(v) for v in (*IMAGE_IDS.values(), ROLLBACK_HUB))
    dummy = {"images": IMAGE_IDS, "rollback": ROLLBACK_HUB,
             "sourceRevision": SOURCE_REVISION,
             "configs": {
                 "hub": {"files": ["/opt/v79/hub/x" + str(i) for i in range(13)] +
                         ["/opt/v79/hub/.env"],
                         "digests": [x if x is not None else "e" * 64 for x in HUB_COMPOSE_HASHES] + ["a" * 64], "composeCount": 13},
                 "tiquet": {"files": ["/opt/tiquet/docker-compose.yml", "/opt/tiquet/.env"],
                            "digests": ["b" * 64, "c" * 64], "composeCount": 1}},
             "mounts": {"v79-hub": ["/app/data"], "v79-tiquet-manager": ["/app/data", "/app/uploads"]}}
    validate_plan(dummy)
    assert len(streams_for(dummy)) == 9
    for mutation in (
        lambda d: d["images"].update({"v79-hub": ROLLBACK_HUB}),
        lambda d: d["configs"]["hub"]["digests"].__setitem__(0, "f" * 64),
        lambda d: d["mounts"]["v79-tiquet-manager"].remove("/app/uploads"),
        lambda d: d["configs"]["tiquet"]["digests"].pop(),
    ):
        sample = json.loads(json.dumps(dummy))
        mutation(sample)
        try:
            validate_plan(sample)
        except Abort:
            continue
        raise AssertionError("Expected fail closed")
    print("SELF_TEST=PASS_CURRENT_PINS_CONFIG_MOUNTS_STREAM_PLAN_NEGATIVES")


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    action = arg.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan", action="store_true")
    action.add_argument("--capture", action="store_true")
    action.add_argument("--verify", metavar="DIR")
    action.add_argument("--self-test", action="store_true")
    arg.add_argument("--approve-live-reads", action="store_true")
    arg.add_argument("--accept-layer-6-sha", default=None,
                     help="The 64-digit SHA256 from read-only --plan, reviewed by the owner")
    arg.add_argument("--offhost-parent", default=str(Path.home() / "V79-P1-R1-Offhost"))
    args = arg.parse_args()
    os.umask(0o077)
    if args.self_test:
        self_test()
        return
    local_safe()
    if args.verify:
        verify_set(args.verify)
        return
    p = probe()
    streams = streams_for(p)
    print("LIVE_PIN_AND_SECURITY=PASS")
    print("HUB_COMPOSE_LAYERS=12_PINNED_1_NEEDS_REPIN")
    print("HUB_COMPOSE_LAYER_6_SHA256=" + p["configs"]["hub"]["digests"][5])
    print("TIQUET_COMPOSE_LAYERS=" + str(p["configs"]["tiquet"]["composeCount"]))
    print("APP_MOUNT_STREAMS=" + str(sum(map(len, p["mounts"].values()))))
    print("PLANNED_ENCRYPTED_STREAMS=" + str(len(streams)))
    print("SOURCE_IMAGE_CHANGE=NONE")
    if args.plan:
        print("MODE=READ_ONLY_PLAN_NO_BACKUPS_CREATED")
        return
    require(args.approve_live_reads, "EXPLICIT_LIVE_BACKUP_READ_APPROVAL_REQUIRED")
    require(isinstance(args.accept_layer_6_sha, str) and
            re.fullmatch(r"[0-9a-f]{64}", args.accept_layer_6_sha) and
            args.accept_layer_6_sha == p["configs"]["hub"]["digests"][5],
            "LAYER_6_SHA256_EXPLICIT_OWNER_REPIN_REQUIRED")
    run_capture(p, args.offhost_parent)


if __name__ == "__main__":
    try:
        main()
    except (Abort, OSError, subprocess.TimeoutExpired, ValueError) as e:
        print("STOP=" + (str(e) if isinstance(e, Abort) else "BACKUP_OPERATION_FAILED_REDACTED"))
        sys.exit(1)
