# APP-01 final targeted Product Design and Ultra audit

## Audit posture

The installed Product Design audit workflow completed the mandatory Stage-1 review and a separate targeted final Ultra review against the actual accepted-real APP-01 application in the in-app Chromium browser on 2026-08-26 at 1,440 × 900 and 1,280 × 800 desktop viewports. The final review used only current-run evidence, applied the Master Control Room high-severity threshold, and did not become a redesign or polish pass. Raw real screenshots, protected values, and network captures remain ignored and local; no real protected capture is committed.

The final current-run review exercised the exact metric selector and all 16 metrics; the two fixed statewide 0–100 domains; the 14 valid-only Type-7 P02–P98 domains; statewide orientation; pan and zoom; one-tract exact values; MODEL noncomputability; DATA-04 unavailable status; support truncation; multi-select and clear; Topo, Imagery + Labels, and Local neutral; QA & Coverage; Evidence Context and protected marker detail; reload; clean launcher restart; keyboard tab navigation; visible focus; and desktop fit without horizontal overflow. Screenshots were visual evidence, not a claim of accessibility compliance.

## Targeted flow health

1. **Initial Explore — healthy.** `Ready` appeared only after the full tract layer was visibly settled; map dominance, status, current metric, legend, and empty inspector were coherent.
2. **Color tracts by — healthy.** The visible selector remained prominent, labeled, and complete.
3. **Representative MODEL and DATA-04 switching — healthy.** Metric title, family, definition, interpretation, unit, source, scale, map colors, and legend stayed synchronized.
4. **Statewide orientation — healthy.** Michigan remained immediately recognizable with adequate public geographic context in Topo and Imagery.
5. **Pan and zoom — healthy.** The map responded without losing controls, metric context, legend, or tract legibility.
6. **One tract selected — healthy.** Selection was visible on the map and in the inspector without dominating the statewide map.
7. **Selected metric/value hierarchy — healthy.** Metric name, exact value, unit, uncertainty, accepted supporting context, and secondary GEOID reference appeared in the required order.
8. **MODEL warning — healthy.** Noncomputability appeared directly under `No Data / Unavailable` and explicitly stated that missingness was not converted to zero.
9. **DATA-04 unavailable/status — healthy.** Unavailable state, status detail, and missingness language remained attached to the affected value.
10. **No Data / Unavailable — healthy.** Text, warning treatment, map popup, and legend all communicated missingness without relying on color.
11. **Multiple selection — healthy.** The inspector explicitly stated the count and that no average represented one tract.
12. **Clear selection — healthy.** The action removed map selection and returned the inspector to the empty state.
13. **Topo — healthy.** Public road and place context remained visible with reviewed attribution.
14. **Imagery + Labels — healthy.** Aerial context and labels remained usable beneath tract fills with reviewed attribution.
15. **Local neutral — healthy.** Tracts, metric switching, legend, selection, and inspector remained usable with zero new external requests.
16. **QA & Coverage — healthy.** Statewide accounting, readiness, metric availability/domain, selected-tract QA, and local runtime stayed separate from scouting.
17. **Sprouts Evidence Context — healthy.** Local neutral was enforced before protected evidence loaded, external transmission was explicitly prohibited, and evidence detail stayed separate from Explore.
18. **Ordinary keyboard controls — healthy within verified scope.** Roving tab navigation changed the active view, essential controls were semantic focus targets, and repository tests retained keyboard/accessibility cues.
19. **Visible focus — healthy.** Tabs, selector, and basemap controls had conspicuous non-color focus treatment.
20. **Common desktop viewports — healthy.** Both inspected sizes preserved a map-dominant workflow with no horizontal overflow.
21. **Reload and restart — healthy.** Reload and the one-step launcher restart returned to accepted-real, 3,017-tract, 16-metric, zero-selection, default-Topo state without browser error.

## Targeted severity decision

