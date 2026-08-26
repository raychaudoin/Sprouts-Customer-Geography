from __future__ import annotations

import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from scripts.pbi01.build_report import build_report
from scripts.pbi01.build_semantic_model import write_semantic_model
from sprouts_customer_geography.pbi01.preflight import Pbi01PreflightError, validate_model13_inputs
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths


CONTRACT_PATH = REPOSITORY / "config" / "model" / "model13_michigan_power_bi_output_contract.json"
GEOMETRY_PATH = REPOSITORY / "powerbi" / "pbi01" / "presentation" / "michigan_2024_tracts.geojson"
GEOMETRY_MANIFEST_PATH = REPOSITORY / "powerbi" / "pbi01" / "presentation" / "michigan_2024_tracts.manifest.json"
PROJECT_ROOT = REPOSITORY / "powerbi" / "pbi01" / "project"
PBI02_SUCCESSOR = (REPOSITORY / "governance/tasks/PBI-02.michigan-map-first-scouting-public-context-redesign.task.json").is_file()
EXPECTED_PAGES = (
    ["Michigan Opportunity Explorer", "Sprouts Evidence Context", "QA & Coverage", "Tract Tooltip"]
    if PBI02_SUCCESSOR
    else ["Michigan Opportunity Explorer", "Sprouts Evidence Context", "QA & Coverage"]
)
EXPECTED_VISUAL_TYPES = (
    {"textbox", "cardVisual", "slicer", "azureMap", "scatterChart", "tableEx"}
    if PBI02_SUCCESSOR
    else {"textbox", "cardVisual", "slicer", "shapeMap", "scatterChart", "tableEx", "clusteredBarChart"}
)


def _temporary_directory() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(dir=os.environ.get("PBI01_TEST_TEMP_ROOT") or None)


def _hash_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _geometry_geoids() -> list[str]:
    document = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
    return sorted(str(feature["properties"]["GEOID"]) for feature in document["features"])


def _write_synthetic_inputs(
    root: Path,
    *,
    duplicate_tract_geoid: bool = False,
    schema_drift: bool = False,
    corrupt_bound_hash: bool = False,
) -> dict[str, Path]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    tract_columns = list(contract["tract_output"]["columns"])
    if schema_drift:
        tract_columns.append("unexpected_column")
    seed_columns = list(contract["seed_context_output"]["columns"])
    paths = {
        "tract": root / contract["tract_output"]["filename"],
        "seed": root / contract["seed_context_output"]["filename"],
        "metadata": root / contract["metadata_output"]["filename"],
        "ready": root / "READY.json",
    }
    root.mkdir(parents=True, exist_ok=True)

    geoids = _geometry_geoids()
    if duplicate_tract_geoid:
        geoids[-1] = geoids[-2]
    with paths["tract"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tract_columns, lineterminator="\n")
        writer.writeheader()
        for index, geoid in enumerate(geoids):
            row = {column: "1" for column in tract_columns}
            row.update({
                "geoid": geoid,
                "internal_point_latitude": "44.0",
                "internal_point_longitude": "-85.0",
                "computability_status": "MODEL_SCORE_COMPUTABLE" if index < 2_973 else "MODEL_SCORE_NONCOMPUTABLE",
                "support_truncation_3mi": "True" if index < 438 else "False",
                "support_truncation_5mi": "True" if index < 438 else "False",
                "support_truncation_7mi": "True" if index < 438 else "False",
                "any_support_truncation": "True" if index < 438 else "False",
                "qa_missingness_status": "OK" if index < 2_973 else "FICTIONAL_NONCOMPUTABLE",
                "model_lineage_id": "fictional-model-lineage",
                "public_lineage_id": "fictional-public-lineage",
            })
            if schema_drift:
                row["unexpected_column"] = "fictional"
            writer.writerow(row)

    with paths["seed"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=seed_columns, lineterminator="\n")
        writer.writeheader()
        for index in range(2):
            row = {column: "1" for column in seed_columns}
            row.update({
                "protected_physical_location_id": f"fictional-location-{index + 1:03d}",
                "latitude": str(44.0 + index * 0.1),
                "longitude": str(-85.0 - index * 0.1),
                "support_truncation": "False",
                "qa_status": "OK",
                "model_lineage_id": "fictional-model-lineage",
            })
            writer.writerow(row)

    metadata = {
        "metadata_id": "MODEL13_MICHIGAN_POWER_BI_METADATA_V1",
        "version": "1.0.0",
        "state": "ready",
        "output_contract_id": "MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1",
        "model_lineage_id": "fictional-model-lineage",
        "public_lineage_id": "fictional-public-lineage",
        "tract_output": {
            "filename": contract["tract_output"]["filename"],
            "row_count": 3_017,
            "computable_count": 2_973,
            "noncomputable_count": 44,
            "support_truncation_count": 438,
            "byte_sha256": _hash_file(paths["tract"]),
        },
        "seed_context_output": {
            "filename": contract["seed_context_output"]["filename"],
            "row_count": 2,
            "fitting_eligible_count": 2,
            "fitting_excluded_count": 0,
            "byte_sha256": _hash_file(paths["seed"]),
        },
        "ready_written_last": True,
    }
    _write_json(paths["metadata"], metadata)
    ready = {
        "state": "ready",
        "finalization_state": "complete",
        "metadata_file_sha256": _hash_file(paths["metadata"]),
        "tract_csv_sha256": _hash_file(paths["tract"]),
        "seed_context_csv_sha256": _hash_file(paths["seed"]),
        "ready_marker_written_last": True,
    }
    _write_json(paths["ready"], ready)
    if corrupt_bound_hash:
        paths["tract"].write_bytes(paths["tract"].read_bytes() + b"\n")
    return paths


