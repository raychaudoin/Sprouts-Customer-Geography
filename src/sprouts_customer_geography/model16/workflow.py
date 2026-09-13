"""MODEL-16 protected orchestration. Output is restricted to safe aggregates."""
from __future__ import annotations

import argparse
import hashlib
import math
from collections import Counter
import json
import os
import pickle
import sqlite3
from pathlib import Path

import numpy as np

from sprouts_customer_geography.readiness.store import recover_project_state
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from .evidence import register_assets, register_evidence_package, StageJournal, OUTPUT_ID
from .intake import inspect_workbook, reconcile_identity, load_targets, SOURCE_ROLES, IntakeError
from .public_data import canonical, digest_file


ROLE_MAP = {"development": "development", "seed_2026": "temporal_test", "pursued": "pursued_test"}
ACCESS_ROLE = {"development": "development", "seed_2026": "temporal_2026", "pursued": "pursued_sites"}


def json_value(value):
    """Finite serialization for protected numerical results; never a sanitizer."""
    if isinstance(value, np.ndarray):
        return json_value(value.tolist())
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_bytes(path, encoded):
    path = Path(path)
    require(not path.is_symlink(), "MODEL16_OUTPUT_SYMLINK", "protected output may not be a symbolic link")
    if path.exists():
        require(path.read_bytes() == encoded, "MODEL16_OUTPUT_REPLAY_MISMATCH", "protected output differs from the completed stage")
        return
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def write_private(path, payload):
    encoded = canonical(payload) + b"\n"
    write_bytes(path, encoded)


def analytical_code(repository):
    """Bind implementation and accepted upstream computation, excluding reports."""
    repo = Path(repository)
    files = sorted(path for path in (repo / "src/sprouts_customer_geography").rglob("*.py") if path.name != "reporting.py")
    files += sorted((repo / "config").rglob("*.json"))
    files += [repo / "pyproject.toml"]
    return {path.relative_to(repo).as_posix(): digest_file(path) for path in files}


def combined_catalog(repository):
    from .features import feature_catalog
    from .public_context import feature_catalog as supplemental_catalog
    catalog = feature_catalog(repository)
    catalog["features"] += supplemental_catalog()
    catalog["eligibility"] = "All source observations retained in evidence; common primary modeling support requires an unambiguous baseline containing tract and three finite spatial household measures. Exclusions are fixed before any targets. Other feature missingness is handled within folds."
    catalog["direction_policy"] = "No sign constraints inferred from targets; hypotheses describe context rather than assert causal customer-fit effects."
    catalog["licensing"] = "Official US government public statistical products; source-specific rights, upstream lineage and omissions recorded in PUBLIC_SOURCE_RESEARCH.md and source_research.json."
    # Public source reference-year maps may have integer keys in Python; the
    # immutable JSON contract always has strings and must round-trip exactly.
    return json.loads(canonical(catalog))


def acs_artifact_version(repository):
    """A corrected recipe gets a new file; prior protected outputs stay intact."""
    from .features import feature_catalog
    from .public_sources import MANIFEST_PATH
    repo = Path(repository)
    modules = ("features.py", "public_data.py", "workflow.py")
    recipe = {"catalog": feature_catalog(repo), "public_manifest_digest": digest_file(repo / MANIFEST_PATH),
              "implementation": {name: digest_file(repo / "src/sprouts_customer_geography/model16" / name) for name in modules}}
    return hashlib.sha256(canonical(recipe)).hexdigest()


def complete_artifact_version(repository):
    from .public_sources import MANIFEST_PATH
    repo = Path(repository)
    modules = ("public_context.py", "lodes_context.py", "bps_context.py", "public_sources.py", "workflow.py")
    recipe = {"catalog": combined_catalog(repo), "acs_artifact_version": acs_artifact_version(repo),
              "public_manifest_digest": digest_file(repo / MANIFEST_PATH),
              "implementation": {name: digest_file(repo / "src/sprouts_customer_geography/model16" / name) for name in modules}}
    return hashlib.sha256(canonical(recipe)).hexdigest()


