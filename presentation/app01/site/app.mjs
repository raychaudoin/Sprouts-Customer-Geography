import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  setWorkerUrl,
} from "/vendor/maplibre-gl/maplibre-gl.mjs";

setWorkerUrl("/vendor/maplibre-gl/maplibre-gl-worker.mjs");

const startedAt = performance.now();
const modelColors = ["#f7ebc6", "#d7cf8a", "#a1b874", "#5f8c68", "#285c4f"];
const descriptiveColors = ["#e8f1f5", "#bdd9e4", "#7bb6c8", "#3e8198", "#164c63"];
const noDataColor = "#d5d7d2";
const tilePathPattern = /^\/arcgis\/rest\/services\/(USGSTopo|USGSImageryTopo)\/MapServer\/tile\/[0-9]+\/[0-9]+\/[0-9]+$/;
const selectedGeoids = new Set();
const externalRequests = [];
const rowByGeoid = new Map();
let runtime;
let bundle;
let metrics;
let geometry;
let map;
let popup;
let evidenceBundle;
let activeMetricIndex = 0;
let activeView = "explore";
let preferredBasemap = "usgs_topo";
let currentBasemap = "local_neutral";
let basemapFailureHandled = false;
let externalEgressEnabled = true;
let hoveredGeoid = null;
let savedExploreCamera = null;

const diagnostics = {
  ready: false,
  dataMode: null,
  featureCount: 0,
  metricCount: 0,
  activeMetric: null,
  activeView: "explore",
  basemap: "local_neutral",
  selectionCount: 0,
  mapReadyMs: null,
  lastMetricSwitchMs: null,
  lastSelectionMs: null,
  externalRequestCount: 0,
  externalHosts: [],
  canaryHits: 0,
  localNeutralRequestDelta: null,
  evidenceLoaded: false,
  error: null,
};
window.__APP01_DIAGNOSTICS__ = diagnostics;

const byId = (id) => document.getElementById(id);

function publishDiagnostics() {
  const data = document.documentElement.dataset;
  data.app01Ready = String(diagnostics.ready);
  data.app01DataMode = diagnostics.dataMode ?? "";
  data.app01FeatureCount = String(diagnostics.featureCount);
  data.app01MetricCount = String(diagnostics.metricCount);
  data.app01ActiveMetric = diagnostics.activeMetric ?? "";
  data.app01ActiveView = diagnostics.activeView;
  data.app01Basemap = diagnostics.basemap;
  data.app01SelectionCount = String(diagnostics.selectionCount);
  data.app01MapReadyMs = diagnostics.mapReadyMs === null ? "" : String(diagnostics.mapReadyMs);
  data.app01MetricSwitchMs = diagnostics.lastMetricSwitchMs === null ? "" : String(diagnostics.lastMetricSwitchMs);
  data.app01SelectionMs = diagnostics.lastSelectionMs === null ? "" : String(diagnostics.lastSelectionMs);
  data.app01ExternalRequestCount = String(diagnostics.externalRequestCount);
  data.app01ExternalHosts = diagnostics.externalHosts.join(",");
  data.app01CanaryHits = String(diagnostics.canaryHits);
  data.app01EvidenceLoaded = String(diagnostics.evidenceLoaded);
  data.app01Error = diagnostics.error ?? "";
}

publishDiagnostics();

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function fetchJson(path) {
  const response = await fetch(path, {method: "GET", cache: "no-store", credentials: "same-origin"});
  if (!response.ok) throw new Error("APP01_LOCAL_INPUT_FETCH_FAILED");
  return response.json();
}

function recordCanaryHit() {
  diagnostics.canaryHits += 1;
  byId("qa-canary-hits").textContent = String(diagnostics.canaryHits);
  publishDiagnostics();
}

