#!/usr/bin/env python3
"""V79 owner-only, read-only host acceptance inventory. No new probe or execution."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys

AST = dt.timezone(dt.timedelta(hours=-4))
REPORT_DEST = "/run/v79-workforce-reports"
WORKER_DIR = Path.home() / ".local/share/v79-approved-task-worker"
WORKER_UNIT = "v79-g2-approved-task-worker.service"
UNITS = (
    "v79-g2-approved-task-worker.timer",
    "v79-workforce-morning.timer",
    "v79-workforce-evening.timer",
)
CONTAINERS = (
    "v79-hub", "v79-business-agent", "v79-tiquet-manager",
    "v79-sentinel-dell-ingress", "v79-sentinel-dell-monitor",
    "v79-sentinel-dell-noc",
)
HEX = re.compile(r"^sha256:[0-9a-f]{64}$")


def command(args, timeout=15):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        if result.returncode or len(result.stdout) > 2_000_000:
            return None
        return result.stdout.decode("utf-8", "strict")
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        return None


def safe_file_bytes(path, max_size=100_000):
    """Never follow a symlink or open loose-permission/private-data paths."""
    fd = None
    try:
        parent = path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or (parent.st_mode & 0o077):
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0))
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or (
            s.st_mode & 0o077) or s.st_size > max_size:
            return None
        with os.fdopen(fd, "rb") as stream:
            fd = None
            data = stream.read(max_size + 1)
        return data if len(data) <= max_size else None
    except (OSError, ValueError):
        return None
    finally:
        if fd is not None:
            os.close(fd)


def parse_iso(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.utcoffset() == dt.timedelta(0) else None
    except ValueError:
        return None


def inspect_report(raw, slot, now):
    """Validate limited persisted Python report contract, not evidence signatures."""
    if not isinstance(raw, dict) or raw.get("schema") != 1 or raw.get("slot") != slot:
        return "INVALID", "-"
    if raw.get("state") != "recorded" or not isinstance(raw.get("report"), dict):
        return "INVALID", "-"
    report = raw["report"]
    checked = parse_iso(raw.get("checkedAt"))
    observed = parse_iso(report.get("evidenceCollectedAt"))
    if not checked or not observed:
        return "INVALID", "-"
    day, label = slot.rsplit("-", 1)
    expected = dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc)
    expected += dt.timedelta(hours=12 if label == "morning" else 23)
    lag = (checked - observed).total_seconds()
    if not (-120 <= lag <= 900 and -300 <= (checked - expected).total_seconds() <= 1800):
        return "INVALID", "-"
    if checked > now + dt.timedelta(minutes=2) or report.get("noActionsExecuted") is not True:
        return "INVALID", "-"
    coverage = report.get("coverage")
    if not isinstance(coverage, str) or coverage.upper() not in ("AVAILABLE", "INCOMPLETE"):
        return "INVALID", "-"
    findings, missing = report.get("verifiedFindings"), report.get("missingSources")
    if (not isinstance(findings, list) or len(findings) > 50 or
            not isinstance(missing, list) or len(missing) > 20):
        return "INVALID", "-"
    if coverage.upper() == "AVAILABLE" and missing:
        return "INVALID", "-"
    if not all(isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,90}", x) for x in missing):
        return "INVALID", "-"
    for f in findings:
        if (not isinstance(f, dict) or
            not all(isinstance(f.get(k), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,90}", f[k])
                    for k in ("system", "metric")) or
            f.get("severity") not in ("attention", "watch", "information") or
            isinstance(f.get("value"), bool) or
            not isinstance(f.get("value"), (float, int)) or
            not (-1e12 < f["value"] < 1e12)):
            return "INVALID", "-"
    return coverage.upper(), str(int(lag))


def systemd():
    for unit in UNITS + (WORKER_UNIT,):
        output = command(["systemctl", "--user", "show", unit,
                          "--property=ActiveState", "--property=Result",
                          "--property=UnitFileState", "--property=ExecMainStatus"])
        if not output:
            print("UNIT=" + unit + "|STATUS=UNKNOWN")
            continue
        props = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        allowed_active = {"active", "inactive", "failed", "activating", "deactivating"}
        active = props.get("ActiveState")
        result = props.get("Result")
        print("UNIT=" + unit +
              "|ACTIVE=" + (active if active in allowed_active else "unknown") +
              "|RESULT=" + (result if result in ("success", "exit-code", "timeout", "signal") else "unknown") +
              "|ENABLED=" + str(props.get("UnitFileState") in ("enabled", "enabled-runtime")).lower())


def worker_inventory():
    worker = WORKER_DIR / "worker.py"
    data = safe_file_bytes(worker, 40_000)
    print("G2_INSTALLED_WORKER_SHA256=" +
          (hashlib.sha256(data).hexdigest() if data is not None else "UNAVAILABLE"))
    unit_text = safe_file_bytes(Path.home() / ".config/systemd/user" / WORKER_UNIT, 12_000)
    expected = ("ExecStart=/usr/bin/python3 -I " + str(worker) + " " +
                str(WORKER_DIR / "config.json"))
    print("G2_SERVICE_EXACT_PATH_MATCH=" +
          str(unit_text is not None and expected.encode() in unit_text).lower())
    config = safe_file_bytes(WORKER_DIR / "config.json", 5_000)
    print("G2_PRIVATE_CONFIG_PRESENT=" + str(config is not None).lower())
    marker = WORKER_DIR / "uncertain.json"
    print("G2_UNCERTAIN_LATCH=" +
          ("PRESENT_DO_NOT_RESET" if marker.exists() or marker.is_symlink() else "ABSENT"))
    status = safe_file_bytes(WORKER_DIR / "status.json", 10_000)
    outcome = "UNAVAILABLE"
    if status:
        try:
            result = json.loads(status)
            if result.get("state") in ("idle", "succeeded"):
                outcome = result["state"].upper()
        except (ValueError, TypeError, AttributeError):
            pass
    print("G2_LAST_STORED_POLL=" + outcome)


def docker_inventory():
    report_source = None
    for name in CONTAINERS:
        output = command(["docker", "inspect", name])
        if output is None:
            print("CONTAINER=" + name + "|STATE=UNKNOWN")
            continue
        try:
            row = json.loads(output)[0]
            identifier = row.get("Image", "")
            state = row.get("State") or {}
            health = (state.get("Health") or {}).get("Status", "not_configured")
            ident = identifier if isinstance(identifier, str) and HEX.fullmatch(identifier) else "UNKNOWN"
            allowed_health = health if health in ("healthy", "unhealthy", "starting", "not_configured") else "UNKNOWN"
            print("CONTAINER=" + name + "|RUNNING=" + str(state.get("Running") is True).lower() +
                  "|HEALTH=" + allowed_health + "|IMAGE=" + ident)
            if name == "v79-hub":
                cfg = row.get("Config") or {}
                vals = {x.split("=", 1)[0]: x.split("=", 1)[1]
                        for x in cfg.get("Env", []) if "=" in x}
                for k in ("V79_WORKFORCE_ACTIONS_ENABLED", "V79_WORKFORCE_REPORTS_ENABLED",
                          "V79_COO_WORKBOARD_ENABLED", "V79_WORKFORCE_GOOGLE_ENABLED"):
                    print("HUB_FLAG=" + k + "|ON=" + str(vals.get(k) == "1").lower())
                for mount in row.get("Mounts", []):
                    if mount.get("Destination") == REPORT_DEST and mount.get("Type") == "bind":
                        print("HUB_REPORT_MOUNT_READONLY=" + str(mount.get("RW") is False).lower())
                        if mount.get("RW") is False:
                            report_source = mount.get("Source")
        except (ValueError, TypeError, AttributeError, IndexError):
            print("CONTAINER=" + name + "|DETAILS=UNAVAILABLE")
    return report_source


def report_inventory(directory, now):
    if not isinstance(directory, str) or not os.path.isabs(directory):
        print("BRIEFING_REPORT_MOUNT=UNAVAILABLE")
        return
    folder = Path(directory)
    try:
        s = folder.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or (s.st_mode & 0o077):
            raise ValueError("Unsafe")
    except (OSError, ValueError):
        print("BRIEFING_REPORT_MOUNT=UNAVAILABLE_OR_UNSAFE")
        return
    print("BRIEFING_REPORT_MOUNT=PRIVATE_READONLY")
    local = now.astimezone(AST).date()
    for offset in (2, 1, 0):
        day = local - dt.timedelta(days=offset)
        for label, hour in (("morning", 12), ("evening", 23)):
            slot = day.isoformat() + "-" + label
            expected = dt.datetime.combine(day, dt.time(0), tzinfo=dt.timezone.utc) + dt.timedelta(hours=hour)
            if now < expected + dt.timedelta(minutes=30):
                state, lag = "NOT_DUE", "-"
            else:
                data = safe_file_bytes(folder / (slot + ".json"))
                if data is None:
                    state, lag = "MISSING_OR_UNSAFE", "-"
                else:
                    try:
                        state, lag = inspect_report(json.loads(data), slot, now)
                    except (ValueError, UnicodeDecodeError):
                        state, lag = "INVALID", "-"
            print("BRIEFING_SLOT=" + slot + "|COVERAGE=" + state +
                  "|LAG_SECONDS=" + lag + "|SOURCE_ATTESTATION=NOT_VERIFIED")


def main():
    if len(sys.argv) != 1 or socket.gethostname() != "v79sl":
        raise SystemExit("STOP=EXPECTED_V79SL_READ_ONLY_INVOCATION")
    now = dt.datetime.now(dt.timezone.utc)
    print("HOST=v79sl")
    print("UTC=" + now.isoformat())
    print("AUDIT=READ_ONLY_NO_CLAIMS_NO_TASKS_NO_NEW_PROBES_NO_DEPLOY")
    systemd()
    worker_inventory()
    report_inventory(docker_inventory(), now)
    print("SENTINEL_TELEMETRY_TRUST=NOT_ESTABLISHED_BY_CONTAINER_HEALTH")
    print("PRODUCTION_CHANGES=NONE")


if __name__ == "__main__":
    main()
