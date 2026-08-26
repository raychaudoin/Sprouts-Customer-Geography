# APP-01 provisional Product Design audit

## Audit posture

The installed Product Design audit workflow inspected the actual APP-01 application in the in-app Chromium browser on 2026-08-26 at 1,440 × 900 and 1,280 × 800 desktop viewports. All captures used the deterministic synthetic validation bundle and public geometry. Raw screenshots remain ignored and local. This was a bounded pre-real review that found and corrected presentation defects early; the mandatory post-real Product Design audit gate remains false until accepted real MODEL-13 operation is available.

The review exercised the initial Michigan view; the exact metric selector and multiple metric families; all 16 metrics programmatically through the visible selector; fixed and Type-7 robust domains; pan and zoom; one-tract exact values; model noncomputability; DATA-04 unavailable state; a retained estimate with inapplicable MOE context; multi-select and clear; Topo, Imagery + Labels, and Local neutral; QA & Coverage; Evidence Context and an evidence marker; reload; 1,280-pixel desktop fit; keyboard focus, arrow navigation, Enter activation, and Escape clearing. Screenshots alone were not treated as accessibility evidence.

## Material findings and corrections

1. **High impact, in scope — Evidence Context retained scouting-only overlays.** The initial candidate carried the previously selected tract outline, metric legend, tract-click hint, and “Coloring tracts by” eyebrow into the protected-local evidence view. That weakened the separation between scouting and protected evidence. The corrected view hides selection/hover layers, legend, and tract hint; changes the title eyebrow to “Viewing”; keeps the subdued public geometry only; and restores those elements on exit.
2. **Medium impact, in scope — Statewide selected outlines were visually heavy.** A fixed 3.2-pixel outline made small tracts look like black glyphs at statewide zoom. Selection now uses a restrained amber fill plus a zoom-responsive dark outline, retaining a non-color boundary cue without dominating the map.
3. **Medium impact, in scope — Local neutral lacked visible public-geometry attribution.** The accepted Census TIGER/Line attribution is now attached to the tract source, so it remains visible in all basemap modes, including network-free Local neutral and Evidence Context.
4. **Medium impact, in scope — View navigation was only partially expressed as tabs.** The corrected navigation uses `tablist`, `tab`, `tabpanel`, `aria-controls`, selected-state `tabindex`, arrow/Home/End movement, Enter/Space activation, and visible focus. Current-run recheck confirmed ArrowRight moved focus and active state from Explore to QA, Enter activated Evidence Context, ArrowLeft returned to QA, and Escape cleared a tract selection.
5. **Medium impact, in scope — Primary targets were undersized.** View tabs, basemap labels, selection controls, and the checkbox target were enlarged to at least 44 CSS pixels where controlled by APP-01; MapLibre zoom controls were enlarged to 40 pixels without replacing the vendored control.
6. **Medium impact, in scope — An estimate-without-MOE warning read like internal implementation language.** The Explore warning now states plainly that the estimate is available while its source or uncertainty status is inapplicable and directs the operator to exact status detail in QA & Coverage.

Corrected screenshots confirmed the separated Evidence Context surface, hidden scouting overlays, restored public-camera exit, refined selection treatment, public attribution, plain warning language, 1,280-pixel fit without visible horizontal scrolling, and keyboard-visible tab focus. The current layout remained map-dominant, kept the inspector hierarchy compact, distinguished model-proxy and descriptive palettes, preserved non-color warning/missing cues, and kept raw QA fields outside ordinary scouting.

## Residual boundary

Local neutral intentionally has no external place labels; adding a geocoder, label service, invented community geography, or new analytical field is outside accepted authority. Real protected screenshots will not be committed. No claim of WCAG or general accessibility compliance is made; the evidence is limited to the specified browser, viewports, keyboard behaviors, focus styling, labels, non-color cues, and inspected contrast/readability.