function requestPolicy(url) {
  const resolved = new URL(url, window.location.href);
  if (resolved.origin === window.location.origin) {
    if (resolved.search || resolved.hash) throw new Error("APP01_LOCAL_QUERY_BLOCKED");
    return {url: resolved.href, method: "GET", credentials: "same-origin"};
  }
  const canaryTokens = bundle?.egress_canary?.tokens ?? [];
  if (canaryTokens.some((token) => token && resolved.href.includes(token))) {
    recordCanaryHit();
    throw new Error("APP01_EGRESS_CANARY_BLOCKED");
  }
  if (
    !externalEgressEnabled
    || activeView === "evidence"
    || resolved.protocol !== "https:"
    || resolved.hostname !== "basemap.nationalmap.gov"
    || resolved.search
    || resolved.hash
    || !tilePathPattern.test(resolved.pathname)
  ) {
    throw new Error("APP01_EXTERNAL_REQUEST_BLOCKED");
  }
  externalRequests.push({host: resolved.hostname, service: resolved.pathname.includes("USGSImageryTopo") ? "USGSImageryTopo" : "USGSTopo"});
  diagnostics.externalRequestCount = externalRequests.length;
  diagnostics.externalHosts = [...new Set(externalRequests.map((entry) => entry.host))];
  byId("qa-external-host").textContent = diagnostics.externalHosts.join(", ") || "None";
  byId("qa-request-count").textContent = String(diagnostics.externalRequestCount);
  publishDiagnostics();
  return {url: resolved.href, method: "GET", headers: {}, credentials: "omit"};
}

function baseStyle() {
  return {
    version: 8,
    sources: {},
    layers: [{id: "neutral-background", type: "background", paint: {"background-color": "#e6eae5"}}],
  };
}

function formatValue(value, metric) {
  if (value === null || value === undefined) return "No Data / Unavailable";
  const numeric = Number(value);
  if (metric.format_policy === "currency_0") {
    return new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", maximumFractionDigits: 0}).format(numeric);
  }
  if (metric.format_policy === "count_0") {
    return new Intl.NumberFormat("en-US", {maximumFractionDigits: 0}).format(numeric);
  }
  if (metric.format_policy === "decimal_2") return numeric.toFixed(2);
  if (metric.format_policy === "percent_1") return `${numeric.toFixed(1)}%`;
  return numeric.toFixed(1);
}

function humanStatus(value) {
  return String(value || "unavailable").replaceAll("_", " ");
}

function paletteFor(metric) {
  return metric.palette === "descriptive_sequential" ? descriptiveColors : modelColors;
}

function fillExpression(index) {
  const metric = metrics[index];
  const domain = bundle.domains[metric.metric_key];
  const range = domain.maximum - domain.minimum;
  const stops = [0, .25, .5, .75, 1].map((portion) => domain.minimum + range * portion);
  const interpolation = ["interpolate", ["linear"], ["get", `m${index}`]];
  stops.forEach((stop, stopIndex) => interpolation.push(stop, paletteFor(metric)[stopIndex]));
  return ["case", ["has", `m${index}`], interpolation, noDataColor];
}

function selectionFilter() {
  if (!selectedGeoids.size) return ["==", ["get", "GEOID"], ""];
  return ["in", ["get", "GEOID"], ["literal", [...selectedGeoids]]];
}

function hoverFilter() {
  return hoveredGeoid ? ["==", ["get", "GEOID"], hoveredGeoid] : ["==", ["get", "GEOID"], ""];
}

function updateLegend() {
  const metric = metrics[activeMetricIndex];
  const domain = bundle.domains[metric.metric_key];
  const interval = (domain.maximum - domain.minimum) / 4;
  const values = [0, 1, 2, 3, 4].map((index) => domain.minimum + interval * index);
  byId("legend-title").textContent = metric.display_name;
  byId("legend-unit").textContent = metric.unit;
  byId("legend-ramp").style.background = `linear-gradient(90deg, ${paletteFor(metric).join(", ")})`;
  byId("legend-labels").replaceChildren(...values.map((value, index) => {
    const span = element("span", "", formatValue(value, metric));
    if (index === 0) span.textContent = `≤ ${span.textContent}`;
    if (index === values.length - 1) span.textContent = `≥ ${span.textContent}`;
    return span;
  }));
}

function updateMetricContext() {
  const metric = metrics[activeMetricIndex];
  const domain = bundle.domains[metric.metric_key];
  byId("metric-context-heading").textContent = metric.display_name;
  if (activeView !== "evidence") byId("map-title-eyebrow").textContent = "Coloring tracts by";
  byId("map-metric-title").textContent = activeView === "evidence" ? "Protected local evidence context" : metric.display_name;
  byId("metric-family").textContent = humanStatus(metric.family);
  byId("metric-definition").textContent = metric.definition;
  byId("metric-interpretation").textContent = metric.interpretation;
  byId("metric-unit").textContent = metric.unit;
  byId("metric-source").textContent = metric.source_vintage;
  byId("metric-domain").textContent = metric.scale_policy === "fixed_0_100"
    ? "Fixed statewide 0–100"
    : `Statewide valid-only Type-7 P02–P98: ${formatValue(domain.minimum, metric)} to ${formatValue(domain.maximum, metric)}`;
  updateLegend();
}

