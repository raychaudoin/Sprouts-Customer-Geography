from __future__ import annotations

import csv
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "src"))

from sprouts_customer_geography.app01.bundle import (  # noqa: E402
    EXPECTED_METRICS,
    SYNTHETIC_CANARY,
    SYNTHETIC_EVIDENCE_CANARY,
    SYNTHETIC_SELECTION_CANARY,
    SYNTHETIC_WARNING_CANARY,
    _type7,
    build_bundle_set,
)
from sprouts_customer_geography.app01.errors import App01Error  # noqa: E402
from sprouts_customer_geography.app01.inputs import (  # noqa: E402
    EXPECTED_DATA04_CANDIDATE_SHA256,
    EXPECTED_GEOMETRY_SHA256,
    _validate_data04_candidate,
    load_accepted_geometry,
    load_local_settings,
    resolve_data04,
    resolve_model13,
)
from sprouts_customer_geography.app01.server import App01Server, CSP  # noqa: E402
from sprouts_customer_geography.data04.contract import load_authority  # noqa: E402
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths  # noqa: E402
from tests.pbi01.test_pbi01_conformance import _write_synthetic_inputs  # noqa: E402


APP_JS = REPOSITORY / "presentation/app01/site/app.mjs"
INDEX_HTML = REPOSITORY / "presentation/app01/site/index.html"
RUNTIME_POLICY = REPOSITORY / "config/app01/app01_runtime_policy.json"
STAGE_GATE = REPOSITORY / "config/app01/app01_stage1_gate.json"
EXPECTED_NAMES = list(EXPECTED_METRICS)


def _temporary_directory() -> tempfile.TemporaryDirectory:
    base = Path(os.environ.get("APP01_TEST_TEMP_ROOT") or REPOSITORY / "outputs" / "app01-test-tmp")
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base)


class App01BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.first = build_bundle_set(REPOSITORY, synthetic=True)
        cls.second = build_bundle_set(REPOSITORY, synthetic=True)
        cls.presentation = json.loads(cls.first.presentation_bytes)
        cls.evidence = json.loads(cls.first.evidence_bytes)

    def test_synthetic_bundle_is_deterministic_and_exactly_reconciled(self) -> None:
        self.assertEqual(self.first.presentation_bytes, self.second.presentation_bytes)
        self.assertEqual(self.first.evidence_bytes, self.second.evidence_bytes)
        bundle = self.presentation
        self.assertEqual((bundle["tract_count"], len(bundle["rows"])), (3_017, 3_017))
        self.assertEqual((bundle["metric_count"], len(bundle["metrics"])), (16, 16))
        self.assertEqual(len({row["geoid"] for row in bundle["rows"]}), 3_017)
        self.assertEqual(sha256(self.first.geometry_bytes).hexdigest(), EXPECTED_GEOMETRY_SHA256)
        self.assertFalse(self.first.health["protected_values_served"])

    def test_exact_metric_order_scale_policy_and_prohibited_income_absence(self) -> None:
        metrics = self.presentation["metrics"]
        self.assertEqual([metric["display_name"] for metric in metrics], EXPECTED_NAMES)
        self.assertEqual([metric["sort_order"] for metric in metrics], list(range(1, 17)))
        fixed = [metric["metric_key"] for metric in metrics if metric["scale_policy"] == "fixed_0_100"]
        self.assertEqual(fixed, ["customer_fit_percentile", "modeled_target_mass_percentile"])
        self.assertFalse({"Average Household Income", "Area Median Income"}.intersection(EXPECTED_NAMES))

    def test_domains_are_fixed_or_type7_valid_only_and_stable(self) -> None:
        rows = self.presentation["rows"]
        for index, metric in enumerate(self.presentation["metrics"]):
            values = [row["values"][index] for row in rows if row["values"][index] is not None]
            domain = self.presentation["domains"][metric["metric_key"]]
            self.assertEqual(domain["valid_value_count"], len(values))
            if metric["scale_policy"] == "fixed_0_100":
                self.assertEqual((domain["minimum"], domain["maximum"]), (0.0, 100.0))
            else:
                self.assertAlmostEqual(domain["minimum"], _type7(values, 0.02), places=10)
                self.assertAlmostEqual(domain["maximum"], _type7(values, 0.98), places=10)
            availability = self.presentation["availability"][metric["metric_key"]]
            self.assertEqual(availability["available"] + availability["unavailable"], 3_017)

    def test_missing_noncomputable_support_and_quality_context_remain_explicit(self) -> None:
        bundle = self.presentation
        rows = {row["geoid"]: row for row in bundle["rows"]}
        audit = bundle["audit_states"]
        self.assertEqual(sum(row["computability_status"] != "MODEL_SCORE_COMPUTABLE" for row in rows.values()), 44)
        self.assertEqual(sum(row["support_truncation"] for row in rows.values()), 438)
        self.assertIsNone(rows[audit["model_warning_geoid"]]["values"][0])
        self.assertEqual(rows[audit["model_warning_geoid"]]["status_details"][0], SYNTHETIC_WARNING_CANARY)
        self.assertIsNone(rows[audit["data_unavailable_geoid"]]["values"][3])
        quality = rows[audit["quality_context_geoid"]]
        self.assertIsNotNone(quality["values"][11])
        self.assertIsNone(quality["moes"][11])
        self.assertEqual(quality["statuses"][11], "inapplicable")

    def test_canaries_cover_protected_shaped_paths_but_are_never_transmittable(self) -> None:
        canary = self.presentation["egress_canary"]
        self.assertTrue(canary["active"])
        self.assertFalse(canary["external_transmission_permitted"])
        for token in (SYNTHETIC_CANARY, SYNTHETIC_WARNING_CANARY, SYNTHETIC_SELECTION_CANARY, SYNTHETIC_EVIDENCE_CANARY):
            self.assertIn(token, self.first.presentation_bytes.decode("utf-8") + self.first.evidence_bytes.decode("utf-8"))
        self.assertTrue(self.evidence["local_only"])
        self.assertFalse(self.evidence["external_transmission_permitted"])


