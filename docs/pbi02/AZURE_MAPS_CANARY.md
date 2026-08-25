# PBI-02 Azure Maps synthetic-canary result

## Result

`BLOCKED_FAIL_CLOSED`

The target installed Power BI Desktop environment did not permit the built-in Azure Maps visual to render without an authenticated Power BI session. Desktop displayed:

> To display Azure Maps visuals, sign in.

The access gate therefore stopped before Road, Satellite road labels, the native Style picker, reference-layer persistence, selection behavior, or outbound-request inspection could be validated. The protected-data nontransmission canary is **not established**.

## Disclosure-safe method

- Desktop version: `2.157.879.0 (26.08)`.
- Surface: an isolated ignored runtime copy of the accepted `MICustomerGeography` PBIP.
- Data posture: `SYNTHETIC_ONLY`.
- Azure Maps roles used before the access stop: a public-format synthetic Michigan GEOID plus synthetic latitude and longitude.
- Protected MODEL-13 values, `Seed Context`, physical-location identifiers, coordinates, sales, predictions, errors, paths, metadata, and other protected content were never connected to Azure Maps.
- No raw network capture or revealing screenshot was added to Git or GitHub.

The visual definition was created by the installed Power BI Desktop rather than inferred from documentation. The test stopped immediately when Desktop required sign-in; it did not attempt to automate authentication.

## Minimum restoration and rerun boundary

An authorized user must sign in to the target Power BI tenant in Power BI Desktop. PBI-02 must then resume on the same task branch and rerun the exact synthetic canary before any real protected MODEL-13 value is bound to Azure Maps. Passing documentation claims alone is insufficient; actual outbound-request inspection remains required.

Until that rerun passes, PBI-02 must not claim Azure Maps access, Road or Satellite road labels, Style picker behavior, outbound-data nontransmission, real-data Desktop validation, exact H, or completion.
