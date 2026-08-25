from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
PBI01_ACCEPTED_BASE = "499cd611605380a3f2abca1e3e1d2f27cc56301c"
PBI01_MANIFEST_PATH = "governance/tasks/PBI-01.michigan-customer-geography-power-bi-mvp.task.json"
PBI01_MANIFEST_BLOB_ID = "23ecf6512e310d151ffdf1b43d555e13faab3efb"


class Pbi02FailClosedConformanceTests(unittest.TestCase):
    def test_exactly_one_manifest_and_work_order_record_blocker(self) -> None:
        manifests = list((REPOSITORY / "governance/tasks").glob("PBI-02*.task.json"))
        work_orders = list((REPOSITORY / "docs/work_orders").glob("PBI_02*.md"))
        self.assertEqual((len(manifests), len(work_orders)), (1, 1))
        task = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(
            (task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"]),
            ("BLOCKED_FAIL_CLOSED", "BLOCKED", "NOT_REVIEWED"),
        )
        self.assertNotIn("implementation_commit", task)
        self.assertEqual(task["exact_next_destination"], "PBI: Power BI Decisions & Acceptance")

    def test_canary_is_synthetic_and_explicitly_not_passed(self) -> None:
        text = (REPOSITORY / "docs/pbi02/AZURE_MAPS_CANARY.md").read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC_ONLY", text)
        self.assertIn("To display Azure Maps visuals, sign in.", text)
        self.assertIn("canary is **not established**", text)
        self.assertIn("never connected to Azure Maps", text)
        self.assertNotIn("canary passed", text.lower())

    def test_pbi01_acceptance_record_remains_byte_identical(self) -> None:
        blob_id = subprocess.run(
            ["git", "rev-parse", f"HEAD:{PBI01_MANIFEST_PATH}"],
            cwd=REPOSITORY,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        diff = subprocess.run(
            ["git", "diff", "--quiet", PBI01_ACCEPTED_BASE, "--", PBI01_MANIFEST_PATH],
            cwd=REPOSITORY,
            check=False,
        )
        self.assertEqual(blob_id, PBI01_MANIFEST_BLOB_ID)
        self.assertEqual(diff.returncode, 0)

    def test_no_local_runtime_capture_or_binary_is_stageable(self) -> None:
        stageable = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=REPOSITORY,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        normalized = [path.replace("\\", "/") for path in stageable]
        self.assertFalse(any(path.startswith(("powerbi/pbi01/local/", "powerbi/pbi01/runtime/")) for path in normalized))
        self.assertFalse(any(path.lower().endswith((".pbix", ".pbit", ".pcap", ".pcapng", ".har")) for path in normalized))


if __name__ == "__main__":
    unittest.main()