def prepare(repository, paths):
    """Join only public features to registered protected identities, without targets."""
    from .public_context import SupplementalContext, feature_catalog as extra_catalog
    from .public_sources import verify_manifest, MANIFEST_PATH
    repo, output = Path(repository), paths[OUTPUT_ID]
    identity = read_json(output / "identity.json")
    require(identity["ready"], "MODEL16_IDENTITY_UNRESOLVED", "resolve identity before feature preparation")
    acs_version = acs_artifact_version(repo)
    verify_manifest(repo, repo / "data/cache/model16")
    acs_path = output / ("features-acs-" + acs_version + ".json")
    acs = read_json(acs_path)
    source_binding = read_json(output / ("features-acs-" + acs_version + ".sources.json"))
    require(source_binding == {"public_manifest_digest": digest_file(repo / MANIFEST_PATH), "matrix_digest": digest_file(acs_path)},
            "MODEL16_ACS_SOURCE_BINDING_CHANGED", "prepared ACS values must be bound to this verified public source manifest")
    require(set(acs) == {row["observation_id"] for row in identity["rows"]}, "MODEL16_FEATURE_MEMBERSHIP_MISMATCH", "every identity requires a feature row")
    context = SupplementalContext(repo / "data/cache/model16")
    names = [item["feature_id"] for item in extra_catalog()]
    matrix, eligibility = {}, {}
    for row in identity["rows"]:
        key = row["observation_id"]
        item = acs[key]
        anchor = item["quality"].get("anchor_tract")
        extra, qa = context.vector(row, anchor) if anchor else (dict.fromkeys(names), {"status": "BASELINE_ANCHOR_UNRESOLVED"})
        values = {**item["features"], **extra}
        eligible = anchor is not None and all(values[name] is not None and math.isfinite(values[name]) for name in ("log_households_5mi", "inner_household_share_3mi_of_7mi", "log_inner_outer_household_density_gradient"))
        matrix[key] = {"features": values, "quality": {"acs": item["quality"], "supplemental": qa}}
        eligibility[key] = {"eligible": eligible, "reason": "COMPUTABLE" if eligible else "BASELINE_GEOGRAPHY_OR_HOUSEHOLDS_NONCOMPUTABLE"}
    catalog = combined_catalog(repo)
    version = complete_artifact_version(repo)
    package = {"catalog": catalog, "matrix": matrix, "eligibility": eligibility, "public_source_quality": context.source_quality,
               "public_manifest_digest": source_binding["public_manifest_digest"]}
    write_private(output / ("features-complete-" + version + ".json"), package)
    # This is a public definition document, never protected feature values.
    (repo / "config/model16/feature_catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return {"stage": "TARGET_BLIND_FEATURE_PREPARATION", "ready": True, "observations": len(matrix), "feature_count": len(catalog["features"]),
            "eligible_by_role": {role: sum(eligibility[row["observation_id"]]["eligible"] for row in identity["rows"] if row["role"] == role) for role in ROLE_MAP.values()},
            "missing_by_feature": {item["feature_id"]: sum(vector["features"][item["feature_id"]] is None for vector in matrix.values()) for item in catalog["features"]}}


def feature_package(repository, output):
    catalog = combined_catalog(repository)
    version = complete_artifact_version(repository)
    path = output / ("features-complete-" + version + ".json")
    package = read_json(path)
    require(package["catalog"] == catalog, "MODEL16_FEATURE_CATALOG_DRIFT", "prepared definitions differ from implementation")
    return path, package


