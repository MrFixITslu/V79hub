"""G2.14 single-use 15-minute supervised Acer -> V79 server TCP pilot.

Explicit owner approval: one TCP 443 attempt every 60 seconds for 15 minutes
from firelion-Aspire-A315-51 to 192.168.100.163; 15 maximum attempts.
It is NOT a deployed Sentinel collector, background service, packet capture,
HTTP/TLS check, network scan, or reusable monitoring permission.

A private local consumption marker is created before the first attempt to
prevent accidental reruns. A failed/aborted run also consumes this approval.
No customer records, credentials, raw packets, or remote service writes.
"""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import platform
import socket
import stat
import sys
import time
from typing import Callable

TARGET = "192.168.100.163"
PORT = 443
APPROVED_ACER_HOSTNAME = "firelion-Aspire-A315-51"
CADENCE_SECONDS = 60
DURATION_SECONDS = 900
MAX_ATTEMPTS = 15
SOCKET_TIMEOUT_SECONDS = 3
GUARD_FILE_NAME = "owner-approved-v79-server-443-one-pilot-20261011.once"


class PilotGuardError(RuntimeError):
    """Refuse execution outside exact scope or after approval is consumed."""


def connect_one_tcp() -> int:
    """Exactly one literal-IPv4 TCP socket attempt; no DNS or retries."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(SOCKET_TIMEOUT_SECONDS)
        try:
            return sock.connect_ex((TARGET, PORT))
        except socket.timeout:
            return errno.ETIMEDOUT
        except OSError as exc:
            return exc.errno or -1


def classify_connect_result(result: object) -> str:
    if type(result) is not int:
        return "connection-failed"
    if result == 0:
        return "tcp-open"
    if result == errno.ECONNREFUSED:
        return "refused"
    if result == errno.ETIMEDOUT:
        return "timeout"
    return "connection-failed"


def claim_one_pilot(*, host: str, home: Path) -> Path:
    """Fail-closed persistent single-use approval marker with 0600 mode."""
    if host != APPROVED_ACER_HOSTNAME:
        raise PilotGuardError("Pilot must run on the approved Acer vantage")
    directory = home / ".local" / "state" / "v79-sentinel"
    if directory.is_symlink():
        raise PilotGuardError("Pilot state directory cannot be a symlink")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink():
        raise PilotGuardError("Pilot state directory cannot be a symlink")
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise PilotGuardError("Pilot state directory owner mismatch")
    directory.chmod(0o700)
    marker = directory / GUARD_FILE_NAME
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(marker, flags, 0o600)
    except FileExistsError as exc:
        raise PilotGuardError("One-time pilot already claimed; do not rerun") from exc
    except OSError as exc:
        raise PilotGuardError("Unable to claim one-time pilot") from exc
    with os.fdopen(fd, "w", encoding="ascii") as output:
        output.write("Approval consumed. Do not rerun without renewed owner authorization.\n")
    return marker


def execute_supervised_pilot(
    *,
    connect: Callable[[], int],
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    emit: Callable[[dict], None],
) -> dict:
    """No more than 15 scheduled attempts; stop after the 900-second window.

    Missed cadence slots are SKIPPED rather than caught up in a burst.
    A connection error counts as a failed attempt; it is never retried.
    """
    started = clock()
    deadline = started + DURATION_SECONDS
    outcomes = {"tcp-open": 0, "refused": 0, "timeout": 0, "connection-failed": 0}
    executed = 0
    skipped = 0
    elapsed_samples = []

    for index in range(MAX_ATTEMPTS):
        slot_start = started + index * CADENCE_SECONDS
        remaining = slot_start - clock()
        if remaining > 0:
            sleep(remaining)
        now = clock()
        if now >= deadline:
            skipped += MAX_ATTEMPTS - index
            break
        if now < slot_start or now > slot_start + SOCKET_TIMEOUT_SECONDS:
            # Clock drift, system suspension, or missed schedule: don't catch up.
            skipped += 1
            continue
        tick = clock()
        try:
            result = connect()
        except (OSError, ValueError, TypeError):
            result = -1
        elapsed_ms = max(0, round((clock() - tick) * 1000))
        outcome = classify_connect_result(result)
        executed += 1
        outcomes[outcome] += 1
        elapsed_samples.append(elapsed_ms)
        emit({
            "sampleNumber": index + 1,
            "outcome": outcome,
            "elapsedMs": elapsed_ms,
        })

    if clock() < deadline:
        sleep(deadline - clock())

    summary = {
        "schemaVersion": 1,
        "status": "bounded_one_time_pilot_finished",
        "source": "owner_acer_operator_run",
        "target": TARGET,
        "port": PORT,
        "cadenceSeconds": CADENCE_SECONDS,
        "durationSeconds": DURATION_SECONDS,
        "attemptsExecuted": executed,
        "scheduledSlotsSkipped": skipped,
        "maxAttempts": MAX_ATTEMPTS,
        "outcomes": outcomes,
        "meanTcpConnectMs": round(sum(elapsed_samples) / executed, 1) if executed else None,
        "additionalProbesAuthorized": False,
        "continuousMonitoringEnabled": False,
        "tlsOrHttpVerified": False,
        "independentlyAuthenticatedCollector": False,
        "trustedForExecutiveUse": False,
        "productionReady": False,
    }
    emit(summary)
    return summary


def main() -> int:
    if len(sys.argv) != 1:
        print("Pilot takes no arguments; fixed V79-owned target and cadence.", file=sys.stderr)
        return 2
    try:
        claim_one_pilot(host=platform.node(), home=Path.home())
    except (PilotGuardError, OSError) as exc:
        # Only a static, non-private guard message is emitted.
        print(f"NOT STARTED: {exc}", file=sys.stderr)
        return 2
    print("Pilot started: ONE approval, 15-minute window; Ctrl+C stops early.", flush=True)
    try:
        execute_supervised_pilot(
            connect=connect_one_tcp,
            clock=time.monotonic,
            sleep=time.sleep,
            emit=lambda result: print(
                json.dumps(result, sort_keys=True, separators=(",", ":")),
                flush=True,
            ),
        )
        print("Pilot ended. No more probes authorized.", flush=True)
        return 0
    except KeyboardInterrupt:
        print("Pilot stopped early. Approval consumed; do not rerun.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
