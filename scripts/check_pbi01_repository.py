"""Repository-safe PBI-01 authority, reconstruction, and disclosure conformance."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys


AUTHORIZATION_BASE = "a7ee04bb6cd9710fa161858f0b5b2559565cfc9f"
EXACT_H = "f05643be7bc5bde94d7ff9778a21bc18d93466ad"
TASK_BRANCH = "task/pbi-01-michigan-customer-geography-power-bi-mvp"
CAPABILITY_OWNER = "PBI: Power BI Decisions & Acceptance"
MCR_DESTINATION = "MASTER CONTROL ROOM: Sprouts Customer Geography"
CONTRACT_ID = "MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1"
PROJECT_NAME = "MICustomerGeography"
EXPECTED_PAGES = [
    "Michigan Opportunity Explorer",
    "Sprouts Evidence Context",
    "QA & Coverage",
]
EXPECTED_VISUAL_TYPES = {
    "textbox",
    "cardVisual",
    "slicer",
    "shapeMap",
    "scatterChart",
    "tableEx",
    "clusteredBarChart",
}
REQUIRED = (
    "governance/tasks/PBI-01.michigan-customer-geography-power-bi-mvp.task.json",
    "docs/work_orders/PBI_01_MICHIGAN_CUSTOMER_GEOGRAPHY_POWER_BI_MVP.md",
    "docs/pbi01/README.md",
    "config/model/model13_michigan_power_bi_output_contract.json",
    "powerbi/pbi01/presentation/michigan_2024_tracts.geojson",
    "powerbi/pbi01/presentation/michigan_2024_tracts.manifest.json",
    "powerbi/pbi01/project/MICustomerGeography.pbip",
    "powerbi/pbi01/project/MICustomerGeography.Report/definition.pbir",
    "powerbi/pbi01/project/MICustomerGeography.Report/definition/report.json",
    "powerbi/pbi01/project/MICustomerGeography.Report/definition/pages/pages.json",
    "powerbi/pbi01/project/MICustomerGeography.SemanticModel/definition.pbism",
    "powerbi/pbi01/project/MICustomerGeography.SemanticModel/definition/model.tmdl",
    "powerbi/pbi01/project/MICustomerGeography.SemanticModel/definition/tables/Michigan Tracts.tmdl",
    "powerbi/pbi01/project/MICustomerGeography.SemanticModel/definition/tables/Seed Context.tmdl",
    "powerbi/pbi01/project/MICustomerGeography.SemanticModel/definition/tables/Metric Selector.tmdl",
    "powerbi/pbi01/project/MICustomerGeography.SemanticModel/definition/tables/Report Measures.tmdl",
    "scripts/pbi01/build_geometry.py",
    "scripts/pbi01/build_report.py",
    "scripts/pbi01/build_semantic_model.py",
    "scripts/pbi01/preflight.py",
    "scripts/pbi01/prepare_runtime.py",
    "src/sprouts_customer_geography/pbi01/geometry.py",
    "src/sprouts_customer_geography/pbi01/preflight.py",
    "tests/pbi01/test_pbi01_conformance.py",
)


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"PBI-01 repository JSON is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"PBI-01 repository JSON must be an object: {path}")
    return value


def _git_lines(repository: Path, *args: str) -> list[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()


def _assert_ignored(repository: Path, paths: list[str]) -> None:
    for path in paths:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", path],
            cwd=repository,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"PBI-01 protected/local path is not ignored: {path}")


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    pbi02_successor = (
        repository / "governance/tasks/PBI-02.michigan-map-first-scouting-public-context-redesign.task.json"
    ).is_file()
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"PBI-01 required repository files absent: {missing}")

    manifests = list((repository / "governance/tasks").glob("PBI-01*.task.json"))
    work_orders = list((repository / "docs/work_orders").glob("PBI_01*.md"))
    if len(manifests) != 1 or len(work_orders) != 1:
        raise SystemExit(
            "PBI-01 requires exactly one task manifest and one work order; "
            f"found {len(manifests)} and {len(work_orders)}"
        )
    task = load_and_validate_task_manifest(
        manifests[0], repository / "schemas/governance/task_manifest.schema.json"
    )
    if (
        task["task_id"] != "PBI-01"
        or task["capability_owner"] != CAPABILITY_OWNER
        or task["implementation_branch"] != TASK_BRANCH
        or task["acceptance_destination"] != CAPABILITY_OWNER
    ):
        raise SystemExit("PBI-01 task identity, branch, or acceptance owner differs")
    if AUTHORIZATION_BASE not in task["authority_source"]:
        raise SystemExit("PBI-01 canonical authorization base differs")
    posture = (
        task["state"],
        task["completion_state"]["execution"],
        task["completion_state"]["capability_acceptance"],
    )
    if posture not in {
        ("IN_PROGRESS", "IN_PROGRESS", "NOT_REVIEWED"),
        ("COMPLETED_AWAITING_ACCEPTANCE", "COMPLETED", "NOT_REVIEWED"),
        ("ACCEPTED_CLOSED", "COMPLETED", "ACCEPTED"),
    }:
        raise SystemExit(f"PBI-01 task posture is invalid: {posture}")
    expected_next_destination = MCR_DESTINATION if posture[0] == "ACCEPTED_CLOSED" else CAPABILITY_OWNER
    if task["exact_next_destination"] != expected_next_destination:
        raise SystemExit("PBI-01 exact next destination differs")
    if posture[0] in {"COMPLETED_AWAITING_ACCEPTANCE", "ACCEPTED_CLOSED"} and task["completion_state"]["implementation_evidence"] != [
        "LOCAL_COMMIT",
        "TEST_PASS",
        "COMPLETION_REPORT",
        "FUTURE_PULL_REQUEST",
    ]:
        raise SystemExit("PBI-01 exact-H implementation evidence differs")
    if posture[0] == "ACCEPTED_CLOSED" and (
        task.get("implementation_commit") != EXACT_H
        or task.get("acceptance_disposition") != "ACCEPTED"
        or task.get("acceptance_metadata")
        != {
            "capability_owner": CAPABILITY_OWNER,
            "recorded_by": CAPABILITY_OWNER,
            "recorded_on": "2026-08-25",
        }
    ):
        raise SystemExit("PBI-01 accepted exact-H record differs")

    contract = _load(repository / "config/model/model13_michigan_power_bi_output_contract.json")
    if contract.get("artifact_id") != CONTRACT_ID:
        raise SystemExit("PBI-01 accepted MODEL-13 contract identity differs")
    if contract.get("tract_output", {}).get("row_count") != 3_017:
        raise SystemExit("PBI-01 accepted tract accounting differs")

    project_root = repository / "powerbi/pbi01/project"
    report_root = project_root / f"{PROJECT_NAME}.Report"
    model_root = project_root / f"{PROJECT_NAME}.SemanticModel"
    pbip = _load(project_root / f"{PROJECT_NAME}.pbip")
    if pbip.get("artifacts") != [{"report": {"path": f"{PROJECT_NAME}.Report"}}]:
        raise SystemExit("PBI-01 PBIP report binding differs")
    definition_pbir = _load(report_root / "definition.pbir")
    if definition_pbir.get("datasetReference", {}).get("byPath", {}).get("path") != f"../{PROJECT_NAME}.SemanticModel":
        raise SystemExit("PBI-01 PBIR semantic-model path binding differs")

    geometry_path = repository / "powerbi/pbi01/presentation/michigan_2024_tracts.geojson"
    geometry_manifest = _load(repository / "powerbi/pbi01/presentation/michigan_2024_tracts.manifest.json")
    geometry_bytes = geometry_path.read_bytes()
    if geometry_manifest.get("artifact_id") != "PBI01_MICHIGAN_2024_TIGER_TRACT_PRESENTATION_GEOMETRY_V1":
        raise SystemExit("PBI-01 presentation-geometry identity differs")
    if geometry_manifest.get("presentation_only") is not True or geometry_manifest.get("analytical_gis_logic_in_power_bi") is not False:
        raise SystemExit("PBI-01 presentation-geometry analytical boundary differs")
    canonical_geometry_bytes = geometry_bytes.replace(b"\r\n", b"\n")
    if geometry_manifest.get("output_byte_sha256") != sha256(canonical_geometry_bytes).hexdigest():
        raise SystemExit("PBI-01 presentation-geometry hash differs")
    geometry = json.loads(geometry_bytes)
    features = geometry.get("features", []) if isinstance(geometry, dict) else []
    geoids = [str(feature.get("properties", {}).get("GEOID", "")) for feature in features]
    if len(geoids) != 3_017 or len(set(geoids)) != 3_017 or not all(re.fullmatch(r"26\d{9}", geoid) for geoid in geoids):
        raise SystemExit("PBI-01 presentation geometry is not exactly 3,017 unique Michigan tract GEOIDs")
    if geometry_manifest.get("tract_count") != 3_017 or geometry_manifest.get("unique_geoid_count") != 3_017:
        raise SystemExit("PBI-01 presentation-geometry manifest accounting differs")

    embedded_geometry = report_root / "StaticResources/RegisteredResources/michigan_2024_tracts.geojson"
    if embedded_geometry.read_bytes() != geometry_bytes:
        raise SystemExit("PBI-01 embedded Shape Map geometry differs from the tracked presentation artifact")
    report = _load(report_root / "definition/report.json")
    registered = [
        item
        for package in report.get("resourcePackages", [])
        if package.get("name") == "RegisteredResources"
        for item in package.get("items", [])
    ]
    if registered != [{"name": geometry_path.name, "path": geometry_path.name, "type": "ShapeMap"}]:
        raise SystemExit("PBI-01 report geometry resource registration differs")

    pages_root = report_root / "definition/pages"
    page_order = _load(pages_root / "pages.json").get("pageOrder", [])
    pages = [_load(pages_root / page_id / "page.json") for page_id in page_order]
    expected_pages = (
        ["Michigan Opportunity Explorer", "Sprouts Evidence Context", "QA & Coverage", "Tract Tooltip"]
        if pbi02_successor
        else EXPECTED_PAGES
    )
    if [page.get("displayName") for page in pages] != expected_pages:
        raise SystemExit("PBI-01 report page inventory or order differs")
    visual_documents = [
        _load(path)
        for page_id in page_order
        for path in sorted((pages_root / page_id / "visuals").glob("*/visual.json"))
    ]
    visual_types = [document.get("visual", {}).get("visualType") for document in visual_documents]
    if pbi02_successor:
        successor_types = {"textbox", "cardVisual", "slicer", "azureMap", "scatterChart", "tableEx"}
        if len(visual_types) != 39 or set(visual_types) != successor_types:
            raise SystemExit(
                f"PBI-01 successor built-in visual inventory differs: {len(visual_types)}, {sorted(set(visual_types))}"
            )
        if visual_types.count("azureMap") != 1 or visual_types.count("shapeMap") != 0 or visual_types.count("scatterChart") != 1:
            raise SystemExit("PBI-01 successor spatial visual inventory differs")
        forbidden_visuals = {"map", "filledMap", "arcGisMap", "esriVisual"}
        if forbidden_visuals.intersection(value for value in visual_types if isinstance(value, str)):
            raise SystemExit("PBI-01 successor introduced an ungoverned map visual")
    else:
        if len(visual_types) != 33 or set(visual_types) != EXPECTED_VISUAL_TYPES:
            raise SystemExit(f"PBI-01 built-in visual inventory differs: {len(visual_types)}, {sorted(set(visual_types))}")
        if visual_types.count("shapeMap") != 2 or visual_types.count("scatterChart") != 1:
            raise SystemExit("PBI-01 spatial visual inventory differs")
        forbidden_visuals = {"azureMap", "map", "filledMap", "arcGisMap", "esriVisual"}
        if forbidden_visuals.intersection(value for value in visual_types if isinstance(value, str)):
            raise SystemExit("PBI-01 report depends on an external-service map visual")
        for document in (item for item in visual_documents if item.get("visual", {}).get("visualType") == "shapeMap"):
            visual = document["visual"]
            if set(visual.get("query", {}).get("queryState", {})) != {"Category", "Value", "Tooltips"}:
                raise SystemExit("PBI-01 Shape Map role binding differs")
            resource = (
                visual.get("objects", {})
                .get("shape", [{}])[0]
                .get("properties", {})
                .get("map", {})
                .get("geoJson", {})
                .get("content", {})
                .get("expr", {})
                .get("ResourcePackageItem")
            )
            if resource != {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": geometry_path.name}:
                raise SystemExit("PBI-01 Shape Map does not bind the deterministic registered geometry")

    table_root = model_root / "definition/tables"
    expected_tables = {
        "Metric Selector.tmdl",
        "Michigan Tracts.tmdl",
        "Report Measures.tmdl",
        "Seed Context.tmdl",
    }
    actual_tables = {path.name for path in table_root.glob("*.tmdl")}
    if (pbi02_successor and not expected_tables.issubset(actual_tables)) or (
        not pbi02_successor and actual_tables != expected_tables
    ):
        raise SystemExit("PBI-01 TMDL baseline table inventory differs")
    tract_tmdl = (table_root / "Michigan Tracts.tmdl").read_text(encoding="utf-8")
    seed_tmdl = (table_root / "Seed Context.tmdl").read_text(encoding="utf-8")
    model_text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(model_root.rglob("*.tmdl")))
    if tract_tmdl.count("__PBI01_TRACT_CSV__") != 1 or seed_tmdl.count("__PBI01_SEED_CSV__") != 1:
        raise SystemExit("PBI-01 protected source tokens differ")
    if re.search(r"(?i)File\.Contents\(\"(?:[A-Za-z]:[\\/]|/)", model_text):
        raise SystemExit("PBI-01 tracked TMDL contains an absolute source path")

    _assert_ignored(
        repository,
        [
            "powerbi/pbi01/local/model13/tract/model13_michigan_tract_scores.csv",
            "powerbi/pbi01/local/model13/seed-context/model13_michigan_seed_context.csv",
            "powerbi/pbi01/local/model13/metadata/model13_michigan_power_bi_metadata.json",
            "powerbi/pbi01/runtime/run/MICustomerGeography.pbip",
            "powerbi/pbi01/project/MICustomerGeography.pbix",
            "powerbi/pbi01/project/MICustomerGeography.SemanticModel/.pbi/cache.abf",
            "powerbi/pbi01/project/MICustomerGeography.SemanticModel/.pbi/editorSettings.json",
        ],
    )
    stageable = _git_lines(repository, "ls-files", "--cached", "--others", "--exclude-standard")
    assert_no_protected_tracked_paths(stageable)
    normalized = [path.replace("\\", "/") for path in stageable]
    forbidden_paths = [
        path
        for path in normalized
        if path.startswith(("powerbi/pbi01/local/", "powerbi/pbi01/runtime/"))
        or (path.startswith("powerbi/pbi01/") and path.lower().endswith((".pbix", ".pbit", ".png", ".jpg", ".jpeg")))
        or "/.pbi/" in path.lower()
    ]
    if forbidden_paths:
        raise SystemExit(f"PBI-01 protected/local artifacts became stageable: {forbidden_paths}")

    project_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted(project_root.rglob("*"))
        if path.is_file()
        and ".pbi" not in [part.lower() for part in path.parts]
        and path.suffix.lower() in {".json", ".tmdl", ".pbir", ".pbip", ".pbism", ".md"}
    )
    forbidden_fragments = ("C:" + "\\Users\\", "C:/Users/", "powerbi/pbi01/local/model13/", "powerbi/pbi01/runtime/")
    if any(fragment.lower() in project_text.lower() for fragment in forbidden_fragments):
        raise SystemExit("PBI-01 protected/local path entered tracked project definitions")

    workflow = (repository / ".github/workflows/repository-validation.yml").read_text(encoding="utf-8")
    if "python scripts/check_pbi01_repository.py" not in workflow or "PBI01_TEST_TEMP_ROOT" not in workflow:
        raise SystemExit("PBI-01 checker or test temp root is absent from Repository Validation")

    print(
        json.dumps(
            {
                "state": "passed",
                "task_posture": posture,
                "contract_id": CONTRACT_ID,
                "representation": "PBIP/PBIR/TMDL",
                "page_count": len(pages),
                "visual_count": len(visual_types),
                "shape_map_count": visual_types.count("shapeMap"),
                "pbi02_successor_active": pbi02_successor,
                "seed_coordinate_view_count": visual_types.count("scatterChart"),
                "presentation_geometry_geoid_count": len(geoids),
                "protected_tracked_path_guard": "passed",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