def feature_freeze(repository, store, paths):
    from .modeling import load_library
    from .preflight import validate_preflight
    from .public_sources import verify_manifest, MANIFEST_PATH
    repo, output = Path(repository), paths[OUTPUT_ID]
    journal = StageJournal(output)
    with journal._connect() as connection:
        existing = "feature_freeze" in journal._verify(connection)
    if existing:
        verify_feature_freeze(repo, paths)
        return {"stage": "FEATURE_SOURCE_LIBRARY_FREEZE", "ready": True, "recovered_completed_freeze": True, "targets_reopened": False}
    prior_access = {logical: store.event_states(logical).get("machine_target_read", "absent") for logical in SOURCE_ROLES}
    require(all(value in {"absent", "false"} for value in prior_access.values()), "MODEL16_TARGETS_READ_BEFORE_FEATURE_FREEZE", "first feature freeze requires no prior or uncertain target access for every exact input asset")
    require(not any((output / filename).exists() for filename in ("development-targets.json", "development-result.pkl", "development-result-integrity.json")),
            "MODEL16_DEVELOPMENT_ARTIFACT_BEFORE_FEATURE_FREEZE", "development artifacts cannot precede the first feature freeze")
    source_manifest = verify_manifest(repo, repo / "data/cache/model16")
    identity = read_json(output / "identity.json")
    path, package = feature_package(repo, output)
    require(identity["ready"], "MODEL16_IDENTITY_UNRESOLVED", "identity must be resolved before freeze")
    require(package["public_manifest_digest"] == digest_file(repo / MANIFEST_PATH), "MODEL16_PREPARED_SOURCE_MANIFEST_DRIFT", "public-source decisions changed after feature preparation")
    preflight = validate_preflight(identity, package, load_library())
    # Original integrity is checked without decoding any target cells.
    require(all(digest_file(paths[key]) == identity["source_integrity"][key] for key in SOURCE_ROLES), "MODEL16_ORIGINAL_CHANGED", "an immutable original differs from intake")
    doc = {"generation": 1, "authority_commit": "12ee5ad97f9a422edeb63664641cfbbae49fe465", "analytical_code": analytical_code(repo),
           "identity_digest": digest_file(output / "identity.json"), "feature_package_digest": digest_file(path),
           "catalog": package["catalog"], "source_research": read_json(repo / "config/model16/source_research.json"), "public_source_manifest": source_manifest,
           "library": load_library(), "eligibility": package["eligibility"], "source_integrity": identity["source_integrity"],
           "target_access_before_freeze": {"development": False, "seed_2026": False, "pursued": False, "impacted": False},
           "prior_machine_target_read_by_asset": prior_access, "target_blind_baseline_preflight": preflight}
    journal.save_feature_freeze(doc)
    return {"stage": "FEATURE_SOURCE_LIBRARY_FREEZE", "ready": True, "feature_count": len(package["catalog"]["features"]), "holdouts_opened": 0}


def verify_feature_freeze(repository, paths):
    output = paths[OUTPUT_ID]
    journal = StageJournal(output)
    document = journal._freeze("feature_freeze")["document"]
    path, package = feature_package(repository, output)
    require(document["analytical_code"] == analytical_code(repository), "MODEL16_ANALYTICAL_CODE_CHANGED_AFTER_FREEZE", "the frozen analytical implementation changed")
    require(document["identity_digest"] == digest_file(output / "identity.json") and document["feature_package_digest"] == digest_file(path), "MODEL16_FROZEN_INPUT_CHANGED", "frozen identities or features changed")
    require(all(digest_file(paths[key]) == document["source_integrity"][key] for key in SOURCE_ROLES), "MODEL16_ORIGINAL_CHANGED", "an immutable original changed")
    return journal, read_json(output / "identity.json"), package


def selected_rows(identity, package, stage, *, eligible_only):
    rows = [row for row in identity["rows"] if row["role"] == ROLE_MAP[stage]]
    return [row for row in rows if package["eligibility"][row["observation_id"]]["eligible"]] if eligible_only else rows