class App01InputAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.geometry = load_accepted_geometry(REPOSITORY)

    def test_model13_adapter_accepts_exact_synthetic_ready_package(self) -> None:
        with _temporary_directory() as directory:
            root = Path(directory)
            _write_synthetic_inputs(root)
            resolved = resolve_model13(REPOSITORY, self.geometry, [root])
        self.assertEqual((resolved.preflight.tract_count, resolved.preflight.computable_count, resolved.preflight.noncomputable_count), (3_017, 2_973, 44))
        self.assertEqual(resolved.preflight.support_truncation_count, 438)
        self.assertTrue(resolved.preflight.seed_context_ready)

    def test_model13_adapter_preserves_unavailable_radius_support_for_noncomputable_tracts(self) -> None:
        with _temporary_directory() as directory:
            root = Path(directory)
            paths = _write_synthetic_inputs(root)
            with paths["tract"].open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
                columns = list(rows[0])
            for row in rows[-44:]:
                row["support_truncation_3mi"] = ""
                row["support_truncation_5mi"] = ""
                row["support_truncation_7mi"] = ""
            with paths["tract"].open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
            metadata["tract_output"]["byte_sha256"] = sha256(paths["tract"].read_bytes()).hexdigest()
            paths["metadata"].write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            ready = json.loads(paths["ready"].read_text(encoding="utf-8"))
            ready["tract_csv_sha256"] = metadata["tract_output"]["byte_sha256"]
            ready["metadata_file_sha256"] = sha256(paths["metadata"].read_bytes()).hexdigest()
            paths["ready"].write_text(json.dumps(ready, indent=2) + "\n", encoding="utf-8")
            resolved = resolve_model13(REPOSITORY, self.geometry, [root])
        self.assertEqual(resolved.preflight.noncomputable_count, 44)
        self.assertTrue(all(row["support_truncation_5mi"] == "" for row in resolved.tract_rows[-44:]))

    def test_model13_adapter_preserves_unavailable_seed_context_values(self) -> None:
        with _temporary_directory() as directory:
            root = Path(directory)
            paths = _write_synthetic_inputs(root)
            with paths["seed"].open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
                columns = list(rows[0])
            for field in ("frozen_model12_prediction", "successor_oof_prediction", "successor_oof_absolute_log_error", "household_opportunity", "customer_fit_proxy", "modeled_target_mass"):
                rows[0][field] = ""
            with paths["seed"].open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
            metadata["seed_context_output"]["byte_sha256"] = sha256(paths["seed"].read_bytes()).hexdigest()
            paths["metadata"].write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            ready = json.loads(paths["ready"].read_text(encoding="utf-8"))
            ready["seed_context_csv_sha256"] = metadata["seed_context_output"]["byte_sha256"]
            ready["metadata_file_sha256"] = sha256(paths["metadata"].read_bytes()).hexdigest()
            paths["ready"].write_text(json.dumps(ready, indent=2) + "\n", encoding="utf-8")
            resolved = resolve_model13(REPOSITORY, self.geometry, [root])
        self.assertEqual(resolved.seed_rows[0]["frozen_model12_prediction"], "")

    def test_model13_equivalent_candidates_use_deterministic_selection(self) -> None:
        with _temporary_directory() as first_directory, _temporary_directory() as second_directory:
            first = Path(first_directory)
            second = Path(second_directory)
            _write_synthetic_inputs(first)
            _write_synthetic_inputs(second)
            resolved = resolve_model13(REPOSITORY, self.geometry, [first, second])
        self.assertEqual(resolved.candidate_count, 2)
        self.assertEqual(resolved.rejected_candidate_count, 0)

    def test_data04_equivalent_candidate_selection_and_disagreement_fail_closed(self) -> None:
        authority = load_authority(REPOSITORY)
        rows = [{"tract_geoid": geoid} for geoid in self.geometry.geoids]
        roots = [REPOSITORY / "outputs" / name for name in ("app01-fictional-z", "app01-fictional-a")]
        original_exists = Path.exists

        def candidate_exists(path: Path) -> bool:
            if path.name == "michigan_tract_candidate_measures.csv" and path.parent.name == "multivariate":
                return True
            return original_exists(path)

        with patch.object(Path, "exists", candidate_exists), patch(
            "sprouts_customer_geography.app01.inputs._validate_data04_candidate",
            return_value=(rows, ("same", EXPECTED_DATA04_CANDIDATE_SHA256)),
        ):
            resolved = resolve_data04(REPOSITORY, self.geometry, roots)
        self.assertEqual(resolved.candidate_count, 2)
        with patch.object(Path, "exists", candidate_exists), patch(
            "sprouts_customer_geography.app01.inputs._validate_data04_candidate",
            side_effect=[(rows, ("first",)), (rows, ("second",))],
        ):
            with self.assertRaisesRegex(App01Error, "APP01_DATA04_CANDIDATES_DISAGREE"):
                resolve_data04(REPOSITORY, self.geometry, roots)
        self.assertEqual(authority.contract["artifact_id"], "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1")

    def test_real_local_data04_candidates_satisfy_accepted_authority_when_present(self) -> None:
        settings = load_local_settings(REPOSITORY)
        if not settings.data04_candidates:
            self.skipTest("No ignored local DATA-04 package is available")
        resolved = resolve_data04(REPOSITORY, self.geometry, settings.data04_candidates)
        self.assertEqual((len(resolved.rows), len({row["tract_geoid"] for row in resolved.rows})), (3_017, 3_017))
        self.assertEqual(resolved.measure_ids, tuple(load_authority(REPOSITORY).data03_contract["output_contract"]["measure_order"]))