def _tree_digest(root: Path) -> str:
    digest = sha256()
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class Pbi01InputContractTests(unittest.TestCase):
    def test_accepted_contract_schema_and_3017_accounting_pass(self) -> None:
        with _temporary_directory() as directory:
            paths = _write_synthetic_inputs(Path(directory))
            result = validate_model13_inputs(REPOSITORY, local_paths=paths, geometry_path=GEOMETRY_PATH)
        self.assertEqual(result.state, "READY")
        self.assertEqual((result.tract_count, result.computable_count, result.noncomputable_count), (3_017, 2_973, 44))
        self.assertEqual(result.support_truncation_count, 438)
        self.assertEqual(result.geometry_geoid_count, 3_017)
        self.assertTrue(result.seed_context_ready)

    def test_duplicate_tract_key_is_rejected(self) -> None:
        with _temporary_directory() as directory:
            paths = _write_synthetic_inputs(Path(directory), duplicate_tract_geoid=True)
            with self.assertRaisesRegex(Pbi01PreflightError, "PBI01_TRACT_DUPLICATE_GEOID"):
                validate_model13_inputs(REPOSITORY, local_paths=paths, geometry_path=GEOMETRY_PATH)

    def test_schema_drift_is_rejected(self) -> None:
        with _temporary_directory() as directory:
            paths = _write_synthetic_inputs(Path(directory), schema_drift=True)
            with self.assertRaisesRegex(Pbi01PreflightError, "PBI01_TRACT_INPUT_INVALID"):
                validate_model13_inputs(REPOSITORY, local_paths=paths, geometry_path=GEOMETRY_PATH)

    def test_hash_mismatch_fails_closed_before_row_use(self) -> None:
        with _temporary_directory() as directory:
            paths = _write_synthetic_inputs(Path(directory), corrupt_bound_hash=True)
            with self.assertRaisesRegex(Pbi01PreflightError, "PBI01_TRACT_HASH_MISMATCH"):
                validate_model13_inputs(REPOSITORY, local_paths=paths, geometry_path=GEOMETRY_PATH)

    def test_duplicate_geometry_key_is_rejected(self) -> None:
        with _temporary_directory() as directory:
            root = Path(directory)
            paths = _write_synthetic_inputs(root / "inputs")
            geometry = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
            geometry["features"][-1]["properties"]["GEOID"] = geometry["features"][0]["properties"]["GEOID"]
            duplicate_geometry = root / "duplicate.geojson"
            _write_json(duplicate_geometry, geometry)
            with self.assertRaisesRegex(Pbi01PreflightError, "PBI01_GEOMETRY_DUPLICATE_GEOID"):
                validate_model13_inputs(REPOSITORY, local_paths=paths, geometry_path=duplicate_geometry)


