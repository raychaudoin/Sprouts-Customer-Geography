"""Repository-safe MODEL-14 pre-H, chronology, and disclosure conformance."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys


AUTHORIZATION_BASE = "e464d5ea2453d7387102d64154bb52f410b12670"
TARGET_BLIND_FREEZE_COMMIT = "d516f2ffce151d83df8c80ea293ea84550378fbf"
GENERATION1_CHECKPOINT = "b41f0e8d96c717654e861d1673d87d57cf42b0cf"
CONTRACT_PATH = "config/model14/experimental_public_feature_contract.json"
COMMITMENT_PATH = "config/model14/target_blind_public_feature_commitment.json"
FREEZE_COMMITMENT_PATH = "config/model/model14_target_blind_public_feature_commitment.json"
REPORT_PATH = "docs/experiments/MODEL_14_PUBLIC_FEATURE_EXPANSION_PRE_H_REPORT.md"
GENERATION2_CONTRACT_PATH = "config/model14/experimental_overture_generation2_contract.json"
GENERATION2_COMMITMENT_PATH = "config/model14/target_blind_overture_generation2_commitment.json"
GENERATION2_REPORT_PATH = "docs/experiments/MODEL_14_OVERTURE_GENERATION2_PRE_H_REPORT.md"
GENERATION2_EXPERIMENT_PATH = "src/sprouts_customer_geography/model14/generation2_experiment.py"
GENERATION2_COMPONENT_MATRIX_SHA256 = "1de6160abcd62046d666ba3727d4267c884213e90ff669b189b2678eddf64c42"
GENERATION2_FEATURE_MATRIX_SHA256 = "b1b9faa9186f99b61026539e2e404d998f0b7583b1713fff3f53a9a324873a8a"
GENERATION2_FREEZE_SEMANTIC_SHA256 = "5b00f4c22f384a6b6a6793f540a520d66ec44c66b41411d1b147858639452e80"
GENERATION2_SOURCE_EXTRACT_SHA256 = "21bf8cc829b864c2cd1207ebe377ab2917268d273159c9296bab6f5d5b0796b8"
GENERATION2_CONTRACT_CONTENT_SHA256 = "a3e4d2797a212a268c5413a8bd0415d38c6d8414e1e8810033711c816c86e2a7"
GENERATION2_COMMITMENT_CONTENT_SHA256 = "d9c5c1c30a8701e104609271b02a8b1ede0aa7b8e903419a309ae8db31abdff3"
GENERATION2_QUERY_ID = "MODEL14_OVERTURE_PLACES_MI_WI_EXACT_POINT_ENVELOPE_V1"
GENERATION2_FEATURE_IDS = (
    "overture_log_commercial_places_tract",
    "overture_log_shopping_places_tract",
    "overture_log_food_and_drink_places_tract",
    "overture_log_grocery_places_tract",
    "overture_log_commercial_places_5mi",
    "overture_log_shopping_places_5mi",
    "overture_log_food_and_drink_places_5mi",
    "overture_log_restaurant_places_5mi",
    "overture_log_grocery_places_5mi",
    "overture_log_fitness_wellness_places_5mi",
    "overture_log_health_care_places_5mi",
    "overture_basic_category_gini_simpson_diversity_5mi",
    "overture_grocery_share_of_commercial_5mi",
    "overture_shopping_share_of_commercial_5mi",
    "overture_food_and_drink_share_of_commercial_5mi",
)
GENERATION1_IMMUTABLE_PATHS = (
    CONTRACT_PATH,
    COMMITMENT_PATH,
    REPORT_PATH,
    "src/sprouts_customer_geography/model14/public.py",
    "src/sprouts_customer_geography/model14/modeling.py",
    "src/sprouts_customer_geography/model14/experiment.py",
)
EXPECTED_CHANGED = {
    ".github/workflows/repository-validation.yml",
    "config/model14/experimental_public_feature_contract.json",
    "config/model14/target_blind_public_feature_commitment.json",
    "docs/experiments/MODEL_14_PUBLIC_FEATURE_EXPANSION_PRE_H_REPORT.md",
    "docs/work_orders/MODEL_14_PUBLIC_FEATURE_EXPANSION_SUCCESSOR_EXPERIMENT.md",
    "governance/tasks/MODEL-14.public-feature-expansion-successor-experiment.task.json",
    "pyproject.toml",
    "scripts/check_model14_repository.py",
    "src/sprouts_customer_geography/model14/__init__.py",
    "src/sprouts_customer_geography/model14/__main__.py",
    "src/sprouts_customer_geography/model14/cli.py",
    "src/sprouts_customer_geography/model14/experiment.py",
    "src/sprouts_customer_geography/model14/modeling.py",
    "src/sprouts_customer_geography/model14/public.py",
    "tests/test_model14_public_features.py",
}
GENERATION2_FREEZE_CHANGED = {
    GENERATION2_CONTRACT_PATH,
    GENERATION2_COMMITMENT_PATH,
    "src/sprouts_customer_geography/model14/overture_generation2.py",
}
GENERATION2_OPTIONAL_CHANGED = {
    GENERATION2_EXPERIMENT_PATH,
    GENERATION2_REPORT_PATH,
    "tests/test_model14_overture_generation2.py",
    "tests/test_model14_overture_generation2_experiment.py",
}


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"MODEL-14 repository JSON is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"MODEL-14 repository JSON must be an object: {path.name}")
    return value


def _git(repository: Path, *arguments: str) -> list[str]:
    result = subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True, text=True)
    return result.stdout.splitlines()


def _git_scalar(repository: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _assert_generation1_unchanged(repository: Path) -> None:
    if subprocess.run(
        ["git", "cat-file", "-e", GENERATION1_CHECKPOINT + "^{commit}"],
        cwd=repository,
        capture_output=True,
    ).returncode != 0:
        raise SystemExit("MODEL-14 Generation-1 checkpoint is absent")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", GENERATION1_CHECKPOINT, "HEAD"],
        cwd=repository,
        capture_output=True,
    ).returncode != 0:
        raise SystemExit("MODEL-14 Generation-1 checkpoint is not an ancestor of HEAD")
    for path in GENERATION1_IMMUTABLE_PATHS:
        current = repository / path
        if not current.is_file():
            raise SystemExit(f"MODEL-14 Generation-1 authoritative file is absent: {path}")
        checkpoint_blob = _git_scalar(repository, "rev-parse", f"{GENERATION1_CHECKPOINT}:{path}")
        working_blob = _git_scalar(repository, "hash-object", f"--path={path}", path)
        if checkpoint_blob != working_blob:
            raise SystemExit(f"MODEL-14 Generation-1 authoritative evidence or code changed: {path}")


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.model14.overture_generation2 import (
        FEATURE_IDS as OVERTURE_GENERATION2_FEATURE_IDS,
        load_generation2_contract,
    )
    from sprouts_customer_geography.model14.public import FEATURE_IDS, load_contract
    from sprouts_customer_geography.pipe01.canonical import content_digest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    required = {
        CONTRACT_PATH,
        COMMITMENT_PATH,
        GENERATION2_CONTRACT_PATH,
        GENERATION2_COMMITMENT_PATH,
        REPORT_PATH,
        "governance/tasks/MODEL-14.public-feature-expansion-successor-experiment.task.json",
        "docs/work_orders/MODEL_14_PUBLIC_FEATURE_EXPANSION_SUCCESSOR_EXPERIMENT.md",
        "src/sprouts_customer_geography/model14/public.py",
        "src/sprouts_customer_geography/model14/experiment.py",
        "src/sprouts_customer_geography/model14/cli.py",
        "tests/test_model14_public_features.py",
    }
    missing = [path for path in sorted(required) if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"MODEL-14 required files are absent: {missing}")
    manifests = list((repository / "governance/tasks").glob("MODEL-14*.task.json"))
    work_orders = list((repository / "docs/work_orders").glob("MODEL_14*.md"))
    if len(manifests) != 1 or len(work_orders) != 1:
        raise SystemExit(f"MODEL-14 requires exactly one manifest and work order; found {len(manifests)} and {len(work_orders)}")
    task = load_and_validate_task_manifest(manifests[0], repository / "schemas/governance/task_manifest.schema.json")
    posture = (task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"])
    if (
        task["task_id"] != "MODEL-14"
        or task["capability_owner"] != "MODEL: Customer-Fit Proxy Decisions & Acceptance"
        or task["implementation_branch"] != "task/model-14-public-feature-expansion-successor-experiment"
        or posture != ("IN_PROGRESS", "IN_PROGRESS", "NOT_REVIEWED")
        or "implementation_commit" in task
    ):
        raise SystemExit(f"MODEL-14 identity or required pre-H posture differs: {posture}")

    contract = load_contract(repository)
    family_counts = contract.get("model_feature_count_by_family")
    if family_counts != {"lodes": 14, "business_context": 0, "traffic_accessibility": 2, "richer_acs": 11}:
        raise SystemExit("MODEL-14 candidate family accounting differs")
    statuses = {key: value.get("status") for key, value in contract["source_families"].items()}
    if statuses != {"lodes": "evaluation-ready", "business_context": "partially-evaluation-ready", "traffic_accessibility": "evaluation-ready", "richer_acs": "evaluation-ready"}:
        raise SystemExit("MODEL-14 source-family readiness differs")
    if len(FEATURE_IDS) != 27 or any(token in feature.lower() for feature in FEATURE_IDS for token in ("race", "ethnicity", "sex", "religion")):
        raise SystemExit("MODEL-14 feature count or protected-characteristic exclusion differs")
    if contract["protected_characteristic_policy"] != {
        "race_used": False,
        "ethnicity_used": False,
        "sex_used": False,
        "religion_used": False,
        "age_composition_used": False,
        "other_protected_class_feature_used": False,
        "lodes_protected_columns_read_for_features": False,
    }:
        raise SystemExit("MODEL-14 protected-characteristic policy differs")

    commitment = _load(repository / COMMITMENT_PATH)
    semantic = copy.deepcopy(commitment)
    recorded = semantic.pop("content_sha256", None)
    chronology = commitment.get("chronology", {})
    matrix = commitment.get("public_matrix_commitment", {})
    if (
        commitment.get("artifact_id") != "MODEL14_TARGET_BLIND_PUBLIC_FEATURE_COMMITMENT_V1"
        or commitment.get("state") != "TARGET_BLIND_PUBLIC_FEATURES_FROZEN"
        or recorded != content_digest(semantic)
        or chronology.get("target_values_accessed") != 0
        or chronology.get("protected_anchor_rows_accessed") != 0
        or chronology.get("sealed_or_prospective_evidence_accessed") is not False
        or matrix.get("row_count") != 4559
        or matrix.get("michigan_row_count") != 3017
        or matrix.get("wisconsin_row_count") != 1542
        or matrix.get("missing_to_zero") is not False
        or matrix.get("determinism_state") != "DETERMINISTIC_BYTE_IDENTICAL"
        or matrix.get("independent_materialization_count") != 2
    ):
        raise SystemExit("MODEL-14 target-blind public commitment differs")

    if subprocess.run(["git", "cat-file", "-e", TARGET_BLIND_FREEZE_COMMIT + "^{commit}"], cwd=repository).returncode != 0:
        raise SystemExit("MODEL-14 target-blind freeze commit is absent")
    frozen_bytes = subprocess.check_output(["git", "show", f"{TARGET_BLIND_FREEZE_COMMIT}:{FREEZE_COMMITMENT_PATH}"], cwd=repository)
    if frozen_bytes != (repository / COMMITMENT_PATH).read_bytes():
        raise SystemExit("MODEL-14 relocated commitment differs from the exact target-blind freeze bytes")
    if subprocess.run(["git", "merge-base", "--is-ancestor", TARGET_BLIND_FREEZE_COMMIT, "HEAD"], cwd=repository).returncode != 0:
        raise SystemExit("MODEL-14 target-blind freeze is not an ancestor of HEAD")

    _assert_generation1_unchanged(repository)

    generation2_config = repository / "config/model14"
    generation2_contracts = sorted(generation2_config.glob("*overture_generation2*contract*.json"))
    generation2_commitments = sorted(generation2_config.glob("*overture_generation2*commitment*.json"))
    if (
        generation2_contracts != [repository / GENERATION2_CONTRACT_PATH]
        or generation2_commitments != [repository / GENERATION2_COMMITMENT_PATH]
    ):
        raise SystemExit(
            "MODEL-14 requires exactly one Generation-2 Overture contract and commitment; "
            f"found {len(generation2_contracts)} and {len(generation2_commitments)}"
        )

    generation2_contract = load_generation2_contract(repository)
    generation2_contract_semantic = copy.deepcopy(generation2_contract)
    generation2_contract_digest = generation2_contract_semantic.pop("content_sha256", None)
    generation2_catalog = tuple(
        str(item.get("feature_id"))
        for item in generation2_contract.get("feature_catalog", [])
        if isinstance(item, dict)
    )
    generation2_source = generation2_contract.get("source", {})
    generation2_geography = generation2_contract.get("geography", {})
    generation2_quality_rules = generation2_contract.get("quality_status_identity_rules", {})
    generation2_taxonomy_rules = generation2_contract.get("taxonomy_rules", {})
    generation2_freeze_policy = generation2_contract.get("freeze", {})
    generation2_candidate_sets = generation2_contract.get("candidate_sets", {})
    if (
        generation2_contract_digest != content_digest(generation2_contract_semantic)
        or generation2_contract_digest != GENERATION2_CONTRACT_CONTENT_SHA256
        or generation2_contract.get("artifact_id") != "MODEL14_OVERTURE_GENERATION2_EXPERIMENTAL_PUBLIC_FEATURE_CONTRACT_V1"
        or generation2_contract.get("status") != "EXPLORATORY_GENERATION2_TARGET_BLIND_DEFINITIONS_FROZEN"
        or generation2_contract.get("generation") != 2
        or generation2_contract.get("exploratory") is not True
        or generation2_contract.get("confirmatory") is not False
        or generation2_contract.get("prior_generation_aggregate_results_known") is not True
        or generation2_contract.get("production_source_authority") is not False
        or generation2_contract.get("target_access_during_generation2_definition_permitted") is not False
        or generation2_source.get("release") != "2026-07-22.0"
        or generation2_source.get("schema_version") != "v1.18.0"
        or generation2_source.get("retrieval_date") != "2026-08-27"
        or generation2_source.get("query_identity") != GENERATION2_QUERY_ID
        or generation2_source.get("extraction_predicate")
        != "exact ST_X/ST_Y point position within the unrounded accepted MI or WI tract envelope, with bbox overlap or null-bbox prefilter"
        or generation2_source.get("bbox_qa")
        != "bbox is optional; all-four-null is retained under exact geometry filtering, partial-null fails, and a present finite bbox must contain the point"
        or generation2_source.get("deprecated_categories_field_used") is not False
        or generation2_geography.get("source_point_crs") != "EPSG:4326"
        or generation2_geography.get("accepted_tract_polygon_crs") != "EPSG:4269"
        or generation2_geography.get("exploratory_datum_semantics")
        != "WGS84 point longitude/latitude are treated as numerically coordinate-equivalent to NAD83 for this experimental tract overlay; no datum shift is introduced, accepted tract geometry is unchanged, and unresolved shared-boundary cases are excluded"
        or generation2_geography.get("production_datum_authority_claimed") is not False
        or generation2_quality_rules.get("release_anomaly_semantics")
        != "nonzero confidence on known permanently_closed rows is an observed pinned-release/schema anomaly; operating status controls exclusion and confidence is not normalized"
        or generation2_taxonomy_rules.get("hierarchy_values_must_be_unique") is not True
        or generation2_catalog != GENERATION2_FEATURE_IDS
        or tuple(OVERTURE_GENERATION2_FEATURE_IDS) != GENERATION2_FEATURE_IDS
        or generation2_contract.get("feature_count") != 15
        or tuple(generation2_candidate_sets) != (
            "A_model13_reproduced_generation2",
            "B_model13_plus_all_generation2_commercial",
            "C_model13_plus_generation2_intensity",
            "D_model13_plus_generation2_mix_diversity",
        )
        or generation2_candidate_sets.get("A_model13_reproduced_generation2") != []
        or generation2_candidate_sets.get("B_model13_plus_all_generation2_commercial") != ["intensity_count", "mix_diversity"]
        or generation2_candidate_sets.get("C_model13_plus_generation2_intensity") != ["intensity_count"]
        or generation2_candidate_sets.get("D_model13_plus_generation2_mix_diversity") != ["mix_diversity"]
        or generation2_freeze_policy.get("expected_tract_row_count") != 4559
        or generation2_freeze_policy.get("expected_michigan_row_count") != 3017
        or generation2_freeze_policy.get("expected_wisconsin_row_count") != 1542
        or generation2_freeze_policy.get("independent_materialization_count") != 2
        or generation2_freeze_policy.get("target_values_accessed_during_generation2_public_phase") != 0
        or generation2_freeze_policy.get("protected_anchor_rows_accessed_during_generation2_public_phase") != 0
    ):
        raise SystemExit("MODEL-14 exploratory Generation-2 Overture contract differs")

    generation2_commitment = _load(repository / GENERATION2_COMMITMENT_PATH)
    generation2_commitment_semantic = copy.deepcopy(generation2_commitment)
    generation2_commitment_digest = generation2_commitment_semantic.pop("content_sha256", None)
    generation2_chronology = generation2_commitment.get("chronology", {})
    generation2_commitment_source = generation2_commitment.get("source", {})
    generation2_matrix = generation2_commitment.get("tract_matrix", {})
    generation2_features = generation2_commitment.get("feature_catalog", {})
    generation2_frozen_rules = generation2_commitment.get("frozen_rules", {})
    generation2_matrix_hashes = (
        generation2_matrix.get("component_matrix_byte_sha256"),
        generation2_matrix.get("feature_matrix_byte_sha256"),
        generation2_matrix.get("freeze_semantic_content_sha256"),
    )
    if (
        generation2_commitment_digest != content_digest(generation2_commitment_semantic)
        or generation2_commitment_digest != GENERATION2_COMMITMENT_CONTENT_SHA256
        or generation2_commitment.get("artifact_id") != "MODEL14_OVERTURE_GENERATION2_TARGET_BLIND_PUBLIC_FEATURE_COMMITMENT_V1"
        or generation2_commitment.get("state") != "EXPLORATORY_GENERATION2_TARGET_BLIND_PUBLIC_FEATURES_FROZEN"
        or generation2_commitment.get("generation") != 2
        or generation2_commitment.get("exploratory") is not True
        or generation2_commitment.get("confirmatory") is not False
        or generation2_commitment.get("prior_generation_aggregate_results_known") is not True
        or generation2_commitment.get("generation1_checkpoint") != GENERATION1_CHECKPOINT
        or generation2_commitment.get("generation1_evidence_preserved_unchanged") is not True
        or generation2_commitment.get("production_source_authority") is not False
        or generation2_commitment.get("contract", {}).get("artifact_id") != generation2_contract.get("artifact_id")
        or generation2_commitment.get("contract", {}).get("content_sha256") != generation2_contract_digest
        or generation2_chronology.get("generation2_definitions_frozen_before_generation2_target_access") is not True
        or generation2_chronology.get("generation2_full_tract_matrix_frozen_before_generation2_target_access") is not True
        or generation2_chronology.get("generation2_target_values_accessed") != 0
        or generation2_chronology.get("generation2_protected_anchor_rows_accessed") != 0
        or generation2_chronology.get("sealed_or_prospective_evidence_accessed") is not False
        or generation2_chronology.get("prior_generation_results_known_and_disclosed_as_exploratory") is not True
        or generation2_commitment_source.get("release") != "2026-07-22.0"
        or generation2_commitment_source.get("schema_version") != "v1.18.0"
        or generation2_commitment_source.get("source_envelope_row_count") != 1160087
        or generation2_commitment_source.get("source_extract_byte_sha256") != GENERATION2_SOURCE_EXTRACT_SHA256
        or not _is_sha256(generation2_commitment_source.get("source_extract_byte_sha256"))
        or generation2_commitment_source.get("retrieval_date") != "2026-08-27"
        or generation2_commitment_source.get("query_identity") != GENERATION2_QUERY_ID
        or generation2_commitment_source.get("duckdb_version") != "1.5.5"
        or generation2_commitment_source.get("deprecated_categories_field_used") is not False
        or generation2_commitment_source.get("names_brands_providers_used") is not False
        or generation2_frozen_rules.get("source_envelope_extraction")
        != "exact ST_X/ST_Y point position in unrounded accepted MI/WI tract envelopes, with schema-valid bbox overlap or null-bbox prefilter"
        or generation2_frozen_rules.get("datum_semantics")
        != "exploratory numeric WGS84-to-NAD83 coordinate equivalence with no datum shift; accepted tract CRS and geometry unchanged; no production datum authority claimed"
        or generation2_frozen_rules.get("bbox_qa")
        != "all source rows had present finite bboxes containing their points; optional all-null would be retained and partial-null would fail"
        or generation2_frozen_rules.get("release_anomaly")
        != "9,538 known permanently_closed rows had nonzero confidence in the pinned release; operating status controlled exclusion and confidence was not normalized"
        or generation2_features.get("feature_count") != 15
        or generation2_features.get("intensity_count_feature_count") != 11
        or generation2_features.get("mix_diversity_feature_count") != 4
        or tuple(generation2_features.get("feature_order", [])) != GENERATION2_FEATURE_IDS
        or generation2_matrix.get("tract_count") != 4559
        or generation2_matrix.get("michigan_tract_count") != 3017
        or generation2_matrix.get("wisconsin_tract_count") != 1542
        or generation2_matrix.get("accepted_tract_key_reconciliation") is not True
        or generation2_matrix.get("tract_rows_dropped") is not False
        or generation2_matrix.get("count_feature_missing_tract_count_by_state") != {"MI": 0, "WI": 0}
        or generation2_matrix.get("mix_diversity_maximum_missing_tract_count_by_state") != {"MI": 29, "WI": 9}
        or generation2_matrix.get("missing_to_zero") is not False
        or generation2_matrix_hashes
        != (
            GENERATION2_COMPONENT_MATRIX_SHA256,
            GENERATION2_FEATURE_MATRIX_SHA256,
            GENERATION2_FREEZE_SEMANTIC_SHA256,
        )
        or not all(_is_sha256(value) for value in generation2_matrix_hashes)
        or generation2_matrix.get("independent_materialization_count") != 2
        or generation2_matrix.get("determinism_state") != "DETERMINISTIC_BYTE_IDENTICAL"
        or generation2_matrix.get("outside_tracked_git") is not True
        or tuple(generation2_commitment.get("candidate_sets_frozen", [])) != tuple(generation2_candidate_sets)
        or generation2_commitment.get("generation1_combination_included") is not False
        or generation2_commitment.get("protected_characteristic_scoring_feature_used") is not False
    ):
        raise SystemExit("MODEL-14 exploratory Generation-2 Overture commitment differs")

    generation2_assignment = generation2_commitment.get("source_quality_and_assignment_accounting", {})
    generation2_assigned_by_state = generation2_assignment.get("assigned_commercial_place_count_by_state", {})
    if (
        generation2_assignment.get("excluded_confidence_not_above_0_7") != 203456
        or generation2_assignment.get("eligible_open_status") != 687123
        or generation2_assignment.get("outside_accepted_support") != 278586
        or generation2_assignment.get("source_present_bbox_count") != 1160087
        or generation2_assignment.get("source_null_bbox_count") != 0
        or generation2_assignment.get("source_present_bbox_count", 0)
        + generation2_assignment.get("source_null_bbox_count", 0)
        != generation2_commitment_source.get("source_envelope_row_count")
        or generation2_assignment.get("permanently_closed_nonzero_confidence_reported") != 9538
        or generation2_assignment.get("assigned_commercial_place_count") != 457442
        or generation2_assigned_by_state != {"MI": 273602, "WI": 183840}
        or sum(generation2_assigned_by_state.values()) != generation2_assignment.get("assigned_commercial_place_count")
        or generation2_assignment.get("assigned_with_basic_category", 0)
        + generation2_assignment.get("assigned_missing_basic_category", 0)
        != generation2_assignment.get("assigned_commercial_place_count")
    ):
        raise SystemExit("MODEL-14 Generation-2 source and tract-assignment accounting differs")

    workflow = (repository / ".github/workflows/repository-validation.yml").read_text(encoding="utf-8")
    if "python scripts/check_model14_repository.py" not in workflow:
        raise SystemExit("MODEL-14 repository checker is absent from Repository Validation")
    report = (repository / REPORT_PATH).read_text(encoding="utf-8")
    for required_text in (
        "Baseline reproduction: **MATCH**",
        "Evidence disposition: **no credible improvement**",
        "No sealed, prospective Milwaukee, Madison, future-vintage, validation-only, or otherwise unconsumed target was opened",
        "MODEL-13 remains accepted and unchanged",
        "MASTER CONTROL ROOM: Sprouts Customer Geography",
    ):
        if required_text not in report:
            raise SystemExit(f"MODEL-14 pre-H report is missing required disposition text: {required_text}")

    generation2_report_path = repository / GENERATION2_REPORT_PATH
    generation2_result_present = generation2_report_path.is_file()
    if generation2_result_present:
        if not (repository / GENERATION2_EXPERIMENT_PATH).is_file():
            raise SystemExit("MODEL-14 Generation-2 pre-H report exists without its bounded experiment implementation")
        generation2_report = generation2_report_path.read_text(encoding="utf-8")
        generation2_report_lower = generation2_report.lower()
        for required_text in (
            "exploratory",
            "baseline reproduction",
            "no sealed",
            "model-13 remains accepted and unchanged",
            "app-01 remains accepted and unchanged",
            "master control room: sprouts customer geography",
        ):
            if required_text not in generation2_report_lower:
                raise SystemExit(
                    "MODEL-14 Generation-2 pre-H report is missing required exploratory or safeguard text: "
                    f"{required_text}"
                )

    stageable = _git(repository, "ls-files", "--cached", "--others", "--exclude-standard")
    assert_no_protected_tracked_paths(stageable)
    forbidden_stageable = [
        path
        for path in stageable
        if path.replace("\\", "/").startswith(("outputs/", "data/raw/", "data/cache/", "data/local/"))
        or path.lower().endswith((".parquet", ".duckdb"))
    ]
    if forbidden_stageable:
        raise SystemExit(f"MODEL-14 raw, generated, or protected paths became stageable: {forbidden_stageable}")
    changed = set(_git(repository, "diff", "--name-only", AUTHORIZATION_BASE, "--"))
    untracked = _git(repository, "ls-files", "--others", "--exclude-standard")
    # Repository Validation installs the package before conformance checks, which
    # creates standard untracked setuptools outputs that are not task changes.
    changed.update(
        path
        for path in untracked
        if not path.replace("\\", "/").startswith(("build/", "src/sprouts_customer_geography.egg-info/"))
    )
    required_changed = EXPECTED_CHANGED | GENERATION2_FREEZE_CHANGED
    allowed_changed = required_changed | GENERATION2_OPTIONAL_CHANGED
    if not required_changed <= changed or changed - allowed_changed:
        raise SystemExit(
            "MODEL-14 changed-file boundary differs: "
            f"unexpected={sorted(changed - allowed_changed)}, absent={sorted(required_changed - changed)}"
        )
    forbidden_predecessor_prefixes = (
        "config/model/model13_",
        "src/sprouts_customer_geography/model13/",
        "tests/test_model13_",
        "scripts/check_model13_",
        "presentation/app01/",
        "src/sprouts_customer_geography/app01/",
        "tests/app01/",
        "powerbi/pbi02/",
        "src/sprouts_customer_geography/pbi02/",
        "tests/pbi02/",
    )
    if any(path.replace("\\", "/").startswith(forbidden_predecessor_prefixes) for path in changed):
        raise SystemExit("MODEL-14 changed accepted MODEL-13, APP-01, or separate PBI-02 content")
    public_text = "\n".join((repository / path).read_text(encoding="utf-8", errors="ignore") for path in sorted(changed) if (repository / path).is_file())
    forbidden_fragments = ("C:" + "\\Users\\", "m13run-" + "primary", "m13run-" + "verification", "phandle-" + "model13")
    if any(fragment.lower() in public_text.lower() for fragment in forbidden_fragments):
        raise SystemExit("MODEL-14 protected path, run identity, or handle entered tracked content")

    print(json.dumps({
        "state": "passed",
        "task_posture": posture,
        "candidate_feature_count": len(FEATURE_IDS),
        "generation2_candidate_feature_count": len(GENERATION2_FEATURE_IDS),
        "tract_count": matrix["row_count"],
        "target_values_accessed_before_freeze": chronology["target_values_accessed"],
        "generation2_target_values_accessed_before_freeze": generation2_chronology["generation2_target_values_accessed"],
        "generation2_evaluation_state": (
            "exploratory_generation2_complete_pre_h"
            if generation2_result_present
            else "exploratory_generation2_public_features_frozen_pre_evaluation"
        ),
        "evaluation_state": "complete_pre_h_no_credible_improvement",
        "generation1_evaluation_state": "complete_pre_h_no_credible_improvement",
        "baseline_reproduction": "MATCH",
        "protected_tracked_path_guard": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
