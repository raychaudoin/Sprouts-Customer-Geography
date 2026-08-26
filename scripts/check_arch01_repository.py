"""Repository-safe ARCH-01 architecture, spike, and disclosure conformance."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


AUTHORIZATION_BASE = "499cd611605380a3f2abca1e3e1d2f27cc56301c"
EXACT_H = "6347b05d1d126f6c63053eeea317dc7abfaa9b50"
TASK_BRANCH = "task/arch-01-local-first-customer-geography-presentation-architecture"
CAPABILITY_OWNER = "ARCH: Presentation Architecture Decisions & Acceptance"
MCR_DESTINATION = "MASTER CONTROL ROOM: Sprouts Customer Geography"
EXPECTED_GEOMETRY_SHA256 = "e0f32095d2e2307f5ad78c9545fc0d3c74fca2250bc866bea8db2368848786ad"
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
REQUIRED = (
    "governance/tasks/ARCH-01.local-first-customer-geography-presentation-architecture.task.json",
    "docs/work_orders/ARCH_01_LOCAL_FIRST_CUSTOMER_GEOGRAPHY_PRESENTATION_ARCHITECTURE.md",
    "docs/architecture/ARCH_01_LOCAL_FIRST_PRESENTATION_ARCHITECTURE_DECISION.md",
    "docs/arch01/ARCH_01_SPIKE_EVIDENCE.md",
    "config/arch01/arch01_metric_catalog.json",
    "config/arch01/arch01_runtime_policy.json",
    "schemas/arch01/metric_catalog.schema.json",
    "schemas/arch01/runtime_policy.schema.json",
    "schemas/arch01/presentation_bundle.schema.json",
    "scripts/arch01/build_synthetic_bundle.py",
    "scripts/arch01/serve_spike.py",
    "presentation/arch01/README.md",
    "presentation/arch01/site/index.html",
    "presentation/arch01/site/styles.css",
    "presentation/arch01/site/app.mjs",
    "presentation/arch01/site/vendor/maplibre-gl/LICENSE.txt",
    "RunArch01Spike.bat",
    "tests/arch01/test_arch01_conformance.py",
)
PREDECESSOR_PATHS = (
    "governance/tasks/MODEL-13.michigan-benchmark-pooled-successor-statewide-scoring.task.json",
    "governance/tasks/DATA-04.michigan-public-data-parity-foundation.task.json",
    "governance/tasks/GEO-05.michigan-statewide-geography-enablement.task.json",
    "governance/tasks/PBI-01.michigan-customer-geography-power-bi-mvp.task.json",
    "docs/work_orders/MODEL_13_MICHIGAN_BENCHMARK_POOLED_SUCCESSOR_STATEWIDE_SCORING.md",
    "docs/work_orders/DATA_04_MICHIGAN_PUBLIC_DATA_PARITY_FOUNDATION.md",
    "docs/work_orders/GEO_05_MICHIGAN_STATEWIDE_GEOGRAPHY_ENABLEMENT.md",
    "docs/work_orders/PBI_01_MICHIGAN_CUSTOMER_GEOGRAPHY_POWER_BI_MVP.md",
    "config/model/model13_michigan_power_bi_output_contract.json",
    "config/data/data04_michigan_public_data_parity_source_contract.json",
    "config/geo/geo05_michigan_statewide_spatial_support_spec.json",
    "powerbi/pbi01",
)


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ARCH-01 JSON is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"ARCH-01 JSON must be an object: {path}")
    return value


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _git_lines(repository: Path, *args: str) -> list[str]:
    return subprocess.run(
        ["git", *args], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.splitlines()


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    sys.path.insert(0, str(repository))
    from scripts.arch01.build_synthetic_bundle import build_bundle, build_bundle_bytes, validate_bundle
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"ARCH-01 required repository files absent: {missing}")

    manifests = list((repository / "governance/tasks").glob("ARCH-01*.task.json"))
    work_orders = list((repository / "docs/work_orders").glob("ARCH_01*.md"))
    if (len(manifests), len(work_orders)) != (1, 1):
        raise SystemExit(f"ARCH-01 requires one manifest and one work order; found {len(manifests)} and {len(work_orders)}")
    task = load_and_validate_task_manifest(manifests[0], repository / "schemas/governance/task_manifest.schema.json")
    if task["task_id"] != "ARCH-01" or task["implementation_branch"] != TASK_BRANCH:
        raise SystemExit("ARCH-01 task identity or branch differs")
    if task["capability_owner"] != CAPABILITY_OWNER or task["acceptance_destination"] != CAPABILITY_OWNER:
        raise SystemExit("ARCH-01 capability owner or acceptance destination differs")
    if AUTHORIZATION_BASE not in task["authority_source"]:
        raise SystemExit("ARCH-01 authorization base differs")
    posture = (task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"])
    if posture not in {
        ("IN_PROGRESS", "IN_PROGRESS", "NOT_REVIEWED"),
        ("COMPLETED_AWAITING_ACCEPTANCE", "COMPLETED", "NOT_REVIEWED"),
        ("ACCEPTED_CLOSED", "COMPLETED", "ACCEPTED"),
    }:
        raise SystemExit(f"ARCH-01 unauthorized task posture: {posture}")
    expected_next_destination = MCR_DESTINATION if posture[0] == "ACCEPTED_CLOSED" else CAPABILITY_OWNER
    if task["exact_next_destination"] != expected_next_destination:
        raise SystemExit("ARCH-01 exact next destination differs")
    if posture[0] == "ACCEPTED_CLOSED" and (
        task.get("implementation_commit") != EXACT_H
        or task.get("acceptance_disposition") != "ACCEPTED"
        or task.get("acceptance_metadata")
        != {
            "capability_owner": CAPABILITY_OWNER,
            "recorded_by": CAPABILITY_OWNER,
            "recorded_on": "2026-08-26",
        }
    ):
        raise SystemExit("ARCH-01 accepted exact-H record differs")

    catalog = _load(repository / "config/arch01/arch01_metric_catalog.json")
    metrics = catalog.get("metrics", [])
    if len(metrics) != 16 or [metric.get("display_name") for metric in metrics] != EXPECTED_METRICS:
        raise SystemExit("ARCH-01 exact 16-metric inventory or order differs")
    if [metric.get("sort_order") for metric in metrics] != list(range(1, 17)):
        raise SystemExit("ARCH-01 metric sort order differs")
    fixed = {metric["metric_key"] for metric in metrics if metric.get("scale_policy") == "fixed_0_100"}
    if fixed != {"customer_fit_percentile", "modeled_target_mass_percentile"}:
        raise SystemExit("ARCH-01 fixed 0-100 domain assignment differs")
    if any(metric.get("scale_policy") != "statewide_valid_p02_p98" for metric in metrics if metric["metric_key"] not in fixed):
        raise SystemExit("ARCH-01 robust valid-only domain assignment differs")
    if any(metric.get("display_name") in {"Average Household Income", "Area Median Income"} for metric in metrics):
        raise SystemExit("ARCH-01 contains an unauthorized income measure")

    bundle = build_bundle()
    validate_bundle(bundle)
    first = build_bundle_bytes()
    second = build_bundle_bytes()
    if first != second:
        raise SystemExit("ARCH-01 synthetic bundle reconstruction is nondeterministic")
    if (bundle["tract_count"], len(bundle["rows"]), bundle["metric_count"], len(bundle["metric_keys"])) != (3017, 3017, 16, 16):
        raise SystemExit("ARCH-01 bundle does not reconcile 3,017 tracts and 16 metrics")
    if bundle["source_bindings"]["geometry_sha256"] != EXPECTED_GEOMETRY_SHA256:
        raise SystemExit("ARCH-01 does not bind the accepted presentation geometry bytes")
    if bundle["canary"]["external_transmission_permitted"] is not False:
        raise SystemExit("ARCH-01 canary transmission posture differs")

    runtime = _load(repository / "config/arch01/arch01_runtime_policy.json")
    topology = runtime.get("topology", {})
    if topology.get("default_bind_host") != "127.0.0.1" or topology.get("non_loopback_binding_permitted") is not False:
        raise SystemExit("ARCH-01 is not loopback-only by default")
    if runtime.get("network_egress", {}).get("allowed_external_hosts") != ["basemap.nationalmap.gov"]:
        raise SystemExit("ARCH-01 external-host allowlist differs")
    if runtime.get("network_egress", {}).get("allowed_methods") != ["GET"]:
        raise SystemExit("ARCH-01 external-method allowlist differs")
    if any(runtime.get("telemetry", {}).get(field) for field in ("application_telemetry", "analytics", "crash_reporting", "remote_logging")):
        raise SystemExit("ARCH-01 remote observability is enabled")
    for vendor in runtime.get("renderer", {}).get("vendored_files", []):
        if _hash(repository / vendor["path"]) != vendor["sha256"]:
            raise SystemExit(f"ARCH-01 vendored dependency hash differs: {vendor['path']}")

    changed_predecessors = _git_lines(repository, "diff", "--name-only", AUTHORIZATION_BASE, "--", *PREDECESSOR_PATHS)
    if changed_predecessors:
        raise SystemExit(f"ARCH-01 accepted predecessor records changed: {changed_predecessors}")

    stageable = _git_lines(repository, "ls-files", "--cached", "--others", "--exclude-standard")
    assert_no_protected_tracked_paths(stageable)
    arch_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in (repository / "config/arch01", repository / "docs/arch01", repository / "presentation/arch01", repository / "scripts/arch01")
        for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".json", ".md", ".html", ".css", ".mjs", ".py", ".txt"}
    )
    if "C:\\Users\\" in arch_text or "C:/Users/" in arch_text:
        raise SystemExit("ARCH-01 tracked evidence contains an absolute user path")
    if "ARCH01_SYNTHETIC_PROTECTED_EGRESS_CANARY_7F3C91D2" in (repository / "presentation/arch01/site/app.mjs").read_text(encoding="utf-8"):
        raise SystemExit("ARCH-01 client code hardcodes the protected-shaped canary")

    workflow = (repository / ".github/workflows/repository-validation.yml").read_text(encoding="utf-8")
    if "python scripts/check_arch01_repository.py" not in workflow:
        raise SystemExit("ARCH-01 checker is absent from Repository Validation")

    print(json.dumps({
        "state": "passed",
        "task_posture": posture,
        "architecture": topology.get("architecture"),
        "renderer": f"{runtime['renderer']['name']} {runtime['renderer']['version']}",
        "tract_count": bundle["tract_count"],
        "metric_count": bundle["metric_count"],
        "synthetic_bundle_bytes": len(first),
        "synthetic_bundle_sha256": sha256(first).hexdigest(),
        "protected_tracked_path_guard": "passed",
        "predecessor_immutability": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
