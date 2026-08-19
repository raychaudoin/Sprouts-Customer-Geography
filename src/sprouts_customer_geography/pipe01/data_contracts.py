"""Validation of the repository-safe DATA-02 source contract."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .canonical import content_digest
from .errors import require


DATA_CONFIG_ID = "DATA01_VALIDATION_SOURCE_CONTRACT_V1"
TIGER_MANIFEST_ID = "DATA02_TIGER2024_WI_TRACT_SOURCE_MANIFEST_V1"
ACS_MANIFEST_ID = "DATA02_ACS2024_ACS5_B11001_WI_TRACT_SOURCE_MANIFEST_V1"


def _without(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop(field, None)
    return result


def verify_content_hash(document: Mapping[str, Any], field: str) -> str:
    """Verify a self-hash that deliberately excludes its own hash field."""
    expected = document.get(field)
    require(isinstance(expected, str) and len(expected) == 64, "DATA_CONTENT_HASH_MISSING", f"missing or invalid {field}")
    actual = content_digest(_without(document, field))
    require(actual == expected, "DATA_CONTENT_HASH_MISMATCH", f"{field} does not match canonical JSON")
    return actual


def _reject_moving_identity(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"accepted_vintage", "vintage", "source_reference", "product"} and isinstance(item, str):
                lowered = item.lower()
                require("latest" not in lowered and "current" not in lowered, "DATA_MOVING_IDENTITY_REJECTED", f"moving identity not permitted in {key}")
            _reject_moving_identity(item)
    elif isinstance(value, list):
        for item in value:
            _reject_moving_identity(item)


def _required_manifest_fields(manifest: Mapping[str, Any]) -> None:
    required = {
        "manifest_id", "manifest_version", "source_id", "source_name", "publisher", "accepted_vintage",
        "source_reference", "official_product_identity", "source_filename", "checksum_algorithm", "byte_sha256",
        "checksum_semantics", "acquisition_state", "schema_version", "lineage", "expected_file_properties",
        "reproduction", "failure_behavior", "supersedes", "supersession_policy", "manifest_content_sha256",
    }
    missing = sorted(field for field in required if field not in manifest or (manifest[field] == "" and field != "supersedes"))
    require(not missing, "DATA_MANIFEST_INCOMPLETE", f"missing required manifest fields: {missing}")
    require(manifest["manifest_version"] == "1.0.0", "DATA_MANIFEST_VERSION_MISMATCH", "unexpected DATA-02 manifest version")
    require(manifest["accepted_vintage"] == "2024", "DATA_SOURCE_VINTAGE_MISMATCH", "accepted source vintage must be 2024")
    require(manifest["checksum_algorithm"] == "SHA-256", "DATA_CHECKSUM_ALGORITHM_MISMATCH", "SHA-256 is required")
    require(manifest["acquisition_state"] == "acquired", "DATA_SOURCE_NOT_ACQUIRED", "authoritative source bytes are not acquired")
    _reject_moving_identity(manifest)
    verify_content_hash(manifest, "manifest_content_sha256")


def validate_data02_contract(config: Mapping[str, Any], tiger: Mapping[str, Any], acs: Mapping[str, Any]) -> dict[str, str]:
    """Fail closed unless all repository-safe DATA-02 identities agree exactly."""
    require(config.get("artifact_id") == DATA_CONFIG_ID, "DATA_CONFIG_ID_MISMATCH", "unexpected DATA configuration ID")
    require(config.get("version") == "1.0.0", "DATA_CONFIG_VERSION_MISMATCH", "unexpected DATA configuration version")
    require(config.get("hash_algorithm") == "SHA-256", "DATA_CONFIG_HASH_ALGORITHM_MISMATCH", "SHA-256 is required")
    config_required = {"status", "controlling_decision", "purpose", "accepted_sources", "content_hash_semantics", "supersedes", "supersession_policy", "failure_behavior"}
    missing_config = sorted(field for field in config_required if field not in config)
    require(not missing_config, "DATA_CONFIG_INCOMPLETE", f"missing required DATA configuration fields: {missing_config}")
    _reject_moving_identity(config)
    accepted_sources = config.get("accepted_sources")
    require(isinstance(accepted_sources, list), "DATA_CONFIG_SOURCES_INVALID", "accepted_sources must be a list")
    by_family = {source.get("family"): source for source in accepted_sources if isinstance(source, Mapping)}
    acs_config = by_family.get("American Community Survey")
    tiger_config = by_family.get("TIGER/Line")
    require(isinstance(acs_config, Mapping) and isinstance(tiger_config, Mapping), "DATA_CONFIG_SOURCES_INVALID", "ACS and TIGER/Line source identities are required")
    require(acs_config.get("product") == "2020-2024 ACS 5-Year Detailed Tables" and acs_config.get("vintage") == "2024", "DATA_CONFIG_ACS_IDENTITY_MISMATCH", "unexpected accepted ACS source identity")
    require(acs_config.get("household_opportunity_table") == "B11001" and acs_config.get("household_estimate_variable") == "B11001_001E" and acs_config.get("household_moe_variable") == "B11001_001M", "DATA_CONFIG_ACS_FIELD_MISMATCH", "unexpected B11001 household-opportunity mapping")
    require(tiger_config.get("product") == "2024 TIGER/Line Census Tracts" and tiger_config.get("vintage") == "2024", "DATA_CONFIG_TIGER_IDENTITY_MISMATCH", "unexpected accepted TIGER source identity")
    require(acs_config.get("source_manifest_id") == ACS_MANIFEST_ID and tiger_config.get("source_manifest_id") == TIGER_MANIFEST_ID, "DATA_CONFIG_MANIFEST_REFERENCE_MISMATCH", "DATA configuration must reference the accepted source manifests")
    config_hash = verify_content_hash(config, "content_sha256")

    _required_manifest_fields(tiger)
    _required_manifest_fields(acs)
    require(tiger.get("manifest_id") == TIGER_MANIFEST_ID, "TIGER_MANIFEST_ID_MISMATCH", "unexpected TIGER manifest ID")
    require(tiger.get("source_filename") == "tl_2024_55_tract.zip", "TIGER_SOURCE_IDENTITY_MISMATCH", "unexpected TIGER source filename")
    require(tiger.get("source_reference") == "https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_55_tract.zip", "TIGER_SOURCE_REFERENCE_MISMATCH", "unexpected TIGER retrieval surface")
    require(acs.get("manifest_id") == ACS_MANIFEST_ID, "ACS_MANIFEST_ID_MISMATCH", "unexpected ACS manifest ID")
    require(acs.get("source_filename") == "acsdt5y2024-b11001.dat", "ACS_SOURCE_IDENTITY_MISMATCH", "unexpected ACS source filename")
    require(acs.get("source_reference") == "https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b11001.dat", "ACS_SOURCE_REFERENCE_MISMATCH", "unexpected ACS retrieval surface")
    request = acs.get("request_identity")
    require(isinstance(request, Mapping), "ACS_REQUEST_IDENTITY_MISSING", "ACS request identity is required")
    require(content_digest(request) == acs.get("request_sha256"), "ACS_REQUEST_HASH_MISMATCH", "ACS request identity hash mismatch")
    fields = set(request.get("header_required", []))
    require({"GEO_ID", "B11001_E001", "B11001_M001"} <= fields, "ACS_REQUIRED_FIELD_MISSING", "required B11001 estimate/MOE source fields are absent")
    mapping = request.get("source_to_contract_mapping")
    require(mapping == {"B11001_E001": "B11001_001E", "B11001_M001": "B11001_001M"}, "ACS_FIELD_MAPPING_MISMATCH", "B11001 estimate/MOE mapping differs from the accepted contract")
    require(acs.get("request_hash_algorithm") == "SHA-256", "ACS_REQUEST_HASH_ALGORITHM_MISMATCH", "SHA-256 is required for ACS request identity")
    require(acs.get("byte_sha256"), "ACS_SOURCE_CHECKSUM_MISSING", "ACS source-byte checksum is required")
    require(tiger.get("byte_sha256"), "TIGER_SOURCE_CHECKSUM_MISSING", "TIGER source-byte checksum is required")
    return {
        "data01_config_id": DATA_CONFIG_ID,
        "data01_config_version": str(config["version"]),
        "data01_artifact_sha256": config_hash,
        "tiger_source_manifest_id": TIGER_MANIFEST_ID,
        "tiger_source_sha256": str(tiger["byte_sha256"]),
        "acs_source_identity": str(acs["source_id"]),
        "acs_retrieval_provenance_id": ACS_MANIFEST_ID,
        "acs_retrieval_manifest_sha256": str(acs["manifest_content_sha256"]),
    }
