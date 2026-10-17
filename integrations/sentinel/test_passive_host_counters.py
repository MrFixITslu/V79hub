"""Synthetic-only tests of passive local host RX/TX counter evidence."""
from __future__ import annotations

import json
import unittest

from passive_host_counters import (
    CounterSourceUnavailable,
    observe_passive_host_counters,
    parse_kernel_counters,
    summarize_counter_samples,
)

HEADER = (
    "Inter-|   Receive                                                |  Transmit\n"
    " face |bytes    packets errs drop fifo frame compressed multicast |bytes    packets errs drop fifo colls carrier compressed\n"
)


def row(name: str, rx: int, tx: int) -> str:
    fields = [rx] + [0] * 7 + [tx] + [0] * 7
    return f" {name}: " + " ".join(str(n) for n in fields) + "\n"


def sample(rx: int, tx: int) -> str:
    return HEADER + row("lo", 1000, 1000) + row("eth0", rx, tx)


class PassiveKernelCountersTests(unittest.TestCase):
    def test_parses_exact_kernel_columns_without_loopback(self):
        self.assertEqual(parse_kernel_counters(sample(300, 500)), {"eth0": (300, 500)})

    def test_two_samples_show_actual_delta_not_cumulative_counter(self):
        result = summarize_counter_samples(sample(300, 500), sample(330, 575), 1.0)
        self.assertEqual(result["rxBytesObserved"], 30)
        self.assertEqual(result["txBytesObserved"], 75)
        self.assertEqual(result["intervalMs"], 1000)
        self.assertEqual(result["interfacesObserved"], 1)
        self.assertEqual(result["measurementOrigin"], "local_linux_kernel_proc_net_dev")
        for key in ("networkServicesVerified", "remoteDevicesVerified",
                    "edgeAgentAuthenticated", "trustedForExecutiveUse", "productionReady"):
            self.assertFalse(result[key])

    def test_zeros_are_valid_but_do_not_prove_device_health(self):
        result = summarize_counter_samples(sample(300, 500), sample(300, 500), 1.0)
        self.assertEqual(result["rxBytesObserved"], 0)
        self.assertEqual(result["txBytesObserved"], 0)
        self.assertFalse(result["networkServicesVerified"])

    def test_interface_names_and_untrusted_strings_never_in_output(self):
        initial = HEADER + row("private-vlan99", 100, 200)
        next_read = HEADER + row("private-vlan99", 120, 240)
        text = json.dumps(summarize_counter_samples(initial, next_read, 1.0))
        self.assertNotIn("private-vlan99", text)
        self.assertNotIn("eth0", text)
        self.assertNotIn("192.168", text)

    def test_virtual_interfaces_are_explicitly_not_traffic_topology(self):
        first = HEADER + row("eth0", 1, 2) + row("veth1", 3, 4)
        second = HEADER + row("eth0", 6, 7) + row("veth1", 8, 9)
        result = summarize_counter_samples(first, second, 1.0)
        self.assertEqual(result["interfacesObserved"], 2)
        self.assertEqual(result["rxBytesObserved"], 10)
        self.assertEqual(result["txBytesObserved"], 10)
        self.assertEqual(result["includesVirtualInterfaces"], "possible")

    def test_malformed_headers_and_numbers_fail_closed(self):
        invalid = (
            "", "garbage\n", HEADER, HEADER + "  private: 1 2\n",
            HEADER + row("eth0", 100, 200).replace("100", "secret", 1),
            HEADER + row("eth0", -2, 400),
            HEADER + row("eth0", 2**64, 2),
            HEADER + row("lo", 5, 5),
            HEADER + row("eth0", 2, 2) + row("eth0", 3, 3),
            HEADER + "a" * 16385,
        )
        for text in invalid:
            with self.subTest(invalid_size=len(text)), self.assertRaises(CounterSourceUnavailable):
                parse_kernel_counters(text)

    def test_reset_wrap_and_interface_set_change_are_denied(self):
        candidates = (
            (sample(100, 100), sample(99, 101)),
            (sample(100, 100), sample(101, 99)),
            (HEADER + row("eth0", 100, 100), HEADER + row("new0", 102, 105)),
            (HEADER + row("eth0", 100, 100), HEADER + row("lo", 102, 105)),
        )
        for before, after in candidates:
            with self.subTest(first_len=len(before)), self.assertRaises(CounterSourceUnavailable):
                summarize_counter_samples(before, after, 1.0)

    def test_sampling_interval_is_bounded(self):
        for interval in (0, 0.49, 5.001, True, None, float("inf")):
            with self.subTest(interval=interval), self.assertRaises(CounterSourceUnavailable):
                summarize_counter_samples(sample(1, 2), sample(2, 4), interval)

    def test_two_readings_with_explicit_reader_and_clock_only(self):
        inputs = iter([sample(1, 2), sample(11, 22)])
        times = iter([20.0, 21.0])
        sleeps = []
        report = observe_passive_host_counters(
            reader=lambda: next(inputs),
            clock=lambda: next(times),
            sleeper=sleeps.append,
        )
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(report["rxBytesObserved"], 10)
        self.assertEqual(report["txBytesObserved"], 20)

    def test_missing_source_fails_without_private_exception_output(self):
        def reader():
            raise OSError("private host 10.0.0.8")
        with self.assertRaisesRegex(CounterSourceUnavailable, "^Local kernel counter sample unavailable$"):
            observe_passive_host_counters(reader=reader, sleeper=lambda *_: None)

    def test_no_packet_files_network_calls_or_privilege_calls_in_sampler(self):
        from pathlib import Path
        module = Path(__file__).with_name("passive_host_counters.py").read_text()
        for forbidden in ("socket.", "subprocess.", "dumpcap", "tshark", "sudo", "requests.", "urllib.request", "pcapng", "os.system"):
            self.assertNotIn(forbidden, module.lower())


if __name__ == "__main__":
    unittest.main()