def read_exact_targets(store, paths, identity, rows, stage, freeze_id=None):
    """Project a role's exact cells; all other Isolated and Impacted bodies denied."""
    values, audits = {}, {}
    for logical in SOURCE_ROLES:
        members = [row for row in rows if row["source_asset_id"] == logical]
        if not members:
            continue
        projection = inspect_workbook(paths[logical], SOURCE_ROLES[logical][0], source_id=logical)
        require(projection.workbook_sha256 == identity["source_integrity"][logical], "MODEL16_ORIGINAL_CHANGED", "source differs from target-blind identity")
        store.record_event("ASSET", logical, "machine_target_read", "uncertain", "MODEL16_" + stage.upper() + "_READ_STARTED")
        targets, audit = load_targets(paths[logical], projection, source_rows={row["source_row"] for row in members}, role=ACCESS_ROLE[stage], holdout_freeze_id=freeze_id)
        store.record_event("ASSET", logical, "machine_target_read", "true", "MODEL16_" + stage.upper() + "_ISOLATED_ONLY")
        values.update({row["observation_id"]: targets[row["source_row"]] for row in members})
        audits[logical] = audit.safe()
    require(len(values) == len(rows), "MODEL16_TARGET_MEMBERSHIP_INCOMPLETE", "target projection did not cover the exact role")
    return {"stage": stage, "values": values, "audits": audits}


def make_dataset(rows, package, values):
    from .modeling import Dataset
    features = package["catalog"]["features"]
    names = tuple(item["feature_id"] for item in features)
    return Dataset(np.asarray([[package["matrix"][row["observation_id"]]["features"][name] for name in names] for row in rows], dtype=float),
                   np.asarray([values[row["observation_id"]] for row in rows], dtype=float),
                   tuple(row["physical_location_id"] for row in rows), tuple(row["state"] for row in rows), tuple(row["forecast_year"] for row in rows),
                   tuple(row["evidence_class"] for row in rows), names, tuple(item["family"] for item in features),
                   tuple(item["feature_id"] for item in features if item["baseline"]), tuple(row["msa"] for row in rows))


def develop(repository, store, paths):
    from .modeling import run_development
    output = paths[OUTPUT_ID]
    journal, identity, package = verify_feature_freeze(repository, paths)
    model_path = output / "development-result.pkl"
    if model_path.exists():
        require((output / "development-result-integrity.json").exists(), "MODEL16_INTERRUPTED_MODEL_SAVE", "incomplete model persistence requires bounded recovery")
        commitment = read_json(output / "development-result-integrity.json")
        require(commitment["feature_freeze_digest"] == journal.feature_freeze_digest(), "MODEL16_DEVELOPMENT_FREEZE_MISMATCH", "saved fitted objects must belong to this feature freeze")
        require(digest_file(model_path) == commitment["sha256"], "MODEL16_MODEL_BYTES_CHANGED", "saved model differs from its commitment")
        result = pickle.loads(model_path.read_bytes())
    else:
        # Never restart development after any model freeze or holdout consumption.
        with journal._connect() as connection:
            require("model_freeze" not in journal._verify(connection), "MODEL16_DEVELOPMENT_AFTER_MODEL_FREEZE", "a frozen generation cannot be redesigned")
        targets_path = output / "development-targets.json"
        if targets_path.exists():
            targets = read_json(targets_path)
        else:
            targets = read_exact_targets(store, paths, identity, selected_rows(identity, package, "development", eligible_only=False), "development")
            targets["feature_freeze_digest"] = journal.feature_freeze_digest()
            write_private(targets_path, targets)
        require(targets["feature_freeze_digest"] == journal.feature_freeze_digest(), "MODEL16_DEVELOPMENT_FREEZE_MISMATCH", "development target access must follow this feature freeze")
        rows = selected_rows(identity, package, "development", eligible_only=True)
        data = make_dataset(rows, package, targets["values"])
        result = run_development(data, progress=lambda candidate: print(json.dumps({"stage": "NESTED_DEVELOPMENT", "candidate": candidate}), flush=True))
        # Repeat prediction uses frozen fit objects, with no additional target read.
        for model in result.frozen_models.values():
            require(np.array_equal(model.predict(data.X, data.states, data.feature_names), model.predict(data.X.copy(), data.states, data.feature_names)), "MODEL16_PREDICTION_NONDETERMINISTIC", "frozen predictions differ on identical inputs")
        write_bytes(model_path, pickle.dumps(result, protocol=5))
        write_private(output / "development-result-integrity.json", {"sha256": digest_file(model_path), "feature_freeze_digest": journal.feature_freeze_digest()})
    journal.save_freeze({"baseline_id": result.selection["baseline_id"], "challenger_id": result.selection["challenger_id"],
                         "feature_freeze_digest": journal.feature_freeze_digest(), "model_artifact_digest": digest_file(model_path),
                         "selection": result.selection, "generation": 1})
    return {"stage": "MODEL_FREEZE", "ready": True, "selection": result.selection, "candidates": len(result.diagnostics), "holdouts_opened": 0}


