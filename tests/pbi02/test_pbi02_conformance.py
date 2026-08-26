from __future__ import annotations

import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from scripts.pbi02.build_report import build_report
from scripts.pbi02.build_semantic_model import write_semantic_model
from sprouts_customer_geography.pbi02.preflight import (
    EXPECTED_CANDIDATE_COLUMNS,
    MEASURE_IDS,
    Pbi02PreflightError,
    validate_pbi02_inputs,
)
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths
from tests.pbi01.test_pbi01_conformance import _write_synthetic_inputs as _write_synthetic_model13


PROJECT_ROOT = REPOSITORY / "powerbi" / "pbi01" / "project"
GEOMETRY_PATH = REPOSITORY / "powerbi" / "pbi01" / "presentation" / "michigan_2024_tracts.geojson"
CATALOG_PATH = REPOSITORY / "config" / "pbi" / "pbi02_metric_catalog.json"
PBI01_ACCEPTED_BASE = "499cd611605380a3f2abca1e3e1d2f27cc56301c"
PBI01_MANIFEST_PATH = "governance/tasks/PBI-01.michigan-customer-geography-power-bi-mvp.task.json"
PBI01_MANIFEST_BLOB_ID = "23ecf6512e310d151ffdf1b43d555e13faab3efb"
EXPECTED_METRICS = [
    "Customer Fit Percentile",
    "5-Mile Household Opportunity",
    "Modeled Target Mass Percentile",
    "Median Household Income",
    "Per Capita Income",
    "Civilian Labor Force Share",
    "Employment Rate",
    "Bachelor's Degree or Higher Share",
    "Owner-Occupied Housing Share",
    "Vacant Housing Unit Share",
    "Median Home Value",
    "Median Gross Rent",
    "Average Household Size",
    "No-Vehicle Household Share",
    "Drive-Alone Commuter Share",
    "Work-from-Home Commuter Share",
]
EXPECTED_PAGES = [
    "Michigan Opportunity Explorer",
    "Sprouts Evidence Context",
    "QA & Coverage",
    "Tract Tooltip",
]


def _temporary_directory() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(dir=os.environ.get("PBI02_TEST_TEMP_ROOT") or None)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _geometry_geoids() -> list[str]:
    geometry = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
    return sorted(str(feature["properties"]["GEOID"]) for feature in geometry["features"])


def _write_synthetic_data04(
    root: Path,
    *,
    duplicate_geoid: bool = False,
    schema_drift: bool = False,
    blank_valid_estimate: bool = False,
    reconciliation_mismatch: bool = False,
    corrupt_bound_hash: bool = False,
) -> tuple[Path, str]:
    candidate = root / "multivariate" / "michigan_tract_candidate_measures.csv"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    columns = list(EXPECTED_CANDIDATE_COLUMNS)
    written_columns = columns + (["unexpected_column"] if schema_drift else [])
    geoids = _geometry_geoids()
    if duplicate_geoid:
        geoids[-1] = geoids[-2]
    if reconciliation_mismatch:
        geoids[-1] = "26999999999"

    with candidate.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=written_columns, lineterminator="\n")
        writer.writeheader()
        for index, geoid in enumerate(geoids):
            row: dict[str, str] = {
                "tract_geoid": geoid,
                "state_fips": geoid[:2],
                "county_fips": geoid[2:5],
                "tract_code": geoid[5:],
            }
            for measure_id in MEASURE_IDS:
                row[f"{measure_id}_estimate"] = str(index + 1)
                row[f"{measure_id}_moe"] = "1"
                row[f"{measure_id}_status"] = "valid"
                row[f"{measure_id}_status_detail"] = "fictional valid test value"
            if blank_valid_estimate and index == 0:
                row[f"{MEASURE_IDS[0]}_estimate"] = ""
            if schema_drift:
                row["unexpected_column"] = "fictional"
            writer.writerow(row)

    candidate_hash = _file_hash(candidate)
    report = {
        "state": "VERIFIED",
        "contract_id": "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1",
        "contract_version": "1.0.0",
        "contract_content_sha256": "4818c91e70d64119391aecf57f7306cd5dd2b3c0e174abb9fdfec6730676155d",
        "multivariate_evidence": {
            "candidate_output": {
                "filename": candidate.name,
                "row_count": 3_017,
                "columns": columns,
                "byte_sha256": candidate_hash,
            }
        },
    }
    report_path = root / "verification_report.json"
    _write_json(report_path, report)
    ready = {
        "household_output_sha256": "fictional-household-hash",
        "multivariate_candidate_output_sha256": candidate_hash,
        "multivariate_normalized_output_sha256": "fictional-normalized-hash",
        "ready_marker_written_last": True,
        "report_filename": report_path.name,
        "report_sha256": _file_hash(report_path),
        "state": "READY",
        "tiger_output_sha256": "fictional-tiger-hash",
    }
    _write_json(root / "READY.json", ready)
    if corrupt_bound_hash:
        candidate.write_bytes(candidate.read_bytes() + b"\n")
    return root, candidate_hash


