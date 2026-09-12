"""Fixed repository surfaces that enforce readiness-mailbox validation."""

from __future__ import annotations


MAILBOX_BRANCH = "readiness-mailbox"
MAILBOX_FILENAME = "development-readiness.json"

# These files are the validation runtime used on the dedicated mailbox branch.
# Publication requires their blobs to match the snapshot's source commit.
MAILBOX_ENFORCEMENT_PATHS = (
    ".github/workflows/readiness-mailbox-validation.yml",
    "pyproject.toml",
    "schemas/readiness/development_readiness.schema.json",
    "scripts/check_readiness_mailbox.py",
    "src/sprouts_customer_geography/__init__.py",
    "src/sprouts_customer_geography/constants.py",
    "src/sprouts_customer_geography/pipe01/__init__.py",
    "src/sprouts_customer_geography/pipe01/errors.py",
    "src/sprouts_customer_geography/readiness/__init__.py",
    "src/sprouts_customer_geography/readiness/disclosure.py",
    "src/sprouts_customer_geography/readiness/mailbox_contract.py",
    "src/sprouts_customer_geography/readiness/repository.py",
)