class App01RuntimePolicyAndUiTests(unittest.TestCase):
    def test_loopback_exact_egress_and_no_remote_observability(self) -> None:
        runtime = json.loads(RUNTIME_POLICY.read_text(encoding="utf-8"))
        self.assertEqual(runtime["topology"]["bind_host"], "127.0.0.1")
        self.assertFalse(runtime["topology"]["non_loopback_binding_permitted"])
        self.assertEqual(runtime["network_egress"]["allowed_external_hosts"], ["basemap.nationalmap.gov"])
        self.assertEqual(runtime["network_egress"]["allowed_external_methods"], ["GET"])
        self.assertFalse(any(runtime["telemetry"].values()))
        for vendor in runtime["renderer"]["vendored_files"]:
            self.assertEqual(sha256((REPOSITORY / vendor["path"]).read_bytes()).hexdigest(), vendor["sha256"])

    def test_ui_contains_required_views_controls_states_and_accessibility_cues(self) -> None:
        app = APP_JS.read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")
        for token in ("Color tracts by", "Topo", "Imagery + Labels", "Local neutral", "Select a tract", "QA &amp; Coverage", "Sprouts Evidence Context", "No Data / Unavailable", "Multiple tracts selected"):
            self.assertIn(token, app + html)
        for token in ("focus-visible", "prefers-reduced-motion", "aria-live", "aria-selected", "aria-label"):
            self.assertIn(token, app + html + (REPOSITORY / "presentation/app01/site/styles.css").read_text(encoding="utf-8"))
        self.assertIn('map.once("idle"', app)
        self.assertLess(app.index('map.once("idle"'), app.index('diagnostics.ready = true'))
        self.assertNotIn("Average Household Income", app + html)
        self.assertNotIn("Area Median Income", app + html)

    def test_request_policy_and_evidence_transition_are_fail_closed(self) -> None:
        app = APP_JS.read_text(encoding="utf-8")
        for token in ('resolved.protocol !== "https:"', 'resolved.hostname !== "basemap.nationalmap.gov"', "tilePathPattern.test", 'method: "GET"', 'credentials: "omit"', "APP01_EGRESS_CANARY_BLOCKED", "APP01_EXTERNAL_REQUEST_BLOCKED"):
            self.assertIn(token, app)
        enter = app.index("async function enterEvidence")
        exit_view = app.index("async function exitEvidence")
        enter_block = app[enter:exit_view]
        self.assertLess(enter_block.index("externalEgressEnabled = false"), enter_block.index("removeBasemap()"))
        self.assertLess(enter_block.index("removeBasemap()"), enter_block.index("loadEvidence()"))
        set_view = app.index("async function setView")
        exit_block = app[exit_view:set_view]
        self.assertLess(exit_block.index("map.jumpTo"), exit_block.index("externalEgressEnabled = true"))
        self.assertLess(exit_block.index("externalEgressEnabled = true"), exit_block.index("selectBasemap"))

    def test_stage_gate_records_final_ultra_completion_and_substantive_h(self) -> None:
        gate = json.loads(STAGE_GATE.read_text(encoding="utf-8"))
        self.assertTrue(gate["substantive_h_exists"])
        self.assertEqual(gate["state"], "ultra_complete")
        self.assertEqual(gate["exact_next_destination"], "ARCH: Presentation Architecture Decisions & Acceptance")
        self.assertTrue(all(gate["gates"].values()))