def _tree_digest(root: Path) -> str:
    digest = sha256()
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _literal(value: object) -> object:
    if not isinstance(value, dict):
        return None
    return value.get("expr", {}).get("Literal", {}).get("Value")


def _pages_and_visuals() -> tuple[dict[str, dict], dict[str, list[dict]]]:
    pages_root = PROJECT_ROOT / "MICustomerGeography.Report" / "definition" / "pages"
    order = json.loads((pages_root / "pages.json").read_text(encoding="utf-8"))["pageOrder"]
    pages = {page_id: json.loads((pages_root / page_id / "page.json").read_text(encoding="utf-8")) for page_id in order}
    visuals = {
        page_id: [json.loads(path.read_text(encoding="utf-8")) for path in sorted((pages_root / page_id / "visuals").glob("*/visual.json"))]
        for page_id in order
    }
    return pages, visuals


class Pbi02InputContractTests(unittest.TestCase):
    def _validate(self, root: Path, **data04_options: bool):
        model13_paths = _write_synthetic_model13(root / "model13")
        data04_root, candidate_hash = _write_synthetic_data04(root / "data04", **data04_options)
        return validate_pbi02_inputs(
            REPOSITORY,
            model13_paths=model13_paths,
            data04_root=data04_root,
            geometry_path=GEOMETRY_PATH,
            expected_candidate_sha256=candidate_hash,
        )

    def test_exact_synthetic_contracts_reconcile_3017_keys(self) -> None:
        with _temporary_directory() as directory:
            result = self._validate(Path(directory))
        self.assertEqual(result.state, "READY")
        self.assertEqual(
            (result.tract_count, result.public_context_unique_geoid_count, result.geometry_unique_geoid_count),
            (3_017, 3_017, 3_017),
        )
        self.assertTrue(result.one_to_one_relationship_eligible)
        self.assertTrue(result.no_missing_to_zero_mutation)

    def test_duplicate_public_geoid_fails_closed(self) -> None:
        with _temporary_directory() as directory:
            with self.assertRaisesRegex(Pbi02PreflightError, "PBI02_DATA04_DUPLICATE_GEOID"):
                self._validate(Path(directory), duplicate_geoid=True)

    def test_candidate_schema_drift_fails_closed(self) -> None:
        with _temporary_directory() as directory:
            with self.assertRaisesRegex(Pbi02PreflightError, "PBI02_DATA04_SCHEMA_MISMATCH"):
                self._validate(Path(directory), schema_drift=True)

    def test_blank_estimate_marked_valid_fails_closed(self) -> None:
        with _temporary_directory() as directory:
            with self.assertRaisesRegex(Pbi02PreflightError, "PBI02_DATA04_VALID_VALUE_INVALID"):
                self._validate(Path(directory), blank_valid_estimate=True)

    def test_cross_source_geoid_mismatch_fails_closed(self) -> None:
        with _temporary_directory() as directory:
            with self.assertRaisesRegex(Pbi02PreflightError, "PBI02_TRACT_RECONCILIATION_MISMATCH"):
                self._validate(Path(directory), reconciliation_mismatch=True)

    def test_candidate_hash_mismatch_fails_before_row_use(self) -> None:
        with _temporary_directory() as directory:
            with self.assertRaisesRegex(Pbi02PreflightError, "PBI02_DATA04_CANDIDATE_HASH_MISMATCH"):
                self._validate(Path(directory), corrupt_bound_hash=True)


