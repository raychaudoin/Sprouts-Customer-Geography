import {Map as MapLibreMap, NavigationControl, setWorkerUrl} from "/vendor/maplibre-gl/maplibre-gl.mjs";

setWorkerUrl("/vendor/maplibre-gl/maplibre-gl-worker.mjs");

const startedAt = performance.now();
const colors = ["#f3edc8", "#aed2b3", "#5d9c79", "#24634d", "#123b31"];
const descriptiveColors = ["#edf1d1", "#bad5af", "#72a982", "#36755f", "#143f39"];
const noDataColor = "#d8d7d0";
const selectedGeoids = new Set();
const externalRequests = [];
let metrics;
let runtime;
let bundle;
let rowByGeoid;
let map;
let activeMetricIndex = 0;
let lastMetricSwitchMs = null;
let lastSelectionMs = null;
let mapReadyMs = null;
let basemapFailure = false;

const diagnostics = {
  ready: false,
  featureCount: 0,
  metricCount: 0,
  mapReadyMs: null,
  lastMetricSwitchMs: null,
  lastSelectionMs: null,
  externalRequestCount: 0,
  externalHosts: [],
  canaryHits: 0,
  selectionCount: 0,
  basemap: "usgs_topo",
  dataMode: "synthetic_architecture_evidence",
  error: null,
};
window.__ARCH01_DIAGNOSTICS__ = diagnostics;

const byId = (id) => document.getElementById(id);

function publishDiagnostics() {
  const root = document.documentElement.dataset;
  root.arch01Ready = String(diagnostics.ready);
  root.arch01FeatureCount = String(diagnostics.featureCount);
  root.arch01MetricCount = String(diagnostics.metricCount);
  root.arch01MapReadyMs = diagnostics.mapReadyMs === null ? "" : String(diagnostics.mapReadyMs);
  root.arch01MetricSwitchMs = diagnostics.lastMetricSwitchMs === null ? "" : String(diagnostics.lastMetricSwitchMs);
  root.arch01SelectionMs = diagnostics.lastSelectionMs === null ? "" : String(diagnostics.lastSelectionMs);
  root.arch01ExternalRequestCount = String(diagnostics.externalRequestCount);
  root.arch01ExternalHosts = diagnostics.externalHosts.join(",");
  root.arch01CanaryHits = String(diagnostics.canaryHits);
  root.arch01SelectionCount = String(diagnostics.selectionCount);
  root.arch01Basemap = diagnostics.basemap;
}

publishDiagnostics();

function requestPolicy(url) {
  const resolved = new URL(url, window.location.href);
  if (resolved.origin === window.location.origin) return {url: resolved.href};
  if (resolved.protocol !== "https:" || resolved.hostname !== "basemap.nationalmap.gov") {
    throw new Error(`External request blocked by ARCH-01 policy: ${resolved.hostname}`);
  }
  if (resolved.href.includes(bundle?.canary?.value ?? "ARCH01_CANARY_NOT_LOADED")) {
    diagnostics.canaryHits += 1;
    byId("qa-canary").textContent = String(diagnostics.canaryHits);
    publishDiagnostics();
    throw new Error("Synthetic protected-data canary blocked from external transmission");
  }
  externalRequests.push({method: "GET", url: resolved.href, body: null, headers: {}});
  diagnostics.externalRequestCount = externalRequests.length;
  diagnostics.externalHosts = [...new Set(externalRequests.map((entry) => new URL(entry.url).hostname))];
  byId("qa-egress").textContent = diagnostics.externalHosts.join(", ") || "None";
  byId("qa-requests").textContent = String(diagnostics.externalRequestCount);
  publishDiagnostics();
  return {url: resolved.href};
}

function baseStyle() {
  return {
    version: 8,
    sources: {},
    layers: [{id: "neutral-background", type: "background", paint: {"background-color": "#e8ebe6"}}],
  };
}

function basemapDefinition(key) {
  const config = runtime.basemaps[key];
  if (!config?.tile_url) return null;
  return {
    type: "raster",
    tiles: [config.tile_url],
    tileSize: 256,
    maxzoom: config.maxzoom,
    attribution: config.attribution,
  };
}

function addBasemap(key) {
  if (map.getLayer("basemap-raster")) map.removeLayer("basemap-raster");
  if (map.getSource("basemap")) map.removeSource("basemap");
  const definition = basemapDefinition(key);
  if (definition) {
    map.addSource("basemap", definition);
    map.addLayer({id: "basemap-raster", type: "raster", source: "basemap", paint: {"raster-opacity": 0.92}}, "tract-fill");
  }
  diagnostics.basemap = key;
  publishDiagnostics();
  basemapFailure = false;
  byId("map-message").hidden = true;
}

