from __future__ import annotations

import argparse
from hashlib import sha1
import json
from pathlib import Path
import shutil
from typing import Any, Iterable


VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"
GEOMETRY_RESOURCE = "michigan_2024_tracts.geojson"
PAGE_IDS = {
    "opportunity": "910adbf89e9910b23532",
    "evidence": "9cc13a91075a2420ffdc",
    "qa": "e974549db89d4df5bced",
}


def _id(page_key: str, visual_key: str) -> str:
    return sha1(f"pbi01:{page_key}:{visual_key}".encode("utf-8")).hexdigest()[:20]


def _literal(value: str) -> dict[str, Any]:
    return {"expr": {"Literal": {"Value": value}}}


def _fill(color: str) -> dict[str, Any]:
    return {"solid": {"color": _literal(f"'{color}'")}}


def _column(table: str, column: str, *, active: bool = False) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}},
        "queryRef": f"{table}.{column}",
        "nativeQueryRef": column,
    }
    if active:
        projection["active"] = True
    return projection


def _measure(table: str, measure: str) -> dict[str, Any]:
    return {
        "field": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": measure}},
        "queryRef": f"{table}.{measure}",
        "nativeQueryRef": measure,
    }


def _position(x: int, y: int, width: int, height: int, order: int) -> dict[str, Any]:
    return {"x": x, "y": y, "z": order * 1000, "height": height, "width": width, "tabOrder": order * 1000}


def _chrome(title: str | None = None, *, alt_text: str | None = None, padding: int = 8) -> dict[str, Any]:
    values: dict[str, Any] = {
        "background": [{"properties": {"show": _literal("true"), "color": _fill("#FFFFFF"), "transparency": _literal("0D")}}],
        "border": [{"properties": {"show": _literal("true"), "color": _fill("#D6DEE8"), "width": _literal("1D"), "radius": _literal("8D")}}],
        "padding": [{"properties": {side: _literal(f"{padding}D") for side in ("top", "bottom", "left", "right")}}],
    }
    if title:
        values["title"] = [{"properties": {
            "show": _literal("true"),
            "text": _literal(f"'{title}'"),
            "fontColor": _fill("#16324F"),
            "fontSize": _literal("12D"),
            "bold": _literal("true"),
            "titleWrap": _literal("true"),
        }}]
    if alt_text:
        values["general"] = [{"properties": {"altText": _literal(f"'{alt_text}'")}}]
    return values


def _visual(page_key: str, key: str, x: int, y: int, width: int, height: int, order: int, visual: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": VISUAL_SCHEMA,
        "name": _id(page_key, key),
        "position": _position(x, y, width, height, order),
        "visual": visual,
    }


def _textbox(page_key: str, key: str, text: str, x: int, y: int, width: int, height: int, order: int, *, size: int, color: str, bold: bool = False) -> dict[str, Any]:
    visual = {
        "visualType": "textbox",
        "objects": {
            "general": [{"properties": {"paragraphs": [{
                "textRuns": [{"value": text, "textStyle": {
                    "fontFamily": "Segoe UI Semibold" if bold else "Segoe UI",
                    "fontSize": f"{size}px",
                    "fontWeight": "bold" if bold else "normal",
                    "color": color,
                }}],
                "horizontalTextAlignment": "left",
            }]}}],
        },
        "visualContainerObjects": {
            "background": [{"properties": {"show": _literal("false")}}],
            "border": [{"properties": {"show": _literal("false")}}],
            "padding": [{"properties": {side: _literal("0D") for side in ("top", "bottom", "left", "right")}}],
        },
    }
    return _visual(page_key, key, x, y, width, height, order, visual)


def _card(page_key: str, key: str, measures: Iterable[str], x: int, y: int, width: int, height: int, order: int, *, title: str | None = None) -> dict[str, Any]:
    projections = [_measure("Report Measures", value) for value in measures]
    visual = {
        "visualType": "cardVisual",
        "query": {"queryState": {"Data": {"projections": projections}}},
        "objects": {"value": [{"properties": {
            "labelDisplayUnits": _literal("1D"),
        }, "selector": {"id": "default"}}]},
        "visualContainerObjects": _chrome(title, alt_text=title or "Summary measures"),
    }
    return _visual(page_key, key, x, y, width, height, order, visual)


