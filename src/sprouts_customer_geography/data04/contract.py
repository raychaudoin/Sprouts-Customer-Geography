"""Validation for additive DATA-04 Michigan public-source authority."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping

from sprouts_customer_geography.data03.contract import (
    EXPECTED_MEASURE_IDS,
    EXPECTED_TABLE_IDS,
    component_index,
    load_source_manifests,
    validate_contract as validate_data03_contract,
)
from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.data_contracts import verify_content_hash
from sprouts_customer_geography.pipe01.errors import require


CONTRACT_ID = "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1"
VERSION = "1.0.0"
CONTRACT_PATH = Path("config/data/data04_michigan_public_data_parity_source_contract.json")
SCHEMA_PATH = Path("schemas/data04/michigan_public_data_parity_source_contract.schema.json")
HOUSEHOLD_MANIFEST_ID = "DATA02_ACS2024_ACS5_B11001_WI_TRACT_SOURCE_MANIFEST_V1"
TIGER_MANIFEST_ID = "DATA04_TIGER2024_MI_TRACT_SOURCE_MANIFEST_V1"
DATA03_CONTRACT_ID = "DATA03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE_CONTRACT_V1"
EXPECTED_TRACT_COUNT = 3017


@dataclass(frozen=True)
class Data04Authority:
    contract: Mapping[str, Any]
    data03_contract: Mapping[str, Any]
    household_manifest: Mapping[str, Any]
    multivariate_manifests: Mapping[str, Mapping[str, Any]]
    tiger_manifest: Mapping[str, Any]


def _without(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop(field, None)
    return result


def _verify_hash(document: Mapping[str, Any], field: str, code: str) -> str:
    expected = document.get(field)
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected) is not None, code, f"missing or invalid {field}")
    actual = content_digest(_without(document, field))
    require(actual == expected, code, f"{field} does not match canonical JSON")
    return actual


def _validate_tiger_manifest(contract: Mapping[str, Any], manifest: Mapping[str, Any]) -> str:
    manifest_hash = verify_content_hash(manifest, "manifest_content_sha256")
    require(manifest.get("manifest_id") == TIGER_MANIFEST_ID and manifest.get("manifest_version") == VERSION, "DATA04_TIGER_MANIFEST_IDENTITY_MISMATCH", "Michigan TIGER manifest identity differs")
    require(manifest.get("publisher") == "U.S. Census Bureau" and manifest.get("accepted_vintage") == "2024", "DATA04_TIGER_PRODUCT_MISMATCH", "Michigan TIGER publisher or vintage differs")
    require(manifest.get("source_filename") == "tl_2024_26_tract.zip", "DATA04_TIGER_SOURCE_MISMATCH", "Michigan TIGER filename differs")
    require(manifest.get("source_reference") == "https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_26_tract.zip", "DATA04_TIGER_SOURCE_MISMATCH", "Michigan TIGER URL differs")
    require(manifest.get("byte_sha256") == contract["tiger_source_authority"]["source_byte_sha256"], "DATA04_TIGER_SOURCE_MISMATCH", "Michigan TIGER checksum differs")
    properties = manifest.get("expected_file_properties", {})
    required_fields = {"STATEFP", "COUNTYFP", "TRACTCE", "GEOID", "INTPTLAT", "INTPTLON"}
    require(properties.get("expected_state_fips") == "26", "DATA04_TIGER_STATE_MISMATCH", "Michigan TIGER STATEFP authority differs")
    require(properties.get("expected_statewide_tract_row_count_at_retrieval") == EXPECTED_TRACT_COUNT, "DATA04_TIGER_TRACT_COUNT_MISMATCH", "Michigan TIGER tract count differs")
    require(set(properties.get("required_source_fields", [])) == required_fields, "DATA04_TIGER_FIELDS_MISMATCH", "Michigan TIGER required fields differ")
    require(properties.get("expected_crs") == "EPSG:4269", "DATA04_TIGER_CRS_MISMATCH", "Michigan TIGER source CRS differs")
    require(contract["source_products"]["tiger"]["official_terms_url"] in manifest.get("attribution", ""), "DATA04_TIGER_TERMS_MISMATCH", "Michigan TIGER manifest omits the official legal and citation reference")
    lineage = manifest.get("lineage", {})
    require(lineage.get("data_contract_id") == CONTRACT_ID and lineage.get("data_contract_content_sha256") == contract.get("content_sha256"), "DATA04_TIGER_LINEAGE_MISMATCH", "Michigan TIGER contract lineage differs")
    return manifest_hash


def validate_authority(
    contract: Mapping[str, Any],
    schema: Mapping[str, Any],
    data03_contract: Mapping[str, Any],
    household_manifest: Mapping[str, Any],
    multivariate_manifests: Mapping[str, Mapping[str, Any]],
    tiger_manifest: Mapping[str, Any],
) -> str:
    """Fail closed unless DATA-04 exactly binds accepted national ACS and Michigan TIGER authority."""
    require(contract.get("artifact_id") == CONTRACT_ID and contract.get("version") == VERSION, "DATA04_CONTRACT_IDENTITY_MISMATCH", "DATA-04 contract identity differs")
    require(contract.get("status") == "active" and contract.get("controlling_decision") == "DATA-04: Michigan Public-Data Parity Foundation", "DATA04_AUTHORITY_MISMATCH", "DATA-04 authority differs")
    require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "DATA04_SCHEMA_INVALID", "DATA-04 schema draft differs")
    require(set(schema.get("required", [])) <= set(contract), "DATA04_CONTRACT_INCOMPLETE", "DATA-04 contract omits a required field")
    require(set(contract) <= set(schema.get("properties", {})), "DATA04_CONTRACT_FIELD_PROHIBITED", "DATA-04 contract contains an ungoverned field")

    scope = contract.get("state_scope", {})
    require(scope.get("state_name") == "Michigan" and scope.get("state_slug") == "michigan" and scope.get("state_fips") == "26", "DATA04_STATE_SCOPE_MISMATCH", "Michigan state identity differs")
    require(scope.get("geography_level") == "tract" and scope.get("table_file_geo_id_prefix") == "1400000US26" and scope.get("tract_geoid_pattern") == r"^26[0-9]{9}$", "DATA04_GEOGRAPHY_SCOPE_MISMATCH", "Michigan tract extraction identity differs")
    require(scope.get("statewide") is True and scope.get("observed_tract_count") == EXPECTED_TRACT_COUNT, "DATA04_TRACT_COUNT_MISMATCH", "statewide Michigan tract count differs")

    products = contract.get("source_products", {})
    acs_product = products.get("acs", {})
    tiger_product = products.get("tiger", {})
    require(acs_product.get("product") == "2020-2024 ACS 5-Year Detailed Tables" and acs_product.get("vintage") == "2024" and acs_product.get("fixed_release") is True, "DATA04_ACS_PRODUCT_MISMATCH", "ACS product or vintage differs")
    require(acs_product.get("materialization_access_surface") == "official ACS table-based Summary File" and acs_product.get("credential_required") is False, "DATA04_ACS_ACCESS_SURFACE_MISMATCH", "ACS credential-free source surface differs")
    require(acs_product.get("official_terms_url") == "https://www.census.gov/data/developers/about/terms-of-service.html", "DATA04_ACS_TERMS_MISMATCH", "ACS terms reference differs")
    require(tiger_product.get("product") == "2024 TIGER/Line Census Tracts" and tiger_product.get("vintage") == "2024" and tiger_product.get("state_fips") == "26", "DATA04_TIGER_PRODUCT_MISMATCH", "TIGER product or state differs")
    require(tiger_product.get("official_terms_url") == "https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2024/TGRSHP2024_TechDoc_Ch1.pdf", "DATA04_TIGER_TERMS_MISMATCH", "TIGER legal and citation reference differs")

    validate_data03_contract(data03_contract)
    accepted = contract.get("accepted_acs_national_authority", {})
    data03_ref = accepted.get("data03_contract", {})
    require(data03_ref.get("artifact_id") == DATA03_CONTRACT_ID and data03_ref.get("content_sha256") == data03_contract.get("content_sha256"), "DATA04_DATA03_AUTHORITY_MISMATCH", "accepted DATA-03 contract identity differs")
    require(data03_ref.get("table_identity_sha256") == content_digest(data03_contract["tables"]), "DATA04_DATA03_TABLE_IDENTITY_MISMATCH", "accepted DATA-03 tables differ")
    require(data03_ref.get("candidate_measure_identity_sha256") == content_digest(data03_contract["candidate_measures"]), "DATA04_DATA03_MEASURE_IDENTITY_MISMATCH", "accepted DATA-03 measures differ")
    require(data03_ref.get("special_value_contract_sha256") == content_digest(data03_contract["special_value_contract"]), "DATA04_DATA03_SPECIAL_VALUE_MISMATCH", "accepted DATA-03 special-value contract differs")
    require(data03_ref.get("derivation_contract_sha256") == content_digest(data03_contract["derivation_contract"]), "DATA04_DATA03_DERIVATION_MISMATCH", "accepted DATA-03 derivation contract differs")
    require(data03_ref.get("metadata_identity_sha256") == data03_contract.get("metadata_identity_sha256"), "DATA04_DATA03_METADATA_MISMATCH", "accepted DATA-03 metadata identity differs")
    require(tuple(table["table_id"] for table in data03_contract["tables"]) == EXPECTED_TABLE_IDS, "DATA04_DATA03_TABLE_IDENTITY_MISMATCH", "accepted table order differs")
    require(tuple(measure["measure_id"] for measure in data03_contract["candidate_measures"]) == EXPECTED_MEASURE_IDS, "DATA04_DATA03_MEASURE_IDENTITY_MISMATCH", "accepted measure order differs")
    require(len(component_index(data03_contract)) == 22, "DATA04_DATA03_COMPONENT_COUNT_MISMATCH", "accepted component-pair count differs")

    household_hash = verify_content_hash(household_manifest, "manifest_content_sha256")
    household_ref = accepted.get("household_manifest", {})
    require(household_manifest.get("manifest_id") == HOUSEHOLD_MANIFEST_ID == household_ref.get("manifest_id"), "DATA04_HOUSEHOLD_MANIFEST_MISMATCH", "accepted B11001 manifest identity differs")
    require(household_manifest.get("source_filename") == household_ref.get("source_filename") == "acsdt5y2024-b11001.dat", "DATA04_HOUSEHOLD_SOURCE_MISMATCH", "accepted B11001 filename differs")
    require(household_manifest.get("retrieval", {}).get("expected_byte_length") == household_ref.get("source_byte_length") and household_manifest.get("byte_sha256") == household_ref.get("source_byte_sha256"), "DATA04_HOUSEHOLD_SOURCE_MISMATCH", "accepted B11001 byte identity differs")
    require(household_hash == household_ref.get("manifest_content_sha256"), "DATA04_HOUSEHOLD_MANIFEST_MISMATCH", "accepted B11001 manifest hash differs")
    request = household_manifest.get("request_identity", {})
    require(request.get("source_to_contract_mapping") == {"B11001_E001": "B11001_001E", "B11001_M001": "B11001_001M"}, "DATA04_HOUSEHOLD_MAPPING_MISMATCH", "B11001 estimate/MOE mapping differs")

    table_refs = accepted.get("multivariate_tables")
    require(isinstance(table_refs, list) and tuple(item.get("table_id") for item in table_refs) == EXPECTED_TABLE_IDS, "DATA04_MULTIVARIATE_SOURCE_LIST_MISMATCH", "accepted multivariate table sources differ")
    for table, reference in zip(data03_contract["tables"], table_refs):
        manifest = multivariate_manifests.get(table["table_id"])
        require(isinstance(manifest, Mapping), "DATA04_MULTIVARIATE_MANIFEST_MISSING", f"accepted manifest is missing for {table['table_id']}")
        require(reference.get("manifest_id") == table["source_manifest_id"] == manifest.get("manifest_id"), "DATA04_MULTIVARIATE_MANIFEST_MISMATCH", f"manifest identity differs for {table['table_id']}")
        require(reference.get("manifest_path") == table["source_manifest_path"], "DATA04_MULTIVARIATE_MANIFEST_MISMATCH", f"manifest path differs for {table['table_id']}")
        require(reference.get("source_filename") == manifest.get("source_filename") and reference.get("source_byte_length") == manifest.get("retrieval", {}).get("expected_byte_length") and reference.get("source_byte_sha256") == manifest.get("byte_sha256"), "DATA04_MULTIVARIATE_SOURCE_MISMATCH", f"accepted national bytes differ for {table['table_id']}")
        require(reference.get("manifest_content_sha256") == manifest.get("manifest_content_sha256"), "DATA04_MULTIVARIATE_MANIFEST_MISMATCH", f"manifest hash differs for {table['table_id']}")

    household = contract.get("household_extraction", {})
    require(household.get("extraction_id") == "DATA04_ACS2024_ACS5_B11001_MI_TRACT_EXTRACTION_V1", "DATA04_HOUSEHOLD_EXTRACTION_MISMATCH", "Michigan B11001 extraction ID differs")
    require((household.get("estimate_variable"), household.get("moe_variable"), household.get("source_estimate_field"), household.get("source_moe_field")) == ("B11001_001E", "B11001_001M", "B11001_E001", "B11001_M001"), "DATA04_HOUSEHOLD_MAPPING_MISMATCH", "Michigan B11001 mapping differs")
    require(household.get("expected_tract_count") == EXPECTED_TRACT_COUNT and "1400000US26" in household.get("geography_selection", ""), "DATA04_HOUSEHOLD_GEOGRAPHY_MISMATCH", "Michigan B11001 geography differs")

    multi = contract.get("multivariate_extraction", {})
    require((multi.get("accepted_table_count"), multi.get("accepted_component_pair_count"), multi.get("accepted_candidate_measure_count")) == (11, 22, 13), "DATA04_MULTIVARIATE_COUNT_MISMATCH", "Michigan multivariate menu counts differ")
    require(multi.get("table_identity_sha256") == data03_ref.get("table_identity_sha256") and multi.get("candidate_measure_identity_sha256") == data03_ref.get("candidate_measure_identity_sha256"), "DATA04_MULTIVARIATE_IDENTITY_MISMATCH", "Michigan multivariate identities differ")
    require(multi.get("special_value_contract_sha256") == data03_ref.get("special_value_contract_sha256") and multi.get("derivation_contract_sha256") == data03_ref.get("derivation_contract_sha256"), "DATA04_MULTIVARIATE_SEMANTICS_MISMATCH", "Michigan multivariate semantics differ")
    require(multi.get("expected_tract_count") == EXPECTED_TRACT_COUNT and "1400000US26" in multi.get("geography_selection", ""), "DATA04_MULTIVARIATE_GEOGRAPHY_MISMATCH", "Michigan multivariate geography differs")
    expected_reconciliation = multi.get("expected_source_row_reconciliation", {})
    require(tuple(expected_reconciliation) == EXPECTED_TABLE_IDS, "DATA04_SOURCE_ROW_RECONCILIATION_MISMATCH", "Michigan table reconciliation order or identity differs")
    for table_id in EXPECTED_TABLE_IDS:
        expected_present = 3011 if table_id == "B19301" else EXPECTED_TRACT_COUNT
        require(
            expected_reconciliation[table_id]
            == {
                "expected_tract_count": EXPECTED_TRACT_COUNT,
                "present_source_row_count": expected_present,
                "missing_source_row_count": EXPECTED_TRACT_COUNT - expected_present,
                "extra_source_row_count": 0,
            },
            "DATA04_SOURCE_ROW_RECONCILIATION_MISMATCH",
            f"Michigan source-row reconciliation differs for {table_id}",
        )

    _validate_tiger_manifest(contract, tiger_manifest)
    policy = contract.get("protected_characteristic_policy", {})
    excluded = {str(value).lower() for value in policy.get("excluded_bases", [])}
    require(policy.get("data03_policy_preserved") is True and policy.get("direct_proxy_recreation_prohibited") is True and policy.get("all_candidate_measures_clear") is True, "DATA04_PROTECTED_POLICY_MISMATCH", "protected-characteristic policy differs")
    require({"race", "ethnicity", "sex", "age composition", "disability", "religion", "national origin", "other protected-class status"} <= excluded, "DATA04_PROTECTED_EXCLUSION_INCOMPLETE", "protected-characteristic exclusions are incomplete")
    boundary = contract.get("protected_evidence_boundary", {})
    require(boundary.get("public_data_only") is True and boundary.get("protected_filesystem_discovery") == "prohibited and unnecessary", "DATA04_PROTECTED_BOUNDARY_MISMATCH", "public-data-only boundary differs")
    output = contract.get("output_contract", {})
    require(output.get("overwrite") == "deny" and output.get("ready_marker_last") is True and output.get("raw_and_generated_git_state") == "outside_tracked_git", "DATA04_OUTPUT_CONTRACT_MISMATCH", "DATA-04 output safeguards differ")
    require(contract.get("hash_algorithm") == "SHA-256" and contract.get("supersedes") is None, "DATA04_HASH_OR_SUCCESSION_MISMATCH", "DATA-04 hash or supersession state differs")
    return _verify_hash(contract, "content_sha256", "DATA04_CONTRACT_HASH_MISMATCH")


def load_authority(repository_root: Path) -> Data04Authority:
    contract = json.loads((repository_root / CONTRACT_PATH).read_text(encoding="utf-8"))
    schema = json.loads((repository_root / SCHEMA_PATH).read_text(encoding="utf-8"))
    data03_path = repository_root / contract["accepted_acs_national_authority"]["data03_contract"]["contract_path"]
    data03_contract = json.loads(data03_path.read_text(encoding="utf-8"))
    household_path = repository_root / contract["accepted_acs_national_authority"]["household_manifest"]["manifest_path"]
    household_manifest = json.loads(household_path.read_text(encoding="utf-8"))
    multivariate_manifests = load_source_manifests(repository_root, data03_contract)
    tiger_path = repository_root / contract["tiger_source_authority"]["manifest_path"]
    tiger_manifest = json.loads(tiger_path.read_text(encoding="utf-8"))
    validate_authority(contract, schema, data03_contract, household_manifest, multivariate_manifests, tiger_manifest)
    return Data04Authority(contract, data03_contract, household_manifest, multivariate_manifests, tiger_manifest)