function fillExpression(index) {
  const metric = metrics[index];
  const domain = bundle.domains[metric.metric_key];
  const range = domain.maximum - domain.minimum;
  const stops = [0, .25, .5, .75, 1].map((portion) => domain.minimum + range * portion);
  const palette = metric.palette === "descriptive_sequential" ? descriptiveColors : colors;
  const interpolation = ["interpolate", ["linear"], ["get", `m${index}`]];
  stops.forEach((stop, stopIndex) => interpolation.push(stop, palette[stopIndex]));
  return ["case", ["has", `m${index}`], interpolation, noDataColor];
}

function selectionFilter() {
  if (!selectedGeoids.size) return ["==", ["get", "GEOID"], ""];
  return ["in", ["get", "GEOID"], ["literal", [...selectedGeoids]]];
}

function formatValue(value, metric) {
  if (value === null || value === undefined) return "No Data / Unavailable";
  if (metric.format_policy === "currency_0") return new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", maximumFractionDigits: 0}).format(value);
  if (metric.format_policy === "count_0") return new Intl.NumberFormat("en-US", {maximumFractionDigits: 0}).format(value);
  if (metric.format_policy === "decimal_2") return Number(value).toFixed(2);
  return `${Number(value).toFixed(1)}${metric.format_policy === "percent_1" ? "%" : ""}`;
}

function updateLegend() {
  const metric = metrics[activeMetricIndex];
  const domain = bundle.domains[metric.metric_key];
  const interval = (domain.maximum - domain.minimum) / 4;
  const values = [domain.minimum, domain.minimum + interval, domain.minimum + 2 * interval, domain.minimum + 3 * interval, domain.maximum];
  byId("legend-title").textContent = metric.display_name;
  byId("legend-unit").textContent = metric.unit;
  byId("legend-ramp").style.background = `linear-gradient(90deg, ${(metric.palette === "descriptive_sequential" ? descriptiveColors : colors).join(", ")})`;
  byId("legend-labels").replaceChildren(...values.map((value, index) => {
    const span = document.createElement("span");
    const formatted = formatValue(value, metric);
    span.textContent = index === 0 ? `≤ ${formatted}` : index === values.length - 1 ? `≥ ${formatted}` : formatted;
    return span;
  }));
}

function updateMetricContext() {
  const metric = metrics[activeMetricIndex];
  const domain = bundle.domains[metric.metric_key];
  byId("metric-unit").textContent = metric.unit;
  byId("metric-family").textContent = metric.family.replaceAll("_", " ");
  byId("metric-definition").textContent = metric.definition;
  byId("metric-source").textContent = metric.source_label;
  byId("metric-domain").textContent = metric.scale_policy === "fixed_0_100"
    ? "Fixed 0–100"
    : `Statewide valid-only P02–P98: ${formatValue(domain.minimum, metric)} to ${formatValue(domain.maximum, metric)}`;
  updateLegend();
}

function warningItems(row, metricIndex) {
  const items = [];
  if (row.statuses[metricIndex] !== "valid") items.push(`Status: ${row.statuses[metricIndex].replaceAll("_", " ")}. Missingness remains explicit and is not converted to zero.`);
  if (row.status_details[metricIndex]) items.push(`Detail: ${row.status_details[metricIndex].replaceAll("_", " ")}.`);
  if (row.support_truncation && metrics[metricIndex].input_binding.logical_input === "model13_tract_output") items.push("Synthetic five-mile support is marked truncated for this tract; interpret model-shaped evidence cautiously.");
  items.push("Architecture evidence uses deterministic synthetic values, not accepted analytical observations.");
  return items;
}

