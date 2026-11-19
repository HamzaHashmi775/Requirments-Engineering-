# Supplementary witness tests for BigCodeBench/145 (B6). The original 5 tests never read the
# CSV content, so no ambiguity about the rows written can be detected. These tests check only
# the ORIGINAL requirement's behaviour (as implemented by the reference solution) and run for
# both prompt variants.
import csv
import ipaddress
import os
import unittest


class WitnessTests(unittest.TestCase):
    def _rows(self, ip_range):
        path = "witness_ips.csv"
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        task_func(ip_range, path)
        # the requirement does not mention a header, so ignore any row that is not an address
        rows = []
        with open(path, newline="") as f:
            for r in csv.reader(f):
                try:
                    rows.append(str(ipaddress.IPv4Address(r[0].strip())))
                except (IndexError, ValueError):
                    pass
        return rows

    def test_witness_every_address_in_range(self):
        # Lexical: every address of the network, network and broadcast addresses included
        self.assertEqual(self._rows("192.168.0.0/30"),
                         ["192.168.0.0", "192.168.0.1", "192.168.0.2", "192.168.0.3"])

    def test_witness_numeric_order(self):
        # Vagueness: rows in the network's natural (numeric) order, not text order
        self.assertEqual(self._rows("10.0.0.0/28"),
                         [str(ip) for ip in ipaddress.IPv4Network("10.0.0.0/28")])
