# Data Directory Policy

This directory may later contain authorized, small, clearly synthetic fixtures and tracked documentation describing data contracts or provenance. Synthetic fixtures must be fictional, minimal, legally permissible, labeled as synthetic, and free of secrets, live business inputs, and confidential fields.

Do not commit raw downloads, source caches, confidential local overlays, production exports, live seed points, candidate sites, proprietary data, credentials, or large generated artifacts here. Intended local-only paths such as `data/raw/`, `data/cache/`, `data/confidential/`, `data/local/`, and `data/external/` are ignored by Git.

Authoritative, public-source manifests and reproducibility configuration may remain trackable here; raw downloaded source bytes remain local-only. `data/manifests/` contains the DATA-02 pinned source evidence, not the source files themselves. Approved synthetic fixtures should remain trackable rather than being broadly ignored. No datasets were downloaded or created during GOV-01.
