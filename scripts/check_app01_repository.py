"""Repository-safe APP-01 runtime, governance, and disclosure conformance."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


AUTHORIZATION_BASE = "b29be0c1c4faf173fc95f402446ddfd92f73f92c"
EXACT_H = "9aa8853f3fa78cad62d9e4e384bae6ef107f3e4f"
PBI02_HEAD_AT_AUTHORIZATION = "b7edf51093bfd210f2856771095dd8005557f577"
TASK_BRANCH = "task/app-01-michigan-local-first-customer-geography-dashboard"
CAPABILITY_OWNER = "ARCH: Presentation Architecture Decisions & Acceptance"
MCR_DESTINATION = "MASTER CONTROL ROOM: Sprouts Customer Geography"
EXPECTED_GEOMETRY_SHA256 = "e0f32095d2e2307f5ad78c9545fc0d3c74fca2250bc866bea8db2368848786ad"
EXPECTED_NAMES = [
    "Customer Fit Percentile", "5-Mile Household Opportunity", "Modeled Target Mass Percentile",
    "Median Household Income", "Per Capita Income", "Civilian Labor Force Share", "Employment Rate",
    "Bachelor's Degree or Higher Share", "Owner-Occupied Housing Share", "Vacant Housing Unit Share",
    "Median Home Value", "Median Gross Rent", "Average Household Size", "No-Vehicle Household Share",
    "Drive-Alone Commuter Share", "Work-from-Home Commuter Share",
]
REQUIRED = (
    "governance/tasks/APP-01.michigan-local-first-customer-geography-dashboard.task.json",
    "docs/work_orders/APP_01_MICHIGAN_LOCAL_FIRST_CUSTOMER_GEOGRAPHY_DASHBOARD.md",
    "docs/app01/APP_01_SYNTHETIC_EGRESS_EVIDENCE.md",
    "docs/app01/APP_01_PRODUCT_DESIGN_AUDIT.md",
    "docs/app01/APP_01_VALIDATION_EVIDENCE.md",
    "config/app01/app01_runtime_policy.json",
    "config/app01/app01_stage1_gate.json",
    "schemas/app01/runtime_policy.schema.json",
    "schemas/app01/stage1_gate.schema.json",
    "schemas/app01/presentation_bundle.schema.json",
    "schemas/app01/evidence_context_bundle.schema.json",
    "src/sprouts_customer_geography/app01/bundle.py",
    "src/sprouts_customer_geography/app01/inputs.py",
    "src/sprouts_customer_geography/app01/server.py",
    "scripts/app01/serve_dashboard.py",
    "presentation/app01/README.md",
    "presentation/app01/app01.local-settings.example.json",
    "presentation/app01/site/index.html",
    "presentation/app01/site/styles.css",
    "presentation/app01/site/app.mjs",
    "RunCustomerGeography.bat",
    "tests/app01/test_app01_conformance.py",
)
PREDECESSOR_PATHS = (
    "config/model",
    "config/data",
    "config/geo",
    "powerbi/pbi01",
    "presentation/arch01",
    "config/arch01",
    "governance/tasks/MODEL-13.michigan-benchmark-pooled-successor-statewide-scoring.task.json",
    "governance/tasks/DATA-04.michigan-public-data-parity-foundation.task.json",
    "governance/tasks/GEO-05.michigan-statewide-geography-enablement.task.json",
    "governance/tasks/PBI-01.michigan-customer-geography-power-bi-mvp.task.json",
    "governance/tasks/ARCH-01.local-first-customer-geography-presentation-architecture.task.json",
)


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"APP-01 JSON is unreadable: {path.relative_to(path.parents[2]) if len(path.parents) > 2 else path.name}") from exc
    if not isinstance(value, dict):
        raise SystemExit("APP-01 JSON must be an object")
    return value


def _git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repository, capture_output=True, text=True)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    sys.path.insert(0, str(repository))
    from sprouts_customer_geography.app01.bundle import build_bundle_set
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"APP-01 required repository files absent: {missing}")
    manifests = list((repository / "governance/tasks").glob("APP-01*.task.json"))
    work_orders = list((repository / "docs/work_orders").glob("APP_01*.md"))
    if (len(manifests), len(work_orders)) != (1, 1):
        raise SystemExit(f"APP-01 requires one manifest and one work order; found {len(manifests)} and {len(work_orders)}")
    task = load_and_validate_task_manifest(manifests[0], repository / "schemas/governance/task_manifest.schema.json")
    if task["task_id"] != "APP-01" or task["implementation_branch"] != TASK_BRANCH:
        raise SystemExit("APP-01 task identity or branch differs")
    if task["capability_owner"] != CAPABILITY_OWNER or task["acceptance_destination"] != CAPABILITY_OWNER:
        raise SystemExit("APP-01 capability owner or acceptance destination differs")
    if AUTHORIZATION_BASE not in task["authority_source"]:
        raise SystemExit("APP-01 authorization base differs")
    posture = (task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"])
    expected_evidence = {"LOCAL_COMMIT", "TEST_PASS", "COMPLETION_REPORT", "FUTURE_PULL_REQUEST"}
    if posture not in {
        ("COMPLETED_AWAITING_ACCEPTANCE", "COMPLETED", "NOT_REVIEWED"),
        ("ACCEPTED_CLOSED", "COMPLETED", "ACCEPTED"),
    }:
        raise SystemExit(f"APP-01 H/A posture differs: {posture}")
    expected_next_destination = MCR_DESTINATION if posture[0] == "ACCEPTED_CLOSED" else CAPABILITY_OWNER
    if task["exact_next_destination"] != expected_next_destination:
        raise SystemExit("APP-01 H/A next destination differs")
    if set(task["completion_state"]["implementation_evidence"]) != expected_evidence:
        raise SystemExit("APP-01 H/A implementation evidence differs")
    if posture[0] == "ACCEPTED_CLOSED":
        if (
            task.get("implementation_commit") != EXACT_H
            or task.get("acceptance_disposition") != "ACCEPTED"
            or task.get("acceptance_metadata")
            != {
                "capability_owner": CAPABILITY_OWNER,
                "recorded_by": CAPABILITY_OWNER,
                "recorded_on": "2026-08-26",
            }
        ):
            raise SystemExit("APP-01 accepted exact-H record differs")
    elif any(key in task for key in ("implementation_commit", "acceptance_disposition", "acceptance_metadata")):
        raise SystemExit("APP-01 H must not claim implementation self-reference or capability acceptance")

    gate = _load(repository / "config/app01/app01_stage1_gate.json")
    if gate.get("substantive_h_exists") is not True or gate.get("exact_next_destination") != CAPABILITY_OWNER:
        raise SystemExit("APP-01 final gate differs from the exact-H stopping boundary")
    if gate.get("state") != "ultra_complete" or not all(gate.get("gates", {}).values()):
        raise SystemExit("APP-01 final Ultra gate is incomplete")

    first = build_bundle_set(repository, synthetic=True)
    second = build_bundle_set(repository, synthetic=True)
    if first.presentation_bytes != second.presentation_bytes or first.evidence_bytes != second.evidence_bytes:
        raise SystemExit("APP-01 synthetic runtime reconstruction is nondeterministic")
    bundle = json.loads(first.presentation_bytes)
    metrics = bundle["metrics"]
    if [metric["display_name"] for metric in metrics] != EXPECTED_NAMES or [metric["sort_order"] for metric in metrics] != list(range(1, 17)):
        raise SystemExit("APP-01 exact 16-metric inventory or order differs")
    if {metric["metric_key"] for metric in metrics if metric["scale_policy"] == "fixed_0_100"} != {"customer_fit_percentile", "modeled_target_mass_percentile"}:
        raise SystemExit("APP-01 fixed 0-100 domain assignment differs")
    if any(metric["display_name"] in {"Average Household Income", "Area Median Income"} for metric in metrics):
        raise SystemExit("APP-01 contains a prohibited income measure")
    if (bundle["tract_count"], len(bundle["rows"]), bundle["metric_count"], sha256(first.geometry_bytes).hexdigest()) != (3_017, 3_017, 16, EXPECTED_GEOMETRY_SHA256):
        raise SystemExit("APP-01 bundle and accepted public geometry do not reconcile")
    if first.health.get("protected_values_served") is not False or json.loads(first.evidence_bytes).get("external_transmission_permitted") is not False:
        raise SystemExit("APP-01 synthetic or Evidence Context disclosure boundary differs")

    runtime = _load(repository / "config/app01/app01_runtime_policy.json")
    if runtime["topology"]["bind_host"] != "127.0.0.1" or runtime["topology"]["non_loopback_binding_permitted"] is not False:
        raise SystemExit("APP-01 is not loopback-only")
    if runtime["network_egress"]["allowed_external_hosts"] != ["basemap.nationalmap.gov"] or runtime["network_egress"]["allowed_external_methods"] != ["GET"]:
        raise SystemExit("APP-01 egress allowlist differs")
    if any(runtime["telemetry"].values()):
        raise SystemExit("APP-01 remote observability is enabled")
    for vendor in runtime["renderer"]["vendored_files"]:
        if sha256((repository / vendor["path"]).read_bytes()).hexdigest() != vendor["sha256"]:
            raise SystemExit(f"APP-01 vendored dependency hash differs: {vendor['path']}")

    predecessor_diff = _git(repository, "diff", "--name-only", AUTHORIZATION_BASE, "--", *PREDECESSOR_PATHS)
    if predecessor_diff.returncode != 0 or predecessor_diff.stdout.splitlines():
        raise SystemExit("APP-01 changed accepted predecessor authority")
    pbi02_present = _git(repository, "cat-file", "-e", PBI02_HEAD_AT_AUTHORIZATION + "^{commit}").returncode == 0
    if pbi02_present and _git(repository, "merge-base", "--is-ancestor", PBI02_HEAD_AT_AUTHORIZATION, "HEAD").returncode == 0:
        raise SystemExit("APP-01 improperly contains the unaccepted PBI-02 head")

    stageable = _git(repository, "ls-files", "--cached", "--others", "--exclude-standard")
    if stageable.returncode != 0:
        raise SystemExit("APP-01 stageable inventory is unavailable")
    stageable_paths = stageable.stdout.splitlines()
    assert_no_protected_tracked_paths(stageable_paths)
    if any(path.replace("\\", "/").startswith("presentation/app01/local/") for path in stageable_paths):
        raise SystemExit("APP-01 ignored protected-local settings entered stageable scope")
    tracked_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in (repository / "config/app01", repository / "schemas/app01", repository / "presentation/app01", repository / "scripts/app01", repository / "src/sprouts_customer_geography/app01")
        for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".json", ".md", ".html", ".css", ".mjs", ".py"}
    )
    if "C:\\Users\\" in tracked_text or "C:/Users/" in tracked_text:
        raise SystemExit("APP-01 tracked scope contains an absolute user path")
    workflow = (repository / ".github/workflows/repository-validation.yml").read_text(encoding="utf-8")
    if "python scripts/check_app01_repository.py" not in workflow:
        raise SystemExit("APP-01 checker is absent from Repository Validation")

    print(json.dumps({
        "state": "passed",
        "task_posture": posture,
        "delivery_gate": gate["state"],
        "tract_count": bundle["tract_count"],
        "metric_count": bundle["metric_count"],
        "synthetic_presentation_sha256": sha256(first.presentation_bytes).hexdigest(),
        "synthetic_evidence_sha256": sha256(first.evidence_bytes).hexdigest(),
        "predecessor_immutability": "passed",
        "pbi02_separation": "passed",
        "protected_tracked_path_guard": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