class Pbi02CatalogAndPresentationTests(unittest.TestCase):
    def test_exact_16_metric_catalog_and_scale_policies(self) -> None:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        metrics = catalog["metrics"]
        self.assertEqual([metric["display_name"] for metric in metrics], EXPECTED_METRICS)
        self.assertEqual([metric["sort_order"] for metric in metrics], list(range(1, 17)))
        self.assertEqual(len({metric["metric_key"] for metric in metrics}), 16)
        self.assertEqual([metric["scale_policy"] for metric in metrics].count("fixed_0_100"), 2)
        self.assertEqual([metric["scale_policy"] for metric in metrics].count("statewide_valid_p02_p98"), 14)
        inventory = "\n".join(
            f"{metric['metric_key']}|{metric['display_name']}|{metric['short_name']}" for metric in metrics
        ).lower()
        self.assertNotIn("average household income", inventory)
        self.assertNotIn("area median income", inventory)
        for metric in metrics:
            for field in (
                "source_authority_id", "family", "unit", "format_policy", "definition", "interpretation",
                "source_label", "vintage_label", "availability_category", "contextual_warning_policy", "palette",
            ):
                self.assertTrue(metric[field], f"{metric['display_name']} missing {field}")

    def test_map_first_page_and_public_only_azure_maps_binding(self) -> None:
        pages, visual_by_page = _pages_and_visuals()
        ordered_pages = list(pages.values())
        self.assertEqual([page["displayName"] for page in ordered_pages], EXPECTED_PAGES)
        primary_id = next(page_id for page_id, page in pages.items() if page["displayName"] == EXPECTED_PAGES[0])
        all_visuals = [visual for values in visual_by_page.values() for visual in values]
        types = [visual["visual"]["visualType"] for visual in all_visuals]
        self.assertEqual(len(types), 39)
        self.assertEqual(types.count("azureMap"), 1)
        self.assertNotIn("shapeMap", types)
        azure_document = next(visual for visual in visual_by_page[primary_id] if visual["visual"]["visualType"] == "azureMap")
        self.assertEqual(
            azure_document["position"],
            {"x": 0, "y": 72, "z": 3000, "height": 1008, "width": 1440, "tabOrder": 3000},
        )
        query_state = azure_document["visual"]["query"]["queryState"]
        self.assertEqual(set(query_state), {"Category", "Tooltips"})
        category = query_state["Category"]["projections"][0]["field"]["Column"]
        self.assertEqual(category["Expression"]["SourceRef"]["Entity"], "Michigan Tracts")
        self.assertEqual(category["Property"], "GEOID")
        tooltip_text = json.dumps(query_state["Tooltips"], sort_keys=True).lower()
        self.assertIn("report measures", tooltip_text)
        for protected in ("seed", "latitude", "longitude", "sales", "prediction", "error", "path", "physical"):
            self.assertNotIn(protected, tooltip_text)

        objects = azure_document["visual"]["objects"]
        controls = objects["mapControls"][0]["properties"]
        self.assertEqual(_literal(controls["defaultStyle"]), "'road'")
        self.assertEqual(_literal(controls["showSelectionControl"]), "false")
        configured_keys = json.dumps(objects, sort_keys=True).lower()
        for prohibited in ("lasso", "routing", "traffic", "navigation", "drivetime", "drive_time"):
            self.assertNotIn(prohibited, configured_keys)
        layers = objects["referenceLayer"]
        resource = layers[0]["properties"]["additionalDatasource"]["geoJson"]["content"]["expr"]["ResourcePackageItem"]
        self.assertEqual(resource["ItemName"], "michigan_2024_tracts.geojson")
        self.assertEqual(_literal(layers[0]["properties"]["polygonStrokeWidth"]), "1L")
        fill = layers[1]["properties"]["polygonFillColor"]["solid"]["color"]["expr"]["Measure"]
        self.assertEqual((fill["Expression"]["SourceRef"]["Entity"], fill["Property"]), ("Report Measures", "Selected Metric Color"))

    def test_inspector_tooltip_qa_and_evidence_separation(self) -> None:
        pages, visual_by_page = _pages_and_visuals()
        by_name = {page["displayName"]: page_id for page_id, page in pages.items()}
        tooltip_page = pages[by_name["Tract Tooltip"]]
        self.assertEqual(
            (tooltip_page["type"], tooltip_page["displayOption"], tooltip_page["width"], tooltip_page["height"]),
            ("Tooltip", "ActualSize", 400, 300),
        )
        tooltip_visuals = visual_by_page[by_name["Tract Tooltip"]]
        self.assertEqual(len(tooltip_visuals), 4)
        self.assertEqual({visual["visual"]["visualType"] for visual in tooltip_visuals}, {"cardVisual"})
        evidence_types = [visual["visual"]["visualType"] for visual in visual_by_page[by_name["Sprouts Evidence Context"]]]
        self.assertEqual(evidence_types.count("scatterChart"), 1)
        self.assertNotIn("azureMap", evidence_types)
        primary_text = json.dumps(visual_by_page[by_name["Michigan Opportunity Explorer"]], sort_keys=True)
        for measure in ("Inspector Heading", "Inspector Selected Metric", "Inspector Warning", "Selected Tract Context"):
            self.assertIn(measure, primary_text)
        qa_text = json.dumps(visual_by_page[by_name["QA & Coverage"]], sort_keys=True)
        for measure in (
            "Selected Public Metric Available Tracts", "Selected Public Metric Unavailable Tracts",
            "Selected Public Metric QA", "Public Context Rows", "Public Context Reconciled Keys",
            "Public Context Relationship State",
        ):
            self.assertIn(measure, qa_text)

    def test_semantic_model_has_one_to_one_public_context_and_valid_only_scales(self) -> None:
        definition = PROJECT_ROOT / "MICustomerGeography.SemanticModel" / "definition"
        tables = definition / "tables"
        self.assertEqual(
            {path.name for path in tables.glob("*.tmdl")},
            {
                "Metric Selector.tmdl", "Michigan Public Context.tmdl", "Michigan Tracts.tmdl",
                "Presentation Scale.tmdl", "Report Measures.tmdl", "Seed Context.tmdl",
            },
        )
        public = (tables / "Michigan Public Context.tmdl").read_text(encoding="utf-8")
        scale = (tables / "Presentation Scale.tmdl").read_text(encoding="utf-8")
        measures = (tables / "Report Measures.tmdl").read_text(encoding="utf-8")
        relationships = (definition / "relationships.tmdl").read_text(encoding="utf-8")
        self.assertEqual(public.count("\n\tcolumn "), 56)
        self.assertEqual(public.count("__PBI02_PUBLIC_CONTEXT_CSV__"), 1)
        self.assertIn("fromCardinality: one", relationships)
        self.assertIn("toCardinality: one", relationships)
        self.assertIn("crossFilteringBehavior: bothDirections", relationships)
        self.assertEqual(scale.count("List.Percentile(V, 0.02)"), 14)
        self.assertEqual(scale.count("List.Percentile(V, 0.98)"), 14)
        self.assertEqual(scale.count('= "valid"'), 13)
        for phrase in (
            '"No Data / Unavailable"', 'SelectedCount = 0, "Select a tract"', '"Multiple tracts selected"',
            'StatusValue = "valid", BLANK()', "measure 'Tooltip Public Context'",
        ):
            self.assertIn(phrase, measures)
        self.assertNotIn("COALESCE(NumericValue, 0)", measures)

    def test_successor_generators_are_deterministic(self) -> None:
        with _temporary_directory() as directory:
            root = Path(directory)
            shutil.copytree(REPOSITORY / "config", root / "config")
            shutil.copytree(PROJECT_ROOT, root / "powerbi" / "pbi01" / "project", ignore=shutil.ignore_patterns(".pbi"))
            presentation = root / "powerbi" / "pbi01" / "presentation"
            presentation.mkdir(parents=True)
            shutil.copyfile(GEOMETRY_PATH, presentation / GEOMETRY_PATH.name)
            build_report(root)
            write_semantic_model(root)
            first = _tree_digest(root / "powerbi" / "pbi01" / "project")
            build_report(root)
            write_semantic_model(root)
            second = _tree_digest(root / "powerbi" / "pbi01" / "project")
        self.assertEqual(first, second)


