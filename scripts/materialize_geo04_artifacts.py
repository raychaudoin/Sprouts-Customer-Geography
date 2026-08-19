"""Materialize GEO-04 repository-safe authority artifacts from a pinned TIGER ZIP."""

from __future__ import annotations

import argparse
from pathlib import Path

from sprouts_customer_geography.geo04 import materialize


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-zip", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("config/geo"))
    args = parser.parse_args()
    materialize(args.source_zip, Path(__file__).resolve().parents[1], args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