function warningFor(row, metricIndex) {
  const metric = metrics[metricIndex];
  const status = row.statuses[metricIndex];
  const detail = row.status_details[metricIndex];
  const value = row.values[metricIndex];
  if (value === null || value === undefined) {
    return `Unavailable — ${humanStatus(status)}${detail ? `. ${humanStatus(detail)}` : ""}. Missingness remains explicit and is not converted to zero.`;
  }
  if (status !== "valid") {
    return `The estimate is available, but its source or uncertainty status is ${humanStatus(status)}. Review the exact status detail in QA & Coverage.`;
  }
  if (row.support_truncation && metric.metric_key === "household_opportunity_5_mile") {
    return "Five-mile household support is truncated for this tract. The accepted raw opportunity value is shown without a boundary correction.";
  }
  if (row.support_truncation && ["customer_fit_percentile", "modeled_target_mass_percentile"].includes(metric.metric_key)) {
    return "Accepted five-mile support is truncated for this tract. Treat the modeled value with the associated support limitation.";
  }
  return null;
}

function supportMetricIndexes() {
  const preferred = [
    "customer_fit_percentile",
    "household_opportunity_5_mile",
    "median_household_income",
    "owner_occupancy_share",
    "no_vehicle_household_share",
    "per_capita_income",
    "average_household_size",
  ];
  return preferred
    .map((key) => metrics.findIndex((metric) => metric.metric_key === key))
    .filter((index) => index >= 0 && index !== activeMetricIndex)
    .slice(0, 5);
}

function updateSelection() {
  const started = performance.now();
  for (const layer of ["tract-selected-fill", "tract-selected"]) {
    if (map?.getLayer(layer)) map.setFilter(layer, selectionFilter());
  }
  const count = selectedGeoids.size;
  diagnostics.selectionCount = count;
  byId("selection-count").textContent = String(count);
  byId("clear-selection").disabled = count === 0;
  const heading = byId("selection-heading");
  const content = byId("selection-content");
  content.replaceChildren();
  if (count === 0) {
    heading.textContent = "Select a tract";
    content.className = "selection-content empty-state";
    content.textContent = "Click a tract to see its exact value and supporting context. Turn on Add to selection to compare several tracts.";
  } else if (count > 1) {
    heading.textContent = "Multiple tracts selected";
    content.className = "selection-content multiple-state";
    content.append(
      element("strong", "", `${count} tracts selected`),
      element("p", "", "No average is shown as if it represented one tract. Clear the selection or choose one tract for exact values."),
    );
  } else {
    const geoid = [...selectedGeoids][0];
    const row = rowByGeoid.get(geoid);
    const metric = metrics[activeMetricIndex];
    heading.textContent = metric.display_name;
    content.className = "selection-content";
    content.append(
      element("p", "selected-metric-label", "Exact selected value"),
      element("p", "selected-value", formatValue(row.values[activeMetricIndex], metric)),
      element("p", "selected-unit", metric.unit),
    );
    const moe = row.moes[activeMetricIndex];
    if (moe !== null && moe !== undefined) {
      content.append(element("p", "selected-moe", `Margin of error: ± ${formatValue(moe, metric)}`));
    }
    const warning = warningFor(row, activeMetricIndex);
    if (warning) content.append(element("div", "warning-box", warning));
    const details = element("dl", "support-list");
    supportMetricIndexes().forEach((index) => {
      const pair = element("div");
      pair.append(
        element("dt", "", metrics[index].display_name),
        element("dd", "", formatValue(row.values[index], metrics[index])),
      );
      details.append(pair);
    });
    content.append(details, element("p", "geoid-reference", `GEOID ${geoid}`));
  }
  diagnostics.lastSelectionMs = Math.round((performance.now() - started) * 10) / 10;
  updateQaSelection();
  publishDiagnostics();
}

function clearSelection() {
  selectedGeoids.clear();
  updateSelection();
}

function selectGeoids(geoids) {
  selectedGeoids.clear();
  geoids.forEach((geoid) => {
    if (rowByGeoid.has(geoid)) selectedGeoids.add(geoid);
  });
  updateSelection();
}

