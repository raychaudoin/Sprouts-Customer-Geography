"""Materialize accepted MODEL-04/MODEL-05 dependencies without target access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--repository-root", type=Path, required=True)
    value.add_argument("--development-workbook", type=Path, required=True)
    value.add_argument("--new-evidence-workbook", type=Path, required=True)
    value.add_argument("--protected-output-root", type=Path, required=True)
    value.add_argument("--commitment-output", type=Path)
    return value


def main() -> int:
    arguments = parser().parse_args()
    repository = arguments.repository_root.resolve()
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.model06 import (
        build_identity_package,
        read_target_blind_projection,
        validate_identity_package,
        validate_preregistration,
        write_protected_materialization,
        write_repository_json,
    )

    development = read_target_blind_projection(
        arguments.development_workbook.resolve(), "MODEL03A_DEVELOPMENT_REFERENCE_WORKBOOK"
    )
    new_evidence = read_target_blind_projection(
        arguments.new_evidence_workbook.resolve(), "MODEL04_NEW_TARGET_BLIND_IDENTITY_ROLE_WORKBOOK"
    )
    package = build_identity_package([development, new_evidence])
    package_result = validate_identity_package(package)
    preregistration_path = repository / "config" / "model" / "model05_prospective_validation_preregistration.json"
    preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
    preregistration_result = validate_preregistration(preregistration)
    package_path, _nonce_path, evidence = write_protected_materialization(
        arguments.protected_output_root, repository, package
    )
    if arguments.commitment_output:
        output = arguments.commitment_output.resolve()
        try:
            output.relative_to(repository)
        except ValueError as exc:
            raise SystemExit("commitment output must be within the repository") from exc
        write_repository_json(output, evidence)
    # Disclosure-safe output: no paths below the approved directory level, no
    # coordinates, IDs tied to records, protected digest, nonce, or target data.
    print(
        json.dumps(
            {
                "state": "materialized",
                "package_validation": package_result,
                "preregistration_validation": preregistration_result,
                "commitment_id": evidence["artifact_id"],
                "commitment_version": evidence["version"],
                "commitment_sha256": evidence["commitment_sha256"],
                "protected_output_root": str(arguments.protected_output_root.resolve()),
                "protected_package_exists": package_path.is_file(),
                "target_blind": True,
                "prediction_artifact_created": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
