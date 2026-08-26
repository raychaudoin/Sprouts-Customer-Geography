"""Repository-safe PBI-02 authority, map, model, and disclosure conformance."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable


TASK_BRANCH = "task/pbi-02-michigan-map-first-scouting-public-context-redesign"
CAPABILITY_OWNER = "PBI: Power BI Decisions & Acceptance"
PBI01_ACCEPTED_BASE = "499cd611605380a3f2abca1e3e1d2f27cc56301c"
PBI01_MANIFEST_PATH = "governance/tasks/PBI-01.michigan-customer-geography-power-bi-mvp.task.json"
PBI01_MANIFEST_BLOB_ID = "23ecf6512e310d151ffdf1b43d555e13faab3efb"
DATA04_CONTRACT_ID = "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1"
DATA04_CONTRACT_VERSION = "1.0.0"
DATA04_CONTRACT_SHA256 = "4818c91e70d64119391aecf57f7306cd5dd2b3c0e174abb9fdfec6730676155d"
DATA04_CANDIDATE_SHA256 = "adcc5ce6b08bb9973ccb5d76ac59162013d7db524e266d18585719581cca9198"
GEOMETRY_SHA256 = "e0f32095d2e2307f5ad78c9545fc0d3c74fca2250bc866bea8db2368848786ad"
PROJECT_NAME = "MICustomerGeography"
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
METADATA_FIELDS = {
    "metric_key",
    "source_authority_id",
    "family",
    "display_name",
    "short_name",
    "sort_order",
    "unit",
    "format_policy",
    "definition",
    "interpretation",
    "source_label",
    "vintage_label",
    "scale_policy",
    "availability_category",
    "contextual_warning_policy",
    "palette",
    "binding",
}
REQUIRED = (
    "governance/tasks/PBI-02.michigan-map-first-scouting-public-context-redesign.task.json",
    "docs/work_orders/PBI_02_MICHIGAN_MAP_FIRST_SCOUTING_PUBLIC_CONTEXT_REDESIGN.md",
    "docs/pbi02/AZURE_MAPS_CANARY.md",
    "docs/pbi02/README.md",
    "config/pbi/pbi02_metric_catalog.json",
    "schemas/pbi02/pbi02_metric_catalog.schema.json",
    "scripts/pbi02/build_project.py",
    "scripts/pbi02/build_report.py",
    "scripts/pbi02/build_semantic_model.py",
    "scripts/pbi02/preflight.py",
    "scripts/pbi02/prepare_runtime.py",
    "src/sprouts_customer_geography/pbi02/preflight.py",
    "tests/pbi02/test_pbi02_conformance.py",
    "powerbi/pbi01/project/MICustomerGeography.pbip",
    "powerbi/pbi01/project/MICustomerGeography.Report/definition.pbir",
    "powerbi/pbi01/project/MICustomerGeography.Report/definition/report.json",
    "powerbi/pbi01/project/MICustomerGeography.Report/definition/pages/pages.json",
    "powerbi/pbi01/project/MICustomerGeography.SemanticModel/definition/model.tmdl",
    "powerbi/pbi01/project/MICustomerGeography.SemanticModel/definition/relationships.tmdl",
)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"PBI-02 JSON is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"PBI-02 JSON must be an object: {path}")
    return value


def _git(repository: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repository, check=check, capture_output=True, text=True
    )


def _literal(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return value.get("expr", {}).get("Literal", {}).get("Value")


def _projections(visual: dict[str, Any]) -> Iterable[dict[str, Any]]:
    query_state = visual.get("visual", {}).get("query", {}).get("queryState", {})
    for role in query_state.values():
        if isinstance(role, dict):
            for projection in role.get("projections", []):
                if isinstance(projection, dict):
                    yield projection


def _projection_identity(projection: dict[str, Any]) -> tuple[str, str, str] | None:
    field = projection.get("field", {})
    for kind in ("Column", "Measure"):
        item = field.get(kind)
        if isinstance(item, dict):
            entity = item.get("Expression", {}).get("SourceRef", {}).get("Entity")
            prop = item.get("Property")
            if isinstance(entity, str) and isinstance(prop, str):
                return kind, entity, prop
    return None


def _keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key)
            yield from _keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _keys(nested)


def _assert_ignored(repository: Path, paths: Iterable[str]) -> None:
    for path in paths:
        if _git(repository, "check-ignore", "--quiet", path, check=False).returncode != 0:
            raise SystemExit(f"PBI-02 local/protected path is not ignored: {path}")


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.pbi02.preflight import EXPECTED_CANDIDATE_COLUMNS, MEASURE_IDS
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"PBI-02 required repository files absent: {missing}")
    manifests = list((repository / "governance/tasks").glob("PBI-02*.task.json"))
    work_orders = list((repository / "docs/work_orders").glob("PBI_02*.md"))
    if (len(manifests), len(work_orders)) != (1, 1):
        raise SystemExit("PBI-02 requires exactly one task manifest and one work order")
    task = load_and_validate_task_manifest(
        manifests[0], repository / "schemas/governance/task_manifest.schema.json"
    )
    if (
        task["task_id"] != "PBI-02"
        or task["implementation_branch"] != TASK_BRANCH
        or task["capability_owner"] != CAPABILITY_OWNER
        or task["acceptance_destination"] != CAPABILITY_OWNER
        or task["exact_next_destination"] != CAPABILITY_OWNER
    ):
        raise SystemExit("PBI-02 identity, branch, owner, or destination differs")
    posture = (
        task["state"],
        task["completion_state"]["execution"],
        task["completion_state"]["capability_acceptance"],
    )
    if posture not in {
        ("IN_PROGRESS", "IN_PROGRESS", "NOT_REVIEWED"),
        ("BLOCKED_FAIL_CLOSED", "BLOCKED", "NOT_REVIEWED"),
        ("COMPLETED_AWAITING_ACCEPTANCE", "COMPLETED", "NOT_REVIEWED"),
    }:
        raise SystemExit(f"PBI-02 governed posture differs: {posture}")
    if task.get("acceptance_disposition") or task.get("acceptance_metadata"):
        raise SystemExit("PBI-02 must not claim capability acceptance")

    head_blob = _git(repository, "rev-parse", f"HEAD:{PBI01_MANIFEST_PATH}").stdout.strip()
    worktree_blob = _git(repository, "hash-object", PBI01_MANIFEST_PATH).stdout.strip()
    pbi01_diff = _git(
        repository, "diff", "--quiet", PBI01_ACCEPTED_BASE, "--", PBI01_MANIFEST_PATH, check=False
    )
    if head_blob != PBI01_MANIFEST_BLOB_ID or worktree_blob != PBI01_MANIFEST_BLOB_ID or pbi01_diff.returncode != 0:
        raise SystemExit("PBI-01 accepted manifest bytes changed")

    canary = (repository / "docs/pbi02/AZURE_MAPS_CANARY.md").read_text(encoding="utf-8")
    canary_evidence = (
        "PASSED_SYNTHETIC_NONTRANSMISSION_GATE",
        "SYNTHETIC_ONLY",
        "2.157.879.0",
        "Road rendered",
        "Satellite road labels rendered",
        "native Style picker",
        "exactly 3,017",
        "69 requests",
        "68 to Azure Maps",
        "Every sentinel count was zero",
        "raw capture remained ignored and untracked",
        "does not accept the capability",
    )
    if any(value not in canary for value in canary_evidence):
        raise SystemExit("PBI-02 disclosure-safe synthetic canary evidence is incomplete")

    contract = _load(repository / "config/data/data04_michigan_public_data_parity_source_contract.json")
    if (
        contract.get("artifact_id") != DATA04_CONTRACT_ID
        or contract.get("version") != DATA04_CONTRACT_VERSION
        or contract.get("status") != "active"
        or contract.get("content_sha256") != DATA04_CONTRACT_SHA256
        or contract.get("state_scope", {}).get("observed_tract_count") != 3_017
        or contract.get("multivariate_extraction", {}).get("accepted_candidate_measure_count") != 13
        or len(EXPECTED_CANDIDATE_COLUMNS) != 56
        or len(MEASURE_IDS) != 13
    ):
        raise SystemExit("PBI-02 DATA-04 authority identity, accounting, or ordered schema differs")

    catalog = _load(repository / "config/pbi/pbi02_metric_catalog.json")
    metrics = catalog.get("metrics")
    if (
        catalog.get("artifact_id") != "PBI02_MICHIGAN_MAP_METRIC_CATALOG_V1"
        or catalog.get("version") != "1.0.0"
        or catalog.get("status") != "active"
        or catalog.get("expected_metric_count") != 16
        or not isinstance(metrics, list)
        or len(metrics) != 16
    ):
        raise SystemExit("PBI-02 metric catalog identity or count differs")
    if [metric.get("display_name") for metric in metrics] != EXPECTED_METRICS:
        raise SystemExit("PBI-02 exact metric inventory or order differs")
    if [metric.get("sort_order") for metric in metrics] != list(range(1, 17)):
        raise SystemExit("PBI-02 metric sort order differs")
    if len({metric.get("metric_key") for metric in metrics}) != 16:
        raise SystemExit("PBI-02 metric keys are not unique")
    for metric in metrics:
        if set(metric) != METADATA_FIELDS:
            raise SystemExit(f"PBI-02 metadata fields differ for {metric.get('display_name')}")
        if any(not str(metric.get(field, "")).strip() for field in METADATA_FIELDS - {"binding", "sort_order"}):
            raise SystemExit(f"PBI-02 metric metadata is incomplete for {metric.get('display_name')}")
        if not isinstance(metric.get("binding"), dict) or not metric["binding"].get("table") or not metric["binding"].get("column"):
            raise SystemExit(f"PBI-02 metric binding is incomplete for {metric.get('display_name')}")
    inventory_text = "\n".join(
        f"{metric['metric_key']}|{metric['display_name']}|{metric['short_name']}" for metric in metrics
    ).lower()
    if "average household income" in inventory_text or "area median income" in inventory_text:
        raise SystemExit("PBI-02 forbidden AHI or AMI entered the metric inventory")
    if [metric["scale_policy"] for metric in metrics].count("fixed_0_100") != 2:
        raise SystemExit("PBI-02 fixed-domain metric count differs")
    if [metric["scale_policy"] for metric in metrics].count("statewide_valid_p02_p98") != 14:
        raise SystemExit("PBI-02 robust-domain metric count differs")
    if "never become zero" not in catalog.get("missing_value_policy", ""):
        raise SystemExit("PBI-02 missing-value catalog policy differs")

    geometry_path = repository / "powerbi/pbi01/presentation/michigan_2024_tracts.geojson"
    geometry_bytes = geometry_path.read_bytes()
    canonical_geometry_bytes = geometry_bytes.replace(b"\r\n", b"\n")
    geometry = json.loads(geometry_bytes)
    geoids = [str(feature.get("properties", {}).get("GEOID", "")) for feature in geometry.get("features", [])]
    if (
        sha256(canonical_geometry_bytes).hexdigest() != GEOMETRY_SHA256
        or len(geoids) != 3_017
        or len(set(geoids)) != 3_017
        or not all(re.fullmatch(r"26[0-9]{9}", value) for value in geoids)
    ):
        raise SystemExit("PBI-02 presentation geometry identity or GEOID accounting differs")

    project = repository / "powerbi/pbi01/project"
    report_root = project / f"{PROJECT_NAME}.Report"
    model_root = project / f"{PROJECT_NAME}.SemanticModel"
    if _load(project / f"{PROJECT_NAME}.pbip").get("artifacts") != [{"report": {"path": f"{PROJECT_NAME}.Report"}}]:
        raise SystemExit("PBI-02 PBIP report binding differs")
    if _load(report_root / "definition.pbir").get("datasetReference", {}).get("byPath", {}).get("path") != f"../{PROJECT_NAME}.SemanticModel":
        raise SystemExit("PBI-02 PBIR semantic-model binding differs")
    embedded = report_root / "StaticResources/RegisteredResources/michigan_2024_tracts.geojson"
    if embedded.read_bytes() != geometry_bytes:
        raise SystemExit("PBI-02 embedded public reference geometry differs")

    pages_root = report_root / "definition/pages"
    page_order = _load(pages_root / "pages.json").get("pageOrder", [])
    pages = {page_id: _load(pages_root / page_id / "page.json") for page_id in page_order}
    if [pages[page_id].get("displayName") for page_id in page_order] != EXPECTED_PAGES:
        raise SystemExit("PBI-02 report page inventory or order differs")
    page_by_name = {page.get("displayName"): page_id for page_id, page in pages.items()}
    for name in EXPECTED_PAGES[:3]:
        page = pages[page_by_name[name]]
        if (page.get("width"), page.get("height")) != (1920, 1080):
            raise SystemExit(f"PBI-02 page dimensions differ: {name}")
    tooltip_page = pages[page_by_name["Tract Tooltip"]]
    if (
        tooltip_page.get("type") != "Tooltip"
        or tooltip_page.get("displayOption") != "ActualSize"
        or (tooltip_page.get("width"), tooltip_page.get("height")) != (400, 300)
    ):
        raise SystemExit("PBI-02 report-page tooltip definition differs")

    visual_by_page = {
        page_id: [_load(path) for path in sorted((pages_root / page_id / "visuals").glob("*/visual.json"))]
        for page_id in page_order
    }
    all_visuals = [visual for page_id in page_order for visual in visual_by_page[page_id]]
    visual_types = [visual.get("visual", {}).get("visualType") for visual in all_visuals]
    allowed_visuals = {"textbox", "cardVisual", "slicer", "azureMap", "scatterChart", "tableEx"}
    if len(all_visuals) != 39 or set(visual_types) != allowed_visuals:
        raise SystemExit(f"PBI-02 built-in visual inventory differs: {len(all_visuals)}, {sorted(set(visual_types))}")
    if visual_types.count("azureMap") != 1 or "shapeMap" in visual_types:
        raise SystemExit("PBI-02 primary spatial visual inventory differs")

    opportunity_id = page_by_name["Michigan Opportunity Explorer"]
    opportunity_visuals = visual_by_page[opportunity_id]
    azure_maps = [visual for visual in opportunity_visuals if visual.get("visual", {}).get("visualType") == "azureMap"]
    if len(azure_maps) != 1:
        raise SystemExit("PBI-02 primary page must contain exactly one Azure Maps visual")
    azure_document = azure_maps[0]
    if azure_document.get("position") != {
        "x": 0, "y": 72, "z": 3000, "height": 1008, "width": 1440, "tabOrder": 3000
    }:
        raise SystemExit("PBI-02 dominant-map layout differs")
    for visual in opportunity_visuals:
        if visual is not azure_document:
            position = visual.get("position", {})
            if position.get("y", 0) >= 72 and position.get("x", 0) < 1440:
                raise SystemExit("PBI-02 primary-page content intrudes into the map region")

    azure = azure_document["visual"]
    query_state = azure.get("query", {}).get("queryState", {})
    if set(query_state) != {"Category", "Tooltips"}:
        raise SystemExit("PBI-02 Azure Maps role inventory differs")
    category = query_state["Category"].get("projections", [])
    if len(category) != 1 or _projection_identity(category[0]) != ("Column", "Michigan Tracts", "GEOID"):
        raise SystemExit("PBI-02 Azure Maps Location must be public GEOID only")
    tooltip_bindings = [_projection_identity(item) for item in query_state["Tooltips"].get("projections", [])]
    if not tooltip_bindings or any(binding is None or binding[:2] != ("Measure", "Report Measures") for binding in tooltip_bindings):
        raise SystemExit("PBI-02 Azure Maps tooltip bindings must use presentation measures only")
    protected_terms = ("seed", "latitude", "longitude", "sales", "prediction", "error", "path", "physical")
    if any(any(term in binding[2].lower() for term in protected_terms) for binding in tooltip_bindings if binding):
        raise SystemExit("PBI-02 protected or coordinate field entered Azure Maps bindings")

    objects = azure.get("objects", {})
    controls = objects.get("mapControls", [])
    if len(controls) != 1:
        raise SystemExit("PBI-02 Azure Maps control definition differs")
    control_props = controls[0].get("properties", {})
    if _literal(control_props.get("defaultStyle")) != "'road'" or _literal(control_props.get("showSelectionControl")) != "false":
        raise SystemExit("PBI-02 Road default or selection-control gate differs")
    forbidden_control_keys = ("lasso", "route", "routing", "traffic", "navigation", "drivetime", "drive_time", "path")
    map_keys = [key.lower() for key in _keys(objects)]
    if any(any(term in key for term in forbidden_control_keys) for key in map_keys):
        raise SystemExit("PBI-02 prohibited Azure Maps behavior is configured")
    reference_layers = objects.get("referenceLayer", [])
    if len(reference_layers) != 2:
        raise SystemExit("PBI-02 Azure Maps reference-layer definition differs")
    reference_props = reference_layers[0].get("properties", {})
    resource_item = (
        reference_props.get("additionalDatasource", {}).get("geoJson", {}).get("content", {})
        .get("expr", {}).get("ResourcePackageItem")
    )
    if resource_item != {
        "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": "michigan_2024_tracts.geojson"
    }:
        raise SystemExit("PBI-02 Azure Maps public reference geometry binding differs")
    if _literal(reference_props.get("polygonStrokeTransparency")) != "55D" or _literal(reference_props.get("polygonStrokeWidth")) != "1L":
        raise SystemExit("PBI-02 tract boundary presentation differs")
    fill_measure = (
        reference_layers[1].get("properties", {}).get("polygonFillColor", {}).get("solid", {})
        .get("color", {}).get("expr", {}).get("Measure", {})
    )
    if (
        fill_measure.get("Expression", {}).get("SourceRef", {}).get("Entity") != "Report Measures"
        or fill_measure.get("Property") != "Selected Metric Color"
        or reference_layers[1].get("selector", {}).get("data") != [{"dataViewWildcard": {"matchingOption": 1}}]
    ):
        raise SystemExit("PBI-02 field-value polygon color binding differs")
    container = azure.get("visualContainerObjects", {})
    section = container.get("visualTooltip", [{}])[0].get("properties", {}).get("section")
    if _literal(section) != f"'{page_by_name['Tract Tooltip']}'":
        raise SystemExit("PBI-02 explicit report-page tooltip binding differs")
    if _literal(container.get("title", [{}])[0].get("properties", {}).get("show")) != "false":
        raise SystemExit("PBI-02 map auto-title must remain hidden")

    slicers = [visual for visual in opportunity_visuals if visual.get("visual", {}).get("visualType") == "slicer"]
    if len(slicers) != 1:
        raise SystemExit("PBI-02 primary selector inventory differs")
    selection = slicers[0]["visual"].get("objects", {}).get("selection", [{}])[0].get("properties", {})
    if (
        _literal(selection.get("singleSelect")) != "true"
        or _literal(selection.get("strictSingleSelect")) != "true"
        or _literal(selection.get("selectAllCheckboxEnabled")) != "false"
    ):
        raise SystemExit("PBI-02 metric selector is not strict single-select")

    evidence_visuals = visual_by_page[page_by_name["Sprouts Evidence Context"]]
    evidence_types = [visual.get("visual", {}).get("visualType") for visual in evidence_visuals]
    if evidence_types.count("scatterChart") != 1 or "azureMap" in evidence_types:
        raise SystemExit("PBI-02 protected Evidence Context separation differs")
    tooltip_visuals = visual_by_page[page_by_name["Tract Tooltip"]]
    if len(tooltip_visuals) != 4 or {visual.get("visual", {}).get("visualType") for visual in tooltip_visuals} != {"cardVisual"}:
        raise SystemExit("PBI-02 tooltip must be noninteractive presentation cards only")

    qa_visuals = visual_by_page[page_by_name["QA & Coverage"]]
    qa_bindings = {_projection_identity(item) for visual in qa_visuals for item in _projections(visual)}
    for measure in (
        "Selected Public Metric Available Tracts",
        "Selected Public Metric Unavailable Tracts",
        "Selected Public Metric QA",
        "Public Context Rows",
        "Public Context Reconciled Keys",
        "Public Context Relationship State",
    ):
        if ("Measure", "Report Measures", measure) not in qa_bindings:
            raise SystemExit(f"PBI-02 DATA-04 QA measure is absent: {measure}")
    for metric in metrics[3:]:
        binding = metric["binding"]
        for column in (binding["column"], binding["moe_column"], binding["status_column"], binding["status_detail_column"]):
            if ("Column", "Michigan Public Context", column) not in qa_bindings:
                raise SystemExit(f"PBI-02 complete public-context QA binding is absent: {column}")

    table_root = model_root / "definition/tables"
    expected_tables = {
        "Metric Selector.tmdl", "Michigan Public Context.tmdl", "Michigan Tracts.tmdl",
        "Presentation Scale.tmdl", "Report Measures.tmdl", "Seed Context.tmdl",
    }
    if {path.name for path in table_root.glob("*.tmdl")} != expected_tables:
        raise SystemExit("PBI-02 TMDL table inventory differs")
    tract_tmdl = (table_root / "Michigan Tracts.tmdl").read_text(encoding="utf-8")
    seed_tmdl = (table_root / "Seed Context.tmdl").read_text(encoding="utf-8")
    public_tmdl = (table_root / "Michigan Public Context.tmdl").read_text(encoding="utf-8")
    scale_tmdl = (table_root / "Presentation Scale.tmdl").read_text(encoding="utf-8")
    measures_tmdl = (table_root / "Report Measures.tmdl").read_text(encoding="utf-8")
    metric_tmdl = (table_root / "Metric Selector.tmdl").read_text(encoding="utf-8")
    model_text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(model_root.rglob("*.tmdl")))
    if (
        tract_tmdl.count("__PBI01_TRACT_CSV__") != 1
        or seed_tmdl.count("__PBI01_SEED_CSV__") != 1
        or public_tmdl.count("__PBI02_PUBLIC_CONTEXT_CSV__") != 1
    ):
        raise SystemExit("PBI-02 protected/local source tokens differ")
    if re.search(r"(?i)File\.Contents\(\"(?:[A-Za-z]:[\\/]|/)", model_text):
        raise SystemExit("PBI-02 tracked TMDL contains an absolute source path")
    if public_tmdl.count("\n\tcolumn ") != 56:
        raise SystemExit("PBI-02 public-context TMDL column count differs")
    for metric in metrics[3:]:
        binding = metric["binding"]
        for column in (binding["moe_column"], binding["status_column"], binding["status_detail_column"]):
            escaped_column = column.replace("'", "''")
            start = public_tmdl.find(f"\tcolumn '{escaped_column}'")
            if start < 0 or "\n\t\tisHidden" not in public_tmdl[start : start + 500]:
                raise SystemExit(f"PBI-02 technical public-context field is not hidden: {column}")
    relationship = (model_root / "definition/relationships.tmdl").read_text(encoding="utf-8")
    if any(value not in relationship for value in (
        "fromColumn: 'Michigan Public Context'.GEOID",
        "toColumn: 'Michigan Tracts'.GEOID",
        "fromCardinality: one",
        "toCardinality: one",
        "crossFilteringBehavior: bothDirections",
    )):
        raise SystemExit("PBI-02 one-to-one public-context relationship differs")
    if scale_tmdl.count("List.Percentile(V, 0.02)") != 14 or scale_tmdl.count("List.Percentile(V, 0.98)") != 14:
        raise SystemExit("PBI-02 P02/P98 refresh-scale semantics differ")
    if scale_tmdl.count('= "valid"') != 13 or scale_tmdl.count('0.0, 100.0, "fixed_0_100"') != 2:
        raise SystemExit("PBI-02 valid-only or fixed-domain scale semantics differ")
    if metric_tmdl.count("statewide_valid_p02_p98") < 14 or metric_tmdl.count("fixed_0_100") < 2:
        raise SystemExit("PBI-02 disconnected metric selector scale metadata differs")
    required_dax = (
        '"#D7DEE4"', '"No Data / Unavailable"', "Position <= 0.20", "Position <= 0.80",
        'SelectedCount = 0, "Select a tract"', '"Multiple tracts selected"',
        '"data04_measure_status_only"', 'StatusValue = "valid", BLANK()',
        'IF([Selected Tract Count] = 1', '"Per Capita Income"',
        "measure 'Selected Public Metric QA'", "measure 'Tooltip Public Context'",
    )
    if any(value not in measures_tmdl for value in required_dax):
        raise SystemExit("PBI-02 missingness, inspector, warning, or tooltip DAX differs")
    if 'COALESCE(NumericValue, 0)' in measures_tmdl or 'IF(ISBLANK(NumericValue), 0' in measures_tmdl:
        raise SystemExit("PBI-02 missing values are zero-filled")

    _assert_ignored(repository, (
        "powerbi/pbi01/local/pbi02-synthetic-validation/model13_michigan_tract_scores.csv",
        "powerbi/pbi01/local/data04/multivariate/michigan_tract_candidate_measures.csv",
        "powerbi/pbi01/runtime/pbi02-run/MICustomerGeography.pbip",
        "powerbi/pbi01/project/MICustomerGeography.pbix",
        "powerbi/pbi01/local/pbi02-canary/raw-capture.har",
    ))
    stageable = _git(repository, "ls-files", "--cached", "--others", "--exclude-standard").stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    normalized = [path.replace("\\", "/") for path in stageable]
    forbidden = [path for path in normalized if (
        path.startswith(("powerbi/pbi01/local/", "powerbi/pbi01/runtime/", "outputs/data04-run-"))
        or path.lower().endswith((".pbix", ".pbit", ".pcap", ".pcapng", ".har"))
        or "/.pbi/" in path.lower()
    )]
    if forbidden:
        raise SystemExit(f"PBI-02 local/protected artifacts became stageable: {forbidden}")
    project_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted(project.rglob("*"))
        if path.is_file() and ".pbi" not in [part.lower() for part in path.parts]
        and path.suffix.lower() in {".json", ".tmdl", ".pbir", ".pbip", ".pbism", ".md"}
    )
    if any(fragment.lower() in project_text.lower() for fragment in (
        "C:\\Users\\", "C:/Users/", "powerbi/pbi01/local/", "powerbi/pbi01/runtime/"
    )):
        raise SystemExit("PBI-02 protected/local path entered tracked project definitions")
    workflow = (repository / ".github/workflows/repository-validation.yml").read_text(encoding="utf-8")
    if "python scripts/check_pbi02_repository.py" not in workflow:
        raise SystemExit("PBI-02 checker is absent from Repository Validation")

    print(json.dumps({
        "state": "passed",
        "task_posture": posture,
        "azure_maps_canary": "PASSED_SYNTHETIC_NONTRANSMISSION_GATE",
        "data04_candidate_sha256": DATA04_CANDIDATE_SHA256,
        "metric_count": len(metrics),
        "page_count": len(pages),
        "visual_count": len(all_visuals),
        "azure_map_count": visual_types.count("azureMap"),
        "public_reference_geoid_count": len(geoids),
        "pbi01_acceptance_history_unchanged": True,
        "protected_tracked_path_guard": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
