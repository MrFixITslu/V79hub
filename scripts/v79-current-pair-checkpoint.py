#!/usr/bin/env python3
"""Guarded encrypted pre-change Hub/Tiquet capture; no release or restore.

The result remains INCOMPLETE until independently copied off-host, decrypted,
and restored in isolation. Run only on v79sl with sudo as root.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

EXPECTED = {
    "v79-hub": "sha256:29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec",
    "v79-hub-postgres": "sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
    "v79-tiquet-manager": "sha256:b1ff48fcef3336ac6750dbdfae9df1aa85db0d3ed800804a88acc98519f1485f",
    "tiquet-postgres": "sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
}
REVISIONS = {"v79-hub": "2e5f872914bb85f98651ce00a4a90b1880e44076",
             "v79-tiquet-manager": "cf73528232fccea94871123c2dec92734889af6c"}
MOUNTS = {
    ("v79-hub", "/app/data"): "6664f5d75026",
    ("v79-hub-postgres", "/var/lib/postgresql/data"): "06b921af1ec3",
    ("v79-tiquet-manager", "/app/data"): "89181df90bf4",
    ("v79-tiquet-manager", "/app/uploads"): "0bc658f5bc36",
    ("tiquet-postgres", "/var/lib/postgresql/data"): "9863c4859258",
}
APPS = ("v79-hub", "v79-tiquet-manager")
DBS = ("v79-hub-postgres", "tiquet-postgres")
APP_MOUNT_SHAPE = {
    "v79-hub": {
        "/app/data": ("bind", True),
        "/run/v79-google": ("volume", False),
        "/run/v79-workforce-reports": ("bind", False),
        "/run/secrets/v79-agent-token": ("bind", False),
        "/run/secrets/v79-coo-github-token": ("bind", False),
        "/run/secrets/v79-readonly-platform-token": ("bind", False),
        "/run/secrets/v79-workforce-token": ("bind", False),
    },
    "v79-tiquet-manager": {
        "/app/data": ("volume", True), "/app/uploads": ("volume", True),
    },
}
HOME = Path("/home/firelion")
BASE = HOME / ".v79-current-pair-checkpoints"
KEY = HOME / ".v79-g12-recovery-public.asc"
OLD_MANIFEST = HOME / ".v79-release-checkpoints/release-20261026T102542Z-def4da1b/checkpoint/manifest.json"
RECIPIENT = "484CF39CE37A02884497AD9C41A17102D2842ECE"

class Stop(Exception): pass
def need(ok, reason):
    if not ok: raise Stop(reason)
def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""): h.update(block)
    return h.hexdigest()
def call(args, timeout=30):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired): raise Stop("COMMAND_UNAVAILABLE_OR_TIMEOUT") from None
    need(p.returncode == 0 and len(p.stdout) < 16_000_000, "COMMAND_FAILED")
    return p.stdout
def inspect(name):
    try: rows = json.loads(call(["docker", "inspect", "--type", "container", name]))
    except (ValueError, UnicodeError): raise Stop("DOCKER_INSPECT_INVALID") from None
    need(isinstance(rows, list) and len(rows) == 1, "DOCKER_INSPECT_SHAPE")
    return rows[0]
def preflight():
    need(socket.gethostname().split(".")[0] == "v79sl" and os.geteuid() == 0,
         "WRONG_HOST_OR_ROOT_USER")
    need(not os.getenv("DOCKER_HOST") and not os.getenv("DOCKER_CONTEXT"), "DOCKER_OVERRIDE")
    for binary in ("docker", "gpg", "tar", "systemd-run", "systemctl"):
        need(shutil.which(binary), "MISSING_" + binary.upper())
    records = {name: inspect(name) for name in EXPECTED}
    for name, row in records.items():
        state = row.get("State") or {}
        need(row.get("Image") == EXPECTED[name] and state.get("Status") == "running"
             and (state.get("Health") or {}).get("Status") == "healthy", "LIVE_DRIFT_" + name)
        need(re.fullmatch(r"[0-9a-f]{64}", row.get("Id", "")), "BAD_CONTAINER_ID")
        call(["docker", "image", "inspect", EXPECTED[name]])
        if name in REVISIONS:
            labels = (row.get("Config") or {}).get("Labels") or {}
            need(labels.get("org.opencontainers.image.revision") == REVISIONS[name],
                 "SOURCE_REVISION_DRIFT_" + name)
    for (name, dest), expected in MOUNTS.items():
        matches = [m for m in records[name].get("Mounts", []) if m.get("Destination") == dest]
        need(len(matches) == 1 and matches[0].get("RW") is True, "MOUNT_DRIFT")
        actual = hashlib.sha256(matches[0].get("Source", "").encode()).hexdigest()[:12]
        need(actual == expected, "MOUNT_SOURCE_DRIFT")
    for name in APPS:
        actual = {m.get("Destination"): (m.get("Type"), m.get("RW"))
                  for m in records[name].get("Mounts", [])}
        need(actual == APP_MOUNT_SHAPE[name] and
             len(records[name].get("Mounts", [])) == len(actual),
             "APP_MOUNT_SET_DRIFT_" + name)
    files = {}
    for name, row in records.items():
        labels = (row.get("Config") or {}).get("Labels") or {}
        raw = labels.get("com.docker.compose.project.config_files", "")
        need(raw, "COMPOSE_LABEL_MISSING")
        for value in raw.split(","):
            p = Path(value)
            need(p.is_absolute() and p.is_file() and not p.is_symlink()
                 and p.stat().st_size < 2_000_000, "COMPOSE_FILE_INVALID")
            files[str(p)] = digest(p)
        work = Path(labels.get("com.docker.compose.project.working_dir", ""))
        env = work / ".env"
        if work.is_absolute() and env.exists():
            need(env.is_file() and not env.is_symlink() and env.stat().st_size < 2_000_000,
                 "ENV_FILE_INVALID")
            files[str(env)] = digest(env)
    # Fail before pausing if any writable application mount cannot be archived safely.
    for app in APPS:
        for mount in records[app].get("Mounts") or []:
            if mount.get("RW"):
                host_app_archive_args(app, mount)
    need(KEY.is_file() and not KEY.is_symlink() and KEY.stat().st_size < 100_000,
         "PUBLIC_KEY_MISSING")
    need(OLD_MANIFEST.is_file(), "ACCEPTED_RECIPIENT_MANIFEST_MISSING")
    need(json.loads(OLD_MANIFEST.read_text()).get("recipient_fingerprint") == RECIPIENT,
         "RECIPIENT_DRIFT")
    need(shutil.disk_usage(HOME).free >= 20*1024**3, "INSUFFICIENT_DISK")
    call(["systemctl", "--system", "show", "--property=Version"])
    for db in DBS:
        call(["docker", "exec", db, "sh", "-ec",
              'pg_isready -q -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" && command -v pg_dump && command -v pg_dumpall && command -v pg_restore'])
        env = dict(v.split("=", 1) for v in records[db]["Config"]["Env"] if "=" in v)
        database = env.get("POSTGRES_DB") or "postgres"
        names = call(["docker", "exec", db, "sh", "-ec",
                      'exec psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" -Atqc "SELECT datname FROM pg_database WHERE datallowconn AND NOT datistemplate"']).decode().splitlines()
        need(bool(names) and set(names) <= {"postgres", database} and database in names,
             "EXTRA_OR_MISSING_DATABASE_" + db)
    return records, files

def host_app_archive_args(name, mount):
    """Archive only pinned writable application data from canonical host paths.

    Never tar a live PostgreSQL volume: databases are captured by pg_dump above.
    A paused container may reject docker cp, so read its already-pinned host mount.
    """
    destination = mount.get("Destination")
    source = mount.get("Source")
    need(name in APPS and mount.get("RW") is True and
         (name, destination) in MOUNTS, "HOST_ARCHIVE_SCOPE")
    need(mount.get("Type") in ("bind", "volume") and
         isinstance(source, str) and source.startswith("/"), "HOST_ARCHIVE_SOURCE_INVALID")
    path = Path(source)
    try:
        canonical = path.resolve(strict=True)
        safe = (path.is_dir() and not path.is_symlink() and
                canonical == path and path != Path("/"))
    except (OSError, RuntimeError):
        safe = False
    need(safe, "HOST_ARCHIVE_SOURCE_INVALID")
    need(hashlib.sha256(source.encode()).hexdigest()[:12] ==
         MOUNTS[(name, destination)], "HOST_ARCHIVE_SOURCE_DRIFT")
    return ["tar", "--acls", "--xattrs", "--numeric-owner",
            "-C", source, "-cf", "-", "."]

def encrypt_stream(args, output, keyring, timeout):
    partial = output.with_suffix(output.suffix + ".partial")
    need(not output.exists() and not partial.exists(), "ARCHIVE_EXISTS")
    producer = consumer = None
    try:
        with partial.open("xb") as target:
            producer = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            consumer = subprocess.Popen(
                ["gpg", "--homedir", str(keyring), "--batch", "--no-tty", "--quiet",
                 "--trust-model", "always", "--recipient", RECIPIENT,
                 "--compress-algo", "none", "--encrypt", "--output", "-"],
                stdin=producer.stdout, stdout=target, stderr=subprocess.DEVNULL)
            producer.stdout.close()
            good = producer.wait(timeout=timeout) == 0 and consumer.wait(timeout=timeout) == 0
        need(good and partial.stat().st_size > 0, "ENCRYPTED_STREAM_FAILED")
        partial.rename(output)
        return {"bytes": output.stat().st_size, "sha256": digest(output)}
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("ENCRYPTED_STREAM_TIMEOUT_OR_IO") from None
    finally:
        for process in (producer, consumer):
            if process is not None and process.poll() is None:
                process.kill(); process.wait()
def keyring():
    temp = Path(tempfile.mkdtemp(prefix=".v79-gpg-", dir=BASE))
    os.chmod(temp, 0o700)
    try:
        call(["gpg", "--homedir", str(temp), "--batch", "--quiet", "--import", str(KEY)])
        listing = call(["gpg", "--homedir", str(temp), "--batch", "--with-colons", "--fingerprint", "--list-keys"]).decode()
        need(RECIPIENT in [l.split(":")[9] for l in listing.splitlines() if l.startswith("fpr:")],
             "PUBLIC_RECIPIENT_MISMATCH")
        secret = call(["gpg", "--homedir", str(temp), "--batch", "--with-colons", "--list-secret-keys"])
        need(not secret.strip(), "PRIVATE_KEY_ON_SERVER")
        return temp
    except BaseException:
        shutil.rmtree(temp)
        raise
def resume_apps():
    failures = []
    for name in APPS:
        try:
            if inspect(name).get("State", {}).get("Paused"):
                call(["docker", "unpause", name], timeout=20)
            need(not inspect(name).get("State", {}).get("Paused"), "STILL_PAUSED")
        except Stop:
            failures.append(name)
    need(not failures, "UNPAUSE_FAILED_WATCHDOG_ARMED")
def capture():
    records, files = preflight()
    os.umask(0o077)
    BASE.mkdir(mode=0o700, exist_ok=True)
    need(not BASE.is_symlink() and BASE.stat().st_mode & 0o077 == 0,
         "CHECKPOINT_DIR_PERMISSIONS")
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BASE / ("pair-" + run_id + "-" + str(os.getpid()))
    dest.mkdir(mode=0o700)
    (dest / "STATUS").write_text("INCOMPLETE\n")
    encrypted = {}
    temp = None
    paused = False
    watchdog = "v79-pair-unpause-" + str(os.getpid())
    try:
        temp = keyring()
        for name in EXPECTED:
            encrypted["image-" + name] = encrypt_stream(
                ["docker", "image", "save", EXPECTED[name]],
                dest / ("image-" + name + ".gpg"), temp, 900)
        encrypted["runtime-inspect"] = encrypt_stream(
            ["docker", "inspect", *EXPECTED.keys()], dest / "runtime-inspect.gpg", temp, 60)
        config_paths = sorted(files)
        encrypted["compose-config"] = encrypt_stream(
            ["tar", "-C", "/", "-cf", "-", *[p.lstrip("/") for p in config_paths]],
            dest / "compose-config.gpg", temp, 60)
        # Capture read-only configuration/secret mounts before the outage
        # window; a copy failure cannot then leave applications paused.
        for name in APPS:
            for index, mount in enumerate(sorted(records[name].get("Mounts") or [],
                                                 key=lambda m: m["Destination"]), 1):
                if mount.get("RW"): continue
                label = name + "-mount-" + f"{index:02d}"
                encrypted[label] = encrypt_stream(
                    ["docker", "cp", name + ":" + mount["Destination"], "-"],
                    dest / (label + ".gpg"), temp, 60)
        # systemd owns the independent unpause if this process or SSH dies.
        rescue = (shutil.which("docker") + " unpause v79-hub >/dev/null 2>&1 || true; "
                  + shutil.which("docker") + " unpause v79-tiquet-manager >/dev/null 2>&1 || true")
        call(["systemd-run", "--quiet", "--on-active=240s", "--unit=" + watchdog,
              "/bin/sh", "-c", rescue])
        try:
            call(["docker", "pause", *APPS], timeout=20)
            paused = True
            deadline = time.monotonic() + 180
            for db in DBS:
                need(time.monotonic() < deadline - 30, "PAUSE_DEADLINE")
                args = ["docker", "exec", db, "sh", "-ec",
                        'exec pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" --format=custom --no-owner --no-acl']
                encrypted["dump-" + db] = encrypt_stream(
                    args, dest / ("dump-" + db + ".gpg"), temp,
                    min(90, max(1, int(deadline - time.monotonic()))))
                encrypted["cluster-" + db] = encrypt_stream(
                    ["docker", "exec", db, "sh", "-ec",
                     'exec pg_dumpall -U "${POSTGRES_USER:-postgres}"'],
                    dest / ("cluster-" + db + ".gpg"), temp,
                    min(60, max(1, int(deadline - time.monotonic()))))
            for name in APPS:
              for index, mount in enumerate(sorted(records[name].get("Mounts") or [],
                                                    key=lambda m: m["Destination"]), 1):
                if not mount.get("RW"): continue
                need(time.monotonic() < deadline - 20, "PAUSE_DEADLINE")
                label = name + "-mount-" + f"{index:02d}"
                encrypted[label] = encrypt_stream(
                    host_app_archive_args(name, mount),
                    dest / (label + ".gpg"), temp,
                    min(45, max(1, int(deadline - time.monotonic()))))
        finally:
            # Always attempt both, even if pause only partially succeeded.
            resume_apps()
            paused = False
            call(["systemctl", "stop", watchdog + ".timer"], timeout=20)
        until = time.monotonic() + 60
        while True:
            post = {name: inspect(name) for name in EXPECTED}
            stable = all(post[n].get("Id") == records[n].get("Id")
                         and post[n].get("Image") == EXPECTED[n]
                         and post[n].get("State", {}).get("Status") == "running"
                         and post[n].get("State", {}).get("Health", {}).get("Status") == "healthy"
                         for n in EXPECTED)
            if stable or time.monotonic() >= until: break
            time.sleep(3)
        need(stable, "POST_CAPTURE_LIVE_DRIFT")
        need(all(Path(p).is_file() and digest(Path(p)) == h for p,h in files.items()),
             "CONFIG_CHANGED_DURING_CAPTURE")
        manifest = {"schema": "v79-current-pair-prechange-v1", "captured_utc": run_id,
                    "images": EXPECTED, "source_revisions": REVISIONS,
                    "container_ids": {n: records[n]["Id"] for n in EXPECTED},
                    "mount_source_hash_prefixes": {n + ":" + d: h for (n,d),h in MOUNTS.items()},
                    "config_sha256_by_path_hash": {
                        hashlib.sha256(p.encode()).hexdigest()[:12]: h for p,h in files.items()},
                    "app_mounts": {
                        name: [{"artifact": name + "-mount-" + f"{index:02d}",
                                "destination": "REDACTED_SECRET_MOUNT" if
                                any(w in m["Destination"].lower() for w in ("secret", "credential"))
                                else m["Destination"]}
                               for index,m in enumerate(sorted(records[name].get("Mounts") or [],
                                                                 key=lambda m: m["Destination"]), 1)]
                        for name in APPS},
                    "recipient_fingerprint": RECIPIENT, "encrypted": encrypted,
                    "apps_resumed_same_ids": True,
                    "cross_database_atomic": False, "offhost_verified": False,
                    "decryption_verified": False, "isolated_restore_tested": False,
                    "release_decision": "HOLD"}
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (dest / "STATUS").write_text("ENCRYPTED_LOCAL_CAPTURE_ONLY_RESTORE_NOT_TESTED\n")
        print("LOCAL_ENCRYPTED_CAPTURE=PASS_OFFHOST_AND_RESTORE_PENDING")
        print("CAPTURE_DIR=" + str(dest))
        print("MANIFEST_SHA256=" + digest(dest / "manifest.json"))
    finally:
        if paused:
            try: resume_apps()
            except Stop: print("STOP_UNPAUSE_FAILED_WATCHDOG_ARMED", file=sys.stderr)
        if temp is not None: shutil.rmtree(temp)
def main():
    need(len(sys.argv) == 2 and sys.argv[1] in ("--preflight", "--capture"),
         "USAGE: --preflight OR --capture")
    mode = sys.argv[1]
    try:
        records, files = preflight() if mode == "--preflight" else (None, None)
        if mode == "--preflight":
            print("PRECHANGE_PREFLIGHT=PASS_READ_ONLY")
            print("CONTAINERS=" + str(len(records)) + " CONFIG_FILES=" + str(len(files)))
            print("OFFHOST_AND_RESTORE=NOT_VERIFIED")
        else: capture()
    except Stop as exc:
        print("STOP=" + str(exc), file=sys.stderr)
        raise SystemExit(2)
if __name__ == "__main__": main()