def _slicer(
    page_key: str,
    key: str,
    table: str,
    column: str,
    title: str,
    x: int,
    y: int,
    width: int,
    height: int,
    order: int,
    *,
    mode: str = "Dropdown",
    selected: str | None = None,
) -> dict[str, Any]:
    objects: dict[str, Any] = {
        "data": [{"properties": {"mode": _literal(f"'{mode}'")}}],
        "header": [{"properties": {"show": _literal("true"), "text": _literal(f"'{title}'")}}],
    }
    if selected is not None:
        alias = "m"
        objects["general"] = [{"properties": {"filter": {"filter": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": table, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": column}}],
                "Values": [[{"Literal": {"Value": f"'{selected}'"}}]],
            }}}],
        }}}}]
    visual = {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [_column(table, column)]}}},
        "objects": objects,
        "visualContainerObjects": {
            "background": [{"properties": {"show": _literal("true"), "color": _fill("#FFFFFF"), "transparency": _literal("0D")}}],
            "border": [{"properties": {"show": _literal("true"), "color": _fill("#D6DEE8"), "width": _literal("1D"), "radius": _literal("8D")}}],
            "padding": [{"properties": {side: _literal("8D") for side in ("top", "bottom", "left", "right")}}],
        },
    }
    return _visual(page_key, key, x, y, width, height, order, visual)


def _table(page_key: str, key: str, fields: Iterable[tuple[str, str]], title: str, x: int, y: int, width: int, height: int, order: int) -> dict[str, Any]:
    visual = {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": [_column(table, column) for table, column in fields]}}},
        "objects": {"columnHeaders": [{"properties": {
            "columnAdjustment": _literal("'growToFit'"),
            "autoSizeColumnWidth": _literal("true"),
            "wordWrap": _literal("true"),
        }}]},
        "visualContainerObjects": _chrome(title, alt_text=title),
    }
    return _visual(page_key, key, x, y, width, height, order, visual)


def _bar(page_key: str, key: str, category: tuple[str, str], measure: str, title: str, x: int, y: int, width: int, height: int, order: int) -> dict[str, Any]:
    category_projection = _column(*category, active=True)
    value_projection = _measure("Report Measures", measure)
    visual = {
        "visualType": "clusteredBarChart",
        "query": {
            "queryState": {
                "Category": {"projections": [category_projection]},
                "Y": {"projections": [value_projection]},
            },
            "sortDefinition": {"sort": [{"field": value_projection["field"], "direction": "Descending"}], "isDefaultSort": False},
        },
        "objects": {
            "dataPoint": [{"properties": {"defaultColor": _fill("#2D7D46")}}],
            "labels": [{"properties": {"show": _literal("true"), "labelPosition": _literal("'OutsideEnd'")}}],
        },
        "visualContainerObjects": _chrome(title, alt_text=title),
    }
    return _visual(page_key, key, x, y, width, height, order, visual)


def _gradient(measure: str, low: str = "#E3F2E8", high: str = "#216E39") -> dict[str, Any]:
    return {
        "solid": {"color": {"expr": {"FillRule": {
            "Input": {"Measure": {"Expression": {"SourceRef": {"Entity": "Report Measures"}}, "Property": measure}},
            "FillRule": {"linearGradient2": {
                "min": {"color": {"Literal": {"Value": f"'{low}'"}}},
                "max": {"color": {"Literal": {"Value": f"'{high}'"}}},
                "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'noColor'"}}},
            }},
        }}}},
    }


TRACT_TOOLTIP_MEASURES = [
    "Customer Fit", "Customer Fit Statewide Rank", "Customer Fit Percentile",
    "Household Opportunity", "Modeled Target Mass", "Modeled Target Mass Statewide Rank",
    "Modeled Target Mass Percentile", "Member Count 3 Mile", "Member Count 5 Mile",
    "Member Count 7 Mile", "Support Completeness 3 Mile", "Support Completeness 5 Mile",
    "Support Completeness 7 Mile", "Support Truncation State", "Computability Detail",
    "QA / Missingness Detail",
]


