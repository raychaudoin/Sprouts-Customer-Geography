"""Repository-safe MODEL-12 authority, scope, execution, and disclosure conformance."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import subprocess
import sys


REQUIRED = (
    "governance/tasks/MODEL-12.michigan-target-blind-seed-intake-frozen-scoring.task.json",
    "docs/work_orders/MODEL_12_MICHIGAN_TARGET_BLIND_SEED_INTAKE_FROZEN_SCORING.md",
    "config/model/model12_michigan_target_blind_frozen_scoring_contract.json",
    "schemas/model12/michigan_target_blind_frozen_scoring_contract.schema.json",
    "schemas/model12/michigan_target_blind_execution_commitment.schema.json",
    "schemas/model12/protected_handle_registry.schema.json",
    "schemas/model12/generic_anchor_input.schema.json",
    "schemas/model12/michigan_field_scoring_package.schema.json",
    "schemas/model12/michigan_identity_package.schema.json",
    "schemas/model12/michigan_public_feature_package.schema.json",
    "schemas/model12/michigan_frozen_scoring_package.schema.json",
    "src/sprouts_customer_geography/model12/contract.py",
    "src/sprouts_customer_geography/model12/resolver.py",
    "src/sprouts_customer_geography/model12/registry_bootstrap.py",
    "src/sprouts_customer_geography/model12/source.py",
    "src/sprouts_customer_geography/model12/public.py",
    "src/sprouts_customer_geography/model12/frozen.py",
    "src/sprouts_customer_geography/model12/materialization.py",
    "src/sprouts_customer_geography/model12/cli.py",
    "tests/test_model12_scoring.py",
)
COMMITMENT_PATH = "config/model/model12_michigan_target_blind_execution_commitment.json"
AUTHORIZATION_BASE = "5531b8c751d075da59ca7d4fcb74ec31ddd05cde"
EXPECTED_SCHEMAS = {
    "generic_anchor_input.schema.json",
    "michigan_field_scoring_package.schema.json",
    "michigan_frozen_scoring_package.schema.json",
    "michigan_identity_package.schema.json",
    "michigan_public_feature_package.schema.json",
    "michigan_target_blind_execution_commitment.schema.json",
    "michigan_target_blind_frozen_scoring_contract.schema.json",
    "protected_handle_registry.schema.json",
}


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"MODEL-12 repository JSON is unreadable: {path.relative_to(path.parents[2])}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"MODEL-12 repository JSON must be an object: {path.name}")
    return value


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.model12.contract import CONTRACT_ID, verify_repository_authority
    from sprouts_customer_geography.pipe01.canonical import content_digest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"MODEL-12 required repository files absent: {missing}")
    manifests = list((repository / "governance/tasks").glob("MODEL-12*.task.json"))
    work_orders = list((repository / "docs/work_orders").glob("MODEL_12*.md"))
    if len(manifests) != 1 or len(work_orders) != 1:
        raise SystemExit(f"MODEL-12 requires exactly one task manifest and one work order; found {len(manifests)} and {len(work_orders)}")
    task = load_and_validate_task_manifest(manifests[0], repository / "schemas/governance/task_manifest.schema.json")
    if task["task_id"] != "MODEL-12" or task["capability_owner"] != "MODEL: Customer-Fit Proxy Decisions & Acceptance":
        raise SystemExit("MODEL-12 task identity or capability owner differs")
    if task["implementation_branch"] != "task/model-12-michigan-target-blind-seed-intake-frozen-scoring":
        raise SystemExit("MODEL-12 implementation branch identity differs")
    allowed_postures = {
        ("IN_PROGRESS", "IN_PROGRESS", "NOT_REVIEWED"),
        ("COMPLETED_AWAITING_ACCEPTANCE", "COMPLETED", "NOT_REVIEWED"),
        ("ACCEPTED_CLOSED", "COMPLETED", "ACCEPTED"),
    }
    posture = (task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"])
    if posture not in allowed_postures:
        raise SystemExit(f"MODEL-12 task posture is not executable or acceptance-bearing: {posture}")

    contract = verify_repository_authority(repository)
    if contract["artifact_id"] != CONTRACT_ID:
        raise SystemExit("MODEL-12 exact contract identity differs")
    if contract["accepted_authority"]["canonical_main_at_authorization"] != "5531b8c751d075da59ca7d4fcb74ec31ddd05cde":
        raise SystemExit("MODEL-12 canonical authorization base differs")
    if contract["source_projection"]["canonical_fields"] != ["vintage", "seed_point_id", "address", "city", "state", "zip", "latitude", "longitude", "market"]:
        raise SystemExit("MODEL-12 target-blind source projection differs")
    if contract["physical_location_identity"]["probable_same_max_m"] != 10.0 or contract["physical_location_identity"]["genuinely_new_minimum_m_exclusive"] != 500.0:
        raise SystemExit("MODEL-12 accepted identity thresholds differ")
    if contract["public_feature_application"]["radii_m"] != [4828.032, 8046.72, 11265.408]:
        raise SystemExit("MODEL-12 exact MODEL-owned radii differ")
    if contract["frozen_scoring"]["preferred_candidate_id"] != "challenger_multivariate_elastic_net":
        raise SystemExit("MODEL-12 frozen preferred candidate differs")
    if contract["generic_anchor_scorer"]["input_fields"] != ["opaque_anchor_id", "latitude", "longitude"] or contract["generic_anchor_scorer"]["additional_input_fields_permitted"] is not False:
        raise SystemExit("MODEL-12 generic field-scorer boundary differs")

    schema_dir = repository / "schemas/model12"
    found_schemas = {path.name for path in schema_dir.glob("*.schema.json")}
    if found_schemas != EXPECTED_SCHEMAS:
        raise SystemExit(f"MODEL-12 schema inventory mismatch: {sorted(found_schemas)}")
    for path in schema_dir.glob("*.schema.json"):
        if _load(path).get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"MODEL-12 schema declaration differs: {path.name}")

    commitment_path = repository / COMMITMENT_PATH
    if posture[0] != "IN_PROGRESS" and not commitment_path.is_file():
        raise SystemExit("completed MODEL-12 posture requires its nondisclosing execution commitment")
    if commitment_path.is_file():
        commitment = _load(commitment_path)
        semantic = copy.deepcopy(commitment)
        expected_hash = semantic.pop("content_sha256", None)
        aggregate = commitment.get("aggregate_conformance", {})
        boundary = commitment.get("execution_boundary", {})
        disclosure = commitment.get("disclosure_boundary", {})
        runs = commitment.get("independent_materializations", [])
        if (
            commitment.get("artifact_id") != "MODEL12_MICHIGAN_TARGET_BLIND_EXECUTION_COMMITMENT_V1"
            or commitment.get("contract_authority", {}).get("content_sha256") != contract["content_sha256"]
            or expected_hash != content_digest(semantic)
        ):
            raise SystemExit("MODEL-12 execution commitment identity or content hash differs")
        if len(runs) != 2 or [item.get("ordinal") for item in runs] != [1, 2]:
            raise SystemExit("MODEL-12 execution commitment does not bind two independent materializations")
        if any(set(item.get("stage_commitments", {})) != {"identity", "public_features", "frozen_scoring"} for item in runs):
            raise SystemExit("MODEL-12 protected stage commitment inventory differs")
        if aggregate.get("complete_source_observation_accounting") is not True or aggregate.get("complete_location_accounting") is not True:
            raise SystemExit("MODEL-12 execution commitment lacks complete accounting")
        if aggregate.get("physical_location_count") != sum(aggregate.get(field, -1) for field in ("quarantined_physical_location_count", "computable_frozen_score_physical_location_count", "noncomputable_frozen_score_physical_location_count")):
            raise SystemExit("MODEL-12 execution aggregate does not partition every physical location")
        if boundary.get("michigan_target_body_values_accessed") != 0 or any(boundary.get(field) is not False for field in ("model_refit_performed", "model_retraining_performed", "model_retuning_performed", "michigan_feature_selection_performed", "michigan_redundancy_screen_performed", "prediction_recalibration_performed", "michigan_distribution_used_to_modify_model")):
            raise SystemExit("MODEL-12 zero-target or frozen-model execution boundary differs")
        if any(value is not False for value in disclosure.values()):
            raise SystemExit("MODEL-12 protected execution disclosure boundary differs")
        if commitment.get("deterministic_comparison") != {"semantic_stage_count": 3, "semantic_packages_byte_identical": True, "aggregate_conformance_identical": True}:
            raise SystemExit("MODEL-12 deterministic comparison evidence differs")

    resolver_source = (repository / "src/sprouts_customer_geography/model12/resolver.py").read_text(encoding="utf-8").lower()
    prohibited_discovery = (".glob(", ".rglob(", "os.walk(")
    used = [operation for operation in prohibited_discovery if operation in resolver_source]
    if used:
        raise SystemExit(f"MODEL-12 exact protected resolver contains broad discovery operation(s): {used}")

    stageable = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    forbidden_paths = [path for path in stageable if path.replace("\\", "/").startswith(("outputs/", "data/raw/", "data/cache/", "data/local/"))]
    if forbidden_paths:
        raise SystemExit(f"MODEL-12 protected raw or generated paths became stageable: {forbidden_paths}")
    changed = set(
        subprocess.run(
            ["git", "diff", "--name-only", AUTHORIZATION_BASE, "--"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    )
    changed.update(subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines())
    changed_files = [path for path in sorted(changed) if (repository / path).is_file()]
    public_text = "\n".join((repository / path).read_text(encoding="utf-8", errors="ignore") for path in changed_files)
    forbidden_fragments = (
        "Sprouts" + "-Protected",
        "m11run-" + "wisconsin",
        "m11freeze-" + "wisconsin",
        "C:" + "\\Users\\",
    )
    if any(fragment.lower() in public_text.lower() for fragment in forbidden_fragments):
        raise SystemExit("MODEL-12 protected-local path or run detail entered stageable repository content")
    if re.search(r"(?i)\bmi[_ -]+seed[_ -]+forecasts\b|\bcity[0-9]+\b", public_text):
        raise SystemExit("MODEL-12 protected source basename or private header alias entered stageable repository content")
    narrative_text = "\n".join(
        (repository / path).read_text(encoding="utf-8", errors="ignore")
        for path in changed_files
        if path.replace("\\", "/").startswith(("config/", "docs/", "governance/"))
    )
    if re.search(r'(?i)[A-Za-z0-9 _.-]+\.xlsx', narrative_text):
        raise SystemExit("MODEL-12 protected or reconstructable workbook filename entered stageable repository content")

    print(
        json.dumps(
            {
                "state": "passed",
                "contract_id": CONTRACT_ID,
                "task_posture": posture,
                "target_body_values_access_authorized": False,
                "frozen_candidate_id": "challenger_multivariate_elastic_net",
                "exact_source_resolution": True,
                "schema_count": len(found_schemas),
                "nondisclosing_execution_commitment": commitment_path.is_file(),
                "protected_tracked_path_guard": "passed",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
