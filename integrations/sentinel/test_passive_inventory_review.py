"""G2.11 offline inventory regression tests — never scan or disclose endpoints."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from passive_inventory_review import (
    InventoryUnavailable, inspect_local_inventory, local_passive_inventory,
)

ROUTE_HEADER = (
    "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
)
ARP_HEADER = "IP address       HW type     Flags       HW address            Mask     Device\n"


def routes():
    return ROUTE_HEADER + (
        "wlan0\t00000000\t0101A8C0\t0003\t0\t0\t600\t00000000\t0\t0\t0\n"
        "wlan0\t0001A8C0\t00000000\t0001\t0\t0\t600\t00FFFFFF\t0\t0\t0\n"
    )


def neighbors():
    return ARP_HEADER + (
        "192.168.1.1 0x1 0x2 02:0a:0b:00:00:01 * wlan0\n"
        "192.168.1.43 0x1 0x2 02:0a:0b:00:00:02 * wlan0\n"
    )


class PassiveInventoryTests(unittest.TestCase):
    def test_counts_only_without_addresses_or_autoapproval(self):
        report = inspect_local_inventory(routes(), neighbors())
        self.assertEqual(report["defaultGatewayCandidates"], 1)
        self.assertEqual(report["cachedNeighborEntries"], 2)
        self.assertEqual(report["distinctCachedNeighbors"], 2)
        self.assertEqual(report["routedInterfacesObserved"], 1)
        self.assertEqual(report["routeEntriesObserved"], 2)
        self.assertEqual(report["approvedMonitoringTargets"], 0)
        for field in ("activeScanPerformed", "deviceReachabilityVerified",
                      "deviceOwnershipVerified", "monitoringEnabled",
                      "sourceAuthenticated", "productionReady"):
            self.assertFalse(report[field])

    def test_never_prints_ips_macs_interface_names(self):
        report = inspect_local_inventory(routes(), neighbors())
        output = json.dumps(report)
        for sensitive in (
            "wlan0", "192.168.1", "02:0a:0b", "0101A8C0", "0001A8C0",
            "00FFFFFF",
        ):
            self.assertNotIn(sensitive, output)

    def test_missing_default_gateway_does_not_claim_any(self):
        text = routes().replace("0101A8C0", "00000000")
        report = inspect_local_inventory(text, neighbors())
        self.assertEqual(report["defaultGatewayCandidates"], 0)
        self.assertFalse(report["deviceReachabilityVerified"])

    def test_neighbor_table_can_be_empty(self):
        report = inspect_local_inventory(routes(), ARP_HEADER)
        self.assertEqual(report["cachedNeighborEntries"], 0)
        self.assertEqual(report["approvedMonitoringTargets"], 0)

    def test_duplicate_cache_entry_is_not_extra_distinct_neighbor(self):
        original = neighbors()
        report = inspect_local_inventory(routes(), original + original.splitlines(True)[-1])
        self.assertEqual(report["cachedNeighborEntries"], 3)
        self.assertEqual(report["distinctCachedNeighbors"], 2)

    def test_rejects_suspicious_unbounded_and_malformed_kernel_data(self):
        tests = (
            ("", neighbors()),
            ("secret" * 10000, neighbors()),
            (ROUTE_HEADER + "private-remote.com 00000000 0101A8C0 0003 0 0 0 0\n", neighbors()),
            (routes(), ""),
            (routes(), ARP_HEADER + "private-host 0x1 0x2 02:0a:0b:00:00:01 * wlan0\n"),
            (routes(), ARP_HEADER + "999.168.1.1 0x1 0x2 02:0a:0b:00:00:01 * wlan0\n"),
            (routes(), ARP_HEADER + "192.168.1.1 0x1 0x2 EXFIL_SECRET * wlan0\n"),
            (routes(), neighbors() + ("192.168.1.2 0x1 0x2 02:00:00:00:00:01 * wlan0\n" * 200)),
        )
        for route_text, arp_text in tests:
            with self.subTest(route_size=len(route_text), arp_size=len(arp_text)):
                with self.assertRaises(InventoryUnavailable):
                    inspect_local_inventory(route_text, arp_text)

    def test_two_explicit_readers_are_only_side_effects(self):
        calls = []
        def route_reader():
            calls.append("route")
            return routes()
        def arp_reader():
            calls.append("arp")
            return neighbors()
        report = local_passive_inventory(read_route=route_reader, read_arp=arp_reader)
        self.assertEqual(calls, ["route", "arp"])
        self.assertEqual(report["status"], "passive_inventory_review")

    def test_missing_kernel_file_is_generic_denial(self):
        def unavailable():
            raise OSError("secret host 10.100.2.4")
        with self.assertRaisesRegex(InventoryUnavailable, "^Passive inventory not available$"):
            local_passive_inventory(read_route=unavailable, read_arp=neighbors)

    def test_module_contains_no_network_request_or_write_operations(self):
        source = Path(__file__).with_name("passive_inventory_review.py").read_text()
        for forbidden in (
            "import socket", "subprocess", "requests.", "urllib", "nmap",
            "scapy", "ip neigh", "sudo", "write_text(", "write_bytes(",
            "os.system(", "pcap", "connect(", "sendto(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
