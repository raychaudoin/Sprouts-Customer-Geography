# APP-01 real protected-operation egress evidence

## Result

The accepted-real APP-01 egress verification passed on 2026-08-26. The application used the same loopback server, explicit read-only routes, restrictive CSP and security headers, vendored MapLibre runtime, external-host allowlist, request transform, and no-telemetry/no-analytics/no-remote-logging configuration exercised by the earlier synthetic production gate. Real operation changes the validated in-memory bundle, not the security-relevant browser or server configuration.

## Method

The installed Product Design audit workflow and in-app browser exercised the actual running production application. Browser asset inventory and application diagnostics were checked across initial Topo rendering, several real metric switches, one- and multi-tract states, MODEL and DATA-04 unavailable warnings, Imagery + Labels, Local neutral, QA & Coverage, entry to protected-local Evidence Context, protected marker detail, reload, and the one-step launcher restart.

Observed network-capable external assets were classified by protocol, host, path, query, and fragment. The application-recorded external request count and canary count were captured before and after Local neutral and Evidence Context transitions. Protected values were inspected only in the local browser. Raw traces and real screenshots were retained only in ignored local audit storage.

## Evidence

- Every observed external application request was an HTTPS `GET` to `basemap.nationalmap.gov` on the exact reviewed USGS Topo or ImageryTopo tile-path shape.
- No observed external URL contained a query string or fragment.
- Local neutral produced zero new external requests.
- Evidence Context disabled external egress and removed the online basemap before loading protected-local evidence. Entry and protected marker selection produced zero new external network assets and zero application-recorded external requests.
- No telemetry, analytics, crash reporting, remote logging, upload, arbitrary file browsing, write API, or remote-control request was observed or configured.
- Canary hits remained zero and the browser runtime recorded no warning or error.
- No protected value, GEOID-bearing request, Seed Context, coordinate, identity, sales value, prediction, error, support flag, lineage, or local path appeared in an external application request.

The targeted final Ultra recheck repeated Topo, Imagery + Labels, Local neutral, and Evidence Context transitions on the accepted-real application. The current browser asset inventory contained only exact reviewed USGS Topo and ImageryTopo HTTPS tile paths at `basemap.nationalmap.gov`, with no query string or fragment. Local neutral and Evidence Context each added zero application-recorded external requests; Evidence Context reported Local neutral before evidence loaded; canary hits and runtime errors remained zero.

## Disclosure boundary

This record intentionally omits protected paths, package names beyond public logical identities, tract-level values, Seed Context counts and fields, coordinates, identities, sales, predictions, errors, lineage, and raw request captures. No protected path, value, generated production bundle, raw trace, or revealing screenshot is tracked.
