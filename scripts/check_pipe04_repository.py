"""Repository-safe PIPE-04 schema, contract, source, and tracked-path guard."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    schemas = repository / "schemas/pipe04"
    expected = {
        "model10_wisconsin_development_binding.schema.json",
        "model10_wisconsin_development_binding_contract.schema.json",
        "protected_handle_registry.schema.json",
    }
    found = {path.name for path in schemas.glob("*.schema.json")}
    if found != expected:
        raise SystemExit(f"PIPE-04 schema inventory mismatch: {sorted(found)}")
    for path in schemas.glob("*.schema.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"invalid PIPE-04 schema declaration: {path.name}")

    contract = json.loads((repository / "config/pipe04/model10_wisconsin_development_binding_contract.json").read_text(encoding="utf-8"))
    if contract.get("artifact_id") != "PIPE04_MODEL10_WISCONSIN_DEVELOPMENT_BINDING_CONTRACT_V1":
        raise SystemExit("PIPE-04 contract identity mismatch")
    model10 = contract["accepted_model10_authority"]
    if model10.get("commitment_id") != "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_COMMITMENT_V1" or model10.get("package_id") != "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_PACKAGE_V1":
        raise SystemExit("PIPE-04 MODEL-10 authority mismatch")
    cohort = contract["cohort_rule"]
    identity = contract["identity_rule"]
    projection = contract["target_projection"]
    if cohort.get("complete_eligible_cohort_required") is not True or cohort.get("quarantined_excluded") is not True or cohort.get("target_content_may_change_membership_or_identity") is not False:
        raise SystemExit("PIPE-04 cohort authority mismatch")
    if identity.get("target_join_identity") != "MODEL-10 successor source-observation lineage" or identity.get("historical_source_observation_equality_required") is not False:
        raise SystemExit("PIPE-04 successor-lineage authority mismatch")
    if projection.get("allowed_target_field") != "Isolated Sales" or projection.get("denied_target_field") != "Impacted Sales" or projection.get("non_wisconsin_denied") is not True:
        raise SystemExit("PIPE-04 target boundary mismatch")

    resolver_source = (repository / "src/sprouts_customer_geography/pipe04/resolver.py").read_text(encoding="utf-8").lower()
    prohibited_discovery = (".glob(", ".rglob(", ".iterdir(", "os.walk(")
    used = [operation for operation in prohibited_discovery if operation in resolver_source]
    if used:
        raise SystemExit(f"PIPE-04 resolver contains discovery operation(s): {used}")

    stageable = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    print(json.dumps({"state": "passed", "schema_count": len(found), "explicit_handle_only": True, "model10_exact_authority": True, "isolated_sales_only": True, "tracked_path_safeguard": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