function updateMetric(index) {
  const started = performance.now();
  activeMetricIndex = index;
  const metric = metrics[index];
  byId("metric-select").value = metric.metric_key;
  if (map?.getLayer("tract-fill")) map.setPaintProperty("tract-fill", "fill-color", fillExpression(index));
  diagnostics.activeMetric = metric.metric_key;
  updateMetricContext();
  updateSelection();
  updateQaMetric();
  diagnostics.lastMetricSwitchMs = Math.round((performance.now() - started) * 10) / 10;
  publishDiagnostics();
}

function updateQaMetric() {
  if (!bundle || !metrics) return;
  const metric = metrics[activeMetricIndex];
  const domain = bundle.domains[metric.metric_key];
  const availability = bundle.availability[metric.metric_key];
  byId("qa-metric-name").textContent = metric.display_name;
  byId("qa-availability").textContent = `${availability.available.toLocaleString("en-US")} / ${availability.unavailable.toLocaleString("en-US")}`;
  byId("qa-domain").textContent = `${formatValue(domain.minimum, metric)} to ${formatValue(domain.maximum, metric)} · ${domain.policy === "fixed_0_100" ? "fixed" : "Type-7 P02–P98"}`;
  byId("qa-source").textContent = metric.source_vintage;
}

function updateQaSelection() {
  if (!bundle || !metrics) return;
  const target = byId("qa-selected-tract");
  target.replaceChildren();
  if (selectedGeoids.size !== 1) {
    target.className = "empty-state";
    target.textContent = selectedGeoids.size > 1
      ? "Multiple tracts are selected. Return to Explore and choose one tract for exact QA evidence."
      : "Select one tract in Explore to inspect its status, margin of error, and status detail.";
    return;
  }
  const geoid = [...selectedGeoids][0];
  const row = rowByGeoid.get(geoid);
  const metric = metrics[activeMetricIndex];
  const dl = element("dl", "metadata-list qa-tract-table");
  const values = [
    ["GEOID", geoid],
    ["Status", humanStatus(row.statuses[activeMetricIndex])],
    ["Value", formatValue(row.values[activeMetricIndex], metric)],
    ["MOE", row.moes[activeMetricIndex] === null ? "Not applicable" : `± ${formatValue(row.moes[activeMetricIndex], metric)}`],
    ["Status detail", row.status_details[activeMetricIndex] ? humanStatus(row.status_details[activeMetricIndex]) : "None"],
    ["5-mile support", row.support_truncation ? "Truncated" : "Complete within accepted boundary evidence"],
  ];
  values.forEach(([term, value]) => {
    const pair = element("div");
    pair.append(element("dt", "", term), element("dd", "", value));
    dl.append(pair);
  });
  target.className = "";
  target.append(dl);
}

function updateQaGlobal() {
  const qa = bundle.qa;
  byId("qa-total-tracts").textContent = bundle.tract_count.toLocaleString("en-US");
  byId("qa-computable").textContent = qa.model_computable_count.toLocaleString("en-US");
  byId("qa-noncomputable").textContent = qa.model_noncomputable_count.toLocaleString("en-US");
  byId("qa-truncated").textContent = qa.support_truncated_count.toLocaleString("en-US");
  byId("qa-model-ready").textContent = qa.model13.state;
  byId("qa-data-ready").textContent = qa.data04.state;
  byId("qa-geometry-ready").textContent = `${qa.geometry.state} · ${qa.geometry.tract_count.toLocaleString("en-US")} tracts`;
  byId("qa-key-ready").textContent = qa.geometry.key_reconciliation;
  updateQaMetric();
  updateQaSelection();
}

function removeBasemap() {
  if (map.getLayer("basemap-raster")) map.removeLayer("basemap-raster");
  if (map.getSource("basemap")) map.removeSource("basemap");
  currentBasemap = "local_neutral";
  diagnostics.basemap = currentBasemap;
  publishDiagnostics();
}

function setBasemapRadio(key) {
  const input = document.querySelector(`input[name="basemap"][value="${key}"]`);
  if (input) input.checked = true;
}

