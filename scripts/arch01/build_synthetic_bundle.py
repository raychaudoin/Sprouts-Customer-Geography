"""Build deterministic public/synthetic ARCH-01 presentation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[2]
GEOMETRY_PATH = REPOSITORY / "powerbi" / "pbi01" / "presentation" / "michigan_2024_tracts.geojson"
GEOMETRY_MANIFEST_PATH = REPOSITORY / "powerbi" / "pbi01" / "presentation" / "michigan_2024_tracts.manifest.json"
METRIC_CATALOG_PATH = REPOSITORY / "config" / "arch01" / "arch01_metric_catalog.json"
EXPECTED_GEOMETRY_SHA256 = "e0f32095d2e2307f5ad78c9545fc0d3c74fca2250bc866bea8db2368848786ad"
EXPECTED_INVENTORY_SHA256 = "8b6698b55423911163f1a2330ad600218a3b8b452576cc9b3d3997ada19e6c9b"
EXPECTED_TRACT_COUNT = 3_017
EXPECTED_METRIC_COUNT = 16
CANARY = "ARCH01_SYNTHETIC_PROTECTED_EGRESS_CANARY_7F3C91D2"
GEOID_RE = re.compile(r"^26[0-9]{9}$")


class Arch01BundleError(RuntimeError):
    """Fail-closed bundle reconstruction error."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_accepted_geometry_bytes() -> bytes:
    """Return the accepted Git-blob bytes despite platform checkout newlines."""
    working_bytes = GEOMETRY_PATH.read_bytes()
    canonical_bytes = working_bytes.replace(b"\r\n", b"\n")
    if _sha256_bytes(canonical_bytes) != EXPECTED_GEOMETRY_SHA256:
        raise Arch01BundleError("ARCH01_GEOMETRY_HASH_MISMATCH: accepted presentation geometry changed")
    return canonical_bytes


def _ranked_subset(geoids: list[str], label: str, count: int) -> set[str]:
    ranked = sorted(geoids, key=lambda geoid: hashlib.sha256(f"ARCH01|{label}|{geoid}".encode()).digest())
    return set(ranked[:count])


def _fraction(geoid: str, metric_key: str, purpose: str = "value") -> float:
    digest = hashlib.sha256(f"ARCH01|{purpose}|{metric_key}|{geoid}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)


def _quantile_type7(values: list[float], probability: float) -> float:
    if not values:
        raise Arch01BundleError("ARCH01_DOMAIN_EMPTY: valid-value domain cannot be empty")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * weight)


def _synthetic_value(geoid: str, metric: dict[str, Any]) -> int | float:
    low, high = metric["synthetic_range"]
    raw = low + (high - low) * _fraction(geoid, metric["metric_key"])
    policy = metric["format_policy"]
    if policy in {"count_0", "currency_0"}:
        return int(round(raw))
    if policy == "decimal_2":
        return round(raw, 2)
    return round(raw, 1)


