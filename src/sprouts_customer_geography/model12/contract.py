"""Repository-safe authority verification for MODEL-12."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256
from sprouts_customer_geography.pipe01.errors import require


CONTRACT_ID = "MODEL12_MICHIGAN_TARGET_BLIND_FROZEN_SCORING_CONTRACT_V1"
CONTRACT_VERSION = "1.0.0"
CONTRACT_PATH = "config/model/model12_michigan_target_blind_frozen_scoring_contract.json"


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required repository authority is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        require(False, code, "required repository authority is unreadable")
    require(isinstance(value, dict), code, "required repository authority must be an object")
    return value


def _canonical_digest(document: Mapping[str, Any]) -> str:
    semantic = copy.deepcopy(dict(document))
    semantic.pop("content_sha256", None)
    return content_digest(semantic)


def _require_commit(repository_root: Path, commit: str) -> None:
    present = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repository_root,
        capture_output=True,
        text=True,
    )
    require(present.returncode == 0, "MODEL12_ACCEPTED_GIT_LINEAGE_MISSING", "accepted predecessor commit is absent")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=repository_root,
        capture_output=True,
        text=True,
    )
    require(ancestor.returncode == 0, "MODEL12_ACCEPTED_GIT_LINEAGE_MISSING", "accepted predecessor commit is not an ancestor of execution HEAD")


def verify_repository_authority(repository_root: Path) -> dict[str, Any]:
    """Require the exact accepted public, identity, and frozen-model authority."""

    root = repository_root.resolve()
    contract = _load_object(root / CONTRACT_PATH, "MODEL12_CONTRACT_MISSING")
    require(
        contract.get("artifact_id") == CONTRACT_ID
        and contract.get("version") == CONTRACT_VERSION
        and contract.get("content_sha256") == _canonical_digest(contract),
        "MODEL12_CONTRACT_IDENTITY_MISMATCH",
        "MODEL-12 contract identity version or content hash differs",
    )

    accepted = contract.get("accepted_authority")
    require(isinstance(accepted, Mapping), "MODEL12_ACCEPTED_AUTHORITY_INVALID", "accepted authority is absent")
    loaded: dict[str, dict[str, Any]] = {}
    for key in ("data04", "geo05", "model10", "model11"):
        authority = accepted.get(key)
        require(isinstance(authority, Mapping), "MODEL12_ACCEPTED_AUTHORITY_INVALID", f"accepted {key} authority is absent")
        path = root / str(authority.get("path"))
        document = _load_object(path, "MODEL12_ACCEPTED_AUTHORITY_MISSING")
        require(
            document.get("artifact_id") == authority.get("artifact_id")
            and str(document.get("version")) == str(authority.get("version"))
            and file_sha256(path) == authority.get("repository_file_sha256")
            and _canonical_digest(document) == authority.get("content_sha256"),
            "MODEL12_ACCEPTED_AUTHORITY_MISMATCH",
            f"accepted {key} identity or hash differs",
        )
        loaded[key] = document
        _require_commit(root, str(authority.get("accepted_substantive_h")))

    canonical = str(accepted.get("canonical_main_at_authorization"))
    _require_commit(root, canonical)
    require(
        loaded["geo05"]["data04_source_authority"]["contract"]["content_sha256"]
        == accepted["data04"]["content_sha256"]
        and loaded["geo05"]["model_downstream_compatibility"]["model11_contract"]["content_sha256"]
        == accepted["model11"]["content_sha256"],
        "MODEL12_PUBLIC_AUTHORITY_BINDING_MISMATCH",
        "GEO-05 does not bind the exact accepted DATA-04 and MODEL-11 authority",
    )
    require(
        loaded["model11"]["accepted_authority"]["model10_contract_id"]
        == accepted["model10"]["artifact_id"]
        and loaded["model11"]["accepted_authority"]["data03_contract_id"]
        == "DATA03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE_CONTRACT_V1",
        "MODEL12_MODEL11_AUTHORITY_BINDING_MISMATCH",
        "MODEL-11 predecessor identity differs",
    )
    preferred = str(accepted["model11"]["preferred_candidate_id"])
    require(
        preferred == "challenger_multivariate_elastic_net"
        and preferred in {candidate.get("candidate_id") for candidate in loaded["model11"].get("candidates", [])},
        "MODEL12_FROZEN_CANDIDATE_MISMATCH",
        "accepted MODEL-11 preferred candidate differs",
    )

    projection = contract["source_projection"]
    identity = contract["physical_location_identity"]
    public = contract["public_feature_application"]
    scoring = contract["frozen_scoring"]
    future = contract["future_transport_evaluation_freeze"]
    require(
        projection.get("outcome_body_values_materialized") is False
        and projection.get("body_values_outside_projection_materialized") is False
        and projection.get("whole_source_file_hash_permitted") is False
        and projection.get("target_content_invariance_required") is True
        and projection.get("required_forecast_vintages") == [2024, 2025, 2026],
        "MODEL12_TARGET_BLIND_CONTRACT_MISMATCH",
        "MODEL-12 hard target-blind source boundary differs",
    )
    require(
        identity.get("reused_identity_version") == "MODEL04_TARGET_BLIND_PHYSICAL_LOCATION_IDENTITY_V1"
        and identity.get("probable_same_max_m") == 10.0
        and identity.get("coherent_stable_non_target_lineage_max_m") == 500.0
        and identity.get("ambiguity_band_m") == {"exclusive_minimum": 10.0, "inclusive_maximum": 500.0}
        and identity.get("market_label_is_identity_partition") is False
        and identity.get("target_evidence_permitted") is False
        and identity.get("new_threshold_or_tolerance_introduced") is False,
        "MODEL12_IDENTITY_CONTRACT_MISMATCH",
        "accepted target-blind physical-location rules differ",
    )
    require(
        public.get("radii_m") == [4828.032, 8046.72, 11265.408]
        and public.get("operation_fingerprint_sha256")
        == loaded["geo05"]["geo03_methodology"]["operation_fingerprint_sha256"]
        and public.get("michigan_redundancy_screen") is False
        and public.get("michigan_feature_selection") is False
        and public.get("imputation") is False
        and public.get("support_completeness_threshold") is None,
        "MODEL12_PUBLIC_FEATURE_CONTRACT_MISMATCH",
        "MODEL-12 public feature or support semantics differ",
    )
    require(
        scoring.get("preferred_candidate_id") == preferred
        and all(scoring.get(flag) is False for flag in ("refit", "retrain", "retune", "feature_selection", "recalibration"))
        and scoring.get("noncomputable_status") == "MODEL_SCORE_NONCOMPUTABLE",
        "MODEL12_FROZEN_SCORING_CONTRACT_MISMATCH",
        "MODEL-12 frozen scoring boundary differs",
    )
    require(
        future.get("independence_unit") == "unique physical location"
        and future.get("metrics") == ["spearman", "kendall_tau_b", "log_rmse", "level_mae"]
        and future.get("pass_fail_conclusion_authorized") is False
        and future.get("target_access_authorized") is False,
        "MODEL12_FUTURE_EVALUATION_FREEZE_MISMATCH",
        "future Michigan transport-evaluation freeze differs",
    )
    return contract
