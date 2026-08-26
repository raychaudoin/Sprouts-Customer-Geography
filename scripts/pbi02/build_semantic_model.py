from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid


REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from scripts.pbi01.build_semantic_model import (  # noqa: E402
    _measure,
    _quote,
    write_semantic_model as write_pbi01_semantic_model,
)


PUBLIC_CONTEXT_TOKEN = "__PBI02_PUBLIC_CONTEXT_CSV__"
CATALOG_PATH = Path("config/pbi/pbi02_metric_catalog.json")
MODEL_MEASURE_KEYS = {
    "customer_fit_percentile",
    "household_opportunity_5_mile",
    "modeled_target_mass_percentile",
}


PUBLIC_COLUMNS = [
    ("GEOID", "string", "tract_geoid", True, False),
    ("State FIPS", "string", "state_fips", False, True),
    ("County FIPS", "string", "county_fips", False, True),
    ("Tract Code", "string", "tract_code", False, True),
    ("Median Household Income", "double", "median_household_income_estimate", False, False),
    ("Median Household Income MOE", "double", "median_household_income_moe", False, True),
    ("Median Household Income Status", "string", "median_household_income_status", False, True),
    ("Median Household Income Status Detail", "string", "median_household_income_status_detail", False, True),
    ("Per Capita Income", "double", "per_capita_income_estimate", False, False),
    ("Per Capita Income MOE", "double", "per_capita_income_moe", False, True),
    ("Per Capita Income Status", "string", "per_capita_income_status", False, True),
    ("Per Capita Income Status Detail", "string", "per_capita_income_status_detail", False, True),
    ("Civilian Labor Force Share", "double", "civilian_labor_force_share_estimate", False, False),
    ("Civilian Labor Force Share MOE", "double", "civilian_labor_force_share_moe", False, True),
    ("Civilian Labor Force Share Status", "string", "civilian_labor_force_share_status", False, True),
    ("Civilian Labor Force Share Status Detail", "string", "civilian_labor_force_share_status_detail", False, True),
    ("Employment Rate", "double", "employment_rate_estimate", False, False),
    ("Employment Rate MOE", "double", "employment_rate_moe", False, True),
    ("Employment Rate Status", "string", "employment_rate_status", False, True),
    ("Employment Rate Status Detail", "string", "employment_rate_status_detail", False, True),
    ("Bachelor's Degree or Higher Share", "double", "bachelors_or_higher_share_estimate", False, False),
    ("Bachelor's Degree or Higher Share MOE", "double", "bachelors_or_higher_share_moe", False, True),
    ("Bachelor's Degree or Higher Share Status", "string", "bachelors_or_higher_share_status", False, True),
    ("Bachelor's Degree or Higher Share Status Detail", "string", "bachelors_or_higher_share_status_detail", False, True),
    ("Owner-Occupied Housing Share", "double", "owner_occupancy_share_estimate", False, False),
    ("Owner-Occupied Housing Share MOE", "double", "owner_occupancy_share_moe", False, True),
    ("Owner-Occupied Housing Share Status", "string", "owner_occupancy_share_status", False, True),
    ("Owner-Occupied Housing Share Status Detail", "string", "owner_occupancy_share_status_detail", False, True),
    ("Vacant Housing Unit Share", "double", "vacancy_share_estimate", False, False),
    ("Vacant Housing Unit Share MOE", "double", "vacancy_share_moe", False, True),
    ("Vacant Housing Unit Share Status", "string", "vacancy_share_status", False, True),
    ("Vacant Housing Unit Share Status Detail", "string", "vacancy_share_status_detail", False, True),
    ("Median Home Value", "double", "median_home_value_estimate", False, False),
    ("Median Home Value MOE", "double", "median_home_value_moe", False, True),
    ("Median Home Value Status", "string", "median_home_value_status", False, True),
    ("Median Home Value Status Detail", "string", "median_home_value_status_detail", False, True),
    ("Median Gross Rent", "double", "median_gross_rent_estimate", False, False),
    ("Median Gross Rent MOE", "double", "median_gross_rent_moe", False, True),
    ("Median Gross Rent Status", "string", "median_gross_rent_status", False, True),
    ("Median Gross Rent Status Detail", "string", "median_gross_rent_status_detail", False, True),
    ("Average Household Size", "double", "average_household_size_estimate", False, False),
    ("Average Household Size MOE", "double", "average_household_size_moe", False, True),
    ("Average Household Size Status", "string", "average_household_size_status", False, True),
    ("Average Household Size Status Detail", "string", "average_household_size_status_detail", False, True),
    ("No-Vehicle Household Share", "double", "no_vehicle_household_share_estimate", False, False),
    ("No-Vehicle Household Share MOE", "double", "no_vehicle_household_share_moe", False, True),
    ("No-Vehicle Household Share Status", "string", "no_vehicle_household_share_status", False, True),
    ("No-Vehicle Household Share Status Detail", "string", "no_vehicle_household_share_status_detail", False, True),
    ("Drive-Alone Commuter Share", "double", "drive_alone_commuter_share_estimate", False, False),
    ("Drive-Alone Commuter Share MOE", "double", "drive_alone_commuter_share_moe", False, True),
    ("Drive-Alone Commuter Share Status", "string", "drive_alone_commuter_share_status", False, True),
    ("Drive-Alone Commuter Share Status Detail", "string", "drive_alone_commuter_share_status_detail", False, True),
    ("Work-from-Home Commuter Share", "double", "work_from_home_commuter_share_estimate", False, False),
    ("Work-from-Home Commuter Share MOE", "double", "work_from_home_commuter_share_moe", False, True),
    ("Work-from-Home Commuter Share Status", "string", "work_from_home_commuter_share_status", False, True),
    ("Work-from-Home Commuter Share Status Detail", "string", "work_from_home_commuter_share_status_detail", False, True),
]


