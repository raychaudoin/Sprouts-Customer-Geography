# APP-01 local operator application

APP-01 is the Michigan map-first customer-geography presentation surface. It reconstructs its runtime bundle in memory from accepted local inputs, serves only on loopback, and writes no production bundle to disk.

## Normal launch

From the repository root, double-click `RunCustomerGeography.bat`. The launcher validates accepted local inputs before it starts the server or opens a browser. Keep the terminal window open while using the application; press `Ctrl+C` there to stop it.

The default accepted MODEL-13 convention is `powerbi/pbi01/local/model13`. An ignored local settings file may instead declare one or more exact presentation-package candidates or an accepted MODEL-13 protected-handle registry. Copy `presentation/app01/app01.local-settings.example.json` to `presentation/app01/local/settings.json`, replace only its local path values, and do not commit the result. `MODEL13_AUTHORITY_REGISTRY` remains an accepted alternative to the settings field. DATA-04 candidate roots may be listed explicitly; accepted materializations under ignored `outputs/` are also resolved and validated.

The application fails closed if an input is absent, unreadable, not READY, does not match its accepted hashes or schemas, disagrees with another valid candidate, or does not reconcile exactly to all 3,017 accepted geometry keys. Diagnostics identify the failure family without printing protected paths or values. Production mode never falls back to synthetic data.

## Validation launch

For the disclosure-safe synthetic runtime, run:

```powershell
python scripts\app01\serve_dashboard.py --synthetic
```

Synthetic mode is visibly labeled and is only for browser, interaction, egress, and accessibility validation. A prerequisite-only check that builds the chosen runtime in memory and exits is available with `--check`.

## Operator workflow

Use **Color tracts by** to choose one of the 16 accepted metrics. Topo is the normal geographic context; Imagery + Labels is optional; Local neutral keeps tract exploration functional without new external requests. Select one tract for exact values, contextual warnings, and supporting accepted context. Turn on **Add to selection** for an explicit multi-tract state; no aggregate is substituted for a tract. **QA & Coverage** separates technical readiness, availability, domain, status, MOE, and key evidence from scouting. **Sprouts Evidence Context** is a separate protected-local view that removes online basemaps and disables external tile egress before loading Seed Context fields.

If USGS tiles are unavailable, switch to Local neutral and continue. If the port is occupied, stop the other local process or launch with `--port` and a free port between 1024 and 65535. A clean restart reconstructs and revalidates the bundle; it does not use a cache or repair an invalid package.

## Security boundary

The server binds only to `127.0.0.1`, accepts only explicit read-only routes, rejects query strings and non-loopback Host headers, and emits restrictive browser security headers. Automatic external requests are limited to HTTPS GET tile requests for reviewed USGS Topo and ImageryTopo paths at `basemap.nationalmap.gov`. No account, telemetry, analytics, crash reporting, remote logging, upload, file browser, write API, or remote-control surface exists.