function updateSelectionPanel(measureInteraction = false) {
  const began = performance.now();
  const content = byId("selection-content");
  const metric = metrics[activeMetricIndex];
  const geoids = [...selectedGeoids].sort();
  byId("selection-count").textContent = String(geoids.length);
  byId("clear-selection").disabled = !geoids.length;
  diagnostics.selectionCount = geoids.length;
  if (!geoids.length) {
    content.className = "empty-state";
    content.textContent = "Select a tract. Hold Shift, Ctrl, or Command while selecting to compare several.";
  } else if (geoids.length === 1) {
    const row = rowByGeoid.get(geoids[0]);
    const moe = row.moes[activeMetricIndex];
    content.className = "";
    content.innerHTML = `<h3>Tract ${row.geoid}</h3><div class="metric-value"></div><p class="selection-unit"></p><p class="selection-moe"></p><ul class="warning-list"></ul>`;
    content.querySelector(".metric-value").textContent = formatValue(row.values[activeMetricIndex], metric);
    content.querySelector(".selection-unit").textContent = metric.unit;
    content.querySelector(".selection-moe").textContent = moe === null ? "Margin of error: not applicable to this synthetic model-shaped value" : `Synthetic margin of error: ±${formatValue(moe, metric)}`;
    content.querySelector(".warning-list").replaceChildren(...warningItems(row, activeMetricIndex).map((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      return li;
    }));
  } else {
    const rows = geoids.map((geoid) => rowByGeoid.get(geoid));
    const valid = rows.map((row) => row.values[activeMetricIndex]).filter((value) => value !== null);
    content.className = "";
    content.innerHTML = `<h3>${geoids.length} tracts selected</h3><p class="selection-summary"></p><ul class="selection-list"></ul>`;
    content.querySelector(".selection-summary").textContent = valid.length
      ? `${valid.length} available · range ${formatValue(Math.min(...valid), metric)} to ${formatValue(Math.max(...valid), metric)}`
      : "No selected tract has an available value for this metric.";
    content.querySelector(".selection-list").replaceChildren(...geoids.slice(0, 40).map((geoid) => {
      const li = document.createElement("li");
      li.textContent = `${geoid}: ${formatValue(rowByGeoid.get(geoid).values[activeMetricIndex], metric)}`;
      return li;
    }));
  }
  if (measureInteraction) {
    requestAnimationFrame(() => {
      lastSelectionMs = performance.now() - began;
      diagnostics.lastSelectionMs = Number(lastSelectionMs.toFixed(3));
      byId("qa-selection").textContent = `${diagnostics.lastSelectionMs.toFixed(1)} ms`;
      publishDiagnostics();
    });
  }
  publishDiagnostics();
}

function selectFeature(event) {
  const feature = event.features?.[0];
  if (!feature) return;
  const geoid = feature.properties.GEOID;
  const additive = byId("additive-mode").checked || event.originalEvent.shiftKey || event.originalEvent.ctrlKey || event.originalEvent.metaKey;
  if (!additive) selectedGeoids.clear();
  if (additive && selectedGeoids.has(geoid)) selectedGeoids.delete(geoid);
  else selectedGeoids.add(geoid);
  map.setFilter("tract-selected", selectionFilter());
  updateSelectionPanel(true);
}

function setMetric(index) {
  const began = performance.now();
  activeMetricIndex = index;
  if (map?.getLayer("tract-fill")) map.setPaintProperty("tract-fill", "fill-color", fillExpression(index));
  updateMetricContext();
  updateSelectionPanel();
  requestAnimationFrame(() => {
    lastMetricSwitchMs = performance.now() - began;
    diagnostics.lastMetricSwitchMs = Number(lastMetricSwitchMs.toFixed(3));
    byId("qa-switch").textContent = `${diagnostics.lastMetricSwitchMs.toFixed(1)} ms`;
    publishDiagnostics();
  });
}

function reconcileInputs(geometry) {
  if (bundle.tract_count !== 3017 || bundle.rows.length !== 3017 || geometry.features.length !== 3017) throw new Error("Expected exactly 3,017 presentation rows and geometry features");
  if (bundle.metric_count !== 16 || metrics.length !== 16) throw new Error("Expected exactly 16 presentation metrics");
  if (bundle.metric_keys.some((key, index) => key !== metrics[index].metric_key)) throw new Error("Presentation bundle and metric catalog order differ");
  rowByGeoid = new Map(bundle.rows.map((row) => [row.geoid, row]));
  const geometryGeoids = new Set();
  geometry.features.forEach((feature) => {
    const geoid = feature.properties?.GEOID;
    if (!geoid || geometryGeoids.has(geoid) || !rowByGeoid.has(geoid)) throw new Error(`Unreconciled or duplicate geometry GEOID: ${geoid ?? "missing"}`);
    geometryGeoids.add(geoid);
    const row = rowByGeoid.get(geoid);
    row.values.forEach((value, index) => { if (value !== null) feature.properties[`m${index}`] = value; });
  });
  if (geometryGeoids.size !== rowByGeoid.size) throw new Error("Presentation and geometry key inventories differ");
  diagnostics.featureCount = geometry.features.length;
  diagnostics.metricCount = metrics.length;
  return geometry;
}