function selectBasemap(key, {failureMessage = null, preservePreference = false} = {}) {
  if (!runtime.basemaps[key]) return;
  if (activeView === "evidence" && key !== "local_neutral") return;
  const requestBaseline = externalRequests.length;
  removeBasemap();
  const config = runtime.basemaps[key];
  if (config.tile_url) {
    map.addSource("basemap", {
      type: "raster",
      tiles: [config.tile_url],
      tileSize: 256,
      maxzoom: config.maxzoom,
      attribution: config.attribution,
    });
    map.addLayer({id: "basemap-raster", type: "raster", source: "basemap", paint: {"raster-opacity": 0.9}}, "tract-fill");
  }
  currentBasemap = key;
  diagnostics.basemap = key;
  if (!preservePreference && activeView !== "evidence") preferredBasemap = key;
  setBasemapRadio(key);
  const message = byId("map-message");
  if (failureMessage) {
    message.textContent = failureMessage;
    message.hidden = false;
  } else {
    message.hidden = true;
  }
  if (key === "local_neutral") {
    window.setTimeout(() => {
      diagnostics.localNeutralRequestDelta = externalRequests.length - requestBaseline;
      publishDiagnostics();
    }, 600);
  }
  publishDiagnostics();
}

function showHover(event) {
  if (activeView !== "explore" || !event.features?.length) return;
  const geoid = event.features[0].properties.GEOID;
  const row = rowByGeoid.get(geoid);
  const metric = metrics[activeMetricIndex];
  hoveredGeoid = geoid;
  map.setFilter("tract-hover", hoverFilter());
  const content = element("div", "hover-content");
  content.append(
    element("strong", "", formatValue(row.values[activeMetricIndex], metric)),
    element("span", "", `${metric.display_name} · GEOID ${geoid}`),
  );
  popup.setLngLat(event.lngLat).setDOMContent(content).addTo(map);
}

function hideHover() {
  hoveredGeoid = null;
  if (map?.getLayer("tract-hover")) map.setFilter("tract-hover", hoverFilter());
  popup?.remove();
}

function onTractClick(event) {
  if (activeView !== "explore" || !event.features?.length) return;
  const geoid = event.features[0].properties.GEOID;
  const additive = byId("additive-mode").checked || event.originalEvent.shiftKey || event.originalEvent.ctrlKey || event.originalEvent.metaKey;
  if (!additive) selectedGeoids.clear();
  if (additive && selectedGeoids.has(geoid)) selectedGeoids.delete(geoid);
  else selectedGeoids.add(geoid);
  updateSelection();
}

async function loadEvidence() {
  if (evidenceBundle) return evidenceBundle;
  const value = await fetchJson("/data/evidence.json");
  if (value.local_only !== true || value.external_transmission_permitted !== false || value.data_mode !== bundle.data_mode || !Array.isArray(value.rows)) {
    throw new Error("APP01_EVIDENCE_BUNDLE_INVALID");
  }
  evidenceBundle = value;
  diagnostics.evidenceLoaded = true;
  byId("evidence-count").textContent = value.row_count.toLocaleString("en-US");
  byId("evidence-mode").textContent = value.data_mode === "accepted_real" ? "Accepted protected-local data" : "Synthetic validation data";
  publishDiagnostics();
  return value;
}

function renderEvidenceDetail(row) {
  const target = byId("evidence-detail");
  target.replaceChildren();
  const dl = element("dl", "metadata-list qa-tract-table");
  const currency = new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", maximumFractionDigits: 0});
  const integer = new Intl.NumberFormat("en-US", {maximumFractionDigits: 0});
  const entries = [
    ["Evidence ID", row.evidence_id],
    ["Mean Isolated Sales", currency.format(row.isolated_sales)],
    ["Frozen MODEL-12 prediction", currency.format(row.frozen_prediction)],
    ["Successor OOF prediction", currency.format(row.successor_prediction)],
    ["Absolute log error", Number(row.absolute_log_error).toFixed(3)],
    ["Household opportunity", integer.format(row.household_opportunity)],
    ["Customer-fit proxy", Number(row.customer_fit_proxy).toFixed(3)],
    ["Modeled target mass", integer.format(row.modeled_target_mass)],
    ["Support", row.support_truncation ? "Truncated" : "Not truncated"],
    ["QA status", humanStatus(row.qa_status)],
  ];
  entries.forEach(([term, value]) => {
    const pair = element("div");
    pair.append(element("dt", "", term), element("dd", "evidence-value", value));
    dl.append(pair);
  });
  target.className = "";
  target.append(dl);
}

