from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fail-closed PBI-02 MODEL-13 and DATA-04 preflight")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--data04-root", type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    sys.path.insert(0, str(root / "src"))
    from sprouts_customer_geography.pbi02.preflight import validate_pbi02_inputs

    result = validate_pbi02_inputs(
        root,
        data04_root=args.data04_root.resolve() if args.data04_root else None,
    )
    print(json.dumps(result.disclosure_safe_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