def frozen_result(journal, output):
    doc = journal._freeze("model_freeze")["document"]
    path = output / "development-result.pkl"
    require(digest_file(path) == doc["model_artifact_digest"], "MODEL16_MODEL_BYTES_CHANGED", "frozen fitted objects differ from their commitment")
    result = pickle.loads(path.read_bytes())
    require(result.selection == doc["selection"], "MODEL16_MODEL_SELECTION_CHANGED", "the frozen selection differs")
    return result


def holdout(repository, store, paths, stage):
    from .modeling import evaluate_frozen
    output = paths[OUTPUT_ID]
    journal, identity, package = verify_feature_freeze(repository, paths)
    recovered = journal.recover_result(stage)
    if recovered is not None:
        return {"stage": stage, "ready": True, "recovered_completed_result": True, "targets_reopened": False}
    result = frozen_result(journal, output)
    all_rows = selected_rows(identity, package, stage, eligible_only=False)
    rows = selected_rows(identity, package, stage, eligible_only=True)
    seeds = sorted({row["physical_location_id"] for row in identity["rows"] if row["evidence_class"] == "SEED_POINT"})
    # Validate all prediction paths on the known features before consuming a holdout.
    preflight = make_dataset(rows, package, {row["observation_id"]: 1.0 for row in rows})
    canonical(json_value(evaluate_frozen(result, preflight, role=ACCESS_ROLE[stage], all_seedpoint_groups=seeds)))
    ticket = journal.begin_holdout(stage)
    targets = read_exact_targets(store, paths, identity, all_rows, stage, ticket.freeze_digest)
    evaluation = evaluate_frozen(result, make_dataset(rows, package, targets["values"]), role=ACCESS_ROLE[stage], all_seedpoint_groups=seeds)
    journal.complete_holdout(ticket, {"evaluation": json_value(evaluation), "access": targets,
                                     "observation_ids": [row["observation_id"] for row in rows], "excluded_count": len(all_rows)-len(rows)})
    return {"stage": stage, "ready": True, "evaluated_observations": len(rows), "excluded_observations": len(all_rows)-len(rows), "one_time_completed": True, "models_evaluated": list(result.frozen_models)}


