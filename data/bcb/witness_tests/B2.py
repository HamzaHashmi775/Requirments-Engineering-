# Supplementary witness tests for BigCodeBench/7 (B2). The original 7 tests cannot tell the
# readings of B2's two ambiguities apart. These tests check only the ORIGINAL requirement's
# behaviour (as implemented by the reference solution) and run for both prompt variants.
import os
import unittest


class WitnessTests(unittest.TestCase):
    def _csv(self, rows):
        path = "witness_sales.csv"
        with open(path, "w", newline="") as f:
            f.write("product,quantity\n")
            for p, q in rows:
                f.write(f"{p},{q}\n")
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_witness_total_not_single_row(self):
        # Syntactic: rank by the accumulated total (B: 4 + 4 = 8), not by the largest single row (A: 5)
        self.assertEqual(task_func(self._csv([("A", 5), ("B", 4), ("B", 4)])), "B")

    def test_witness_tie_first_encountered(self):
        # Vagueness: on a tie the reference returns the product encountered first, not the alphabetical first
        self.assertEqual(task_func(self._csv([("Zeta", 5), ("Alpha", 5)])), "Zeta")
