from __future__ import annotations

import argparse
from hashlib import sha1
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Iterable


REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from scripts.pbi01.build_report import (  # noqa: E402
    GEOMETRY_RESOURCE,
    PAGE_SCHEMA,
    PAGES_SCHEMA,
    _chrome,
    _column,
    _evidence_visuals,
    _fill,
    _literal,
    _measure,
    _position,
    _slicer,
    _table,
    _textbox,
    _visual,
    _write_json,
    build_report as build_pbi01_report,
)


VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"
PAGE_IDS = {
    "opportunity": "910adbf89e9910b23532",
    "evidence": "9cc13a91075a2420ffdc",
    "qa": "e974549db89d4df5bced",
    "tooltip": sha1(b"pbi02:page:tract-tooltip").hexdigest()[:20],
}
PALETTE = ("#E5F2F0", "#B9DED8", "#7FC4BB", "#3E9B91", "#12685F")
NEUTRAL = "#D7DEE4"


def _id(page_key: str, visual_key: str) -> str:
    return sha1(f"pbi02:{page_key}:{visual_key}".encode("utf-8")).hexdigest()[:20]


def _container(
    *,
    title: str | None = None,
    alt_text: str | None = None,
    background: str = "#FFFFFF",
    border: bool = True,
    padding: int = 8,
) -> dict[str, Any]:
    result = _chrome(title, alt_text=alt_text, padding=padding)
    result["background"] = [
        {
            "properties": {
                "show": _literal("true"),
                "color": _fill(background),
                "transparency": _literal("0D"),
            }
        }
    ]
    if not border:
        result["border"] = [{"properties": {"show": _literal("false")}}]
    return result


def _measure_card(
    page_key: str,
    key: str,
    measures: Iterable[str],
    x: int,
    y: int,
    width: int,
    height: int,
    order: int,
    *,
    title: str,
    alt_text: str | None = None,
    font_size: int = 11,
    background: str = "#FFFFFF",
    show_labels: bool = True,
) -> dict[str, Any]:
    visual = {
        "visualType": "cardVisual",
        "query": {"queryState": {"Data": {"projections": [_measure("Report Measures", name) for name in measures]}}},
        "objects": {
            "value": [
                {
                    "properties": {
                        "fontSize": _literal(f"{font_size}D"),
                        "labelDisplayUnits": _literal("1D"),
                    },
                    "selector": {"id": "default"},
                }
            ],
            "label": [
                {
                    "properties": {
                        "show": _literal("true" if show_labels else "false"),
                        "fontSize": _literal("9D"),
                        "position": _literal("'aboveValue'"),
                    },
                    "selector": {"id": "default"},
                }
            ],
        },
        "visualContainerObjects": _container(
            title=title,
            alt_text=alt_text or title,
            background=background,
            padding=8,
        ),
    }
    return {
        "$schema": VISUAL_SCHEMA,
        "name": _id(page_key, key),
        "position": _position(x, y, width, height, order),
        "visual": visual,
    }


def _swatch(page_key: str, key: str, color: str, x: int, y: int, width: int, height: int, order: int) -> dict[str, Any]:
    visual = {
        "visualType": "textbox",
        "objects": {
            "general": [
                {
                    "properties": {
                        "paragraphs": [
                            {
                                "textRuns": [{"value": "", "textStyle": {"fontFamily": "Segoe UI", "fontSize": "8px"}}],
                                "horizontalTextAlignment": "left",
                            }
                        ]
                    }
                }
            ]
        },
        "visualContainerObjects": {
            "background": [{"properties": {"show": _literal("true"), "color": _fill(color), "transparency": _literal("0D")}}],
            "border": [{"properties": {"show": _literal("false")}}],
            "padding": [{"properties": {side: _literal("0D") for side in ("top", "bottom", "left", "right")}}],
        },
    }
    return {
        "$schema": VISUAL_SCHEMA,
        "name": _id(page_key, key),
        "position": _position(x, y, width, height, order),
        "visual": visual,
    }