class Pbi02GovernanceAndDisclosureTests(unittest.TestCase):
    def test_single_manifest_work_order_and_passed_synthetic_gate(self) -> None:
        manifests = list((REPOSITORY / "governance" / "tasks").glob("PBI-02*.task.json"))
        work_orders = list((REPOSITORY / "docs" / "work_orders").glob("PBI_02*.md"))
        self.assertEqual((len(manifests), len(work_orders)), (1, 1))
        task = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(
            (task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"]),
            ("BLOCKED_FAIL_CLOSED", "BLOCKED", "NOT_REVIEWED"),
        )
        self.assertNotIn("implementation_commit", task)
        self.assertEqual(task["exact_next_destination"], "PBI: Power BI Decisions & Acceptance")
        canary = (REPOSITORY / "docs" / "pbi02" / "AZURE_MAPS_CANARY.md").read_text(encoding="utf-8")
        self.assertIn("PASSED_SYNTHETIC_NONTRANSMISSION_GATE", canary)
        self.assertIn("69 requests, 68 to Azure Maps", canary)
        self.assertIn("Every sentinel count was zero", canary)
        self.assertIn("does not accept the capability", canary)

    def test_pbi01_acceptance_record_remains_byte_identical(self) -> None:
        blob_id = subprocess.run(
            ["git", "rev-parse", f"HEAD:{PBI01_MANIFEST_PATH}"], cwd=REPOSITORY, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        diff = subprocess.run(
            ["git", "diff", "--quiet", PBI01_ACCEPTED_BASE, "--", PBI01_MANIFEST_PATH],
            cwd=REPOSITORY, check=False,
        )
        self.assertEqual(blob_id, PBI01_MANIFEST_BLOB_ID)
        self.assertEqual(diff.returncode, 0)

    def test_no_local_runtime_capture_or_binary_is_stageable(self) -> None:
        for candidate in (
            "powerbi/pbi01/local/pbi02-synthetic-validation/model13_michigan_tract_scores.csv",
            "powerbi/pbi01/local/data04/multivariate/michigan_tract_candidate_measures.csv",
            "powerbi/pbi01/runtime/pbi02-run/MICustomerGeography.pbip",
            "powerbi/pbi01/local/pbi02-canary/raw-capture.har",
            "powerbi/pbi01/project/MICustomerGeography.pbix",
        ):
            self.assertEqual(subprocess.run(["git", "check-ignore", "--quiet", candidate], cwd=REPOSITORY).returncode, 0)
        stageable = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=REPOSITORY,
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        assert_no_protected_tracked_paths(stageable)
        normalized = [path.replace("\\", "/") for path in stageable]
        self.assertFalse(any(path.startswith(("powerbi/pbi01/local/", "powerbi/pbi01/runtime/", "outputs/data04-run-")) for path in normalized))
        self.assertFalse(any(path.lower().endswith((".pbix", ".pbit", ".pcap", ".pcapng", ".har")) for path in normalized))

    def test_repository_checker_passes(self) -> None:
        result = subprocess.run(
            ["python", "scripts/check_pbi02_repository.py"], cwd=REPOSITORY,
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
