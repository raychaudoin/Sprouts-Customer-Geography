"""Validation for the additive DATA-03 ACS source contract and manifests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlencode

from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import require


CONTRACT_ID = "DATA03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE_CONTRACT_V1"
VERSION = "1.0.0"
EXPECTED_TABLE_IDS = (
    "B08201",
    "B08301",
    "B15003",
    "B19013",
    "B19301",
    "B23025",
    "B25002",
    "B25003",
    "B25010",
    "B25064",
    "B25077",
)
EXPECTED_MEASURE_IDS = (
    "median_household_income",
    "per_capita_income",
    "civilian_labor_force_share",
    "employment_rate",
    "bachelors_or_higher_share",
    "owner_occupancy_share",
    "vacancy_share",
    "median_home_value",
    "median_gross_rent",
    "average_household_size",
    "no_vehicle_household_share",
    "drive_alone_commuter_share",
    "work_from_home_commuter_share",
)
CONTRACT_PATH = Path("config/data/data03_wisconsin_multivariate_acs_feature_source_contract.json")
SCHEMA_PATH = Path("schemas/data03/wisconsin_multivariate_acs_feature_source_contract.schema.json")
VARIABLE_RE = re.compile(r"^(B[0-9]{5})_([0-9]{3})([EM])$")
TABLE_FIELD_RE = re.compile(r"^(B[0-9]{5})_([EM])([0-9]{3})$")


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


def component_index(contract: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for table in contract.get("tables", []):
        for variable in table.get("variables", []):
            component_id = variable.get("component_id")
            require(isinstance(component_id, str) and component_id not in output, "DATA03_COMPONENT_ID_INVALID", "component IDs must be unique nonempty strings")
            output[component_id] = variable
    return output


def metadata_identity_document(contract: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    identity: dict[str, dict[str, str]] = {}
    for table in contract.get("tables", []):
        table_id = str(table.get("table_id", ""))
        for variable in table.get("variables", []):
            for role in ("estimate", "moe"):
                variable_id = str(variable[f"{role}_variable"])
                require(variable_id not in identity, "DATA03_VARIABLE_DUPLICATE", f"duplicate variable {variable_id}")
                identity[variable_id] = {
                    "group": table_id,
                    "label": str(variable[f"{role}_label"]),
                    "predicateType": str(variable["predicate_type"]),
                }
    return identity


def table_metadata_identity_document(table: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    identity: dict[str, dict[str, str]] = {}
    for variable in table["variables"]:
        for role in ("estimate", "moe"):
            variable_id = str(variable[f"{role}_variable"])
            identity[variable_id] = {
                "group": str(table["table_id"]),
                "label": str(variable[f"{role}_label"]),
                "predicateType": str(variable["predicate_type"]),
            }
    return identity


def source_manifest_document(contract: Mapping[str, Any], table: Mapping[str, Any], observation: Mapping[str, Any]) -> dict[str, Any]:
    """Render a repository-safe manifest candidate from observed official source bytes."""
    table_id = str(table["table_id"])
    filename = f"acsdt5y2024-{table_id.lower()}.dat"
    source_reference = f"{contract['source_product']['table_file_base_url']}/{filename}"
    require(observation.get("table_id") == table_id and observation.get("filename") == filename and observation.get("source_reference") == source_reference, "DATA03_ACQUISITION_OBSERVATION_MISMATCH", f"acquisition observation differs for {table_id}")
    required_fields = ["GEO_ID"] + [field for variable in table["variables"] for field in (variable["table_estimate_field"], variable["table_moe_field"])]
    mapping = {variable["table_estimate_field"]: variable["estimate_variable"] for variable in table["variables"]}
    mapping.update({variable["table_moe_field"]: variable["moe_variable"] for variable in table["variables"]})
    request_identity = {
        "access_surface": "official ACS table-based Summary File HTTPS distribution",
        "source_file": filename,
        "record_delimiter": "LF",
        "field_delimiter": "|",
        "header_required": required_fields,
        "geography_selection": "Rows whose GEO_ID begins exactly 1400000US55; no market target or seed filtering.",
        "metadata_reference": table["metadata_url"],
        "source_to_contract_mapping": mapping,
    }
    manifest: dict[str, Any] = {
        "$schema": "../../schemas/pipe01/source_manifest.schema.json",
        "manifest_id": table["source_manifest_id"],
        "manifest_version": VERSION,
        "source_id": f"census-acs-2024-acs5-detailed-{table_id.lower()}",
        "source_name": f"2020-2024 ACS 5-Year Detailed Table {table_id}",
        "publisher": "U.S. Census Bureau",
        "accepted_vintage": "2024",
        "source_reference": source_reference,
        "official_product_identity": f"2020-2024 ACS 5-Year Detailed Tables, official table-based Summary File, {table_id}",
        "source_filename": filename,
        "source_geography_and_type": f"National table-based Detailed Table {table_id} file, deterministically filtered to GEO_ID prefix 1400000US55 for Wisconsin Census tracts.",
        "retrieval": {
            "method": "HTTPS GET of the exact source_reference URL; no latest/current alias or API credential is used.",
            "retrieval_date": contract["source_product"]["retrieval_date"],
            "expected_byte_length": int(observation["byte_length"]),
            "access_surface_reason": contract["source_product"]["access_surface_reason"],
        },
        "request_identity": request_identity,
        "request_hash_algorithm": "SHA-256",
        "request_hash_semantics": "SHA-256 of canonical UTF-8 JSON for request_identity: recursively sorted object keys compact separators Unicode preserved no NaN.",
        "request_sha256": content_digest(request_identity),
        "checksum_algorithm": "SHA-256",
        "byte_sha256": str(observation["byte_sha256"]),
        "checksum_semantics": f"SHA-256 over the exact downloaded {filename} bytes before filtering parsing normalization or conversion.",
        "acquisition_state": "acquired",
        "schema_version": "data-authoritative-source-manifest-v1",
        "expected_file_properties": {
            "container": "UTF-8-compatible pipe-delimited text with one header row",
            "required_source_fields": required_fields,
            "required_contract_estimate_fields": [variable["estimate_variable"] for variable in table["variables"]],
            "required_contract_moe_fields": [variable["moe_variable"] for variable in table["variables"]],
            "selected_metadata_identity_sha256": content_digest(table_metadata_identity_document(table)),
            "expected_wisconsin_tract_row_count_at_retrieval": contract["geography"]["expected_tract_count"],
        },
        "annotation_and_special_value_contract": {
            "official_reference": contract["special_value_contract"]["official_reference"],
            "api_annotation_state": "The official metadata defines paired annotation variables, but the selected table-based file contains no annotation columns.",
            "required_parser_behavior": "Preserve raw estimate and MOE tokens. Apply the DATA-03 special-value contract; missing suppressed inapplicable special or invalid evidence remains noncomputable and never becomes zero.",
        },
        "reproduction": f"Download exactly source_reference as {filename}; require exact byte length SHA-256 header mapping metadata identity and 1,542 unique Wisconsin tract rows before downstream use.",
        "failure_behavior": f"Fail closed on unavailable source product vintage filename byte length checksum header metadata estimate/MOE pairing duplicate tract special value malformed record or Wisconsin coverage mismatch for {table_id}. Do not substitute another release table geography or zero.",
        "attribution": f"U.S. Census Bureau, American Community Survey 2020-2024 5-Year Detailed Table {table_id}.",
        "lineage": {
            "controlling_decision": "DATA-03: Wisconsin Multivariate ACS Feature Source Expansion",
            "data_contract_id": CONTRACT_ID,
            "data_contract_version": VERSION,
            "data_contract_content_sha256": contract["content_sha256"],
            "additive_to": "DATA01_VALIDATION_SOURCE_CONTRACT_V1; accepted DATA-01 authority is unchanged.",
            "model_boundary": "Source variables and documented source-safe derivations only; no final model feature selection fitting scoring or target-conditioned authority.",
        },
        "supersedes": None,
        "supersession_policy": "A correction or newly accepted release requires a new manifest ID/version and explicit supersedes lineage; never overwrite this accepted manifest.",
    }
    manifest["manifest_content_sha256"] = content_digest(manifest)
    return manifest


def build_api_query_url(contract: Mapping[str, Any]) -> str:
    query = contract["api_query_identity"]
    params = [
        ("get", ",".join(query["ordered_get_variables"])),
        ("for", query["for"]),
        ("in", query["in"]),
    ]
    return f"{query['dataset_url']}?{urlencode(params)}"


def validate_contract(contract: Mapping[str, Any], schema: Mapping[str, Any] | None = None) -> str:
    require(isinstance(contract, Mapping), "DATA03_CONTRACT_INVALID", "contract must be an object")
    require(contract.get("artifact_id") == CONTRACT_ID and contract.get("version") == VERSION, "DATA03_CONTRACT_IDENTITY_MISMATCH", "unexpected contract identity or version")
    require(contract.get("status") == "active" and contract.get("controlling_decision") == "DATA-03: Wisconsin Multivariate ACS Feature Source Expansion", "DATA03_AUTHORITY_MISMATCH", "DATA-03 authority state differs")
    if schema is not None:
        require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "DATA03_SCHEMA_INVALID", "schema must use JSON Schema 2020-12")
        require(set(schema.get("required", [])) <= set(contract), "DATA03_CONTRACT_INCOMPLETE", "contract omits a schema-required field")
        require(set(contract) <= set(schema.get("properties", {})), "DATA03_CONTRACT_FIELD_PROHIBITED", "contract contains a field outside its schema")

    product = contract.get("source_product", {})
    require(product.get("publisher") == "U.S. Census Bureau", "DATA03_SOURCE_PUBLISHER_MISMATCH", "publisher must be the U.S. Census Bureau")
    require(product.get("product") == "2020-2024 ACS 5-Year Detailed Tables" and product.get("release_period") == "2020-2024" and product.get("vintage") == "2024", "DATA03_SOURCE_VINTAGE_MISMATCH", "only the exact 2020-2024 ACS 5-Year release is accepted")
    require(product.get("api_base_url") == "https://api.census.gov/data/2024/acs/acs5", "DATA03_API_IDENTITY_MISMATCH", "unexpected Census API dataset")
    require(product.get("table_file_base_url") == "https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData", "DATA03_SOURCE_REFERENCE_MISMATCH", "unexpected table-file source surface")
    require(product.get("fixed_release") is True, "DATA03_MOVING_SOURCE_REJECTED", "source release must be fixed")

    geography = contract.get("geography", {})
    require(geography.get("level") == "tract" and geography.get("state_fips") == "55", "DATA03_GEOGRAPHY_SCOPE_MISMATCH", "only Wisconsin tracts are accepted")
    require(geography.get("api_for") == "tract:*" and geography.get("api_in") == "state:55" and geography.get("table_file_geo_id_prefix") == "1400000US55", "DATA03_GEOGRAPHY_QUERY_MISMATCH", "Wisconsin tract query semantics differ")
    require(geography.get("expected_tract_count") == 1542, "DATA03_TRACT_COUNT_AUTHORITY_MISMATCH", "expected Wisconsin tract count differs")

    tables = contract.get("tables")
    require(isinstance(tables, list) and tuple(table.get("table_id") for table in tables) == EXPECTED_TABLE_IDS, "DATA03_TABLE_MENU_MISMATCH", "accepted table menu or order differs")
    flattened: list[str] = []
    manifest_ids: set[str] = set()
    manifest_paths: set[str] = set()
    for table in tables:
        table_id = str(table["table_id"])
        require(table.get("metadata_url") == f"https://api.census.gov/data/2024/acs/acs5/groups/{table_id}.json", "DATA03_METADATA_REFERENCE_MISMATCH", f"metadata URL differs for {table_id}")
        require(table.get("source_manifest_id") == f"DATA03_ACS2024_ACS5_{table_id}_WI_TRACT_SOURCE_MANIFEST_V1", "DATA03_MANIFEST_REFERENCE_MISMATCH", f"manifest ID differs for {table_id}")
        require(table.get("source_manifest_id") not in manifest_ids and table.get("source_manifest_path") not in manifest_paths, "DATA03_MANIFEST_REFERENCE_DUPLICATE", "source manifest references must be unique")
        manifest_ids.add(str(table["source_manifest_id"]))
        manifest_paths.add(str(table["source_manifest_path"]))
        variables = table.get("variables")
        require(isinstance(variables, list) and variables, "DATA03_VARIABLE_MENU_INVALID", f"{table_id} has no variables")
        for variable in variables:
            estimate = str(variable.get("estimate_variable", ""))
            moe = str(variable.get("moe_variable", ""))
            estimate_match = VARIABLE_RE.fullmatch(estimate)
            moe_match = VARIABLE_RE.fullmatch(moe)
            require(estimate_match is not None and moe_match is not None and estimate_match.groups() == (table_id, moe_match.group(2), "E") and moe_match.group(1) == table_id and moe_match.group(3) == "M", "DATA03_ESTIMATE_MOE_PAIR_MISMATCH", f"estimate/MOE pair differs for {estimate}")
            expected_estimate_field = f"{table_id}_E{estimate_match.group(2)}"
            expected_moe_field = f"{table_id}_M{estimate_match.group(2)}"
            require(variable.get("table_estimate_field") == expected_estimate_field and variable.get("table_moe_field") == expected_moe_field, "DATA03_TABLE_FIELD_MAPPING_MISMATCH", f"table field mapping differs for {estimate}")
            require(variable.get("predicate_type") in {"int", "float"}, "DATA03_PREDICATE_TYPE_INVALID", f"unsupported type for {estimate}")
            flattened.extend((estimate, moe))

    components = component_index(contract)
    measures = contract.get("candidate_measures")
    require(isinstance(measures, list) and tuple(item.get("measure_id") for item in measures) == EXPECTED_MEASURE_IDS, "DATA03_MEASURE_MENU_MISMATCH", "accepted candidate-measure menu or order differs")
    for measure in measures:
        sources = measure.get("source_components")
        require(isinstance(sources, list) and sources and all(component in components for component in sources), "DATA03_MEASURE_LINEAGE_INVALID", f"unknown source component in {measure.get('measure_id')}")
        require(measure.get("target_blind") is True and measure.get("final_model_feature_authority") is False and measure.get("protected_characteristic_basis") is False, "DATA03_ANALYTICAL_BOUNDARY_MISMATCH", f"candidate boundary differs for {measure.get('measure_id')}")
        kind = measure.get("kind")
        require(kind in {"direct", "subset_percentage"}, "DATA03_MEASURE_KIND_INVALID", f"unsupported measure kind {kind}")
        if kind == "direct":
            require(len(sources) == 1 and "numerator_components" not in measure and "denominator_component" not in measure, "DATA03_DIRECT_MEASURE_INVALID", f"direct measure lineage differs for {measure.get('measure_id')}")
        else:
            numerators = measure.get("numerator_components")
            denominator = measure.get("denominator_component")
            require(isinstance(numerators, list) and numerators and all(item in sources for item in numerators) and denominator in sources and denominator not in numerators, "DATA03_DERIVED_MEASURE_INVALID", f"derived measure lineage differs for {measure.get('measure_id')}")

    query = contract.get("api_query_identity")
    require(isinstance(query, Mapping) and query.get("dataset_url") == product.get("api_base_url"), "DATA03_API_IDENTITY_MISMATCH", "API query dataset differs")
    require(query.get("ordered_get_variables") == flattened and len(flattened) == 44 and len(flattened) <= 49, "DATA03_API_VARIABLE_MENU_MISMATCH", "API get list must match the bounded estimate/MOE menu")
    require(query.get("for") == "tract:*" and query.get("in") == "state:55", "DATA03_API_GEOGRAPHY_MISMATCH", "API query geography differs")
    require(query.get("credential_parameter") == "key" and query.get("credential_environment_variable") == "CENSUS_API_KEY" and query.get("credential_excluded_from_identity") is True, "DATA03_CREDENTIAL_BOUNDARY_MISMATCH", "credential handling differs")
    require(content_digest(query) == contract.get("api_query_sha256"), "DATA03_API_QUERY_HASH_MISMATCH", "API query identity hash differs")
    require(content_digest(metadata_identity_document(contract)) == contract.get("metadata_identity_sha256"), "DATA03_METADATA_IDENTITY_HASH_MISMATCH", "metadata identity hash differs")

    policy = contract.get("protected_characteristic_policy", {})
    excluded = {str(value).lower() for value in policy.get("excluded_bases", [])}
    require(policy.get("candidate_menu_target_blind") is True and policy.get("direct_proxy_recreation_prohibited") is True and policy.get("all_candidate_measures_clear") is True, "DATA03_PROTECTED_POLICY_MISMATCH", "protected-characteristic policy differs")
    require({"race", "ethnicity", "sex", "age composition", "disability", "religion", "national origin", "other protected-class status"} <= excluded, "DATA03_PROTECTED_EXCLUSION_INCOMPLETE", "protected-characteristic exclusions are incomplete")
    require(contract.get("derivation_contract", {}).get("imputation") == "prohibited", "DATA03_IMPUTATION_PROHIBITED", "imputation must remain prohibited")
    output = contract.get("output_contract", {})
    require(output.get("measure_order") == list(EXPECTED_MEASURE_IDS) and output.get("raw_and_generated_git_state") == "outside_tracked_git" and output.get("overwrite") == "deny" and output.get("ready_marker_last") is True, "DATA03_OUTPUT_CONTRACT_MISMATCH", "output contract differs")
    require(contract.get("hash_algorithm") == "SHA-256" and contract.get("supersedes") is None, "DATA03_HASH_OR_SUCCESSION_MISMATCH", "hash or succession policy differs")
    return _verify_hash(contract, "content_sha256", "DATA03_CONTRACT_HASH_MISMATCH")


def validate_metadata_documents(contract: Mapping[str, Any], documents: Mapping[str, Mapping[str, Any]]) -> str:
    observed: dict[str, dict[str, str]] = {}
    for table in contract["tables"]:
        table_id = table["table_id"]
        document = documents.get(table_id)
        require(isinstance(document, Mapping), "DATA03_METADATA_MISSING", f"metadata is absent for {table_id}")
        variables = document.get("variables")
        require(isinstance(variables, Mapping), "DATA03_METADATA_SCHEMA_CHANGED", f"metadata variables object is absent for {table_id}")
        for variable in table["variables"]:
            for role in ("estimate", "moe"):
                variable_id = variable[f"{role}_variable"]
                metadata = variables.get(variable_id)
                require(isinstance(metadata, Mapping), "DATA03_METADATA_VARIABLE_MISSING", f"metadata is absent for {variable_id}")
                require(str(metadata.get("concept", "")).casefold() == str(table["concept"]).casefold(), "DATA03_METADATA_CONCEPT_CHANGED", f"concept changed for {variable_id}")
                observed[variable_id] = {field: str(metadata.get(field, "")) for field in contract["metadata_identity_fields"]}
    expected = metadata_identity_document(contract)
    require(observed == expected, "DATA03_METADATA_SCHEMA_CHANGED", "selected variable metadata differs from the pinned identity")
    digest = content_digest(observed)
    require(digest == contract.get("metadata_identity_sha256"), "DATA03_METADATA_IDENTITY_HASH_MISMATCH", "observed metadata hash differs")
    return digest


def validate_source_manifest(contract: Mapping[str, Any], table: Mapping[str, Any], manifest: Mapping[str, Any]) -> str:
    table_id = str(table["table_id"])
    expected_filename = f"acsdt5y2024-{table_id.lower()}.dat"
    expected_url = f"{contract['source_product']['table_file_base_url']}/{expected_filename}"
    required = {"$schema", "manifest_id", "manifest_version", "source_id", "source_name", "publisher", "accepted_vintage", "source_reference", "official_product_identity", "source_filename", "source_geography_and_type", "retrieval", "request_identity", "request_hash_algorithm", "request_hash_semantics", "request_sha256", "checksum_algorithm", "byte_sha256", "checksum_semantics", "acquisition_state", "schema_version", "expected_file_properties", "annotation_and_special_value_contract", "reproduction", "failure_behavior", "attribution", "lineage", "supersedes", "supersession_policy", "manifest_content_sha256"}
    require(required <= set(manifest), "DATA03_MANIFEST_INCOMPLETE", f"manifest is incomplete for {table_id}")
    require(manifest.get("manifest_id") == table.get("source_manifest_id") and manifest.get("manifest_version") == VERSION, "DATA03_MANIFEST_IDENTITY_MISMATCH", f"manifest identity differs for {table_id}")
    require(manifest.get("accepted_vintage") == "2024" and manifest.get("publisher") == "U.S. Census Bureau", "DATA03_MANIFEST_VINTAGE_MISMATCH", f"manifest vintage differs for {table_id}")
    require(manifest.get("source_filename") == expected_filename and manifest.get("source_reference") == expected_url, "DATA03_MANIFEST_SOURCE_MISMATCH", f"source file identity differs for {table_id}")
    require(manifest.get("checksum_algorithm") == "SHA-256" and manifest.get("acquisition_state") == "acquired", "DATA03_MANIFEST_ACQUISITION_MISMATCH", f"source is not acquired for {table_id}")
    require(isinstance(manifest.get("retrieval", {}).get("expected_byte_length"), int) and manifest["retrieval"]["expected_byte_length"] > 0, "DATA03_MANIFEST_LENGTH_MISSING", f"source length is absent for {table_id}")
    require(re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("byte_sha256", ""))) is not None, "DATA03_MANIFEST_CHECKSUM_MISSING", f"source checksum is absent for {table_id}")
    request = manifest.get("request_identity")
    require(isinstance(request, Mapping) and content_digest(request) == manifest.get("request_sha256"), "DATA03_MANIFEST_REQUEST_HASH_MISMATCH", f"request identity differs for {table_id}")
    required_fields = ["GEO_ID"] + [field for variable in table["variables"] for field in (variable["table_estimate_field"], variable["table_moe_field"])]
    require(request.get("header_required") == required_fields, "DATA03_MANIFEST_HEADER_MISMATCH", f"required header differs for {table_id}")
    expected_mapping = {variable["table_estimate_field"]: variable["estimate_variable"] for variable in table["variables"]}
    expected_mapping.update({variable["table_moe_field"]: variable["moe_variable"] for variable in table["variables"]})
    require(request.get("source_to_contract_mapping") == expected_mapping, "DATA03_MANIFEST_FIELD_MAPPING_MISMATCH", f"source mapping differs for {table_id}")
    require(manifest.get("expected_file_properties", {}).get("expected_wisconsin_tract_row_count_at_retrieval") == contract["geography"]["expected_tract_count"], "DATA03_MANIFEST_TRACT_COUNT_MISMATCH", f"tract count differs for {table_id}")
    require(manifest.get("expected_file_properties", {}).get("selected_metadata_identity_sha256") == content_digest(table_metadata_identity_document(table)), "DATA03_MANIFEST_METADATA_MISMATCH", f"metadata identity differs for {table_id}")
    require(manifest.get("lineage", {}).get("data_contract_id") == CONTRACT_ID and manifest.get("lineage", {}).get("data_contract_content_sha256") == contract.get("content_sha256"), "DATA03_MANIFEST_LINEAGE_MISMATCH", f"contract lineage differs for {table_id}")
    return _verify_hash(manifest, "manifest_content_sha256", "DATA03_MANIFEST_HASH_MISMATCH")


def load_contract(repository_root: Path) -> dict[str, Any]:
    contract = json.loads((repository_root / CONTRACT_PATH).read_text(encoding="utf-8"))
    schema = json.loads((repository_root / SCHEMA_PATH).read_text(encoding="utf-8"))
    validate_contract(contract, schema)
    return contract


def load_source_manifests(repository_root: Path, contract: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for table in contract["tables"]:
        path = repository_root / table["source_manifest_path"]
        require(path.is_file(), "DATA03_MANIFEST_MISSING", f"source manifest is absent for {table['table_id']}")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        validate_source_manifest(contract, table, manifest)
        manifests[table["table_id"]] = manifest
    return manifests