function onEvidenceClick(event) {
  if (!evidenceBundle || !event.features?.length) return;
  const index = Number(event.features[0].properties.evidenceIndex);
  const row = evidenceBundle.rows[index];
  if (!row) return;
  renderEvidenceDetail(row);
  map.setFilter("evidence-points-selected", ["==", ["get", "evidenceIndex"], index]);
}

function removeEvidenceLayers() {
  popup?.remove();
  if (map.getLayer("evidence-points")) map.off("click", "evidence-points", onEvidenceClick);
  for (const layer of ["evidence-points-selected", "evidence-points"]) {
    if (map.getLayer(layer)) map.removeLayer(layer);
  }
  if (map.getSource("evidence")) map.removeSource("evidence");
}

function setTractInteractionVisibility(visible) {
  const visibility = visible ? "visible" : "none";
  for (const layer of ["tract-selected-fill", "tract-selected", "tract-hover"]) {
    if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", visibility);
  }
}

async function enterEvidence() {
  savedExploreCamera = {
    center: map.getCenter().toArray(),
    zoom: map.getZoom(),
    bearing: map.getBearing(),
    pitch: map.getPitch(),
  };
  externalEgressEnabled = false;
  removeBasemap();
  setTractInteractionVisibility(false);
  setBasemapRadio("local_neutral");
  byId("basemap-controls").disabled = true;
  byId("map-title-eyebrow").textContent = "Viewing";
  byId("map-legend").hidden = true;
  byId("map-hint").hidden = true;
  map.setPaintProperty("tract-fill", "fill-opacity", 0.22);
  const evidence = await loadEvidence();
  const features = evidence.rows.map((row, index) => ({
    type: "Feature",
    id: index,
    properties: {evidenceIndex: index},
    geometry: {type: "Point", coordinates: [row.longitude, row.latitude]},
  }));
  map.addSource("evidence", {type: "geojson", data: {type: "FeatureCollection", features}});
  map.addLayer({
    id: "evidence-points",
    type: "circle",
    source: "evidence",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 5, 9, 9],
      "circle-color": "#d49a43",
      "circle-stroke-color": "#173f2e",
      "circle-stroke-width": 2,
      "circle-opacity": 0.9,
    },
  });
  map.addLayer({
    id: "evidence-points-selected",
    type: "circle",
    source: "evidence",
    filter: ["==", ["get", "evidenceIndex"], -1],
    paint: {"circle-radius": 13, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#176f91", "circle-stroke-width": 3},
  });
  map.on("click", "evidence-points", onEvidenceClick);
  if (features.length) {
    const longitudes = features.map((feature) => feature.geometry.coordinates[0]);
    const latitudes = features.map((feature) => feature.geometry.coordinates[1]);
    map.fitBounds(
      [[Math.min(...longitudes), Math.min(...latitudes)], [Math.max(...longitudes), Math.max(...latitudes)]],
      {padding: 70, maxZoom: 8.5, duration: 0},
    );
  }
  byId("map-metric-title").textContent = "Protected local evidence context";
  diagnostics.basemap = "local_neutral";
  publishDiagnostics();
}

async function exitEvidence() {
  removeEvidenceLayers();
  map.setPaintProperty("tract-fill", "fill-opacity", 0.72);
  setTractInteractionVisibility(true);
  if (savedExploreCamera) map.jumpTo(savedExploreCamera);
  await new Promise((resolve) => requestAnimationFrame(resolve));
  externalEgressEnabled = true;
  selectBasemap(preferredBasemap, {preservePreference: true});
  byId("basemap-controls").disabled = false;
  byId("map-legend").hidden = false;
  byId("map-hint").hidden = false;
  savedExploreCamera = null;
  updateMetricContext();
}