No high-severity issue was identified. The operator could complete the core workflow; the three key analytical concepts remained distinct; selected-tract, warning, missingness, protected/public, fallback, focus, viewport, and readiness states were not materially misleading or unusable. Therefore the final Ultra pass made no product-code or presentation change and no correction-specific recheck was required.

No medium- or low-severity recommendation was judged important enough to carry into APP-01. The final review intentionally did not pursue minor copy, wrapping, spacing, or persistent-mode preferences. The current interface is preserved as the usable baseline.

## Prior corrections confirmed under accepted-real operation

The real application preserved every material correction from the provisional synthetic review:

1. Evidence Context removes online basemaps and external tile egress before loading protected-local evidence, hides scouting-only selection/hover overlays, legend, and tract hint, and restores the prior public camera and scouting context on exit.
2. Selected tracts use a restrained amber fill and zoom-responsive dark outline rather than a visually dominant fixed outline.
3. Accepted Census TIGER/Line attribution remains visible in Topo, Imagery + Labels, Local neutral, and Evidence Context.
4. View navigation uses tablist/tab/tabpanel semantics, arrow/Home/End movement, Enter/Space activation, selected-state tabindex, and visible focus.
5. Primary APP-01 view, basemap, selection, and checkbox targets retain their corrected desktop sizing; vendored MapLibre controls are not replaced.
6. Available estimates with nonstandard source or uncertainty status retain plain operator language and route exact detail to QA & Coverage.

Real-versus-synthetic comparisons confirmed consistent layout, spacing, typography, control treatment, inspector hierarchy, warning/missingness cues, metric-family palette distinction, QA separation, Evidence separation, and public-data boundary language. The real data distribution is materially different from the synthetic reference, but the fixed/robust scale contracts and `No Data / Unavailable` treatment remained legible and intact.

## Stage-1 material finding and correction confirmed

**Medium impact, in scope — `Ready` could precede the visible tract paint after reload.** A capture taken immediately when the runtime readiness flag changed showed the public basemap and controls before the tract layer had visibly settled. The application remained functional and rendered the layer shortly afterward, but the status created a brief perceived-stability mismatch.

The corrected runtime waits for the MapLibre idle state before clearing the loading treatment and publishing `Ready`. The affected accepted-real reload and launcher-restart flows were rechecked. The immediate corrected capture showed the full tract layer already visible, with disclosure-safe readiness observations of approximately 0.42 seconds on reload and 0.61 seconds after launcher restart on this workstation.

The final targeted review reconfirmed this correction under reload and launcher restart. No high-severity issue appeared, and no Product Design correction reopened architecture, metric inventory, analytical meaning, MODEL-13, DATA-04, GEO authority, external-service authority, or protected-data authority.

## Accessibility and security observations

Current-run keyboard evidence confirmed ArrowRight moved focus and active state from Explore to QA, and tabs, the metric selector, and basemap controls had visible non-color focus outlines. The semantic focus order exposed the selected view tab, metric selector, basemap radio group, additive-selection checkbox, map, and MapLibre controls. The in-app browser automation surface did not faithfully execute native Tab/Space default behavior, so those native defaults remain a screenshot/browser-tool evidence limit rather than a negative product finding; repository tests and semantic inspection corroborate the intended order and control types. The 1,280 × 800 layout had no horizontal overflow. This is not a general WCAG conformance claim.

The Product Design flow also rechecked protected egress. Initial, Topo, Imagery, and Local neutral states observed only reviewed USGS tile requests on exact allowlisted paths. Evidence Context forced Local neutral before protected evidence loaded, produced no new external network asset or application-recorded request, and recorded no runtime warning or error.

## Residual boundary

Local neutral intentionally has no external place labels. Adding a geocoder, label service, invented community geography, protected evidence clustering, or new analytical field would exceed the accepted APP-01 boundary. No such change is recommended for exact H, and no out-of-scope implementation remains pending.
