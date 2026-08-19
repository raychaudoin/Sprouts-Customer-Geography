"""GEO-03 internal-point parsing and exact membership semantics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from sprouts_customer_geography.constants import SOURCE_CRS, TARGET_CRS

from .errors import require


class CoordinateTransformer(Protocol):
    source_crs: str
    target_crs: str
    operation_fingerprint: str

    def transform(self, longitude: float, latitude: float) -> tuple[float, float]: ...


@dataclass(frozen=True)
class InternalPoint:
    raw_latitude: str | None
    raw_longitude: str | None
    latitude: float | None
    longitude: float | None
    coordinate_state: str


def parse_internal_point(raw_latitude: object, raw_longitude: object) -> InternalPoint:
    raw_lat = None if raw_latitude is None else str(raw_latitude)
    raw_lon = None if raw_longitude is None else str(raw_longitude)
    if raw_lat is None or raw_lon is None or not raw_lat.strip() or not raw_lon.strip():
        return InternalPoint(raw_lat, raw_lon, None, None, "missing")
    try:
        latitude = float(raw_lat)
        longitude = float(raw_lon)
    except (TypeError, ValueError):
        return InternalPoint(raw_lat, raw_lon, None, None, "invalid_parse")
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return InternalPoint(raw_lat, raw_lon, None, None, "invalid_nonfinite")
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return InternalPoint(raw_lat, raw_lon, latitude, longitude, "invalid_range")
    return InternalPoint(raw_lat, raw_lon, latitude, longitude, "valid")


def validate_transformer(transformer: CoordinateTransformer, accepted_fingerprint: str) -> None:
    require(transformer.source_crs == SOURCE_CRS, "TRANSFORM_SOURCE_CRS_MISMATCH", f"expected {SOURCE_CRS}")
    require(transformer.target_crs == TARGET_CRS, "TRANSFORM_TARGET_CRS_MISMATCH", f"expected {TARGET_CRS}")
    require(bool(accepted_fingerprint), "TRANSFORM_FINGERPRINT_MISSING", "accepted GEO-03 operation fingerprint is required")
    require(
        transformer.operation_fingerprint == accepted_fingerprint,
        "TRANSFORM_FINGERPRINT_MISMATCH",
        "runtime operation does not match accepted GEO-03 transformation evidence",
    )


def project_internal_point(point: InternalPoint, transformer: CoordinateTransformer) -> tuple[float, float] | None:
    if point.coordinate_state != "valid":
        return None
    # Explicit longitude, latitude call order is part of the frozen contract.
    try:
        projected = transformer.transform(point.longitude, point.latitude)  # type: ignore[arg-type]
    except (ArithmeticError, ValueError):
        return None
    if not isinstance(projected, (tuple, list)) or len(projected) != 2 or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in projected):
        return None
    return float(projected[0]), float(projected[1])


def planar_distance_m(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def ordinary_membership(distance_m: float, radius_m: float) -> bool:
    # Intentionally no epsilon, rounding, or tolerance.
    return distance_m <= radius_m