def finalize_evidence(repository, store, paths):
    journal, identity, package = verify_feature_freeze(repository, paths)
    result = frozen_result(journal, paths[OUTPUT_ID])
    require(all(journal.recover_result(stage) is not None for stage in ("seed_2026", "pursued")), "MODEL16_HOLDOUT_RESULTS_INCOMPLETE", "both one-time evaluations must be complete")
    observations = [{**row, "role": row["role"] if package["eligibility"][row["observation_id"]]["eligible"] else "excluded"} for row in identity["rows"]]
    candidates = {}
    for item in result.diagnostics:
        name = item["candidate_id"]
        candidates[name] = {"parent_model_id": None, "status": "frozen" if name in result.frozen_models else "candidate",
                            "membership": {row["observation_id"]: row["role"] if row["role"] in {"excluded", "development"} or name in result.frozen_models else "not_used" for row in observations}}
        for diagnostic in item.get("same_architecture_family_robustness", []):
            if "candidate_id" in diagnostic:
                candidates[diagnostic["candidate_id"]] = {"parent_model_id": name, "status": "candidate", "membership": {row["observation_id"]: row["role"] if row["role"] in {"excluded", "development"} else "not_used" for row in observations}}
    document = register_evidence_package(store, paths[OUTPUT_ID], observations, candidates)
    for logical in SOURCE_ROLES:
        store.register_source(logical, logical, "V2024_2026" if SOURCE_ROLES[logical][0] == "SEED_POINT" else "V2025", "ISOLATED_SALES", "ready")
    for filename, logical, kind in (("model16-stage-journal.sqlite3", "MODEL16_STAGE_JOURNAL", "MODEL16_FREEZE_AND_TARGET_ACCESS"),
                                   ("development-result.pkl", "MODEL16_FROZEN_DEVELOPMENT", "MODEL16_BOUNDED_CANDIDATE_RESULTS")):
        store.register_asset(logical, "MODEL16_REBUILD_OUTPUT_ROOT", filename, "PROTECTED_MODEL_RECORD")
        store.register_artifact(logical, logical, kind, "recoverable")
    store.verify()
    return {"stage": "BOUNDED_EVIDENCE_COMPLETE", "ready": document["bounded_readiness"] == "READY", "observations": len(observations), "candidates_with_exact_membership": len(candidates), "project_wide_completeness_claimed": False}


def report(repository, paths):
    """Write only the explicit aggregate report allowlist, never row-level outputs."""
    from .reporting import build_public_report, render_markdown
    journal, identity, package = verify_feature_freeze(repository, paths)
    temporal = journal.recover_result("seed_2026")
    pursued = journal.recover_result("pursued")
    require(temporal is not None and pursued is not None, "MODEL16_HOLDOUT_RESULTS_INCOMPLETE", "both one-time evaluations must be complete before reporting")
    observations = [{**row, "role": row["role"] if package["eligibility"][row["observation_id"]]["eligible"] else "excluded"} for row in identity["rows"]]
    missingness = {item["feature_id"]: {role: {state: sum(
                    package["matrix"][row["observation_id"]]["features"][item["feature_id"]] is None
                    for row in observations if row["role"] == role and (state == "all" or row["state"] == state))
                    for state in ("all", "MI", "WI")} for role in ("development", "temporal_test", "pursued_test", "excluded")}
                    for item in package["catalog"]["features"]}
    payload = build_public_report(frozen_result(journal, paths[OUTPUT_ID]), temporal, pursued,
                                  public_catalog=package["catalog"], observations=observations, public_missingness=missingness)
    root = Path(repository) / "docs/model16"
    write_bytes(root / "RESULTS.json", canonical(payload) + b"\n")
    write_bytes(root / "RESULTS.md", render_markdown(payload).encode("utf-8"))
    return {"stage": "DISCLOSURE_SAFE_REPORT", "ready": True, "targets_reopened": False}