def _tract_map(page_key: str, key: str, title: str, x: int, y: int, width: int, height: int, order: int, *, color_measure: str = "Selected Metric Value") -> dict[str, Any]:
    query_state = {
        "Category": {"projections": [_column("Michigan Tracts", "GEOID", active=True)]},
        "Value": {"projections": [_measure("Report Measures", color_measure)]},
        "Tooltips": {"projections": [_measure("Report Measures", name) for name in TRACT_TOOLTIP_MEASURES]},
    }
    shape_resource = {
        "geoJson": {
            "type": _literal("'file_upload'"),
            "name": _literal(f"'{GEOMETRY_RESOURCE}'"),
            "content": {"expr": {"ResourcePackageItem": {
                "PackageName": "RegisteredResources",
                "PackageType": 1,
                "ItemName": GEOMETRY_RESOURCE,
            }}},
        }
    }
    visual = {
        "visualType": "shapeMap",
        "query": {"queryState": query_state},
        "objects": {
            "shape": [{"properties": {
                "datasourceType": _literal("'file_upload'"),
                "map": shape_resource,
                "projectionEnum": _literal("'equirectangular'"),
            }}],
            "dataPoint": [
                {"properties": {
                    "defaultColor": _fill("#DCE7DF"),
                    "showAllDataPoints": _literal("true"),
                }},
                {"properties": {"fill": _gradient(color_measure)}, "selector": {"data": [{"dataViewWildcard": {"matchingOption": 0}}]}},
            ],
            "zoom": [{"properties": {
                "autoZoom": _literal("true"),
                "selectionZoom": _literal("false"),
                "manualZoom": _literal("true"),
            }}],
        },
        "visualContainerObjects": _chrome(title, alt_text=f"Michigan census tract choropleth: {title}"),
        "drillFilterOtherVisuals": True,
    }
    return _visual(page_key, key, x, y, width, height, order, visual)


def _seed_map(page_key: str, key: str, x: int, y: int, width: int, height: int, order: int) -> dict[str, Any]:
    query_state = {
        "Y": {"projections": [_column("Seed Context", "Latitude")]},
        "X": {"projections": [_column("Seed Context", "Longitude")]},
        "Series": {"projections": [_column("Seed Context", "Support Truncation")]},
        "Tooltips": {"projections": [_measure("Report Measures", name) for name in (
            "Mean Isolated Sales", "Frozen MODEL-12 Prediction", "Successor OOF Prediction",
            "Successor OOF Absolute Log Error", "Seed Household Opportunity", "Seed Customer Fit",
            "Seed Modeled Target Mass", "Seed Support State", "Seed QA Status",
        )]},
    }
    visual = {
        "visualType": "scatterChart",
        "query": {"queryState": query_state},
        "objects": {
            "bubbles": [{"properties": {
                "bubbleSize": _literal("5L"),
                "markerRangeType": _literal("'auto'"),
                "preventOverflow": _literal("true"),
                "markerShape": _literal("'circle'"),
            }}],
            "markers": [{"properties": {
                "transparency": _literal("5D"),
                "borderShow": _literal("true"),
                "borderWidth": _literal("1D"),
                "borderColor": _fill("#FFFFFF"),
            }}],
            "categoryAxis": [{"properties": {
                "show": _literal("true"),
                "start": _literal("-91D"),
                "end": _literal("-82D"),
                "showAxisTitle": _literal("true"),
                "titleText": _literal("'Longitude'"),
            }}],
            "valueAxis": [{"properties": {
                "show": _literal("true"),
                "start": _literal("41D"),
                "end": _literal("49D"),
                "showAxisTitle": _literal("true"),
                "titleText": _literal("'Latitude'"),
            }}],
        },
        "visualContainerObjects": _chrome("Accepted Michigan evidence coordinates", alt_text="Protected-local Michigan seed evidence coordinate plot"),
        "drillFilterOtherVisuals": True,
    }
    return _visual(page_key, key, x, y, width, height, order, visual)


def _page(display_name: str, page_id: str) -> dict[str, Any]:
    return {"$schema": PAGE_SCHEMA, "name": page_id, "displayName": display_name, "displayOption": "FitToPage", "height": 1080, "width": 1920}


