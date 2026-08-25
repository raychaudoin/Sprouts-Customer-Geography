from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic public PBI-01 Michigan tract presentation geometry")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("powerbi/pbi01/presentation/michigan_2024_tracts.geojson"))
    parser.add_argument("--manifest", type=Path, default=Path("powerbi/pbi01/presentation/michigan_2024_tracts.manifest.json"))
    parser.add_argument("--replace", action="store_true")
    arguments = parser.parse_args()
    root = arguments.repository_root.resolve()
    sys.path.insert(0, str(root / "src"))
    from sprouts_customer_geography.pbi01.geometry import write_geometry

    manifest = write_geometry(root, arguments.source_zip, root / arguments.output, root / arguments.manifest, replace=arguments.replace)
    print(json.dumps({"state": "READY", "tract_count": manifest["tract_count"], "unique_geoid_count": manifest["unique_geoid_count"], "source_identity_verified": True, "presentation_only": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
