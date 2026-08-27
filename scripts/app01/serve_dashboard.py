"""Repository-root launcher for the APP-01 local dashboard."""

from __future__ import annotations

from pathlib import Path
import sys


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "src"))

from sprouts_customer_geography.app01.server import main


if __name__ == "__main__":
    raise SystemExit(main(["--repository-root", str(REPOSITORY), *sys.argv[1:]]))
