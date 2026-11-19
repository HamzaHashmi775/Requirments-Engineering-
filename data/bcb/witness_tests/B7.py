# Supplementary witness test for BigCodeBench/6 (B7). The original 5 tests cannot tell the
# readings of B7's semantic ambiguity apart (every test pattern ends in '$', so re.match and
# re.fullmatch agree). This test checks only the ORIGINAL requirement's behaviour (as
# implemented by the reference solution, re.match) and runs for both prompt variants.
import os
import shutil
import tempfile
import unittest


class WitnessTests(unittest.TestCase):
    def test_witness_pattern_matches_name_prefix(self):
        # Semantic: the pattern only has to match from the start of the name (re.match),
        # not the whole name (re.fullmatch)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, "access.log.1"), "w") as f:
            f.write("x")
        self.assertEqual(task_func(r"^access\.log", d), os.path.join(d, "access.log.1"))
