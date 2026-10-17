"""G2.10 isolated passive Linux host telemetry (NetPulse-counter inspired).

One operator-triggered local process, two kernel reads, no packet capture,
network connection, elevated privileges, host inventory upload, file writes,
or changes to an existing Sentinel service.

Counts are host interface byte counters only; virtual/tunnel interfaces may
be double counted. They do not prove device discovery, bandwidth, loss,
service health or an authenticated Edge agent. Never use these alone to
advertise active Sentinel monitoring or to feed a trusted executive agent.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable

KERNEL_COUNTER_FILE = Path("/proc/net/dev")
MAX_SOURCE_BYTES = 16_384
MAX_INTERFACES = 64
MAX_COUNTER = (1 << 64) - 1
INTERFACE = re.compile(r"^[A-Za-z0-9_.@:-]{1,64}$")


class CounterSourceUnavailable(ValueError):
    """A bounded, redacted failure that must never grant monitoring trust."""


def parse_kernel_counters(data: str) -> dict[str, tuple[int, int]]:
    """Parse Linux /proc/net/dev with exact RX/TX columns; no names published."""
    if not isinstance(data, str) or len(data.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise CounterSourceUnavailable("Invalid bounded kernel snapshot")
    lines = data.splitlines()
    if len(lines) < 3 or "Inter-" not in lines[0] or "face" not in lines[1]:
        raise CounterSourceUnavailable("Missing Linux kernel counter header")
    counters: dict[str, tuple[int, int]] = {}
    for line in lines[2:]:
        if not line.strip():
            continue
        if ":" not in line:
            raise CounterSourceUnavailable("Invalid interface counter row")
        name, payload = line.rsplit(":", 1)
        name = name.strip()
        values = payload.split()
        if (not INTERFACE.fullmatch(name) or name in counters
            or len(values) != 16 or len(counters) >= MAX_INTERFACES):
            raise CounterSourceUnavailable("Unexpected interface counter row")
        if any(not value.isascii() or not value.isdecimal() for value in values):
            raise CounterSourceUnavailable("Non-numeric kernel counter")
        fields = [int(v) for v in values]
        if any(v > MAX_COUNTER for v in fields):
            raise CounterSourceUnavailable("Counter overflow")
        # Linux /proc/net/dev exposes RX bytes in column 1 and TX in column 9.
        counters[name] = fields[0], fields[8]
    counters.pop("lo", None)
    if not counters:
        raise CounterSourceUnavailable("No non-loopback interface counters")
    return counters


def summarize_counter_samples(
    first: str, second: str, interval_s: float
) -> dict:
    """Produce bounded non-identifying host RX/TX deltas from two reads."""
    if (type(interval_s) not in (float, int)
        or not 0.5 <= interval_s <= 5.0):
        raise CounterSourceUnavailable("Invalid sampling interval")
    before = parse_kernel_counters(first)
    after = parse_kernel_counters(second)
    if before.keys() != after.keys():
        raise CounterSourceUnavailable("Interface set changed during sampling")
    rx_delta = tx_delta = 0
    for name in before:
        earlier_rx, earlier_tx = before[name]
        later_rx, later_tx = after[name]
        if later_rx < earlier_rx or later_tx < earlier_tx:
            raise CounterSourceUnavailable("Counter reset during sampling")
        rx_delta += later_rx - earlier_rx
        tx_delta += later_tx - earlier_tx
    return {
        "schemaVersion": 1,
        "status": "passive_host_counter_sample",
        "measurementOrigin": "local_linux_kernel_proc_net_dev",
        "intervalMs": round(interval_s * 1000),
        "interfacesObserved": len(before),
        "rxBytesObserved": rx_delta,
        "txBytesObserved": tx_delta,
        "includesVirtualInterfaces": "possible",
        "networkServicesVerified": False,
        "remoteDevicesVerified": False,
        "edgeAgentAuthenticated": False,
        "trustedForExecutiveUse": False,
        "productionReady": False,
        "note": "Local host counters only; no device discovery, bandwidth assurance, or packet content.",
    }


def observe_passive_host_counters(
    *, reader: Callable[[], str] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Read only the fixed kernel counter file twice; default 1-second gap."""
    if reader is None:
        def reader():
            return KERNEL_COUNTER_FILE.read_text(encoding="ascii")
    try:
        first = reader()
        t0 = clock()
        sleeper(1.0)
        second = reader()
        interval = clock() - t0
        return summarize_counter_samples(first, second, interval)
    except (OSError, UnicodeError, CounterSourceUnavailable,
            TypeError, ValueError, OverflowError) as exc:
        raise CounterSourceUnavailable("Local kernel counter sample unavailable") from exc


def main() -> int:
    try:
        report = observe_passive_host_counters()
        success = True
    except Exception:
        # The output must never echo an interface name, IP, or exception.
        report = {
            "schemaVersion": 1,
            "status": "passive_host_counter_unavailable",
            "networkServicesVerified": False,
            "remoteDevicesVerified": False,
            "edgeAgentAuthenticated": False,
            "trustedForExecutiveUse": False,
            "productionReady": False,
        }
        success = False
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
