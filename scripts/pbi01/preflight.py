from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate protected-local MODEL-13 inputs for PBI-01")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--geometry", type=Path)
    arguments = parser.parse_args()
    root = arguments.repository_root.resolve()
    sys.path.insert(0, str(root / "src"))
    from sprouts_customer_geography.pbi01.preflight import validate_model13_inputs

    result = validate_model13_inputs(root, geometry_path=None if arguments.geometry is None else arguments.geometry.resolve())
    print(json.dumps(result.disclosure_safe_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
