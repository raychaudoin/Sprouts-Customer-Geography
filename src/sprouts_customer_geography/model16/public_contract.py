"""Exact public Work Order facts recognized by predecessor disclosure guards."""
import hashlib
from pathlib import Path
import re


MODEL16_PUBLIC_WORK_ORDER = "docs/work_orders/MODEL_16_CLEAN_MI_WI_EVIDENCE_REBUILD.md"
# UTF-8/LF bytes of this public document at authority commit
# 12ee5ad97f9a422edeb63664641cfbbae49fe465, verified before implementation.
MODEL16_PUBLIC_WORK_ORDER_SHA256 = "f97cd1ca113bfa03c179cf6284abd3d9584569cb2c233008d1de6a68ea744048"
MODEL16_PUBLIC_LOGICAL_IDS = (
    "MI_SEED_FORECASTS_2024_2026_V1", "WI_SEED_FORECASTS_2024_2026_V1",
    "MI_WI_PURSUED_SITES_2025_ISOLATED_V1",
)
MODEL16_PUBLIC_HEADER_PATHS = {
    MODEL16_PUBLIC_WORK_ORDER,
    "src/sprouts_customer_geography/model16/intake.py",
    "tests/test_model16_intake.py",
}


def source_name_guard_text(repository: Path, path: str, text: str) -> str:
    """Recognize only published tokens for the private-name check alone.

    Every other guard receives unmodified text. No path or general name pattern
    is exempt, and changed/missing controlling authority grants no exception.
    """
    authority = repository / MODEL16_PUBLIC_WORK_ORDER
    if not authority.is_file() or hashlib.sha256(authority.read_text(encoding="utf-8").encode()).hexdigest() != MODEL16_PUBLIC_WORK_ORDER_SHA256:
        return text
    for logical in MODEL16_PUBLIC_LOGICAL_IDS:
        text = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(logical) + r"(?![A-Za-z0-9_])", "PUBLIC_LOGICAL_ASSET", text)
    if path.replace("\\", "/") in MODEL16_PUBLIC_HEADER_PATHS:
        text = re.sub(r"(?i)\bcity2\b", "PUBLIC_CITY_SCHEMA_ALIAS", text)
    return text
