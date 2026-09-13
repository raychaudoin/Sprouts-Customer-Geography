"""CI package staging is ignored; canonical source stays disclosure-checked."""
from pathlib import Path
import subprocess
import unittest


class BuildStagingTests(unittest.TestCase):
    def test_setuptools_copy_is_ignored_but_canonical_source_is_not(self):
        root = Path(__file__).resolve().parents[1]
        source = "src/sprouts_customer_geography/model16/intake.py"
        staged = "build/lib/sprouts_customer_geography/model16/intake.py"
        # --no-index checks ignore policy even for the tracked canonical file;
        # neither path needs to be created or modified for this regression.
        result = subprocess.run(["git", "check-ignore", "--no-index", "--", staged, source],
                                cwd=root, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [staged])


if __name__ == "__main__":
    unittest.main()
