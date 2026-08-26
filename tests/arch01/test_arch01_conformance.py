from __future__ import annotations

from hashlib import sha256
import http.client
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.arch01.build_synthetic_bundle import (
    CANARY,
    EXPECTED_GEOMETRY_SHA256,
    build_bundle,
    build_bundle_bytes,
    load_accepted_geometry_bytes,
    validate_bundle,
)
from scripts.arch01.serve_spike import Arch01Server, CSP


REPOSITORY = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPOSITORY / "config/arch01/arch01_metric_catalog.json"
RUNTIME_PATH = REPOSITORY / "config/arch01/arch01_runtime_policy.json"
APP_PATH = REPOSITORY / "presentation/arch01/site/app.mjs"
INDEX_PATH = REPOSITORY / "presentation/arch01/site/index.html"
EXPECTED_NAMES = [
    "Customer Fit Percentile", "5-Mile Household Opportunity", "Modeled Target Mass Percentile",
    "Median Household Income", "Per Capita Income", "Civilian Labor Force Share", "Employment Rate",
    "Bachelor's Degree or Higher Share", "Owner-Occupied Housing Share", "Vacant Housing Unit Share",
    "Median Home Value", "Median Gross Rent", "Average Household Size", "No-Vehicle Household Share",
    "Drive-Alone Commuter Share", "Work-from-Home Commuter Share",
]


class Arch01BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.bundle = build_bundle()

    def test_exact_metric_inventory_order_and_scale_policies(self) -> None:
        metrics = self.catalog["metrics"]
        self.assertEqual([metric["display_name"] for metric in metrics], EXPECTED_NAMES)
        self.assertEqual([metric["sort_order"] for metric in metrics], list(range(1, 17)))
        fixed = [metric["metric_key"] for metric in metrics if metric["scale_policy"] == "fixed_0_100"]
        self.assertEqual(fixed, ["customer_fit_percentile", "modeled_target_mass_percentile"])
        self.assertTrue(all(metric["scale_policy"] == "statewide_valid_p02_p98" for metric in metrics if metric["metric_key"] not in fixed))
        self.assertFalse({"Average Household Income", "Area Median Income"}.intersection(metric["display_name"] for metric in metrics))

    def test_bundle_is_deterministic_and_reconciles_exactly(self) -> None:
        first = build_bundle_bytes()
        second = build_bundle_bytes()
        self.assertEqual(first, second)
        validate_bundle(self.bundle)
        self.assertEqual((self.bundle["tract_count"], len(self.bundle["rows"])), (3017, 3017))
        self.assertEqual((self.bundle["metric_count"], len(self.bundle["metric_keys"])), (16, 16))
        self.assertEqual(len({row["geoid"] for row in self.bundle["rows"]}), 3017)
        self.assertEqual(self.bundle["source_bindings"]["geometry_sha256"], EXPECTED_GEOMETRY_SHA256)

    def test_missingness_support_and_valid_only_domains_are_explicit(self) -> None:
        rows = self.bundle["rows"]
        self.assertEqual(sum(row["support_truncation"] for row in rows), 438)
        for index, metric in enumerate(self.catalog["metrics"]):
            valid = [row["values"][index] for row in rows if row["statuses"][index] == "valid"]
            unavailable = [row for row in rows if row["statuses"][index] != "valid"]
            self.assertTrue(all(row["values"][index] is None for row in unavailable))
            domain = self.bundle["domains"][metric["metric_key"]]
            self.assertEqual(domain["valid_value_count"], len(valid))
            if metric["scale_policy"] == "fixed_0_100":
                self.assertEqual((domain["minimum"], domain["maximum"]), (0.0, 100.0))
                self.assertEqual(len(unavailable), 44)
            else:
                ordered = sorted(valid)
                position_low = (len(ordered) - 1) * .02
                position_high = (len(ordered) - 1) * .98
                def interpolate(position: float) -> float:
                    lower = int(position)
                    upper = min(lower + 1, len(ordered) - 1)
                    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
                self.assertAlmostEqual(domain["minimum"], round(interpolate(position_low), 6), places=6)
                self.assertAlmostEqual(domain["maximum"], round(interpolate(position_high), 6), places=6)
                self.assertLess(min(valid), domain["minimum"])
                self.assertGreater(max(valid), domain["maximum"])

    def test_canary_is_local_only_and_not_hardcoded_in_client(self) -> None:
        self.assertEqual(self.bundle["canary"], {"value": CANARY, "external_transmission_permitted": False})
        app = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn(CANARY, app)
        self.assertIn("bundle?.canary?.value", app)
        self.assertIn('resolved.hostname !== "basemap.nationalmap.gov"', app)
        self.assertIn('method: "GET"', app)