function populateControls() {
  const metricSelect = byId("metric-select");
  metricSelect.replaceChildren(...metrics.map((metric, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `${metric.sort_order}. ${metric.display_name}`;
    return option;
  }));
  metricSelect.disabled = false;
  byId("basemap-select").disabled = false;
  metricSelect.addEventListener("change", (event) => setMetric(Number(event.target.value)));
  byId("basemap-select").addEventListener("change", (event) => addBasemap(event.target.value));
  byId("clear-selection").addEventListener("click", () => {
    selectedGeoids.clear();
    map.setFilter("tract-selected", selectionFilter());
    updateSelectionPanel(true);
  });
}

function showFailure(error) {
  diagnostics.error = String(error.message ?? error);
  byId("loading-card").hidden = true;
  byId("runtime-state").textContent = "Failed closed";
  byId("runtime-state").className = "status-dot error";
  byId("map-message").textContent = `Local input validation failed: ${diagnostics.error}`;
  byId("map-message").hidden = false;
  console.error(error);
}

function publishMapView() {
  const center = map.getCenter();
  document.documentElement.dataset.arch01Zoom = map.getZoom().toFixed(3);
  document.documentElement.dataset.arch01Center = `${center.lng.toFixed(5)},${center.lat.toFixed(5)}`;
}

async function initialize() {
  const [catalogResponse, runtimeResponse, bundleResponse, geometryResponse] = await Promise.all([
    fetch("/config/metrics.json", {cache: "no-store"}),
    fetch("/config/runtime.json", {cache: "no-store"}),
    fetch("/data/presentation.json", {cache: "no-store"}),
    fetch("/data/geometry.geojson", {cache: "no-store"}),
  ]);
  if (![catalogResponse, runtimeResponse, bundleResponse, geometryResponse].every((response) => response.ok)) throw new Error("One or more allowlisted local inputs could not be loaded");
  const [catalog, loadedRuntime, loadedBundle, geometry] = await Promise.all([
    catalogResponse.json(), runtimeResponse.json(), bundleResponse.json(), geometryResponse.json(),
  ]);
  metrics = catalog.metrics;
  runtime = loadedRuntime;
  bundle = loadedBundle;
  if (bundle.data_mode !== "synthetic_architecture_evidence" || bundle.canary.external_transmission_permitted !== false) throw new Error("Synthetic evidence classification or canary policy is invalid");
  const reconciledGeometry = reconcileInputs(geometry);
  populateControls();
  updateMetricContext();

  map = new MapLibreMap({
    container: "map",
    style: baseStyle(),
    center: [-85.45, 44.35],
    zoom: 5.7,
    minZoom: 4.7,
    maxZoom: 16,
    maxBounds: [[-91.5, 40.4], [-80.0, 48.7]],
    attributionControl: true,
    transformRequest: requestPolicy,
    renderWorldCopies: false,
  });
  map.on("moveend", publishMapView);
  map.on("zoomend", publishMapView);
  map.addControl(new NavigationControl({showCompass: false}), "top-right");
  map.on("load", () => {
    map.addSource("tracts", {type: "geojson", data: reconciledGeometry, promoteId: "GEOID", tolerance: 0});
    map.addLayer({
      id: "tract-fill", type: "fill", source: "tracts",
      paint: {"fill-color": fillExpression(activeMetricIndex), "fill-opacity": 0.69, "fill-outline-color": "rgba(42,55,48,.24)"},
    });
    map.addLayer({
      id: "tract-selected", type: "line", source: "tracts", filter: selectionFilter(),
      paint: {"line-color": "#f07d24", "line-width": 3.1, "line-opacity": 1},
    });
    addBasemap(runtime.basemaps.default);
    publishMapView();
    map.on("click", "tract-fill", selectFeature);
    map.on("mouseenter", "tract-fill", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "tract-fill", () => { map.getCanvas().style.cursor = ""; });
    map.once("idle", () => {
      mapReadyMs = performance.now() - startedAt;
      diagnostics.mapReadyMs = Number(mapReadyMs.toFixed(3));
      diagnostics.ready = true;
      publishDiagnostics();
      byId("loading-card").hidden = true;
      byId("runtime-state").textContent = "Ready";
      byId("runtime-state").className = "status-dot ready";
      byId("qa-tracts").textContent = "3,017 / 3,017";
      byId("qa-metrics").textContent = "16 / 16";
      byId("qa-ready").textContent = `${Math.round(mapReadyMs)} ms`;
    });
  });
  map.on("error", (event) => {
    const message = String(event.error?.message ?? event.error ?? "Map resource error");
    if (diagnostics.basemap !== "local_neutral" && /tile|raster|network|fetch|request/i.test(message)) {
      basemapFailure = true;
      byId("map-message").textContent = "External basemap unavailable. Tract interaction remains local; choose Local neutral for a network-free view.";
      byId("map-message").hidden = false;
    }
  });
}

initialize().catch(showFailure);