class Pbi01PresentationAndReconstructionTests(unittest.TestCase):
    def test_geometry_manifest_and_full_geoid_reconciliation(self) -> None:
        manifest = json.loads(GEOMETRY_MANIFEST_PATH.read_text(encoding="utf-8"))
        document = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
        geoids = [str(feature["properties"]["GEOID"]) for feature in document["features"]]
        self.assertEqual(manifest["artifact_id"], "PBI01_MICHIGAN_2024_TIGER_TRACT_PRESENTATION_GEOMETRY_V1")
        self.assertTrue(manifest["presentation_only"])
        self.assertFalse(manifest["analytical_gis_logic_in_power_bi"])
        self.assertEqual((len(geoids), len(set(geoids))), (3_017, 3_017))
        canonical_bytes = GEOMETRY_PATH.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(manifest["output_byte_sha256"], sha256(canonical_bytes).hexdigest())

    def test_pbip_pbir_tmdl_reconstruction_inventory(self) -> None:
        pbip = json.loads((PROJECT_ROOT / "MICustomerGeography.pbip").read_text(encoding="utf-8"))
        self.assertEqual(pbip["artifacts"], [{"report": {"path": "MICustomerGeography.Report"}}])
        definition_pbir = json.loads((PROJECT_ROOT / "MICustomerGeography.Report" / "definition.pbir").read_text(encoding="utf-8"))
        self.assertEqual(definition_pbir["datasetReference"]["byPath"]["path"], "../MICustomerGeography.SemanticModel")

        pages_root = PROJECT_ROOT / "MICustomerGeography.Report" / "definition" / "pages"
        page_order = json.loads((pages_root / "pages.json").read_text(encoding="utf-8"))["pageOrder"]
        pages = [json.loads((pages_root / page_id / "page.json").read_text(encoding="utf-8")) for page_id in page_order]
        self.assertEqual([page["displayName"] for page in pages], EXPECTED_PAGES)
        visuals = [json.loads(path.read_text(encoding="utf-8")) for path in pages_root.glob("*/visuals/*/visual.json")]
        visual_types = [visual["visual"]["visualType"] for visual in visuals]
        self.assertEqual(len(visuals), 39 if PBI02_SUCCESSOR else 33)
        self.assertEqual(set(visual_types), EXPECTED_VISUAL_TYPES)
        self.assertEqual(visual_types.count("shapeMap"), 0 if PBI02_SUCCESSOR else 2)
        self.assertEqual(visual_types.count("scatterChart"), 1)
        self.assertEqual(visual_types.count("azureMap"), 1 if PBI02_SUCCESSOR else 0)
        for visual in (item for item in visuals if item["visual"]["visualType"] == "shapeMap"):
            self.assertEqual(set(visual["visual"]["query"]["queryState"]), {"Category", "Value", "Tooltips"})
            resource = visual["visual"]["objects"]["shape"][0]["properties"]["map"]["geoJson"]["content"]["expr"]["ResourcePackageItem"]
            self.assertEqual(resource, {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": "michigan_2024_tracts.geojson"})

        tables = PROJECT_ROOT / "MICustomerGeography.SemanticModel" / "definition" / "tables"
        tract_tmdl = (tables / "Michigan Tracts.tmdl").read_text(encoding="utf-8")
        seed_tmdl = (tables / "Seed Context.tmdl").read_text(encoding="utf-8")
        measures_tmdl = (tables / "Report Measures.tmdl").read_text(encoding="utf-8")
        self.assertEqual(tract_tmdl.count("__PBI01_TRACT_CSV__"), 1)
        self.assertEqual(seed_tmdl.count("__PBI01_SEED_CSV__"), 1)
        self.assertIn("measure 'Selected Metric Value' = ```", measures_tmdl)
        self.assertNotRegex(tract_tmdl + seed_tmdl, r"File\.Contents\(\"(?:[A-Za-z]:[\\/]|/)")

    def test_report_and_semantic_generators_are_deterministic(self) -> None:
        with _temporary_directory() as directory:
            root = Path(directory)
            report_target = root / "powerbi" / "pbi01" / "project" / "MICustomerGeography.Report"
            semantic_target = root / "powerbi" / "pbi01" / "project" / "MICustomerGeography.SemanticModel"
            presentation_target = root / "powerbi" / "pbi01" / "presentation"
            shutil.copytree(PROJECT_ROOT / "MICustomerGeography.Report", report_target, ignore=shutil.ignore_patterns(".pbi"))
            shutil.copytree(PROJECT_ROOT / "MICustomerGeography.SemanticModel", semantic_target, ignore=shutil.ignore_patterns(".pbi"))
            presentation_target.mkdir(parents=True)
            shutil.copyfile(GEOMETRY_PATH, presentation_target / GEOMETRY_PATH.name)

            build_report(root)
            write_semantic_model(root)
            first = (_tree_digest(report_target), _tree_digest(semantic_target))
            build_report(root)
            write_semantic_model(root)
            second = (_tree_digest(report_target), _tree_digest(semantic_target))
        self.assertEqual(first, second)


class Pbi01DisclosureSafeguardTests(unittest.TestCase):
    def test_protected_local_runtime_and_power_bi_state_are_ignored(self) -> None:
        candidates = [
            "powerbi/pbi01/local/model13/tract/model13_michigan_tract_scores.csv",
            "powerbi/pbi01/local/model13/seed-context/model13_michigan_seed_context.csv",
            "powerbi/pbi01/local/model13/metadata/model13_michigan_power_bi_metadata.json",
            "powerbi/pbi01/runtime/run/MICustomerGeography.pbip",
            "powerbi/pbi01/project/MICustomerGeography.pbix",
            "powerbi/pbi01/project/MICustomerGeography.SemanticModel/.pbi/cache.abf",
            "powerbi/pbi01/project/MICustomerGeography.SemanticModel/.pbi/editorSettings.json",
        ]
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                result = subprocess.run(["git", "check-ignore", "--quiet", candidate], cwd=REPOSITORY)
                self.assertEqual(result.returncode, 0)

    def test_stageable_inventory_contains_no_protected_rows_paths_or_binary_report(self) -> None:
        stageable = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=REPOSITORY,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        assert_no_protected_tracked_paths(stageable)
        normalized = [path.replace("\\", "/") for path in stageable]
        self.assertFalse(any(path.startswith(("powerbi/pbi01/local/", "powerbi/pbi01/runtime/")) for path in normalized))
        self.assertFalse(any(path.lower().endswith((".pbix", ".pbit", ".png", ".jpg", ".jpeg")) for path in normalized if path.startswith("powerbi/pbi01/")))
        project_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in PROJECT_ROOT.rglob("*")
            if path.is_file() and ".pbi" not in path.parts and path.suffix.lower() in {".json", ".tmdl", ".pbir", ".pbip", ".pbism"}
        )
        self.assertNotRegex(project_text, r"(?i)File\.Contents\(\"(?:[A-Za-z]:[\\/]|/)")
        self.assertNotIn("C:\\Users\\", project_text)
        self.assertNotIn("C:/Users/", project_text)

    def test_exactly_one_manifest_and_work_order(self) -> None:
        manifests = list((REPOSITORY / "governance" / "tasks").glob("PBI-01*.task.json"))
        work_orders = list((REPOSITORY / "docs" / "work_orders").glob("PBI_01*.md"))
        self.assertEqual((len(manifests), len(work_orders)), (1, 1))


if __name__ == "__main__":
    unittest.main()
