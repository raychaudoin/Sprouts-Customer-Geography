from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from scripts.pbi02.build_report import build_report  # noqa: E402
from scripts.pbi02.build_semantic_model import write_semantic_model  # noqa: E402


def build_project(repository_root: Path) -> dict[str, object]:
    semantic_model = write_semantic_model(repository_root)
    report = build_report(repository_root)
    return {"state": "READY", "semantic_model": semantic_model, "report": report}


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruct the governed PBI-02 PBIP/PBIR/TMDL project")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(build_project(args.repository_root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