async function setView(nextView) {
  if (!["explore", "qa", "evidence"].includes(nextView) || nextView === activeView) return;
  const leavingEvidence = activeView === "evidence";
  activeView = nextView;
  if (leavingEvidence) await exitEvidence();
  document.querySelectorAll(".view-tab").forEach((button) => {
    const active = button.dataset.view === nextView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll(".rail-view").forEach((panel) => {
    const active = panel.id === `view-${nextView}`;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
  if (nextView === "evidence") await enterEvidence();
  else updateMetricContext();
  diagnostics.activeView = nextView;
  publishDiagnostics();
}

function installControls() {
  const selector = byId("metric-select");
  selector.replaceChildren(...metrics.map((metric) => {
    const option = element("option", "", metric.display_name);
    option.value = metric.metric_key;
    return option;
  }));
  selector.disabled = false;
  selector.addEventListener("change", () => updateMetric(metrics.findIndex((metric) => metric.metric_key === selector.value)));
  document.querySelectorAll("input[name='basemap']").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) {
        basemapFailureHandled = false;
        selectBasemap(input.value);
      }
    });
  });
  byId("basemap-controls").disabled = false;
  byId("clear-selection").addEventListener("click", clearSelection);
  const viewTabs = [...document.querySelectorAll(".view-tab")];
  viewTabs.forEach((button, index) => {
    button.addEventListener("click", () => setView(button.dataset.view));
    button.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        setView(button.dataset.view);
        return;
      }
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let targetIndex = index;
      if (event.key === "Home") targetIndex = 0;
      else if (event.key === "End") targetIndex = viewTabs.length - 1;
      else targetIndex = (index + (event.key === "ArrowRight" ? 1 : -1) + viewTabs.length) % viewTabs.length;
      const target = viewTabs[targetIndex];
      target.focus();
      setView(target.dataset.view);
    });
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && selectedGeoids.size) clearSelection();
  });
}

function joinedFeatureCollection() {
  const featureGeoids = geometry.features.map((feature) => String(feature.properties.GEOID));
  if (
    geometry.type !== "FeatureCollection"
    || featureGeoids.length !== bundle.tract_count
    || new Set(featureGeoids).size !== bundle.tract_count
    || featureGeoids.some((geoid) => !rowByGeoid.has(geoid))
  ) {
    throw new Error("APP01_BROWSER_KEY_RECONCILIATION_FAILED");
  }
  return {
    type: "FeatureCollection",
    features: geometry.features.map((feature) => {
      const geoid = String(feature.properties.GEOID);
      const row = rowByGeoid.get(geoid);
      const properties = {GEOID: geoid};
      row.values.forEach((value, index) => {
        if (value !== null && value !== undefined) properties[`m${index}`] = value;
      });
      return {type: "Feature", properties, geometry: feature.geometry};
    }),
  };
}

