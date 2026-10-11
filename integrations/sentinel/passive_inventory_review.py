"""G2.11 V79-owned monitoring inventory preflight — passive only.

Reads the Acer's own Linux /proc/net/route and /proc/net/arp snapshots.
Does NOT discover or contact endpoints, run subprocesses, enumerate packet
contents, copy addresses/MACs or service identities to output, write files,
modify monitoring, or infer ownership. The report is a hint for the owner to
construct a SEPARATE explicit target allowlist after review, not consent.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

ROUTE_FILE = Path("/proc/net/route")
ARP_FILE = Path("/proc/net/arp")
MAX_SOURCE_SIZE = 32768
MAX_RECORDS = 128
_INTERFACE = re.compile(r"^[A-Za-z0-9_.@:-]{1,64}$")
_HEX32 = re.compile(r"^[A-Fa-f0-9]{8}$")
_IPV4 = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")
_MAC = re.compile(r"^[A-Fa-f0-9:]{17}$")


class InventoryUnavailable(ValueError):
    """Ambiguous or malformed local inventory fails without data emission."""


def _bounded_lines(value: str) -> list[str]:
    if type(value) is not str or len(value.encode("utf-8")) > MAX_SOURCE_SIZE:
        raise InventoryUnavailable("Invalid bounded kernel inventory")
    lines = value.splitlines()
    if len(lines) > MAX_RECORDS + 1 or not lines:
        raise InventoryUnavailable("Invalid bounded kernel inventory")
    return lines


def inspect_local_inventory(route_text: str, arp_text: str) -> dict:
    """Count kernel-present evidence only; never print addresses or names."""
    routes = _bounded_lines(route_text)
    neighbors = _bounded_lines(arp_text)

    route_header = routes[0].split()
    if len(route_header) < 8 or route_header[:3] != ["Iface", "Destination", "Gateway"]:
        raise InventoryUnavailable("Unexpected route table")
    if neighbors[0].split() != ["IP", "address", "HW", "type", "Flags", "HW", "address", "Mask", "Device"]:
        raise InventoryUnavailable("Unexpected neighbor table")

    default_gateways = set()
    route_rows = 0
    routed_interfaces = set()
    for line in routes[1:]:
        if not line.strip():
            continue
        cols = line.split()
        if len(cols) < 8 or len(cols) > 11 or not _INTERFACE.fullmatch(cols[0]):
            raise InventoryUnavailable("Malformed route")
        if not (_HEX32.fullmatch(cols[1]) and _HEX32.fullmatch(cols[2])):
            raise InventoryUnavailable("Malformed route")
        if any(not re.fullmatch(r"[A-Fa-f0-9]{1,8}", v) for v in (cols[3],)):
            raise InventoryUnavailable("Malformed route")
        route_rows += 1
        routed_interfaces.add(cols[0])
        if cols[1] == "00000000" and cols[2] != "00000000":
            default_gateways.add((cols[0], cols[2]))

    arp_rows = 0
    neighbors_seen = set()
    for line in neighbors[1:]:
        if not line.strip():
            continue
        cols = line.split()
        if len(cols) != 6 or not _IPV4.fullmatch(cols[0]) or not _INTERFACE.fullmatch(cols[-1]):
            raise InventoryUnavailable("Malformed neighbor cache")
        try:
            ip = tuple(map(int, cols[0].split(".")))
        except ValueError as exc:
            raise InventoryUnavailable("Malformed neighbor cache") from exc
        if any(v > 255 for v in ip):
            raise InventoryUnavailable("Malformed neighbor cache")
        if len(cols[3]) != 17 or not _MAC.fullmatch(cols[3]):
            raise InventoryUnavailable("Malformed neighbor cache")
        if not all(re.fullmatch(r"0x[0-9A-Fa-f]{1,8}", v) for v in (cols[1], cols[2])):
            raise InventoryUnavailable("Malformed neighbor cache")
        arp_rows += 1
        neighbors_seen.add((cols[0], cols[-1]))

    return {
        "schemaVersion": 1,
        "status": "passive_inventory_review",
        "origin": "local_linux_kernel_route_and_neighbor_cache",
        "routeEntriesObserved": route_rows,
        "routedInterfacesObserved": len(routed_interfaces),
        "defaultGatewayCandidates": len(default_gateways),
        "cachedNeighborEntries": arp_rows,
        "distinctCachedNeighbors": len(neighbors_seen),
        "activeScanPerformed": False,
        "deviceReachabilityVerified": False,
        "deviceOwnershipVerified": False,
        "approvedMonitoringTargets": 0,
        "monitoringEnabled": False,
        "sourceAuthenticated": False,
        "productionReady": False,
        "note": "Kernel route/ARP hints only; neighbors may be stale or outside the owner's control.",
    }


def local_passive_inventory(
    *, read_route: Callable[[], str] | None = None,
    read_arp: Callable[[], str] | None = None,
) -> dict:
    if read_route is None:
        read_route = lambda: ROUTE_FILE.read_text(encoding="ascii")
    if read_arp is None:
        read_arp = lambda: ARP_FILE.read_text(encoding="ascii")
    try:
        return inspect_local_inventory(read_route(), read_arp())
    except (OSError, UnicodeError, ValueError, OverflowError, TypeError) as exc:
        raise InventoryUnavailable("Passive inventory not available") from exc


def main() -> int:
    try:
        report = local_passive_inventory()
        success = True
    except Exception:
        report = {
            "schemaVersion": 1, "status": "passive_inventory_unavailable",
            "activeScanPerformed": False, "deviceOwnershipVerified": False,
            "approvedMonitoringTargets": 0, "monitoringEnabled": False,
            "productionReady": False,
        }
        success = False
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