def _single_select_metric_slicer(page_key: str, x: int, y: int, width: int, height: int, order: int) -> dict[str, Any]:
    visual = _slicer(
        page_key,
        "metric-selector",
        "Metric Selector",
        "Metric",
        "COLOR TRACTS BY",
        x,
        y,
        width,
        height,
        order,
        mode="Dropdown",
        selected="Customer Fit Percentile",
    )
    visual["$schema"] = VISUAL_SCHEMA
    visual["name"] = _id(page_key, "metric-selector")
    visual["visual"]["objects"]["selection"] = [
        {
            "properties": {
                "singleSelect": _literal("true"),
                "strictSingleSelect": _literal("true"),
                "selectAllCheckboxEnabled": _literal("false"),
            }
        }
    ]
    visual["visual"]["query"]["queryState"]["Values"]["projections"][0]["active"] = True
    return visual


MAP_TOOLTIP_MEASURES = (
    "Map Tooltip Selected Metric",
    "Customer Fit Percentile Display",
    "Household Opportunity Display",
    "Median Household Income Display",
    "Owner-Occupied Housing Share Display",
    "No-Vehicle Household Share Display",
    "Map Tooltip GEOID",
    "Inspector Warning",
    "Map Tooltip Source Vintage",
)


def _azure_tract_map(page_key: str, x: int, y: int, width: int, height: int, order: int) -> dict[str, Any]:
    resource = {
        "geoJson": {
            "type": _literal("'packaged'"),
            "name": _literal(f"'{GEOMETRY_RESOURCE}'"),
            "content": {
                "expr": {
                    "ResourcePackageItem": {
                        "PackageName": "RegisteredResources",
                        "PackageType": 1,
                        "ItemName": GEOMETRY_RESOURCE,
                    }
                }
            },
        }
    }
    query_state = {
        "Category": {"projections": [_column("Michigan Tracts", "GEOID", active=True)]},
        "Tooltips": {"projections": [_measure("Report Measures", name) for name in MAP_TOOLTIP_MEASURES]},
    }
    visual = {
        "visualType": "azureMap",
        "query": {"queryState": query_state},
        "objects": {
            "mapControls": [
                {
                    "properties": {
                        "zoom": _literal("5.35D"),
                        "centerLatitude": _literal("44.75D"),
                        "centerLongitude": _literal("-85.55D"),
                        "defaultStyle": _literal("'road'"),
                        "showSelectionControl": _literal("false"),
                    }
                }
            ],
            "referenceLayer": [
                {
                    "properties": {
                        "additionalDatasource": resource,
                        "polygonStrokeTransparency": _literal("55D"),
                        "polygonStrokeWidth": _literal("1L"),
                        "polygonStrokeColor": _fill("#667784"),
                    }
                },
                {
                    "properties": {
                        "polygonFillColor": {
                            "solid": {
                                "color": {
                                    "expr": {
                                        "Measure": {
                                            "Expression": {"SourceRef": {"Entity": "Report Measures"}},
                                            "Property": "Selected Metric Color",
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]},
                },
            ],
        },
        "visualContainerObjects": {
            "background": [{"properties": {"show": _literal("false")}}],
            "border": [{"properties": {"show": _literal("false")}}],
            "title": [{"properties": {"show": _literal("false")}}],
            "padding": [{"properties": {side: _literal("0D") for side in ("top", "bottom", "left", "right")}}],
            "general": [
                {
                    "properties": {
                        "altText": _literal(
                            "'Michigan public tract reference layer on Azure Maps. Road is the default; the native Style picker permits Satellite road labels. Single tract selection filters the inspector.'"
                        )
                    }
                }
            ],
            "visualTooltip": [{"properties": {"section": _literal(f"'{PAGE_IDS['tooltip']}'")}}],
        },
        "drillFilterOtherVisuals": True,
    }
    return {
        "$schema": VISUAL_SCHEMA,
        "name": _id(page_key, "azure-tract-map"),
        "position": _position(x, y, width, height, order),
        "visual": visual,
    }


def _mixed_table(
    page_key: str,
    key: str,
    columns: Iterable[tuple[str, str]],
    measures: Iterable[str],
    title: str,
    x: int,
    y: int,
    width: int,
    height: int,
    order: int,
) -> dict[str, Any]:
    projections = [_column(table, column) for table, column in columns]
    projections.extend(_measure("Report Measures", measure) for measure in measures)
    visual = {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": projections}}},
        "objects": {
            "columnHeaders": [
                {
                    "properties": {
                        "columnAdjustment": _literal("'growToFit'"),
                        "autoSizeColumnWidth": _literal("true"),
                        "wordWrap": _literal("true"),
                    }
                }
            ]
        },
        "visualContainerObjects": _container(title=title, alt_text=title),
    }
    return {
        "$schema": VISUAL_SCHEMA,
        "name": _id(page_key, key),
        "position": _position(x, y, width, height, order),
        "visual": visual,
    }


def _page(display_name: str, page_id: str, *, tooltip: bool = False) -> dict[str, Any]:
    if tooltip:
        return {
            "$schema": PAGE_SCHEMA,
            "name": page_id,
            "displayName": display_name,
            "displayOption": "ActualSize",
            "height": 300,
            "width": 400,
            "type": "Tooltip",
        }
    return {
        "$schema": PAGE_SCHEMA,
        "name": page_id,
        "displayName": display_name,
        "displayOption": "FitToPage",
        "height": 1080,
        "width": 1920,
    }


def _opportunity_visuals() -> list[dict[str, Any]]:
    p = "opportunity"
    visuals: list[dict[str, Any]] = [
        _textbox(p, "title", "Sprouts Customer Geography — Michigan", 24, 10, 770, 38, 1, size=25, color="#16324F", bold=True),
        _textbox(
            p,
            "subtitle",
            "Map-first statewide decision support · public-data proxy · not routing, final site selection, a site forecast, or Sprouts’ proprietary customer model",
            800,
            16,
            1096,
            30,
            2,
            size=13,
            color="#53657A",
        ),
        _azure_tract_map(p, 0, 72, 1440, 1008, 3),
        _textbox(p, "selector-heading", "COLOR TRACTS BY", 1464, 88, 432, 24, 4, size=12, color="#53657A", bold=True),
        _single_select_metric_slicer(p, 1464, 116, 432, 66, 5),
        _measure_card(
            p,
            "metric-help",
            ["Metric Help"],
            1464,
            190,
            432,
            166,
            6,
            title="Current layer",
            alt_text="Selected metric unit, source, vintage, definition, and interpretation",
            font_size=10,
            show_labels=False,
        ),
        _textbox(p, "legend-heading", "STATEWIDE SCALE", 1464, 365, 432, 22, 7, size=11, color="#53657A", bold=True),
    ]
    swatch_width = 62
    for index, color in enumerate(PALETTE):
        visuals.append(_swatch(p, f"swatch-{index + 1}", color, 1464 + index * 68, 391, swatch_width, 14, 8 + index))
    visuals.append(_swatch(p, "swatch-no-data", NEUTRAL, 1804, 391, 92, 14, 13))
    visuals.extend(
        [
            _measure_card(
                p,
                "legend",
                ["Five-Step Legend"],
                1464,
                411,
                432,
                102,
                14,
                title="Fixed for this refresh",
                alt_text="Dynamic five-step legend with fixed or statewide valid-value P02 to P98 domain and neutral unavailable state",
                font_size=10,
                show_labels=False,
            ),
            _measure_card(
                p,
                "selected-tract",
                ["Inspector Heading", "Inspector Selected Metric", "Inspector Selected Value"],
                1464,
                521,
                432,
                158,
                15,
                title="Selected tract",
                alt_text="Empty, single, or multiple tract selection state and exact selected metric value",
                font_size=12,
                background="#F7FAFC",
                show_labels=False,
            ),
            _measure_card(
                p,
                "warning",
                ["Inspector Warning"],
                1464,
                687,
                432,
                76,
                16,
                title="Contextual warning",
                alt_text="Metric-specific selected tract warning",
                font_size=10,
                background="#FFF8ED",
                show_labels=False,
            ),
            _measure_card(
                p,
                "tract-context",
                ["Selected Tract Context"],
                1464,
                771,
                432,
                285,
                17,
                title="Accepted public context",
                alt_text="Duplicate-suppressed customer fit, household opportunity, selected demographics, and public GEOID",
                font_size=11,
                show_labels=False,
            ),
        ]
    )
    return visuals


def _qa_visuals(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    p = "qa"
    selected_columns = [
        ("Michigan Tracts", "GEOID"),
        ("Michigan Tracts", "Computability Status"),
        ("Michigan Tracts", "QA / Missingness Status"),
        ("Michigan Tracts", "Support Truncation 5 Mile"),
        ("Michigan Tracts", "Any Support Truncation"),
    ]
    selected_measures = [
        "Selected Metric Label",
        "Selected Metric Formatted Value",
        "Selected Metric Available",
        "Selected Metric Status",
        "Selected Metric MOE",
        "Selected Metric Status Detail",
        "Inspector Warning",
    ]
    public_columns: list[tuple[str, str]] = [("Michigan Public Context", "GEOID")]
    for metric in catalog["metrics"]:
        binding = metric["binding"]
        if binding["table"] != "Michigan Public Context":
            continue
        public_columns.extend(
            [
                ("Michigan Public Context", binding["column"]),
                ("Michigan Public Context", binding["moe_column"]),
                ("Michigan Public Context", binding["status_column"]),
                ("Michigan Public Context", binding["status_detail_column"]),
            ]
        )
    return [
        _textbox(p, "title", "QA & Coverage", 40, 20, 760, 44, 1, size=28, color="#16324F", bold=True),
        _textbox(
            p,
            "boundary-note",
            "MODEL-13 and DATA-04 status evidence remains explicit. Missing, invalid, inapplicable, and noncomputable values are never zero-filled, imputed, or treated as favorable.",
            40,
            70,
            1840,
            42,
            2,
            size=15,
            color="#8A3B12",
            bold=True,
        ),
        _single_select_metric_slicer(p, 40, 124, 520, 72, 3),
        _measure_card(p, "model-qa", ["Total Tracts", "Computable Tracts", "Noncomputable Tracts", "Support-Truncated Tracts"], 580, 124, 620, 112, 4, title="MODEL-13 statewide QA", font_size=12),
        _measure_card(p, "public-qa", ["Public Context Rows", "Public Context Reconciled Keys", "Public Context Relationship State"], 1220, 124, 660, 112, 5, title="DATA-04 key reconciliation", font_size=11),
        _measure_card(p, "availability-qa", ["Selected Public Metric Available Tracts", "Selected Public Metric Unavailable Tracts", "Selected Metric Scale Valid Count"], 40, 248, 740, 116, 6, title="Selected metric availability and domain participation", font_size=11),
        _measure_card(p, "status-qa", ["Selected Public Metric QA"], 800, 248, 1080, 116, 7, title="Selected DATA-04 status, MOE, and detail", font_size=11, show_labels=False),
        _mixed_table(p, "selected-qa-table", selected_columns, selected_measures, "Selected metric tract-level QA and contextual warning", 40, 380, 1840, 286, 8),
        _table(p, "public-context-table", public_columns, "Complete 3,017-key DATA-04 estimates, MOEs, statuses, and status details", 40, 682, 1840, 350, 9),
        _textbox(p, "footer", "Technical field names and status codes are confined to QA. The scouting page uses the governed operator catalog and source-specific warnings.", 40, 1038, 1840, 30, 10, size=13, color="#53657A"),
    ]


def _tooltip_visuals() -> list[dict[str, Any]]:
    p = "tooltip"
    return [
        _measure_card(p, "tooltip-metric", ["Map Tooltip Selected Metric"], 8, 8, 384, 58, 1, title="Selected metric", font_size=12, background="#F7FAFC", show_labels=False),
        _measure_card(p, "tooltip-warning", ["Inspector Warning"], 8, 72, 384, 54, 2, title="Relevant warning", font_size=9, background="#FFF8ED", show_labels=False),
        _measure_card(p, "tooltip-context", ["Tooltip Public Context"], 8, 132, 384, 90, 3, title="Useful public context", font_size=9, show_labels=False),
        _measure_card(p, "tooltip-reference", ["Map Tooltip GEOID", "Map Tooltip Source Vintage"], 8, 228, 384, 64, 4, title="Public reference and source", font_size=9, show_labels=False),
    ]


def build_report(repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    catalog = json.loads((root / "config" / "pbi" / "pbi02_metric_catalog.json").read_text(encoding="utf-8"))
    if len(catalog.get("metrics", [])) != 16:
        raise ValueError("PBI-02 metric catalog must contain exactly 16 rows")

    build_pbi01_report(root)
    report = root / "powerbi" / "pbi01" / "project" / "MICustomerGeography.Report"
    pages_root = report / "definition" / "pages"
    if report.name != "MICustomerGeography.Report" or root not in report.resolve().parents:
        raise ValueError("refusing to write outside the governed PBI-02 successor report")
    if pages_root.exists():
        shutil.rmtree(pages_root)

    definitions = [
        (PAGE_IDS["opportunity"], "Michigan Opportunity Explorer", _opportunity_visuals(), False),
        (PAGE_IDS["evidence"], "Sprouts Evidence Context", _evidence_visuals(), False),
        (PAGE_IDS["qa"], "QA & Coverage", _qa_visuals(catalog), False),
        (PAGE_IDS["tooltip"], "Tract Tooltip", _tooltip_visuals(), True),
    ]
    for page_id, display_name, visuals, is_tooltip in definitions:
        page_dir = pages_root / page_id
        _write_json(page_dir / "page.json", _page(display_name, page_id, tooltip=is_tooltip))
        for visual in visuals:
            visual["$schema"] = VISUAL_SCHEMA
            _write_json(page_dir / "visuals" / visual["name"] / "visual.json", visual)
    _write_json(
        pages_root / "pages.json",
        {
            "$schema": PAGES_SCHEMA,
            "pageOrder": [page_id for page_id, _display_name, _visuals, _tooltip in definitions],
            "activePageName": PAGE_IDS["opportunity"],
        },
    )

    report_json_path = report / "definition" / "report.json"
    report_json = json.loads(report_json_path.read_text(encoding="utf-8"))
    packages = [value for value in report_json.get("resourcePackages", []) if value.get("name") != "RegisteredResources"]
    packages.append(
        {
            "name": "RegisteredResources",
            "type": "RegisteredResources",
            "items": [{"name": GEOMETRY_RESOURCE, "path": GEOMETRY_RESOURCE, "type": "ShapeMap"}],
        }
    )
    report_json["resourcePackages"] = packages
    settings = report_json.setdefault("settings", {})
    settings["exportDataMode"] = "AllowSummarized"
    settings["defaultFilterActionIsDataFilter"] = True
    settings["useEnhancedTooltips"] = True
    _write_json(report_json_path, report_json)

    visual_count = sum(len(visuals) for _page_id, _name, visuals, _tooltip in definitions)
    return {
        "state": "READY",
        "page_count": 4,
        "visual_count": visual_count,
        "azure_map_count": 1,
        "shape_map_count": 0,
        "metric_count": 16,
        "built_in_visuals_only": True,
        "protected_rows_embedded": False,
        "public_reference_geometry_count": 3_017,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic PBI-02 PBIR report definitions")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(build_report(args.repository_root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