def _opportunity_visuals() -> list[dict[str, Any]]:
    p = "opportunity"
    visuals = [
        _textbox(p, "title", "Sprouts Customer Geography — Michigan", 40, 20, 1100, 52, 1, size=30, color="#16324F", bold=True),
        _textbox(p, "subtitle", "Michigan Opportunity Explorer · Public-data proxy decision support, not final site selection or Sprouts’ proprietary model.", 40, 76, 1240, 36, 2, size=15, color="#53657A"),
        _slicer(p, "metric", "Metric Selector", "Metric", "Map metric", 1340, 24, 540, 80, 3, selected="Customer Fit"),
        _card(p, "tract-cards", ["Total Tracts", "Computable Tracts", "Noncomputable Tracts", "Support-Truncated Tracts"], 40, 120, 1280, 112, 4),
        _tract_map(p, "tract-map", "Statewide tract opportunity", 40, 248, 1280, 740, 5),
    ]
    slicers = [
        ("cf-pct", "Customer Fit Percentile", "Customer Fit percentile", "Between"),
        ("cf-rank", "Customer Fit Statewide Rank", "Customer Fit rank", "Between"),
        ("mt-pct", "Modeled Target Mass Percentile", "Modeled target percentile", "Between"),
        ("mt-rank", "Modeled Target Mass Statewide Rank", "Modeled target rank", "Between"),
        ("hh", "Household Opportunity", "Household opportunity", "Between"),
        ("compute", "Computability Status", "Computability", "Dropdown"),
        ("trunc", "Any Support Truncation", "Support truncation", "Dropdown"),
        ("qa", "QA / Missingness Status", "QA / missingness", "Dropdown"),
    ]
    for index, (key, column, title, mode) in enumerate(slicers):
        row, col = divmod(index, 2)
        visuals.append(_slicer(p, key, "Michigan Tracts", column, title, 1340 + col * 276, 120 + row * 88, 264, 80, 6 + index, mode=mode))
    detail_fields = [("Michigan Tracts", name) for name in (
        "GEOID", "Customer Fit", "Customer Fit Statewide Rank", "Customer Fit Percentile",
        "Household Opportunity", "Modeled Target Mass", "Modeled Target Mass Statewide Rank",
        "Modeled Target Mass Percentile", "Member Count 3 Mile", "Member Count 5 Mile",
        "Member Count 7 Mile", "Support Completeness 3 Mile", "Support Completeness 5 Mile",
        "Support Completeness 7 Mile", "Any Support Truncation", "Computability Status",
        "QA / Missingness Status",
    )]
    visuals.append(_table(p, "tract-detail", detail_fields, "Tract detail", 1340, 480, 540, 508, 14))
    visuals.append(_textbox(p, "footer", "Customer Fit, Household Opportunity, and Modeled Target Mass are distinct MODEL-13 outputs. Select a tract or use the filters to inspect details.", 40, 1002, 1840, 48, 15, size=14, color="#53657A"))
    return visuals


def _evidence_visuals() -> list[dict[str, Any]]:
    p = "evidence"
    fields = [("Seed Context", name) for name in (
        "Mean Isolated Sales", "Frozen MODEL-12 Prediction", "Successor OOF Prediction",
        "Successor OOF Absolute Log Error", "Household Opportunity", "Customer Fit",
        "Modeled Target Mass", "Support Truncation", "QA Status",
    )]
    return [
        _textbox(p, "title", "Sprouts Evidence Context", 40, 20, 1000, 52, 1, size=30, color="#16324F", bold=True),
        _textbox(p, "subtitle", "Accepted Michigan physical-location evidence shown locally. Coordinates, identities, sales, predictions, and rendered evidence remain protected-local.", 40, 76, 1800, 36, 2, size=15, color="#53657A"),
        _seed_map(p, "seed-map", 40, 130, 1120, 760, 3),
        _card(p, "seed-cards", ["Evidence Locations", "Mean Isolated Sales", "Successor OOF Absolute Log Error", "Seed Customer Fit"], 1180, 130, 700, 120, 4),
        _slicer(p, "seed-qa", "Seed Context", "QA Status", "QA status", 1180, 270, 340, 80, 5),
        _slicer(p, "seed-support", "Seed Context", "Support Truncation", "Support truncation", 1540, 270, 340, 80, 6),
        _table(p, "seed-detail", fields, "Evidence detail (local only)", 1180, 370, 700, 520, 7),
        _textbox(p, "note", "Evidence points support interpretation; they are not automatic ground truth. The local coordinate view avoids external map-service or organizational sign-in dependency and uses only the accepted protected-local MODEL-13 seed-context output.", 40, 920, 1840, 64, 8, size=15, color="#53657A"),
    ]


