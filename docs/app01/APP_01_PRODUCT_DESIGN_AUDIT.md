# APP-01 post-real Product Design audit

## Audit posture

The installed Product Design audit workflow inspected the actual accepted-real APP-01 application in the in-app Chromium browser on 2026-08-26 at 1,440 × 900 and 1,280 × 800 desktop viewports. Raw real screenshots, protected values, and network captures remain ignored and local. Repository-safe synthetic captures from the earlier provisional audit were used only as visual references; real protected captures were not committed.

The current-run review exercised the initial Michigan Explore view; the exact metric selector and several metric families; all 16 metrics programmatically through the visible selector; the two fixed statewide 0–100 domains; the 14 valid-only Type-7 P02–P98 domains; statewide orientation; pan and zoom; one-tract exact values; MODEL noncomputability; DATA-04 unavailable status; support truncation; multi-select and clear; Topo, Imagery + Labels, and Local neutral; QA & Coverage; Evidence Context and protected marker detail; reload; clean launcher restart; keyboard tab navigation; visible focus; and desktop fit without horizontal overflow. Screenshots were visual evidence, not a claim of accessibility compliance.

## Prior corrections confirmed under accepted-real operation

The real application preserved every material correction from the provisional synthetic review:

1. Evidence Context removes online basemaps and external tile egress before loading protected-local evidence, hides scouting-only selection/hover overlays, legend, and tract hint, and restores the prior public camera and scouting context on exit.
2. Selected tracts use a restrained amber fill and zoom-responsive dark outline rather than a visually dominant fixed outline.
3. Accepted Census TIGER/Line attribution remains visible in Topo, Imagery + Labels, Local neutral, and Evidence Context.
4. View navigation uses tablist/tab/tabpanel semantics, arrow/Home/End movement, Enter/Space activation, selected-state tabindex, and visible focus.
5. Primary APP-01 view, basemap, selection, and checkbox targets retain their corrected desktop sizing; vendored MapLibre controls are not replaced.
6. Available estimates with nonstandard source or uncertainty status retain plain operator language and route exact detail to QA & Coverage.

Real-versus-synthetic comparisons confirmed consistent layout, spacing, typography, control treatment, inspector hierarchy, warning/missingness cues, metric-family palette distinction, QA separation, Evidence separation, and public-data boundary language. The real data distribution is materially different from the synthetic reference, but the fixed/robust scale contracts and `No Data / Unavailable` treatment remained legible and intact.

## Current-run material finding and correction

**Medium impact, in scope — `Ready` could precede the visible tract paint after reload.** A capture taken immediately when the runtime readiness flag changed showed the public basemap and controls before the tract layer had visibly settled. The application remained functional and rendered the layer shortly afterward, but the status created a brief perceived-stability mismatch.

The corrected runtime waits for the MapLibre idle state before clearing the loading treatment and publishing `Ready`. The affected accepted-real reload and launcher-restart flows were rechecked. The immediate corrected capture showed the full tract layer already visible, with disclosure-safe readiness observations of approximately 0.42 seconds on reload and 0.61 seconds after launcher restart on this workstation.

No other high- or medium-impact real-specific issue was found. The dense protected evidence pattern remains zoomable and selectable without adding clustering, new geography, or changed evidence semantics. No Product Design correction reopened architecture, metric inventory, analytical meaning, MODEL-13, DATA-04, GEO authority, external-service authority, or protected-data authority.

## Accessibility and security observations

Current-run keyboard evidence confirmed ArrowRight moved focus and active state from Explore to QA, and the focused tab had a visible non-color outline. The 1,280 × 800 layout had no horizontal overflow. Labels, missingness text, warning boxes, selected outlines, status text, and focus styling provide cues beyond color alone. This evidence is limited to the inspected Chromium-family browser and viewports and is not a general WCAG conformance claim.

The Product Design flow also rechecked protected egress. Initial, Topo, Imagery, and Local neutral states observed only reviewed USGS tile requests on exact allowlisted paths. Evidence Context forced Local neutral before protected evidence loaded, produced no new external network asset or application-recorded request, and recorded no runtime warning or error.

## Residual boundary

Local neutral intentionally has no external place labels. Adding a geocoder, label service, invented community geography, protected evidence clustering, or new analytical field would exceed the accepted APP-01 boundary. No such change is recommended for this Stage-1 gate, and no out-of-scope implementation remains pending.