def intake(store, paths):
    output = paths[OUTPUT_ID]
    projections = {logical: inspect_workbook(paths[logical], role[0], source_id=logical) for logical, role in SOURCE_ROLES.items()}
    for logical in SOURCE_ROLES:
        store.register_source(logical, logical, "V2024_2026" if SOURCE_ROLES[logical][0] == "SEED_POINT" else "V2025", "ISOLATED_SALES", "incomplete")
        store.record_event("ASSET", logical, "identity_read", "true", "MODEL16_TARGET_BLIND_INTAKE")
    identity = reconcile_identity(projections)
    normalized = [{**row, "source_asset_id": row["source_id"], "forecast_year": row["year"],
                   "role": {"temporal_2026": "temporal_test", "pursued_sites": "pursued_test"}.get(row["role"], row["role"])} for row in identity.rows]
    document = {"rows": normalized, "matches": identity.matches, "unresolved": identity.unresolved,
                "aggregates": identity.aggregates, "ready": identity.ready,
                "source_integrity": {key: value.workbook_sha256 for key, value in projections.items()},
                "audit": {key: value.audit.safe() for key, value in projections.items()}}
    write_private(output / "identity.json", document)
    result = dict(identity.aggregates)
    result["ready"] = identity.ready
    result["unresolved_reason_counts"] = dict(Counter(row["reason"] for row in identity.unresolved))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("register_identity", "identity", "features", "prepare", "freeze_features", "develop", "seed_2026", "pursued", "finalize_evidence", "report"))
    parser.add_argument("--input-mi", type=Path)
    parser.add_argument("--input-wi", type=Path)
    parser.add_argument("--input-pursued", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        store = recover_project_state(repository_root=Path.cwd())
        if args.stage == "register_identity":
            supplied = [args.input_mi, args.input_wi, args.input_pursued]
            require(all(path is not None for path in supplied) and args.output is not None,
                    "MODEL16_REGISTRATION_ARGUMENTS", "registration requires the three exact files and bounded output")
            require(len({path.parent.resolve() for path in supplied}) == 1,
                    "MODEL16_REGISTRATION_INPUT_ROOT", "all originals must share the authorized input directory")
            names = dict(zip(SOURCE_ROLES, [path.name for path in supplied]))
            paths = register_assets(store, supplied[0].parent, names, args.output, repository_root=Path.cwd())
        else:
            paths = {logical: store.resolve_asset(logical).path for logical in {*SOURCE_ROLES, OUTPUT_ID}}
        if args.stage == "prepare":
            result = prepare(Path.cwd(), paths)
        elif args.stage == "freeze_features":
            result = feature_freeze(Path.cwd(), store, paths)
        elif args.stage == "develop":
            result = develop(Path.cwd(), store, paths)
        elif args.stage in {"seed_2026", "pursued"}:
            result = holdout(Path.cwd(), store, paths, args.stage)
        elif args.stage == "finalize_evidence":
            result = finalize_evidence(Path.cwd(), store, paths)
        elif args.stage == "report":
            result = report(Path.cwd(), paths)
        elif args.stage == "features":
            from .features import materialize, feature_catalog
            from .public_sources import verify_manifest, MANIFEST_PATH
            verify_manifest(Path.cwd(), Path("data/cache/model16"))
            identity = json.loads((paths[OUTPUT_ID] / "identity.json").read_text())
            require(identity["ready"], "MODEL16_IDENTITY_UNRESOLVED", "identity reconciliation must finish before feature construction")
            matrix = materialize(Path.cwd(), Path("data/cache/model16"), identity["rows"])
            feature_version = acs_artifact_version(Path.cwd())
            matrix_path = paths[OUTPUT_ID] / ("features-acs-" + feature_version + ".json")
            write_private(matrix_path, matrix)
            write_private(paths[OUTPUT_ID] / ("features-acs-" + feature_version + ".sources.json"),
                          {"public_manifest_digest": digest_file(Path.cwd() / MANIFEST_PATH), "matrix_digest": digest_file(matrix_path)})
            result = {"stage": "PUBLIC_FEATURE_JOIN", "observations": len(matrix), "ready": True,
                      "status_counts": dict(Counter(row["quality"]["status"] for row in matrix.values())),
                      "missing_by_feature": {item["feature_id"]: sum(row["features"][item["feature_id"]] is None for row in matrix.values()) for item in feature_catalog(Path.cwd())["features"]}}
        else:
            result = intake(store, paths)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["ready"] else 2
    except (ConformanceError, IntakeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": str(exc).split(":")[0]}))
        return 2
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": "MODEL16_BOUNDED_OPERATION_FAILED", "error_type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