def _qa_visuals() -> list[dict[str, Any]]:
    p = "qa"
    qa_fields = [("Michigan Tracts", name) for name in (
        "GEOID", "Computability Status", "QA / Missingness Status", "Any Support Truncation",
        "Support Truncation 3 Mile", "Support Truncation 5 Mile", "Support Truncation 7 Mile",
        "Support Completeness 3 Mile", "Support Completeness 5 Mile", "Support Completeness 7 Mile",
        "Member Count 3 Mile", "Member Count 5 Mile", "Member Count 7 Mile",
    )]
    return [
        _textbox(p, "title", "QA & Coverage", 40, 20, 900, 52, 1, size=30, color="#16324F", bold=True),
        _textbox(p, "boundary-note", "Boundary support truncation is descriptive. Unsupported out-of-state or Canadian demographics were not manufactured.", 40, 78, 1840, 48, 2, size=17, color="#8A3B12", bold=True),
        _card(p, "qa-cards", ["Total Tracts", "Noncomputable Tracts", "Support-Truncated Tracts"], 40, 140, 800, 112, 3),
        _slicer(p, "qa-compute", "Michigan Tracts", "Computability Status", "Computability", 880, 140, 300, 80, 4),
        _slicer(p, "qa-trunc", "Michigan Tracts", "Any Support Truncation", "Support truncation", 1200, 140, 300, 80, 5),
        _slicer(p, "qa-status", "Michigan Tracts", "QA / Missingness Status", "QA / missingness", 1520, 140, 360, 80, 6),
        _bar(p, "qa-bar", ("Michigan Tracts", "QA / Missingness Status"), "Total Tracts", "Tracts by QA / missingness category", 40, 280, 700, 320, 7),
        _tract_map(p, "qa-map", "Geographic support completeness", 760, 280, 1120, 320, 8, color_measure="Support Completeness 7 Mile"),
        _table(p, "qa-table", qa_fields, "Tract-level QA and support diagnostics", 40, 620, 1840, 390, 9),
        _textbox(p, "footer", "Noncomputable and support-truncated tracts remain explicit; missing inputs are never converted to favorable or neutral values.", 40, 1020, 1840, 40, 10, size=14, color="#53657A"),
    ]


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_report(repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    report = root / "powerbi" / "pbi01" / "project" / "MICustomerGeography.Report"
    pages_root = report / "definition" / "pages"
    if report.name != "MICustomerGeography.Report" or root not in report.resolve().parents:
        raise ValueError("refusing to write outside the governed PBI-01 report")
    if pages_root.exists():
        shutil.rmtree(pages_root)
    resources = report / "StaticResources" / "RegisteredResources"
    resources.mkdir(parents=True, exist_ok=True)
    geometry = root / "powerbi" / "pbi01" / "presentation" / GEOMETRY_RESOURCE
    if not geometry.is_file():
        raise FileNotFoundError("presentation geometry must be generated before the report")
    shutil.copyfile(geometry, resources / GEOMETRY_RESOURCE)

    definitions = [
        (PAGE_IDS["opportunity"], "Michigan Opportunity Explorer", _opportunity_visuals()),
        (PAGE_IDS["evidence"], "Sprouts Evidence Context", _evidence_visuals()),
        (PAGE_IDS["qa"], "QA & Coverage", _qa_visuals()),
    ]
    for page_id, display_name, visuals in definitions:
        page_dir = pages_root / page_id
        _write_json(page_dir / "page.json", _page(display_name, page_id))
        for visual in visuals:
            _write_json(page_dir / "visuals" / visual["name"] / "visual.json", visual)
    _write_json(pages_root / "pages.json", {
        "$schema": PAGES_SCHEMA,
        "pageOrder": [page_id for page_id, _name, _visuals in definitions],
        "activePageName": PAGE_IDS["opportunity"],
    })

    report_json_path = report / "definition" / "report.json"
    report_json = json.loads(report_json_path.read_text(encoding="utf-8"))
    packages = [value for value in report_json.get("resourcePackages", []) if value.get("name") != "RegisteredResources"]
    packages.append({
        "name": "RegisteredResources",
        "type": "RegisteredResources",
        "items": [{"name": GEOMETRY_RESOURCE, "path": GEOMETRY_RESOURCE, "type": "ShapeMap"}],
    })
    report_json["resourcePackages"] = packages
    report_json.setdefault("settings", {})["exportDataMode"] = "AllowSummarized"
    report_json["settings"]["defaultFilterActionIsDataFilter"] = True
    report_json["settings"]["useEnhancedTooltips"] = True
    _write_json(report_json_path, report_json)
    return {
        "state": "READY",
        "page_count": 3,
        "visual_count": sum(len(visuals) for _page_id, _name, visuals in definitions),
        "built_in_visuals_only": True,
        "protected_rows_embedded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic PBI-01 PBIR report definitions")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(build_report(args.repository_root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
