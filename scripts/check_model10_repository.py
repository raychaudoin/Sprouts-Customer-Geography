"""Repository-safe MODEL-10 schema, source, and tracked-path guard."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    schemas = repository / "schemas/model10"
    expected = {
        "protected_handle_registry.schema.json",
        "wisconsin_cohort_identity_lineage_commitment.schema.json",
        "wisconsin_cohort_identity_lineage_package.schema.json",
    }
    found = {path.name for path in schemas.glob("*.schema.json")}
    if found != expected:
        raise SystemExit(f"MODEL-10 schema inventory mismatch: {sorted(found)}")
    for path in schemas.glob("*.schema.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"invalid MODEL-10 schema declaration: {path.name}")

    contract = json.loads((repository / "config/model/model10_wisconsin_cohort_identity_lineage_contract.json").read_text(encoding="utf-8"))
    if contract.get("artifact_id") != "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_CONTRACT_V1":
        raise SystemExit("MODEL-10 contract identity mismatch")
    rules = contract["model04_rule_reuse"]
    if rules.get("probable_same_max_m") != 10.0 or rules.get("genuinely_new_minimum_m_exclusive") != 500.0 or rules.get("new_threshold_or_tolerance_introduced") is not False:
        raise SystemExit("MODEL-10 rule reuse differs from accepted MODEL-04 authority")
    market_rule = contract["successor_market_lineage_rule"]
    if market_rule.get("source_market_retained_exactly_as_lineage") is not True or market_rule.get("physical_location_matching_partition") != "wisconsin_state" or market_rule.get("source_market_label_is_physical_identity_partition") is not False:
        raise SystemExit("MODEL-10 statewide market-lineage rule differs from explicit authority")
    commitment = json.loads((repository / "config/model/model10_wisconsin_cohort_identity_lineage_commitment.json").read_text(encoding="utf-8"))
    if commitment.get("artifact_id") != "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_COMMITMENT_V1" or commitment.get("protected_package_id") != "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_PACKAGE_V1":
        raise SystemExit("MODEL-10 commitment identity mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", str(commitment.get("commitment_sha256"))):
        raise SystemExit("MODEL-10 nondisclosing commitment is missing")
    if commitment.get("protected_package_digest_disclosed") is not False or commitment.get("nonce_disclosed") is not False or commitment.get("observation_content_disclosed") is not False:
        raise SystemExit("MODEL-10 commitment disclosure boundary mismatch")

    resolver_source = (repository / "src/sprouts_customer_geography/model10/resolver.py").read_text(encoding="utf-8").lower()
    prohibited_discovery = (".glob(", ".rglob(", ".iterdir(", "os.walk(")
    used = [operation for operation in prohibited_discovery if operation in resolver_source]
    if used:
        raise SystemExit(f"MODEL-10 resolver contains discovery operation(s): {used}")

    stageable = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    print(json.dumps({"state": "passed", "schema_count": len(found), "explicit_handle_only": True, "model04_rule_reuse": True, "nondisclosing_commitment": True, "tracked_path_safeguard": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