class App01ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundles = build_bundle_set(REPOSITORY, synthetic=True)
        cls.server = App01Server(("127.0.0.1", 0), cls.bundles, REPOSITORY)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def test_health_routes_and_security_headers(self) -> None:
        with urlopen(self._url("/health"), timeout=5) as response:
            body = json.loads(response.read())
            self.assertEqual((response.status, body["tract_count"], body["metric_count"]), (200, 3_017, 16))
            self.assertEqual(response.headers["Content-Security-Policy"], CSP)
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            self.assertNotIn("Python", response.headers.get("Server", ""))
        for route in ("/data/presentation.json", "/data/evidence.json", "/data/geometry.geojson", "/app.mjs", "/styles.css", "/vendor/maplibre-gl/maplibre-gl.mjs"):
            with self.subTest(route=route), urlopen(self._url(route), timeout=5) as response:
                self.assertEqual(response.status, 200)

    def test_unallowlisted_paths_queries_and_methods_are_rejected(self) -> None:
        for path, status in (("/not-found", 404), ("/../README.md", 404), ("/health?x=1", 400)):
            with self.subTest(path=path), self.assertRaises(HTTPError) as raised:
                urlopen(self._url(path), timeout=5)
            self.assertEqual(raised.exception.code, status)
        for method in ("HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            request = Request(self._url("/health"), data=None if method == "HEAD" else b"x", method=method)
            with self.subTest(method=method), self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 405)

    def test_non_loopback_host_header_is_rejected(self) -> None:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.putrequest("GET", "/health", skip_host=True)
        connection.putheader("Host", "example.invalid")
        connection.endheaders()
        response = connection.getresponse()
        response.read()
        connection.close()
        self.assertEqual(response.status, 403)

    def test_clean_restart_reconstructs_deterministically(self) -> None:
        expected = self.bundles.presentation_bytes
        for _ in range(2):
            server = App01Server(("127.0.0.1", 0), build_bundle_set(REPOSITORY, synthetic=True), REPOSITORY)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_address[1]
            try:
                with urlopen(f"http://127.0.0.1:{port}/data/presentation.json", timeout=5) as response:
                    self.assertEqual(response.read(), expected)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


