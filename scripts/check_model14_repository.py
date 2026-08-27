"""Repository-safe MODEL-14 pre-H, chronology, and disclosure conformance."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys


AUTHORIZATION_BASE = "e464d5ea2453d7387102d64154bb52f410b12670"
TARGET_BLIND_FREEZE_COMMIT = "d516f2ffce151d83df8c80ea293ea84550378fbf"
CONTRACT_PATH = "config/model14/experimental_public_feature_contract.json"
COMMITMENT_PATH = "config/model14/target_blind_public_feature_commitment.json"
FREEZE_COMMITMENT_PATH = "config/model/model14_target_blind_public_feature_commitment.json"
REPORT_PATH = "docs/experiments/MODEL_14_PUBLIC_FEATURE_EXPANSION_PRE_H_REPORT.md"
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


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.model14.public import FEATURE_IDS, load_contract
    from sprouts_customer_geography.pipe01.canonical import content_digest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    required = {
        CONTRACT_PATH,
        COMMITMENT_PATH,
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

    stageable = _git(repository, "ls-files", "--cached", "--others", "--exclude-standard")
    assert_no_protected_tracked_paths(stageable)
    forbidden_stageable = [path for path in stageable if path.replace("\\", "/").startswith(("outputs/", "data/raw/", "data/cache/", "data/local/"))]
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
    if changed != EXPECTED_CHANGED:
        raise SystemExit(f"MODEL-14 changed-file boundary differs: unexpected={sorted(changed - EXPECTED_CHANGED)}, absent={sorted(EXPECTED_CHANGED - changed)}")
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
        "tract_count": matrix["row_count"],
        "target_values_accessed_before_freeze": chronology["target_values_accessed"],
        "evaluation_state": "complete_pre_h_no_credible_improvement",
        "baseline_reproduction": "MATCH",
        "protected_tracked_path_guard": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