def _tag(kind: str, name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sprouts-customer-geography:pbi02:{kind}:{name}"))


def _m_text(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _m_column(name: str) -> str:
    return name if name.replace("_", "").isalnum() and " " not in name else f'#"{name}"'


def _m_type(data_type: str) -> str:
    return {"string": "type text", "double": "type number", "int64": "Int64.Type"}[data_type]


def _m_table_type(data_type: str) -> str:
    return {"string": "text", "double": "number", "int64": "Int64.Type"}[data_type]


def _column_tmdl(
    table: str,
    name: str,
    data_type: str,
    *,
    is_key: bool = False,
    is_hidden: bool = False,
    sort_by: str | None = None,
) -> str:
    lines = [f"\tcolumn {_quote(name)}", f"\t\tdataType: {data_type}"]
    if is_key:
        lines.append("\t\tisKey")
    if is_hidden:
        lines.append("\t\tisHidden")
    if data_type == "double":
        lines.append("\t\tformatString: 0.00")
    elif data_type == "int64":
        lines.append("\t\tformatString: 0")
    lines.extend(
        [
            f"\t\tlineageTag: {_tag('column', table + ':' + name)}",
            "\t\tsummarizeBy: none",
            f"\t\tsourceColumn: {name}",
        ]
    )
    if sort_by:
        lines.append(f"\t\tsortByColumn: {_quote(sort_by)}")
    lines.append("\n\t\tannotation SummarizationSetBy = Automatic")
    return "\n".join(lines)


def _public_context_table() -> str:
    rename_pairs = ", ".join(
        f'{{"{source}", "{name}"}}' for name, _data_type, source, _is_key, _is_hidden in PUBLIC_COLUMNS
    )
    type_pairs = ", ".join(
        f'{{"{name}", {_m_type(data_type)}}}' for name, data_type, _source, _is_key, _is_hidden in PUBLIC_COLUMNS
    )
    column_blocks = "\n\n".join(
        _column_tmdl("Michigan Public Context", name, data_type, is_key=is_key, is_hidden=is_hidden)
        for name, data_type, _source, is_key, is_hidden in PUBLIC_COLUMNS
    )
    return f'''/// Exact accepted DATA-04 public tract estimates and QA evidence; presentation labels only.
table 'Michigan Public Context'
\tlineageTag: {_tag('table', 'Michigan Public Context')}

{column_blocks}

\tpartition 'Michigan Public Context' = m
\t\tmode: import
\t\tsource =
\t\t\t\tlet
\t\t\t\t\tSource = Csv.Document(File.Contents("{PUBLIC_CONTEXT_TOKEN}"), [Delimiter = ",", Columns = {len(PUBLIC_COLUMNS)}, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
\t\t\t\t\t#"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
\t\t\t\t\t#"Renamed Columns" = Table.RenameColumns(#"Promoted Headers", {{{rename_pairs}}}, MissingField.Error),
\t\t\t\t\t#"Typed Columns" = Table.TransformColumnTypes(#"Renamed Columns", {{{type_pairs}}}, "en-US")
\t\t\t\tin
\t\t\t\t\t#"Typed Columns"

\tannotation PBI_NavigationStepName = Navigation

\tannotation PBI_ResultType = Table
'''


SELECTOR_FIELDS = [
    ("Metric", "string", False),
    ("Metric Key", "string", True),
    ("Source Authority ID", "string", True),
    ("Family", "string", True),
    ("Short Name", "string", True),
    ("Sort Order", "int64", True),
    ("Unit", "string", True),
    ("Format Policy", "string", True),
    ("Definition", "string", True),
    ("Interpretation", "string", True),
    ("Source Label", "string", True),
    ("Vintage Label", "string", True),
    ("Scale Policy", "string", True),
    ("Availability Category", "string", True),
    ("Contextual Warning Policy", "string", True),
]


def _metric_selector(catalog: dict) -> str:
    columns = "\n\n".join(
        _column_tmdl(
            "Metric Selector",
            name,
            data_type,
            is_hidden=is_hidden,
            sort_by="Sort Order" if name == "Metric" else None,
        )
        for name, data_type, is_hidden in SELECTOR_FIELDS
    )
    type_fields = ", ".join(f"{_m_column(name)} = {_m_table_type(data_type)}" for name, data_type, _hidden in SELECTOR_FIELDS)
    rows: list[str] = []
    for metric in catalog["metrics"]:
        values = [
            metric["display_name"],
            metric["metric_key"],
            metric["source_authority_id"],
            metric["family"],
            metric["short_name"],
            metric["sort_order"],
            metric["unit"],
            metric["format_policy"],
            metric["definition"],
            metric["interpretation"],
            metric["source_label"],
            metric["vintage_label"],
            metric["scale_policy"],
            metric["availability_category"],
            metric["contextual_warning_policy"],
        ]
        rows.append("{" + ", ".join(str(value) if isinstance(value, int) else _m_text(value) for value in values) + "}")
    row_text = ",\n\t\t\t\t\t\t".join(rows)
    return f'''/// Disconnected 16-layer presentation selector; no analytical scoring logic.
table 'Metric Selector'
\tlineageTag: {_tag('table', 'Metric Selector')}

{columns}

\tpartition 'Metric Selector' = m
\t\tmode: import
\t\tsource =
\t\t\t\t#table(
\t\t\t\t\ttype table [{type_fields}],
\t\t\t\t\t{{
\t\t\t\t\t\t{row_text}
\t\t\t\t\t}}
\t\t\t\t)

\tannotation PBI_NavigationStepName = Navigation

\tannotation PBI_ResultType = Table
'''


def _presentation_scale(catalog: dict) -> str:
    columns = "\n\n".join(
        _column_tmdl("Presentation Scale", name, data_type, is_key=name == "Metric Key", is_hidden=True)
        for name, data_type in (
            ("Metric Key", "string"),
            ("Scale Low", "double"),
            ("Scale High", "double"),
            ("Scale Policy", "string"),
            ("Valid Value Count", "int64"),
        )
    )
    rows: list[str] = []
    for metric in catalog["metrics"]:
        key = metric["metric_key"]
        binding = metric["binding"]
        if metric["scale_policy"] == "fixed_0_100":
            value_column = binding["column"]
            rows.append(
                f'{{"{key}", 0.0, 100.0, "fixed_0_100", '
                f'List.Count(List.RemoveNulls(Table.Column(#"Michigan Tracts", "{value_column}")))}}'
            )
        elif binding["table"] == "Michigan Tracts":
            value_column = binding["column"]
            rows.append(
                f'let V = List.RemoveNulls(Table.Column(#"Michigan Tracts", "{value_column}")) '
                f'in {{"{key}", List.Percentile(V, 0.02), List.Percentile(V, 0.98), "statewide_valid_p02_p98", List.Count(V)}}'
            )
        else:
            value_column = binding["column"]
            status_column = binding["status_column"]
            rows.append(
                f'let T = Table.SelectRows(#"Michigan Public Context", each Record.Field(_, "{status_column}") = "valid"), '
                f'V = List.RemoveNulls(Table.Column(T, "{value_column}")) '
                f'in {{"{key}", List.Percentile(V, 0.02), List.Percentile(V, 0.98), "statewide_valid_p02_p98", List.Count(V)}}'
            )
    row_text = ",\n\t\t\t\t\t\t".join(rows)
    return f'''/// Refresh-stable presentation domains; never changes authoritative values.
table 'Presentation Scale'
\tisHidden
\tlineageTag: {_tag('table', 'Presentation Scale')}

{columns}

\tpartition 'Presentation Scale' = m
\t\tmode: import
\t\tsource =
\t\t\t\t#table(
\t\t\t\t\ttype table [#"Metric Key" = text, #"Scale Low" = number, #"Scale High" = number, #"Scale Policy" = text, #"Valid Value Count" = Int64.Type],
\t\t\t\t\t{{
\t\t\t\t\t\t{row_text}
\t\t\t\t\t}}
\t\t\t\t)

\tannotation PBI_NavigationStepName = Navigation

\tannotation PBI_ResultType = Table
'''


def _selected_switch(catalog: dict, property_name: str, default: str) -> str:
    cases = ",\n".join(
        f'        "{metric["metric_key"]}", "{metric[property_name].replace(chr(34), chr(34) * 2)}"'
        for metric in catalog["metrics"]
    )
    return f'''VAR MetricKey = [Selected Metric Key]
RETURN
    SWITCH(
        MetricKey,
{cases},
        "{default.replace(chr(34), chr(34) * 2)}"
    )'''


def _value_expression(metric: dict) -> str:
    binding = metric["binding"]
    return f"MAX('{binding['table']}'[{binding['column']}])"


def _switch_expression(catalog: dict, expression_for_metric, default: str = "BLANK()") -> str:
    cases = ",\n".join(
        f'        "{metric["metric_key"]}", {expression_for_metric(metric)}' for metric in catalog["metrics"]
    )
    return f'''VAR MetricKey = [Selected Metric Key]
RETURN
    SWITCH(
        MetricKey,
{cases},
        {default}
    )'''


def _status_expression(metric: dict) -> str:
    key = metric["metric_key"]
    if key in {"customer_fit_percentile", "modeled_target_mass_percentile"}:
        return "SELECTEDVALUE('Michigan Tracts'[Computability Status])"
    if key == "household_opportunity_5_mile":
        return 'IF(ISBLANK(MAX(\'Michigan Tracts\'[Household Opportunity])), "missing", "valid")'
    binding = metric["binding"]
    return f"SELECTEDVALUE('{binding['table']}'[{binding['status_column']}])"


def _moe_expression(metric: dict) -> str:
    binding = metric["binding"]
    if "moe_column" not in binding:
        return "BLANK()"
    return f"MAX('{binding['table']}'[{binding['moe_column']}])"


def _status_detail_expression(metric: dict) -> str:
    key = metric["metric_key"]
    if key in MODEL_MEASURE_KEYS:
        return "SELECTEDVALUE('Michigan Tracts'[QA / Missingness Status])"
    binding = metric["binding"]
    return f"SELECTEDVALUE('{binding['table']}'[{binding['status_detail_column']}])"


def _format_value_dax(value_expression: str) -> str:
    return f'''VAR ValueToFormat = {value_expression}
VAR Policy = [Selected Metric Format Policy]
RETURN
    IF(
        ISBLANK(ValueToFormat),
        "No Data / Unavailable",
        SWITCH(
            Policy,
            "percentile_1", FORMAT(ValueToFormat, "0.0") & " percentile",
            "count_0", FORMAT(ValueToFormat, "#,0") & " households",
            "currency_0", FORMAT(ValueToFormat, "$#,0"),
            "percent_1", FORMAT(ValueToFormat, "0.0") & " %",
            "decimal_2", FORMAT(ValueToFormat, "0.00"),
            FORMAT(ValueToFormat, "#,0.00")
        )
    )'''


def _scale_label_expression(fraction: float, prefix: str) -> str:
    return f'''VAR LowValue = [Selected Metric Scale Low]
VAR HighValue = [Selected Metric Scale High]
VAR PointValue = LowValue + ((HighValue - LowValue) * {fraction})
VAR Policy = [Selected Metric Format Policy]
VAR FormattedValue =
    SWITCH(
        Policy,
        "percentile_1", FORMAT(PointValue, "0.0"),
        "count_0", FORMAT(PointValue, "#,0"),
        "currency_0", FORMAT(PointValue, "$#,0"),
        "percent_1", FORMAT(PointValue, "0.0") & " %",
        "decimal_2", FORMAT(PointValue, "0.00"),
        FORMAT(PointValue, "#,0.00")
    )
RETURN "{prefix}" & FormattedValue'''


def _report_measures(catalog: dict) -> str:
    measures: list[tuple[str, str, str | None, str | None]] = [
        ("Total Tracts", "COUNTROWS('Michigan Tracts')", "#,0", "Statewide tract count after report filters."),
        ("Computable Tracts", "CALCULATE(COUNTROWS('Michigan Tracts'), 'Michigan Tracts'[Computability Status] = \"MODEL_SCORE_COMPUTABLE\")", "#,0", "Tracts with authoritative MODEL-13 scores."),
        ("Noncomputable Tracts", "[Total Tracts] - [Computable Tracts]", "#,0", "Tracts explicitly noncomputable in MODEL-13."),
        ("Support-Truncated Tracts", "CALCULATE(COUNTROWS('Michigan Tracts'), 'Michigan Tracts'[Any Support Truncation] = TRUE())", "#,0", "Tracts with descriptive boundary support truncation."),
        ("Public Context Rows", "COUNTROWS('Michigan Public Context')", "#,0", "DATA-04 public-context tract rows after report filters."),
        ("Public Context Reconciled Keys", "COUNTROWS(INTERSECT(VALUES('Michigan Tracts'[GEOID]), VALUES('Michigan Public Context'[GEOID])))", "#,0", "Reconciled public GEOID count."),
        ("Selected Metric Key", "SELECTEDVALUE('Metric Selector'[Metric Key], \"customer_fit_percentile\")", None, "Stable selected catalog key."),
        ("Selected Metric Label", "SELECTEDVALUE('Metric Selector'[Metric], \"Customer Fit Percentile\")", None, "Operator selected map-layer label."),
        ("Selected Metric Short Name", "SELECTEDVALUE('Metric Selector'[Short Name], \"Customer Fit\")", None, None),
        ("Selected Metric Unit", "SELECTEDVALUE('Metric Selector'[Unit], \"statewide percentile\")", None, None),
        ("Selected Metric Format Policy", "SELECTEDVALUE('Metric Selector'[Format Policy], \"percentile_1\")", None, None),
        ("Selected Metric Definition", "SELECTEDVALUE('Metric Selector'[Definition], \"Percentile position of the accepted customer-fit public-data proxy among computable Michigan tracts.\")", None, None),
        ("Selected Metric Interpretation", "SELECTEDVALUE('Metric Selector'[Interpretation], \"Use as relative statewide decision support. It is not Sprouts' proprietary customer model and is not a final site recommendation.\")", None, None),
        ("Selected Metric Source", "SELECTEDVALUE('Metric Selector'[Source Label], \"Accepted MODEL-13 Michigan public-data proxy output\")", None, None),
        ("Selected Metric Vintage", "SELECTEDVALUE('Metric Selector'[Vintage Label], \"2024 public-source inputs\")", None, None),
        ("Selected Metric Scale Policy", "SELECTEDVALUE('Metric Selector'[Scale Policy], \"fixed_0_100\")", None, None),
        ("Selected Metric Availability Category", "SELECTEDVALUE('Metric Selector'[Availability Category], \"model13_computability\")", None, None),
        ("Selected Metric Warning Policy", "SELECTEDVALUE('Metric Selector'[Contextual Warning Policy], \"model_noncomputability_and_relevant_support\")", None, None),
        ("Selected Metric Value", _switch_expression(catalog, _value_expression), "0.00", "Presentation-only switch across distinct authoritative fields."),
        ("Selected Metric Status", _switch_expression(catalog, _status_expression, '"missing"'), None, "Selected source-specific availability status."),
        ("Selected Metric MOE", _switch_expression(catalog, _moe_expression), "0.00", "Selected DATA-04 margin of error when applicable."),
        ("Selected Metric Status Detail", _switch_expression(catalog, _status_detail_expression, '""'), None, None),
        (
            "Selected Metric Available",
            '''VAR MetricKey = [Selected Metric Key]
VAR StatusValue = [Selected Metric Status]
VAR NumericValue = [Selected Metric Value]
RETURN
    IF(
        NOT ISBLANK(NumericValue)
            && IF(
                MetricKey IN {"customer_fit_percentile", "modeled_target_mass_percentile"},
                StatusValue = "MODEL_SCORE_COMPUTABLE",
                StatusValue = "valid"
            ),
        1,
        0
    )''',
            "0",
            "Explicit availability; missingness never becomes zero or favorable.",
        ),
        (
            "Selected Metric Scale Low",
            '''VAR MetricKey = [Selected Metric Key]
RETURN CALCULATE(MAX('Presentation Scale'[Scale Low]), TREATAS({MetricKey}, 'Presentation Scale'[Metric Key]))''',
            "0.00",
            "Refresh-stable scale lower bound.",
        ),
        (
            "Selected Metric Scale High",
            '''VAR MetricKey = [Selected Metric Key]
RETURN CALCULATE(MAX('Presentation Scale'[Scale High]), TREATAS({MetricKey}, 'Presentation Scale'[Metric Key]))''',
            "0.00",
            "Refresh-stable scale upper bound.",
        ),
        (
            "Selected Metric Scale Valid Count",
            '''VAR MetricKey = [Selected Metric Key]
RETURN CALCULATE(MAX('Presentation Scale'[Valid Value Count]), TREATAS({MetricKey}, 'Presentation Scale'[Metric Key]))''',
            "#,0",
            None,
        ),
        (
            "Selected Metric Color",
            '''VAR ValueToColor = [Selected Metric Value]
VAR LowValue = [Selected Metric Scale Low]
VAR HighValue = [Selected Metric Scale High]
VAR Span = HighValue - LowValue
VAR Position = DIVIDE(ValueToColor - LowValue, Span, 0)
RETURN
    IF(
        [Selected Metric Available] <> 1 || ISBLANK(ValueToColor) || ISBLANK(LowValue) || ISBLANK(HighValue),
        "#D7DEE4",
        SWITCH(
            TRUE(),
            Position <= 0.20, "#E5F2F0",
            Position <= 0.40, "#B9DED8",
            Position <= 0.60, "#7FC4BB",
            Position <= 0.80, "#3E9B91",
            "#12685F"
        )
    )''',
            None,
            "Field-value color for Azure Maps reference polygons; sequential and neutral for unavailable values.",
        ),
        ("Selected Metric Formatted Value", _format_value_dax("[Selected Metric Value]"), None, "Exact selected metric value formatted by catalog policy."),
        ("Legend Step 1", _scale_label_expression(0.0, "≤ "), None, None),
        ("Legend Step 2", _scale_label_expression(0.25, ""), None, None),
        ("Legend Step 3", _scale_label_expression(0.5, ""), None, None),
        ("Legend Step 4", _scale_label_expression(0.75, ""), None, None),
        ("Legend Step 5", _scale_label_expression(1.0, "≥ "), None, None),
        ("Legend No Data", '"No Data / Unavailable"', None, None),
        ("Metric Help", '[Selected Metric Unit] & " · " & [Selected Metric Source] & " · " & [Selected Metric Vintage] & UNICHAR(10) & [Selected Metric Definition] & UNICHAR(10) & [Selected Metric Interpretation]', None, "Operator-facing unit, source, vintage, definition, and interpretation."),
        ("Five-Step Legend", '[Legend Step 1] & "   " & [Legend Step 2] & "   " & [Legend Step 3] & "   " & [Legend Step 4] & "   " & [Legend Step 5] & UNICHAR(10) & [Legend No Data]', None, "Dynamic five-step scale plus neutral unavailable state."),
        ("Selected Tract Count", "IF(ISFILTERED('Michigan Tracts'[GEOID]), COUNTROWS(VALUES('Michigan Tracts'[GEOID])), 0)", "#,0", "Zero, one, or multiple selected GEOIDs."),
        (
            "Inspector State",
            '''VAR SelectedCount = [Selected Tract Count]
RETURN SWITCH(TRUE(), SelectedCount = 0, "Select a tract", SelectedCount = 1, "Single tract selected", "Multiple tracts selected")''',
            None,
            "Explicit empty, single, and multiple-selection state.",
        ),
        ("Selected GEOID", "IF([Selected Tract Count] = 1, SELECTEDVALUE('Michigan Tracts'[GEOID]), BLANK())", None, "Public GEOID technical reference only."),
        (
            "Inspector Heading",
            '''VAR SelectedCount = [Selected Tract Count]
RETURN SWITCH(TRUE(), SelectedCount = 0, "Select a tract", SelectedCount = 1, "TRACT " & [Selected GEOID], "Multiple tracts selected")''',
            None,
            None,
        ),
        ("Inspector Selected Metric", "IF([Selected Tract Count] = 1, [Selected Metric Label], BLANK())", None, None),
        ("Inspector Selected Value", "IF([Selected Tract Count] = 1, [Selected Metric Formatted Value], BLANK())", None, None),
        (
            "Inspector Warning",
            '''VAR SelectedCount = [Selected Tract Count]
VAR Policy = [Selected Metric Warning Policy]
VAR StatusValue = [Selected Metric Status]
VAR DetailValue = [Selected Metric Status Detail]
RETURN
    IF(
        SelectedCount <> 1,
        BLANK(),
        SWITCH(
            Policy,
            "data04_measure_status_only",
                IF(StatusValue = "valid", BLANK(), [Selected Metric Label] & " unavailable: " & COALESCE(StatusValue, "missing") & IF(NOT ISBLANK(DetailValue), " — " & DetailValue, "")),
            "five_mile_support_truncation",
                IF(SELECTEDVALUE('Michigan Tracts'[Support Truncation 5 Mile], FALSE()), "Five-mile support is boundary-truncated; interpret household opportunity with caution.", BLANK()),
            "model_noncomputability_and_relevant_support",
                IF(
                    StatusValue <> "MODEL_SCORE_COMPUTABLE",
                    "MODEL-13 value unavailable: " & COALESCE(DetailValue, "noncomputable"),
                    IF(SELECTEDVALUE('Michigan Tracts'[Any Support Truncation], FALSE()), "One or more accepted model support radii are boundary-truncated; interpret the model proxy with caution.", BLANK())
                ),
            BLANK()
        )
    )''',
            None,
            "Metric-specific warning immediately below selected value.",
        ),
        ("Map Tooltip Selected Metric", '[Selected Metric Label] & ": " & [Selected Metric Formatted Value]', None, None),
        ("Map Tooltip GEOID", "SELECTEDVALUE('Michigan Tracts'[GEOID])", None, None),
        ("Map Tooltip Source Vintage", '[Selected Metric Source] & " · " & [Selected Metric Vintage]', None, None),
        ("Customer Fit", "AVERAGE('Michigan Tracts'[Customer Fit])", "0.0000", "Authoritative MODEL-13 customer-fit proxy."),
        ("Customer Fit Statewide Rank", "SELECTEDVALUE('Michigan Tracts'[Customer Fit Statewide Rank])", "#,0", None),
        ("Customer Fit Percentile", "MAX('Michigan Tracts'[Customer Fit Percentile])", "0.0", None),
        ("Household Opportunity", "MAX('Michigan Tracts'[Household Opportunity])", "#,0.00", "Authoritative MODEL-13 five-mile household opportunity."),
        ("Modeled Target Mass", "AVERAGE('Michigan Tracts'[Modeled Target Mass])", "#,0.00", "Authoritative MODEL-13 modeled target mass."),
        ("Modeled Target Mass Statewide Rank", "SELECTEDVALUE('Michigan Tracts'[Modeled Target Mass Statewide Rank])", "#,0", None),
        ("Modeled Target Mass Percentile", "MAX('Michigan Tracts'[Modeled Target Mass Percentile])", "0.0", None),
        ("Member Count 3 Mile", "SELECTEDVALUE('Michigan Tracts'[Member Count 3 Mile])", "#,0", None),
        ("Member Count 5 Mile", "SELECTEDVALUE('Michigan Tracts'[Member Count 5 Mile])", "#,0", None),
        ("Member Count 7 Mile", "SELECTEDVALUE('Michigan Tracts'[Member Count 7 Mile])", "#,0", None),
        ("Support Completeness 3 Mile", "AVERAGE('Michigan Tracts'[Support Completeness 3 Mile])", "0.0%", None),
        ("Support Completeness 5 Mile", "AVERAGE('Michigan Tracts'[Support Completeness 5 Mile])", "0.0%", None),
        ("Support Completeness 7 Mile", "AVERAGE('Michigan Tracts'[Support Completeness 7 Mile])", "0.0%", None),
        ("Support Truncation State", "IF(SELECTEDVALUE('Michigan Tracts'[Any Support Truncation], FALSE()), \"Boundary support truncated\", \"No boundary support truncation\")", None, None),
        ("Computability Detail", "SELECTEDVALUE('Michigan Tracts'[Computability Status], \"Multiple states\")", None, None),
        ("QA / Missingness Detail", "SELECTEDVALUE('Michigan Tracts'[QA / Missingness Status], \"Multiple categories\")", None, None),
    ]

    public_metric_names = [metric["display_name"] for metric in catalog["metrics"] if metric["metric_key"] not in MODEL_MEASURE_KEYS]
    for name in public_metric_names:
        measures.append((name, f"MAX('Michigan Public Context'[{name}])", "0.00", f"Exact DATA-04 {name} estimate."))

    measures.extend(
        [
            (
                "Customer Fit Percentile Display",
                'IF([Selected Tract Count] = 1 && NOT ISBLANK([Customer Fit Percentile]), FORMAT([Customer Fit Percentile], "0.0") & " percentile", "No Data / Unavailable")',
                None,
                None,
            ),
            (
                "Household Opportunity Display",
                'IF([Selected Tract Count] = 1 && NOT ISBLANK([Household Opportunity]), FORMAT([Household Opportunity], "#,0") & " households", "No Data / Unavailable")',
                None,
                None,
            ),
            (
                "Median Household Income Display",
                'IF([Selected Tract Count] = 1 && SELECTEDVALUE(\'Michigan Public Context\'[Median Household Income Status]) = "valid", FORMAT([Median Household Income], "$#,0"), "No Data / Unavailable")',
                None,
                None,
            ),
            (
                "Owner-Occupied Housing Share Display",
                'IF([Selected Tract Count] = 1 && SELECTEDVALUE(\'Michigan Public Context\'[Owner-Occupied Housing Share Status]) = "valid", FORMAT([Owner-Occupied Housing Share], "0.0") & " %", "No Data / Unavailable")',
                None,
                None,
            ),
            (
                "No-Vehicle Household Share Display",
                'IF([Selected Tract Count] = 1 && SELECTEDVALUE(\'Michigan Public Context\'[No-Vehicle Household Share Status]) = "valid", FORMAT([No-Vehicle Household Share], "0.0") & " %", "No Data / Unavailable")',
                None,
                None,
            ),
            (
                "Per Capita Income Display",
                'IF([Selected Tract Count] = 1 && SELECTEDVALUE(\'Michigan Public Context\'[Per Capita Income Status]) = "valid", FORMAT([Per Capita Income], "$#,0"), "No Data / Unavailable")',
                None,
                None,
            ),
        ]
    )

    support_rows = [
        (1, "customer_fit_percentile", "Customer Fit Percentile", "Customer Fit Percentile Display"),
        (2, "household_opportunity_5_mile", "5-Mile Household Opportunity", "Household Opportunity Display"),
        (3, "median_household_income", "Median Household Income", "Median Household Income Display"),
        (4, "owner_occupancy_share", "Owner-Occupied Housing Share", "Owner-Occupied Housing Share Display"),
        (5, "no_vehicle_household_share", "No-Vehicle Household Share", "No-Vehicle Household Share Display"),
    ]
    for index, duplicate_key, default_label, default_measure in support_rows:
        measures.append(
            (
                f"Support Row {index} Label",
                f'IF([Selected Metric Key] = "{duplicate_key}", "Per Capita Income", "{default_label}")',
                None,
                "Suppress duplicate selected metric and substitute Per Capita Income.",
            )
        )
        measures.append(
            (
                f"Support Row {index} Value",
                f'IF([Selected Metric Key] = "{duplicate_key}", [Per Capita Income Display], [{default_measure}])',
                None,
                None,
            )
        )
    measures.extend(
        [
            ("Support Row 6 Label", '"GEOID"', None, None),
            ("Support Row 6 Value", 'IF([Selected Tract Count] = 1, [Selected GEOID], BLANK())', None, None),
            ("Selected Tract Context", 'IF([Selected Tract Count] = 1, [Support Row 1 Label] & ": " & [Support Row 1 Value] & UNICHAR(10) & [Support Row 2 Label] & ": " & [Support Row 2 Value] & UNICHAR(10) & [Support Row 3 Label] & ": " & [Support Row 3 Value] & UNICHAR(10) & [Support Row 4 Label] & ": " & [Support Row 4 Value] & UNICHAR(10) & [Support Row 5 Label] & ": " & [Support Row 5 Value] & UNICHAR(10) & [Support Row 6 Label] & ": " & [Support Row 6 Value], BLANK())', None, "Duplicate-suppressed selected-tract context in governed display order."),
            ("Selected Public Metric Status", 'IF([Selected Metric Availability Category] = "data04_measure_status", [Selected Metric Status], "Not applicable")', None, None),
            ("Selected Public Metric MOE", 'IF([Selected Metric Availability Category] = "data04_measure_status", [Selected Metric MOE], BLANK())', "0.00", None),
            ("Selected Public Metric Status Detail", 'IF([Selected Metric Availability Category] = "data04_measure_status", [Selected Metric Status Detail], "Not applicable")', None, None),
            ("Selected Public Metric Available Tracts", 'VAR K=[Selected Metric Key] RETURN IF(K IN {"customer_fit_percentile","household_opportunity_5_mile","modeled_target_mass_percentile"}, BLANK(), SUMX(VALUES(\'Michigan Tracts\'[GEOID]), [Selected Metric Available]))', "#,0", None),
            ("Selected Public Metric Unavailable Tracts", 'IF(ISBLANK([Selected Public Metric Available Tracts]), BLANK(), [Public Context Rows] - [Selected Public Metric Available Tracts])', "#,0", "Missing, invalid, inapplicable, or otherwise unavailable selected public metric rows."),
            ("Public Context Relationship State", 'IF([Public Context Rows] = 3017 && [Public Context Reconciled Keys] = 3017, "3,017 / 3,017 keys reconciled one-to-one", "FAIL CLOSED — public-context key reconciliation differs")', None, "Operator QA state for the public one-to-one relationship."),
            ("Selected Public Metric QA", '"Status: " & [Selected Public Metric Status] & IF(NOT ISBLANK([Selected Public Metric MOE]), " · MOE: " & FORMAT([Selected Public Metric MOE], "#,0.00"), "") & UNICHAR(10) & [Selected Public Metric Status Detail]', None, "Selected DATA-04 status, MOE, and status detail for QA."),
            ("Tooltip Public Context", '[Customer Fit Percentile Display] & " · " & [Household Opportunity Display] & UNICHAR(10) & [Median Household Income Display] & " · " & [Owner-Occupied Housing Share Display] & " · " & [No-Vehicle Household Share Display]', None, "Compact report-page tooltip public context."),
            ("Evidence Locations", "COUNTROWS('Seed Context')", "#,0", "Accepted nonquarantined Michigan physical-location evidence rows."),
            ("Mean Isolated Sales", "AVERAGE('Seed Context'[Mean Isolated Sales])", "#,0.00", None),
            ("Frozen MODEL-12 Prediction", "AVERAGE('Seed Context'[Frozen MODEL-12 Prediction])", "#,0.00", None),
            ("Successor OOF Prediction", "AVERAGE('Seed Context'[Successor OOF Prediction])", "#,0.00", None),
            ("Successor OOF Absolute Log Error", "AVERAGE('Seed Context'[Successor OOF Absolute Log Error])", "0.000", None),
            ("Seed Household Opportunity", "AVERAGE('Seed Context'[Household Opportunity])", "#,0.00", None),
            ("Seed Customer Fit", "AVERAGE('Seed Context'[Customer Fit])", "0.0000", None),
            ("Seed Modeled Target Mass", "AVERAGE('Seed Context'[Modeled Target Mass])", "#,0.00", None),
            ("Seed Support State", "IF(SELECTEDVALUE('Seed Context'[Support Truncation], FALSE()), \"Boundary support truncated\", \"No boundary support truncation\")", None, None),
            ("Seed QA Status", "SELECTEDVALUE('Seed Context'[QA Status], \"Multiple categories\")", None, None),
        ]
    )

    measure_text = "\n\n".join(_measure(name, expression, format_string, description) for name, expression, format_string, description in measures)
    return f'''/// Light PBI-02 presentation measures; all analytical values remain accepted upstream authority.
table 'Report Measures'
\tlineageTag: {_tag('table', 'Report Measures')}

\tcolumn Anchor
\t\tdataType: string
\t\tisHidden
\t\tlineageTag: {_tag('column', 'Report Measures:Anchor')}
\t\tsummarizeBy: none
\t\tsourceColumn: Anchor

\t\tannotation SummarizationSetBy = Automatic

{measure_text}

\tpartition 'Report Measures' = m
\t\tmode: import
\t\tsource = #table(type table [Anchor = text], {{{{"PBI-02"}}}})

\tannotation PBI_NavigationStepName = Navigation

\tannotation PBI_ResultType = Table
'''


def write_semantic_model(repository_root: Path) -> dict[str, object]:
    root = repository_root.resolve()
    catalog = json.loads((root / CATALOG_PATH).read_text(encoding="utf-8"))
    if len(catalog.get("metrics", [])) != 16:
        raise ValueError("PBI-02 metric catalog must contain exactly 16 rows")

    write_pbi01_semantic_model(root)
    definition = root / "powerbi" / "pbi01" / "project" / "MICustomerGeography.SemanticModel" / "definition"
    tables = definition / "tables"
    documents = {
        "Metric Selector.tmdl": _metric_selector(catalog),
        "Michigan Public Context.tmdl": _public_context_table(),
        "Presentation Scale.tmdl": _presentation_scale(catalog),
        "Report Measures.tmdl": _report_measures(catalog),
    }
    for filename, content in documents.items():
        (tables / filename).write_text(content.rstrip() + "\n", encoding="utf-8")

    model_path = definition / "model.tmdl"
    model = model_path.read_text(encoding="utf-8")
    model = model.split("\nref table ", 1)[0].rstrip()
    refs = "\n\n".join(
        f"ref table {_quote(name)}"
        for name in (
            "Michigan Tracts",
            "Seed Context",
            "Metric Selector",
            "Michigan Public Context",
            "Presentation Scale",
            "Report Measures",
        )
    )
    model_path.write_text(model + "\n\n" + refs + "\n", encoding="utf-8")

    relationship_id = _tag("relationship", "Michigan Public Context GEOID to Michigan Tracts GEOID")
    relationship = f'''relationship {relationship_id}
\tfromColumn: 'Michigan Public Context'.GEOID
\ttoColumn: 'Michigan Tracts'.GEOID
\tfromCardinality: one
\ttoCardinality: one
\tcrossFilteringBehavior: bothDirections
'''
    (definition / "relationships.tmdl").write_text(relationship, encoding="utf-8")
    return {
        "state": "READY",
        "tables": 6,
        "relationships": 1,
        "metric_count": 16,
        "protected_paths_embedded": False,
        "analytical_authority_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic PBI-02 TMDL semantic-model definitions")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(write_semantic_model(args.repository_root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