class Arch01RuntimePolicyTests(unittest.TestCase):
    def test_schemas_fail_closed_on_runtime_egress_and_binding_shape(self) -> None:
        runtime_schema = json.loads((REPOSITORY / "schemas/arch01/runtime_policy.schema.json").read_text(encoding="utf-8"))
        metric_schema = json.loads((REPOSITORY / "schemas/arch01/metric_catalog.schema.json").read_text(encoding="utf-8"))
        bundle_schema = json.loads((REPOSITORY / "schemas/arch01/presentation_bundle.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(runtime_schema["additionalProperties"])
        self.assertFalse(runtime_schema["$defs"]["network_egress"]["additionalProperties"])
        self.assertEqual(runtime_schema["$defs"]["network_egress"]["properties"]["allowed_external_hosts"]["prefixItems"], [{"const": "basemap.nationalmap.gov"}])
        self.assertEqual(runtime_schema["$defs"]["telemetry"]["properties"]["remote_logging"], {"const": False})
        input_options = metric_schema["$defs"]["metric"]["properties"]["input_binding"]["oneOf"]
        self.assertEqual(input_options[0]["not"], {"required": ["measure_id"]})
        self.assertEqual(input_options[1]["not"], {"required": ["column"]})
        self.assertEqual(bundle_schema["properties"]["source_bindings"]["properties"]["geometry_sha256"], {"const": EXPECTED_GEOMETRY_SHA256})

    def test_loopback_no_telemetry_and_exact_external_allowlist(self) -> None:
        runtime = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
        self.assertEqual(runtime["topology"]["default_bind_host"], "127.0.0.1")
        self.assertFalse(runtime["topology"]["non_loopback_binding_permitted"])
        self.assertEqual(runtime["network_egress"]["allowed_external_hosts"], ["basemap.nationalmap.gov"])
        self.assertEqual(runtime["network_egress"]["allowed_methods"], ["GET"])
        self.assertFalse(any(runtime["telemetry"][key] for key in ("application_telemetry", "analytics", "crash_reporting", "remote_logging")))
        for vendor in runtime["renderer"]["vendored_files"]:
            self.assertEqual(sha256((REPOSITORY / vendor["path"]).read_bytes()).hexdigest(), vendor["sha256"])

    def test_spike_exposes_required_interaction_and_context_concepts(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        html = INDEX_PATH.read_text(encoding="utf-8")
        for token in ("transformRequest", "tract-fill", "tract-selected", "shiftKey", "ctrlKey", "metaKey", "fillExpression", "No Data / Unavailable", "lastMetricSwitchMs", "lastSelectionMs"):
            self.assertIn(token, app)
        for token in ("metric-select", "basemap-select", "selection-content", "Technical QA", "legend-labels", "Local neutral"):
            self.assertIn(token, html)


class Arch01ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle_bytes = build_bundle_bytes()
        cls.geometry_bytes = load_accepted_geometry_bytes()
        cls.server = Arch01Server(("127.0.0.1", 0), cls.bundle_bytes, cls.geometry_bytes)
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

    def test_health_and_security_headers(self) -> None:
        with urlopen(self._url("/health"), timeout=5) as response:
            body = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(body["tract_count"], 3017)
            self.assertEqual(response.headers["Content-Security-Policy"], CSP)
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")

    def test_only_allowlisted_routes_and_no_query_strings(self) -> None:
        for path, status in (("/not-found", 404), ("/../README.md", 404), ("/health?x=1", 400)):
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as raised:
                    urlopen(self._url(path), timeout=5)
                self.assertEqual(raised.exception.code, status)

    def test_write_methods_are_rejected(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                with self.assertRaises(HTTPError) as raised:
                    urlopen(Request(self._url("/health"), data=b"x", method=method), timeout=5)
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

    def test_served_bundle_and_geometry_are_exact(self) -> None:
        with urlopen(self._url("/data/presentation.json"), timeout=5) as response:
            self.assertEqual(response.read(), self.bundle_bytes)
        with urlopen(self._url("/data/geometry.geojson"), timeout=5) as response:
            geometry = response.read()
        self.assertEqual(sha256(geometry).hexdigest(), EXPECTED_GEOMETRY_SHA256)

    def test_clean_restart_rebuilds_without_cache_or_repair(self) -> None:
        for _ in range(3):
            server = Arch01Server(("127.0.0.1", 0), build_bundle_bytes(), load_accepted_geometry_bytes())
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_address[1]
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
                    self.assertEqual(response.status, 200)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


class Arch01GovernanceTests(unittest.TestCase):
    def test_exactly_one_manifest_and_work_order(self) -> None:
        self.assertEqual(len(list((REPOSITORY / "governance/tasks").glob("ARCH-01*.task.json"))), 1)
        self.assertEqual(len(list((REPOSITORY / "docs/work_orders").glob("ARCH_01*.md"))), 1)


if __name__ == "__main__":
    unittest.main()
