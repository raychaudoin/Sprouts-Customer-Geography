"""Target-blind baseline computability through every declared validation split."""
from pathlib import Path
import json
import numpy as np

from sprouts_customer_geography.readiness.store import recover_project_state
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from .evidence import OUTPUT_ID
from .intake import SOURCE_ROLES
from .modeling import FoldPreprocessor, build_candidates, grouped_folds, load_library, ModelingError
from .workflow import read_json, feature_package, make_dataset, selected_rows, write_private, complete_artifact_version


def validate_preflight(identity, package, library):
    rows = selected_rows(identity, package, "development", eligible_only=True)
    data = make_dataset(rows, package, {row["observation_id"]: 1.0 for row in rows})
    data.validate(development=True)
    candidate = build_candidates(data, library)[0]
    indices = tuple(data.feature_names.index(name) for name in candidate["features"])
    outer = grouped_folds(data.groups, data.states, library["outer_folds"], library["seed"])
    checks = 0
    def check(train, test):
        nonlocal checks
        preprocessor = FoldPreprocessor(indices, data.feature_names, True, library["preprocessing"], "baseline_elastic_net")
        preprocessor.fit(train.X, train.groups)
        require(np.isfinite(preprocessor.transform(test.X)).all(), "MODEL16_BASELINE_PREFLIGHT_NONFINITE", "the baseline preprocessor cannot compute a declared split")
        checks += 1
    for fold in range(library["outer_folds"]):
        train, test = data.take(outer != fold), data.take(outer == fold)
        check(train, test)
        inner = grouped_folds(train.groups, train.states, library["inner_folds"], library["seed"]+1)
        for inner_fold in range(library["inner_folds"]):
            check(train.take(inner != inner_fold), train.take(inner == inner_fold))
    # Final refit tuning also has its own full-development inner folds.
    inner = grouped_folds(data.groups, data.states, library["inner_folds"], library["seed"]+1)
    for fold in range(library["inner_folds"]):
        check(data.take(inner != fold), data.take(inner == fold))
    for role in ("seed_2026", "pursued"):
        selected = selected_rows(identity, package, role, eligible_only=True)
        holdout_features = make_dataset(selected, package, {row["observation_id"]: 1.0 for row in selected})
        check(data, holdout_features)
    return {"stage": "TARGET_BLIND_BASELINE_PREFLIGHT", "ready": True, "split_checks": checks,
            "development_observations": len(rows), "development_physical_locations": len(set(data.groups)),
            "real_targets_read": 0, "target_blind": True}


def main():
    try:
        repo = Path.cwd()
        store = recover_project_state(repository_root=repo)
        require(all(store.event_states(key).get("machine_target_read", "absent") in {"absent", "false"} for key in SOURCE_ROLES), "MODEL16_PREFLIGHT_TARGET_ACCESS_ALREADY_OCCURRED", "this preflight must precede target opening")
        output = store.resolve_asset(OUTPUT_ID).path
        _, package = feature_package(repo, output)
        result = validate_preflight(read_json(output / "identity.json"), package, load_library())
        write_private(output / ("preflight-" + complete_artifact_version(repo) + ".json"), result)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ConformanceError, ModelingError) as exc:
        print(json.dumps({"ready": False, "reason_code": str(exc).split(":")[0]}))
        return 2
    except (OSError, ValueError, KeyError):
        print(json.dumps({"ready": False, "reason_code": "MODEL16_PREFLIGHT_FAILED"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