def _load_authority() -> tuple[list[str], dict[str, Any], bytes, bytes]:
    geometry_bytes = load_accepted_geometry_bytes()
    geometry_manifest = json.loads(GEOMETRY_MANIFEST_PATH.read_text(encoding="utf-8"))
    if geometry_manifest.get("artifact_id") != "PBI01_MICHIGAN_2024_TIGER_TRACT_PRESENTATION_GEOMETRY_V1":
        raise Arch01BundleError("ARCH01_GEOMETRY_AUTHORITY_MISMATCH: unexpected geometry authority")
    geometry = json.loads(geometry_bytes)
    features = geometry.get("features")
    if not isinstance(features, list) or len(features) != EXPECTED_TRACT_COUNT:
        raise Arch01BundleError("ARCH01_GEOMETRY_COUNT_MISMATCH: expected exactly 3017 tract features")
    geoids = [feature.get("properties", {}).get("GEOID") for feature in features]
    if any(not isinstance(geoid, str) or not GEOID_RE.fullmatch(geoid) for geoid in geoids):
        raise Arch01BundleError("ARCH01_GEOID_INVALID: geometry contains an invalid Michigan GEOID")
    if len(set(geoids)) != EXPECTED_TRACT_COUNT:
        raise Arch01BundleError("ARCH01_GEOID_DUPLICATE: geometry GEOIDs are not unique")
    ordered_geoids = sorted(geoids)
    inventory_bytes = json.dumps(
        {"ordered_geoids": ordered_geoids}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if _sha256_bytes(inventory_bytes) != EXPECTED_INVENTORY_SHA256:
        raise Arch01BundleError("ARCH01_GEOID_INVENTORY_MISMATCH: accepted 3017-key inventory changed")

    catalog_bytes = METRIC_CATALOG_PATH.read_bytes()
    catalog = json.loads(catalog_bytes)
    metrics = catalog.get("metrics")
    if not isinstance(metrics, list) or len(metrics) != EXPECTED_METRIC_COUNT:
        raise Arch01BundleError("ARCH01_METRIC_COUNT_MISMATCH: expected exactly 16 metrics")
    if [metric.get("sort_order") for metric in metrics] != list(range(1, EXPECTED_METRIC_COUNT + 1)):
        raise Arch01BundleError("ARCH01_METRIC_ORDER_MISMATCH: metric order must be 1 through 16")
    keys = [metric.get("metric_key") for metric in metrics]
    if len(set(keys)) != EXPECTED_METRIC_COUNT:
        raise Arch01BundleError("ARCH01_METRIC_KEY_DUPLICATE: metric keys must be unique")
    return ordered_geoids, catalog, geometry_bytes, catalog_bytes


def build_bundle() -> dict[str, Any]:
    geoids, catalog, geometry_bytes, catalog_bytes = _load_authority()
    metrics = catalog["metrics"]
    noncomputable_geoids = _ranked_subset(geoids, "model_noncomputable", 44)
    support_truncated_geoids = _ranked_subset(geoids, "support_truncation", 438)
    per_capita_missing_geoids = _ranked_subset(geoids, "per_capita_missing_source", 6)
    unavailable_by_metric = {
        metric["metric_key"]: _ranked_subset(geoids, f"unavailable|{metric['metric_key']}", 8)
        for metric in metrics
        if metric["input_binding"]["logical_input"] == "data04_candidate_measure"
        and metric["metric_key"] != "per_capita_income"
    }

    rows: list[dict[str, Any]] = []
    valid_values: dict[str, list[float]] = {metric["metric_key"]: [] for metric in metrics}
    for geoid in geoids:
        values: list[int | float | None] = []
        statuses: list[str] = []
        details: list[str | None] = []
        moes: list[int | float | None] = []
        for metric in metrics:
            key = metric["metric_key"]
            logical_input = metric["input_binding"]["logical_input"]
            unavailable = False
            status = "valid"
            detail: str | None = None
            if logical_input == "model13_tract_output" and key in {
                "customer_fit_percentile", "modeled_target_mass_percentile"
            } and geoid in noncomputable_geoids:
                unavailable = True
                status = "noncomputable"
                detail = "synthetic_model_noncomputable"
            elif key == "per_capita_income" and geoid in per_capita_missing_geoids:
                unavailable = True
                status = "missing_source_row"
                detail = "synthetic_missing_source_row"
            elif key in unavailable_by_metric and geoid in unavailable_by_metric[key]:
                unavailable = True
                status = "unavailable"
                detail = "synthetic_explicit_unavailable"

            if unavailable:
                value = None
                moe = None
            else:
                value = _synthetic_value(geoid, metric)
                valid_values[key].append(float(value))
                if logical_input == "data04_candidate_measure":
                    moe_fraction = 0.04 + 0.08 * _fraction(geoid, key, "moe")
                    moe = round(abs(float(value)) * moe_fraction, 2)
                else:
                    moe = None
            values.append(value)
            statuses.append(status)
            details.append(detail)
            moes.append(moe)
        rows.append(
            {
                "geoid": geoid,
                "values": values,
                "statuses": statuses,
                "status_details": details,
                "moes": moes,
                "support_truncation": geoid in support_truncated_geoids,
            }
        )

    domains: dict[str, dict[str, int | float | str]] = {}
    for metric in metrics:
        key = metric["metric_key"]
        values = valid_values[key]
        if metric["scale_policy"] == "fixed_0_100":
            minimum, maximum = 0.0, 100.0
        else:
            minimum = round(_quantile_type7(values, 0.02), 6)
            maximum = round(_quantile_type7(values, 0.98), 6)
        if minimum >= maximum:
            raise Arch01BundleError(f"ARCH01_DOMAIN_INVALID: {key} domain is not increasing")
        domains[key] = {
            "minimum": minimum,
            "maximum": maximum,
            "policy": metric["scale_policy"],
            "valid_value_count": len(values),
        }

    return {
        "$schema": "arch01-presentation-bundle-v1",
        "artifact_id": "ARCH01_SYNTHETIC_MICHIGAN_PRESENTATION_BUNDLE_V1",
        "version": "1.0.0",
        "data_mode": "synthetic_architecture_evidence",
        "synthetic_notice": "All values are deterministic synthetic architecture evidence. They are not MODEL-13 or DATA-04 observations and must not be used for business decisions.",
        "canary": {"value": CANARY, "external_transmission_permitted": False},
        "source_bindings": {
            "geometry_artifact_id": "PBI01_MICHIGAN_2024_TIGER_TRACT_PRESENTATION_GEOMETRY_V1",
            "geometry_sha256": _sha256_bytes(geometry_bytes),
            "geoid_inventory_sha256": EXPECTED_INVENTORY_SHA256,
            "metric_catalog_artifact_id": "ARCH01_MICHIGAN_PRESENTATION_METRIC_CATALOG_V1",
            "metric_catalog_sha256": _sha256_bytes(catalog_bytes),
        },
        "tract_count": EXPECTED_TRACT_COUNT,
        "metric_count": EXPECTED_METRIC_COUNT,
        "metric_keys": [metric["metric_key"] for metric in metrics],
        "domains": domains,
        "rows": rows,
    }


def build_bundle_bytes() -> bytes:
    bundle = build_bundle()
    validate_bundle(bundle)
    return _canonical_bytes(bundle)


def validate_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("artifact_id") != "ARCH01_SYNTHETIC_MICHIGAN_PRESENTATION_BUNDLE_V1":
        raise Arch01BundleError("ARCH01_BUNDLE_ID_MISMATCH: unexpected bundle identity")
    if bundle.get("tract_count") != EXPECTED_TRACT_COUNT or len(bundle.get("rows", [])) != EXPECTED_TRACT_COUNT:
        raise Arch01BundleError("ARCH01_BUNDLE_TRACT_COUNT_MISMATCH: bundle must contain 3017 rows")
    if bundle.get("metric_count") != EXPECTED_METRIC_COUNT or len(bundle.get("metric_keys", [])) != EXPECTED_METRIC_COUNT:
        raise Arch01BundleError("ARCH01_BUNDLE_METRIC_COUNT_MISMATCH: bundle must contain 16 metrics")
    geoids = [row.get("geoid") for row in bundle["rows"]]
    if geoids != sorted(geoids) or len(set(geoids)) != EXPECTED_TRACT_COUNT:
        raise Arch01BundleError("ARCH01_BUNDLE_GEOID_MISMATCH: bundle GEOIDs must be ordered and unique")
    for row in bundle["rows"]:
        for field in ("values", "statuses", "status_details", "moes"):
            if len(row.get(field, [])) != EXPECTED_METRIC_COUNT:
                raise Arch01BundleError(f"ARCH01_BUNDLE_ROW_WIDTH_MISMATCH: {field} must contain 16 entries")
        for value, status in zip(row["values"], row["statuses"], strict=True):
            if status == "valid" and not isinstance(value, (int, float)):
                raise Arch01BundleError("ARCH01_BUNDLE_VALID_VALUE_MISSING: valid status requires a numeric value")
            if status != "valid" and value is not None:
                raise Arch01BundleError("ARCH01_BUNDLE_UNAVAILABLE_VALUE_PRESENT: unavailable status requires null")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic ARCH-01 synthetic presentation evidence.")
    parser.add_argument("--output", type=Path, help="Optional output path; parent must already exist.")
    parser.add_argument("--summary", action="store_true", help="Print only disclosure-safe aggregate metadata.")
    args = parser.parse_args()
    bundle = build_bundle()
    validate_bundle(bundle)
    payload = _canonical_bytes(bundle)
    if args.output:
        if not args.output.parent.is_dir():
            raise Arch01BundleError("ARCH01_OUTPUT_PARENT_MISSING: output parent must already exist")
        args.output.write_bytes(payload)
    if args.summary or not args.output:
        summary = {
            "state": "ready",
            "tract_count": bundle["tract_count"],
            "metric_count": bundle["metric_count"],
            "support_truncated_count": sum(row["support_truncation"] for row in bundle["rows"]),
            "synthetic_bundle_sha256": _sha256_bytes(payload),
            "synthetic_bundle_bytes": len(payload),
        }
        print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
