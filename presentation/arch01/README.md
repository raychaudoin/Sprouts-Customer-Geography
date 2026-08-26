# ARCH-01 local architecture spike

This bounded browser spike is evidence for the ARCH-01 architecture decision. It is not a production dashboard. It uses the accepted public Michigan 2024 tract presentation geometry and deterministic synthetic values only.

## Run

From the repository root on Windows, run:

```powershell
.\RunArch01Spike.bat
```

Then open `http://127.0.0.1:8766/`. Stop the server with `Ctrl+C`. Python 3.11 or later and a modern WebGL2 browser are the only operator-runtime prerequisites; MapLibre GL JS 6.6.0 is vendored and requires no package installation or CDN.

The server builds and validates the synthetic presentation bundle in memory on every clean start. It binds only to `127.0.0.1`, suppresses request logging, rejects unexpected hosts, methods, query strings, and paths, and serves an explicit asset/input allowlist. No database, hidden imported-data cache, telemetry, analytics, crash reporter, account, or hosted backend is used.

The default USGS Topo and optional USGS ImageryTopo layers send only public viewport-derived raster tile identifiers and ordinary HTTPS metadata to `basemap.nationalmap.gov`. Choosing **Local neutral** makes the map context network-free while preserving all tract interaction.

## Reconstruct and verify

Disclosure-safe bundle metadata:

```powershell
python scripts\arch01\build_synthetic_bundle.py --summary
```

Fail-closed server readiness without opening a listener:

```powershell
python scripts\arch01\serve_spike.py --check
```

Repository conformance is covered by `python scripts/check_arch01_repository.py` and the ARCH-01 unit tests. Do not commit a generated bundle or replace the synthetic builder with protected MODEL-13 values under this task.
