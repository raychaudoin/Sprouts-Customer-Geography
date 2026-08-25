# Michigan tract presentation geometry

`michigan_2024_tracts.geojson` is the public, disclosure-safe Shape Map resource for the PBI-01 report. Its manifest pins the official 2024 Michigan TIGER/Line tract archive, deterministic transform settings, 3,017 unique GEOIDs, and file hashes.

This is simplified presentation geometry only. It does not calculate spatial membership, support completeness, analytical features, or scores. Reconstruct it with `scripts/pbi01/build_geometry.py` from the pinned official archive held in ignored local staging.
