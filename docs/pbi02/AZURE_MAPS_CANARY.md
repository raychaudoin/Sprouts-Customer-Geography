# PBI-02 Azure Maps synthetic-canary result

## Result

`PASSED_SYNTHETIC_NONTRANSMISSION_GATE`

The authenticated target Power BI Desktop environment rendered the built-in Azure Maps visual and passed the required synthetic-only capability and outbound-request inspection gate. The earlier unauthenticated stop displayed:

> To display Azure Maps visuals, sign in.

After the user signed in, the canary was rerun in the same PBI-02 task and target Desktop environment. Sign-in alone was not treated as sufficient evidence.

## Disclosure-safe method

- Desktop version: `2.157.879.0 (26.08)`.
- Surface: an isolated ignored runtime copy of the accepted `MICustomerGeography` PBIP in the authenticated target Desktop session.
- Data posture: `SYNTHETIC_ONLY`; no real protected MODEL-13 value was connected before this result.
- Public reference layer: the tracked 2024 Michigan TIGER presentation geometry, exactly 3,017 unique public tract GEOIDs. The packaged file and tracked artifact had identical SHA-256 `84dbbecb3388345a838ae8bf93fe1f8213f8cce6dfe3921db106766ece6389c7`.
- Azure Maps data role: public-format synthetic Michigan GEOID only. Distinctive synthetic values were bound only to polygon color, tooltip, selection, and inspector interaction.
- Protected MODEL-13 values, `Seed Context`, physical-location identifiers, coordinates, sales, predictions, errors, paths, metadata, and other protected content were never connected to Azure Maps.
- No raw network capture or revealing screenshot was added to Git or GitHub.

The installed Desktop-created visual proved all of the following in the target environment:

- the visual rendered and persisted through save and reopen;
- Road rendered with road/place labels;
- Satellite road labels rendered through the native Style picker;
- the native Style picker remained available to the report reader;
- the public reference layer supported exactly 3,017 data-bound tract polygons;
- the native polygon treatment retained a semi-transparent dynamic fill over readable basemap labels with a subdued 55%-transparent 1 px boundary;
- ordinary single-tract click selection filtered the synthetic inspector to exactly one public GEOID;
- the selection-control/multi-selection surface was disabled; and
- no lasso, routing, traffic, drive-time, or navigation role or control was enabled.

## Actual outbound-request inspection

An already-installed Chromium DevTools inspection surface on the Power BI WebView recorded a bounded 65-second live request window while the synthetic canary changed style and selected a tract. It observed 69 requests, 68 to Azure Maps endpoints. The Azure Maps request paths were basemap/style/attribution/tile/tileset/sprite requests, including the Satellite style request.

Four distinctive text sentinels and three distinctive numeric sentinels used only for polygon color, tooltip, selection, and inspector interaction were searched across captured request URLs, methods, post bodies, and available request headers. Every sentinel count was zero. The synthetic-only values were therefore absent from the observed outbound Azure Maps request path.

The raw capture remained ignored and untracked. This result authorizes PBI-02 to proceed to the governed implementation and real-data Desktop validation; it does not accept the capability, establish exact H, or authorize publication, deployment, merge, or follow-on work.
