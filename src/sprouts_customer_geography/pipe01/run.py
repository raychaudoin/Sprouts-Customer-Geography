"""Protected-local staged execution and immutable finalization."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from sprouts_customer_geography.constants import PIPE_SCHEMA_VERSION

from .canonical import content_digest, file_sha256, write_json_exclusive
from .commitment import freeze_commitment, new_nonce
from .errors import require
from .pipeline import reject_target_inputs


MANDATORY_DEPENDENCIES = {
    "data01_config_id",
    "data01_config_version",
    "data01_artifact_sha256",
    "geo02_context_spec_id",
    "geo02_context_artifact_sha256",
    "geo03_transform_fingerprint",
    "geo03_artifact_sha256",
    "model04_package_id",
    "model04_package_version",
    "model04_package_sha256",
    "model05_model_spec_id",
    "model05_model_spec_version",
    "model05_artifact_sha256",
    "model05_preregistration_id",
    "model05_preregistration_version",
    "tiger_source_manifest_id",
    "tiger_source_sha256",
    "canonical_inventory_derivation_spec_id",
    "acs_source_identity",
    "acs_retrieval_provenance_id",
    "acs_retrieval_manifest_sha256",
}


def audit_dependency_package(dependencies: Mapping[str, Any]) -> dict[str, Any]:
    """Return names/states only; never echo protected dependency values."""
    missing = sorted(key for key in MANDATORY_DEPENDENCIES if not dependencies.get(key))
    unexpected = sorted(set(dependencies) - MANDATORY_DEPENDENCIES)
    return {
        "state": "established" if not missing and not unexpected else "blocked",
        "required_count": len(MANDATORY_DEPENDENCIES),
        "established_count": len(MANDATORY_DEPENDENCIES) - len(missing),
        "missing_fields": missing,
        "unexpected_fields": unexpected,
    }


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


class ProtectedRun:
    """One opaque protected run. Finalized run IDs can never be reused."""

    def __init__(self, protected_root: Path, repository_root: Path, run_id: str | None = None, supersedes: str | None = None):
        self.protected_root = protected_root.resolve()
        self.repository_root = repository_root.resolve()
        require(not _is_within(self.protected_root, self.repository_root), "PROTECTED_ROOT_INSIDE_REPOSITORY", "protected output root must be physically outside the repository")
        self.run_id = run_id or f"prun-{uuid.uuid4()}"
        require(self.run_id.startswith("prun-") and all(char.isalnum() or char in "-_" for char in self.run_id), "RUN_ID_INVALID", "protected run ID must be opaque and filesystem-safe")
        self.run_dir = self.protected_root / "runs" / self.run_id
        require(not self.run_dir.exists(), "RUN_ALREADY_EXISTS", "never overwrite an existing or finalized protected run")
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.supersedes = supersedes
        write_json_exclusive(
            self.run_dir / "run_state.json",
            {"run_id": self.run_id, "state": "incomplete", "finalization_state": "not_started", "supersedes": supersedes},
        )

    def write_artifact(self, name: str, value: Any) -> Path:
        require(name.endswith(".json") and Path(name).name == name, "ARTIFACT_NAME_INVALID", "artifact name must be a simple JSON filename")
        reject_target_inputs(value)
        path = self.run_dir / "artifacts" / name
        write_json_exclusive(path, value)
        return path

    def finalize(
        self,
        dependencies: Mapping[str, Any],
        code_identity: str,
        configuration_identities: Mapping[str, Any],
        conformance_results: Mapping[str, Any],
        sealed_targets_supplied: bool,
    ) -> dict[str, Any]:
        dependency_audit = audit_dependency_package(dependencies)
        require(not dependency_audit["missing_fields"], "ACCEPTED_DEPENDENCIES_MISSING", f"missing accepted dependency identities: {dependency_audit['missing_fields']}")
        require(not dependency_audit["unexpected_fields"], "UNEXPECTED_DEPENDENCIES_REJECTED", f"unexpected dependency fields: {dependency_audit['unexpected_fields']}")
        reject_target_inputs(dependencies)
        reject_target_inputs(configuration_identities)
        reject_target_inputs(conformance_results)
        require(bool(code_identity), "CODE_IDENTITY_MISSING", "exact code identity is required")
        require(bool(configuration_identities), "CONFIGURATION_IDENTITY_MISSING", "exact configuration identities are required")
        require(conformance_results.get("mandatory_passed") is True, "CONFORMANCE_NOT_PASSED", "mandatory protected-run conformance must pass")
        require(sealed_targets_supplied is False, "SEALED_TARGETS_PROHIBITED", "sealed targets must not be supplied to the freeze pipeline")
        artifact_dir = self.run_dir / "artifacts"
        artifacts = sorted(artifact_dir.glob("*.json")) if artifact_dir.exists() else []
        require(bool(artifacts), "FREEZE_ARTIFACTS_MISSING", "no protected freeze artifacts were written")
        artifact_hashes = {path.name: file_sha256(path) for path in artifacts}
        run_manifest = {
            "run_id": self.run_id,
            "pipe_schema_version": PIPE_SCHEMA_VERSION,
            "dependency_ids": dict(dependencies),
            "source_checksums": {"tiger_source_sha256": dependencies["tiger_source_sha256"]},
            "code_identity": code_identity,
            "configuration_identities": dict(configuration_identities),
            "protected_input_package_identity": f"{dependencies['model04_package_id']}@{dependencies['model04_package_version']}",
            "artifact_ids": artifact_hashes,
            "conformance_results": dict(conformance_results),
            "run_state": "frozen",
            "finalization_state": "complete",
            "supersedes": self.supersedes,
        }
        write_json_exclusive(self.run_dir / "run_manifest.json", run_manifest)
        manifest = {
            "run_id": self.run_id,
            "state": "frozen",
            "finalization_state": "complete",
            "supersedes": self.supersedes,
            "code_identity": code_identity,
            "configuration_identities": dict(configuration_identities),
            "dependencies": dict(dependencies),
            "protected_artifact_sha256": artifact_hashes,
            "run_manifest_sha256": file_sha256(self.run_dir / "run_manifest.json"),
            "conformance_results": dict(conformance_results),
            "target_blind_statement": "Sealed validation targets were not supplied to or used by the PIPE-01 freeze pipeline.",
        }
        manifest_digest = content_digest(manifest)
        nonce = new_nonce()
        commitment = freeze_commitment(manifest_digest, nonce)
        write_json_exclusive(self.run_dir / "freeze_manifest.json", manifest)
        nonce_path = self.run_dir / "freeze_nonce.bin"
        with nonce_path.open("xb") as handle:
            handle.write(nonce)
            handle.flush()
            os.fsync(handle.fileno())
        write_json_exclusive(
            self.run_dir / "commitment_evidence.json",
            {"domain": "sprouts-customer-geography/pipe01/freeze-commitment/v1", "commitment_sha256": commitment},
        )
        # Completion marker is deliberately last. Its absence means incomplete.
        write_json_exclusive(
            self.run_dir / "FROZEN.json",
            {"run_id": self.run_id, "state": "frozen", "finalization_state": "complete", "commitment_sha256": commitment},
        )
        return {"run_id": self.run_id, "commitment_sha256": commitment, "state": "frozen"}


def protected_run_is_frozen(run_dir: Path) -> bool:
    return (run_dir / "FROZEN.json").is_file()