class App01GovernanceAndDisclosureTests(unittest.TestCase):
    def test_exact_task_identity_branch_lane_and_h_posture(self) -> None:
        manifests = list((REPOSITORY / "governance/tasks").glob("APP-01*.task.json"))
        work_orders = list((REPOSITORY / "docs/work_orders").glob("APP_01*.md"))
        self.assertEqual((len(manifests), len(work_orders)), (1, 1))
        task = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(task["task_id"], "APP-01")
        self.assertEqual(task["implementation_branch"], "task/app-01-michigan-local-first-customer-geography-dashboard")
        self.assertEqual((task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"]), ("COMPLETED_AWAITING_ACCEPTANCE", "COMPLETED", "NOT_REVIEWED"))
        self.assertEqual(task["exact_next_destination"], "ARCH: Presentation Architecture Decisions & Acceptance")
        self.assertEqual(set(task["completion_state"]["implementation_evidence"]), {"LOCAL_COMMIT", "TEST_PASS", "COMPLETION_REPORT", "FUTURE_PULL_REQUEST"})
        self.assertNotIn("implementation_commit", task)
        self.assertNotIn("acceptance_disposition", task)
        self.assertNotIn("acceptance_metadata", task)

    def test_accepted_predecessors_remain_unchanged_from_authorization_base(self) -> None:
        protected = ["config/model", "config/data", "config/geo", "powerbi/pbi01", "presentation/arch01", "config/arch01", "governance/tasks/MODEL-13.michigan-benchmark-pooled-successor-statewide-scoring.task.json", "governance/tasks/DATA-04.michigan-public-data-parity-foundation.task.json", "governance/tasks/PBI-01.michigan-customer-geography-power-bi-mvp.task.json", "governance/tasks/ARCH-01.local-first-customer-geography-presentation-architecture.task.json"]
        changed = subprocess.run(["git", "diff", "--name-only", "b29be0c1c4faf173fc95f402446ddfd92f73f92c", "--", *protected], cwd=REPOSITORY, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(changed, [])

    def test_tracked_scope_contains_no_protected_runtime_paths_or_absolute_user_paths(self) -> None:
        stageable = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=REPOSITORY, check=True, capture_output=True, text=True).stdout.splitlines()
        assert_no_protected_tracked_paths(stageable)
        normalized = [path.replace("\\", "/") for path in stageable]
        self.assertFalse(any(path.startswith("presentation/app01/local/") for path in normalized))
        tracked_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for root in (REPOSITORY / "config/app01", REPOSITORY / "schemas/app01", REPOSITORY / "presentation/app01", REPOSITORY / "scripts/app01", REPOSITORY / "src/sprouts_customer_geography/app01")
            for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".json", ".md", ".html", ".css", ".mjs", ".py"}
        )
        self.assertNotIn("C:\\Users\\", tracked_text)
        self.assertNotIn("C:/Users/", tracked_text)

    def test_app01_json_documents_are_well_formed_and_schemas_are_strict(self) -> None:
        for path in [*list((REPOSITORY / "config/app01").glob("*.json")), *list((REPOSITORY / "schemas/app01").glob("*.json")), REPOSITORY / "presentation/app01/app01.local-settings.example.json"]:
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))
        runtime_schema = json.loads((REPOSITORY / "schemas/app01/runtime_policy.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(runtime_schema["additionalProperties"])
        self.assertFalse(runtime_schema["properties"]["network_egress"]["additionalProperties"])
        self.assertEqual(runtime_schema["properties"]["telemetry"]["properties"]["remote_logging"], {"const": False})


if __name__ == "__main__":
    unittest.main()