function initializeMap() {
  map = new MapLibreMap({
    container: "map",
    style: baseStyle(),
    center: [-85.5, 44.45],
    zoom: 5.35,
    minZoom: 4.2,
    maxZoom: 16,
    maxBounds: [[-93.2, 40.0], [-79.0, 50.0]],
    attributionControl: true,
    transformRequest: requestPolicy,
    cooperativeGestures: false,
  });
  map.addControl(new NavigationControl({showCompass: false, visualizePitch: false}), "top-right");
  popup = new Popup({closeButton: false, closeOnClick: false, offset: 12, maxWidth: "290px"});
  map.on("load", () => {
    map.addSource("tracts", {
      type: "geojson",
      data: joinedFeatureCollection(),
      generateId: false,
      attribution: "U.S. Census Bureau, 2024 TIGER/Line Shapefiles.",
    });
    map.addLayer({
      id: "tract-fill",
      type: "fill",
      source: "tracts",
      paint: {"fill-color": fillExpression(activeMetricIndex), "fill-opacity": 0.72},
    });
    map.addLayer({
      id: "tract-line",
      type: "line",
      source: "tracts",
      paint: {"line-color": "#ffffff", "line-opacity": 0.62, "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.25, 10, 1.1]},
    });
    map.addLayer({
      id: "tract-selected-fill",
      type: "fill",
      source: "tracts",
      filter: selectionFilter(),
      paint: {"fill-color": "#d49a43", "fill-opacity": 0.36},
    });
    map.addLayer({
      id: "tract-selected",
      type: "line",
      source: "tracts",
      filter: selectionFilter(),
      paint: {
        "line-color": "#173f2e",
        "line-width": ["interpolate", ["linear"], ["zoom"], 4, 1.15, 7, 2.1, 11, 3.4],
        "line-opacity": 1,
      },
    });
    map.addLayer({
      id: "tract-hover",
      type: "line",
      source: "tracts",
      filter: hoverFilter(),
      paint: {"line-color": "#176f91", "line-width": 2.3, "line-opacity": 1},
    });
    map.fitBounds([[-90.42, 41.65], [-82.1, 48.35]], {padding: 28, duration: 0});
    selectBasemap(runtime.basemaps.default || "usgs_topo");
    map.on("mousemove", "tract-fill", showHover);
    map.on("mouseleave", "tract-fill", hideHover);
    map.on("click", "tract-fill", onTractClick);
    map.on("mouseenter", "tract-fill", () => { if (activeView === "explore") map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "tract-fill", () => { map.getCanvas().style.cursor = ""; });
    map.on("error", () => {
      if (currentBasemap !== "local_neutral" && !basemapFailureHandled) {
        basemapFailureHandled = true;
        selectBasemap("local_neutral", {
          failureMessage: "USGS map context is unavailable. Local neutral remains fully usable for tract exploration.",
        });
      }
    });
    requestAnimationFrame(() => {
      diagnostics.ready = true;
      diagnostics.mapReadyMs = Math.round((performance.now() - startedAt) * 10) / 10;
      byId("qa-map-ready").textContent = `${diagnostics.mapReadyMs.toLocaleString("en-US")} ms`;
      byId("loading-card").hidden = true;
      byId("runtime-status").textContent = "Ready";
      byId("runtime-status").className = "runtime-status ready";
      publishDiagnostics();
    });
  });
}

function installSyntheticTestApi() {
  if (bundle.data_mode !== "synthetic_validation") return;
  const auditActions = {
    Digit1: () => selectGeoids([bundle.audit_states.single_valid_geoid]),
    Digit2: () => selectGeoids([bundle.audit_states.model_warning_geoid]),
    Digit3: () => selectGeoids([bundle.audit_states.data_unavailable_geoid]),
    Digit4: () => selectGeoids(bundle.audit_states.multiple_geoids),
    Digit5: () => selectGeoids([bundle.audit_states.quality_context_geoid]),
    Digit0: clearSelection,
  };
  window.addEventListener("keydown", (event) => {
    if (!event.altKey || !event.shiftKey || !auditActions[event.code]) return;
    event.preventDefault();
    auditActions[event.code]();
  });
  window.__APP01_TEST_API__ = Object.freeze({
    auditStates: Object.freeze({...bundle.audit_states}),
    setMetric(metricKey) {
      const index = metrics.findIndex((metric) => metric.metric_key === metricKey);
      if (index < 0) throw new Error("APP01_TEST_METRIC_UNKNOWN");
      updateMetric(index);
    },
    selectGeoids(geoids) { selectGeoids(geoids); },
    clearSelection,
    async setView(view) { await setView(view); },
    setBasemap(key) { selectBasemap(key); },
    snapshot() { return {...diagnostics}; },
  });
}

async function initialize() {
  try {
    [runtime, bundle, geometry] = await Promise.all([
      fetchJson("/config/runtime.json"),
      fetchJson("/data/presentation.json"),
      fetchJson("/data/geometry.geojson"),
    ]);
    if (
      runtime.artifact_id !== "APP01_LOCAL_FIRST_RUNTIME_POLICY_V1"
      || bundle.artifact_id !== "APP01_MICHIGAN_PRESENTATION_BUNDLE_V1"
      || bundle.tract_count !== 3017
      || bundle.metric_count !== 16
      || !Array.isArray(bundle.rows)
      || !Array.isArray(bundle.metrics)
    ) throw new Error("APP01_BROWSER_BUNDLE_INVALID");
    metrics = bundle.metrics;
    bundle.rows.forEach((row) => rowByGeoid.set(row.geoid, row));
    if (rowByGeoid.size !== 3017) throw new Error("APP01_BROWSER_DUPLICATE_GEOID");
    diagnostics.dataMode = bundle.data_mode;
    diagnostics.featureCount = bundle.tract_count;
    diagnostics.metricCount = bundle.metric_count;
    diagnostics.activeMetric = metrics[0].metric_key;
    const badge = byId("data-mode-badge");
    badge.textContent = bundle.notice;
    badge.className = `data-mode-badge ${bundle.data_mode === "accepted_real" ? "real" : "synthetic"}`;
    installControls();
    updateMetricContext();
    updateQaGlobal();
    updateSelection();
    initializeMap();
    installSyntheticTestApi();
    publishDiagnostics();
  } catch (_error) {
    diagnostics.error = "APP01_BROWSER_RUNTIME_FAILED";
    byId("runtime-status").textContent = "Unable to start";
    byId("runtime-status").className = "runtime-status error";
    byId("loading-card").textContent = "APP-01 could not prepare the local map. Restart the launcher and review its plain-English diagnostic.";
    byId("map-message").textContent = "No accepted data has been shown.";
    byId("map-message").hidden = false;
    publishDiagnostics();
  }
}

initialize();
