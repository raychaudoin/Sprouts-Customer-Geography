from __future__ import annotations

import argparse
from pathlib import Path
import uuid


TRACT_COLUMNS = [
    ("GEOID", "string", "geoid", None, True, False),
    ("Internal Point Latitude", "double", "internal_point_latitude", "Latitude", False, True),
    ("Internal Point Longitude", "double", "internal_point_longitude", "Longitude", False, True),
    ("Computability Status", "string", "computability_status", None, False, False),
    ("Household Opportunity", "double", "household_opportunity", None, False, False),
    ("Customer Fit", "double", "customer_fit_proxy", None, False, False),
    ("Customer Fit Statewide Rank", "int64", "customer_fit_statewide_rank", None, False, False),
    ("Customer Fit Percentile", "double", "customer_fit_statewide_percentile", None, False, False),
    ("Modeled Target Mass", "double", "modeled_target_mass", None, False, False),
    ("Modeled Target Mass Statewide Rank", "int64", "modeled_target_mass_statewide_rank", None, False, False),
    ("Modeled Target Mass Percentile", "double", "modeled_target_mass_statewide_percentile", None, False, False),
    ("Member Count 3 Mile", "int64", "tract_member_count_3mi", None, False, False),
    ("Member Count 5 Mile", "int64", "tract_member_count_5mi", None, False, False),
    ("Member Count 7 Mile", "int64", "tract_member_count_7mi", None, False, False),
    ("Support Completeness 3 Mile", "double", "support_completeness_3mi", None, False, False),
    ("Support Completeness 5 Mile", "double", "support_completeness_5mi", None, False, False),
    ("Support Completeness 7 Mile", "double", "support_completeness_7mi", None, False, False),
    ("Support Truncation 3 Mile", "boolean", "support_truncation_3mi", None, False, False),
    ("Support Truncation 5 Mile", "boolean", "support_truncation_5mi", None, False, False),
    ("Support Truncation 7 Mile", "boolean", "support_truncation_7mi", None, False, False),
    ("Any Support Truncation", "boolean", "any_support_truncation", None, False, False),
    ("QA / Missingness Status", "string", "qa_missingness_status", None, False, False),
    ("Model Lineage ID", "string", "model_lineage_id", None, False, True),
    ("Public Lineage ID", "string", "public_lineage_id", None, False, True),
]

SEED_COLUMNS = [
    ("Protected Physical Location ID", "string", "protected_physical_location_id", None, False, True),
    ("Latitude", "double", "latitude", "Latitude", False, False),
    ("Longitude", "double", "longitude", "Longitude", False, False),
    ("Mean Isolated Sales", "double", "mean_isolated_sales", None, False, False),
    ("Frozen MODEL-12 Prediction", "double", "frozen_model12_prediction", None, False, False),
    ("Successor OOF Prediction", "double", "successor_oof_prediction", None, False, False),
    ("Successor OOF Absolute Log Error", "double", "successor_oof_absolute_log_error", None, False, False),
    ("Household Opportunity", "double", "household_opportunity", None, False, False),
    ("Customer Fit", "double", "customer_fit_proxy", None, False, False),
    ("Modeled Target Mass", "double", "modeled_target_mass", None, False, False),
    ("Support Truncation", "boolean", "support_truncation", None, False, False),
    ("QA Status", "string", "qa_status", None, False, False),
    ("Model Lineage ID", "string", "model_lineage_id", None, False, True),
]


def _quote(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _tag(kind: str, name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sprouts-customer-geography:pbi01:{kind}:{name}"))


def _m_type(data_type: str) -> str:
    return {
        "string": "type text",
        "double": "type number",
        "int64": "Int64.Type",
        "boolean": "type logical",
    }[data_type]


def _column_tmdl(table_name: str, column: tuple[str, str, str, str | None, bool, bool]) -> str:
    name, data_type, _source_name, data_category, is_key, is_hidden = column
    lines = [
        f"\tcolumn {_quote(name)}",
        f"\t\tdataType: {data_type}",
    ]
    if is_key:
        lines.append("\t\tisKey")
    if is_hidden:
        lines.append("\t\tisHidden")
    if data_type in {"double", "int64"}:
        lines.append(f"\t\tformatString: {'0.00' if data_type == 'double' else '#,0'}")
    lines.extend([
        f"\t\tlineageTag: {_tag('column', table_name + ':' + name)}",
        "\t\tsummarizeBy: none",
        f"\t\tsourceColumn: {name}",
    ])
    if data_category:
        lines.append(f"\t\tdataCategory: {data_category}")
    lines.append("\n\t\tannotation SummarizationSetBy = Automatic")
    return "\n".join(lines)


def _csv_table(table_name: str, columns: list[tuple[str, str, str, str | None, bool, bool]], token: str) -> str:
    rename_pairs = ", ".join(f'{{"{source}", "{name}"}}' for name, _dtype, source, _cat, _key, _hidden in columns)
    type_pairs = ", ".join(f'{{"{name}", {_m_type(dtype)}}}' for name, dtype, _source, _cat, _key, _hidden in columns)
    blocks = [
        f"/// Authoritative protected-local MODEL-13 presentation output; presentation typing and labels only.",
        f"table {_quote(table_name)}",
        f"\tlineageTag: {_tag('table', table_name)}",
        "",
    ]
    blocks.extend(_column_tmdl(table_name, column) + "\n" for column in columns)
    blocks.extend([
        f"\tpartition {_quote(table_name)} = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\tlet",
        f'\t\t\t\t\tSource = Csv.Document(File.Contents("{token}"), [Delimiter = ",", Columns = {len(columns)}, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "\t\t\t\t\t#\"Promoted Headers\" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f"\t\t\t\t\t#\"Renamed Columns\" = Table.RenameColumns(#\"Promoted Headers\", {{{rename_pairs}}}, MissingField.Error),",
        f"\t\t\t\t\t#\"Typed Columns\" = Table.TransformColumnTypes(#\"Renamed Columns\", {{{type_pairs}}}, \"en-US\")",
        "\t\t\t\tin",
        "\t\t\t\t\t#\"Typed Columns\"",
        "",
        "\tannotation PBI_NavigationStepName = Navigation",
        "",
        "\tannotation PBI_ResultType = Table",
        "",
    ])
    return "\n".join(blocks)


def _metric_selector() -> str:
    return f"""/// Disconnected presentation selector; no analytical scoring logic.
table 'Metric Selector'
\tlineageTag: {_tag('table', 'Metric Selector')}

\tcolumn Metric
\t\tdataType: string
\t\tlineageTag: {_tag('column', 'Metric Selector:Metric')}
\t\tsummarizeBy: none
\t\tsourceColumn: Metric
\t\tsortByColumn: 'Sort Order'

\t\tannotation SummarizationSetBy = Automatic

\tcolumn 'Sort Order'
\t\tdataType: int64
\t\tisHidden
\t\tformatString: 0
\t\tlineageTag: {_tag('column', 'Metric Selector:Sort Order')}
\t\tsummarizeBy: none
\t\tsourceColumn: Sort Order

\t\tannotation SummarizationSetBy = Automatic

\tpartition 'Metric Selector' = m
\t\tmode: import
\t\tsource =
\t\t\t\t#table(
\t\t\t\t\ttype table [Metric = text, Sort Order = Int64.Type],
\t\t\t\t\t{{
\t\t\t\t\t\t{{"Customer Fit", 1}},
\t\t\t\t\t\t{{"Household Opportunity", 2}},
\t\t\t\t\t\t{{"Modeled Target Mass", 3}}
\t\t\t\t\t}}
\t\t\t\t)

\tannotation PBI_NavigationStepName = Navigation

\tannotation PBI_ResultType = Table
"""


def _measure(name: str, expression: str, format_string: str | None = None, description: str | None = None) -> str:
    lines: list[str] = []
    if description:
        lines.append(f"\t/// {description}")
    if "\n" in expression:
        lines.append(f"\tmeasure {_quote(name)} = ```")
        lines.extend(f"\t\t{line}" if line else "" for line in expression.splitlines())
        lines.append("\t\t```")
    else:
        lines.append(f"\tmeasure {_quote(name)} = {expression}")
    if format_string:
        lines.append(f"\t\tformatString: {format_string}")
    lines.append(f"\t\tlineageTag: {_tag('measure', name)}")
    return "\n".join(lines)


def _report_measures() -> str:
    measures = [
        ("Total Tracts", "COUNTROWS('Michigan Tracts')", "#,0", "Statewide tract count after report filters."),
        ("Computable Tracts", "CALCULATE(COUNTROWS('Michigan Tracts'), 'Michigan Tracts'[Computability Status] = \"MODEL_SCORE_COMPUTABLE\")", "#,0", "Tracts with authoritative MODEL-13 scores."),
        ("Noncomputable Tracts", "[Total Tracts] - [Computable Tracts]", "#,0", "Tracts explicitly noncomputable in MODEL-13."),
        ("Support-Truncated Tracts", "CALCULATE(COUNTROWS('Michigan Tracts'), 'Michigan Tracts'[Any Support Truncation] = TRUE())", "#,0", "Tracts with descriptive boundary support truncation."),
        ("Selected Metric Value", """VAR MetricName = SELECTEDVALUE('Metric Selector'[Metric], \"Customer Fit\")
RETURN
    SWITCH(
        MetricName,
        \"Customer Fit\", AVERAGE('Michigan Tracts'[Customer Fit Percentile]),
        \"Household Opportunity\", AVERAGE('Michigan Tracts'[Household Opportunity]),
        \"Modeled Target Mass\", AVERAGE('Michigan Tracts'[Modeled Target Mass Percentile]),
        AVERAGE('Michigan Tracts'[Customer Fit Percentile])
    )""", "0.00", "Presentation-only switch across distinct authoritative MODEL-13 fields."),
        ("Selected Metric Label", "SELECTEDVALUE('Metric Selector'[Metric], \"Customer Fit\")", None, "Current map metric label."),
        ("Customer Fit", "AVERAGE('Michigan Tracts'[Customer Fit])", "0.0000", "Authoritative MODEL-13 customer-fit proxy."),
        ("Customer Fit Statewide Rank", "SELECTEDVALUE('Michigan Tracts'[Customer Fit Statewide Rank])", "#,0", None),
        ("Customer Fit Percentile", "AVERAGE('Michigan Tracts'[Customer Fit Percentile])", "0.0", None),
        ("Household Opportunity", "AVERAGE('Michigan Tracts'[Household Opportunity])", "#,0.00", "Authoritative MODEL-13 household opportunity."),
        ("Modeled Target Mass", "AVERAGE('Michigan Tracts'[Modeled Target Mass])", "#,0.00", "Authoritative MODEL-13 modeled target mass."),
        ("Modeled Target Mass Statewide Rank", "SELECTEDVALUE('Michigan Tracts'[Modeled Target Mass Statewide Rank])", "#,0", None),
        ("Modeled Target Mass Percentile", "AVERAGE('Michigan Tracts'[Modeled Target Mass Percentile])", "0.0", None),
        ("Member Count 3 Mile", "SELECTEDVALUE('Michigan Tracts'[Member Count 3 Mile])", "#,0", None),
        ("Member Count 5 Mile", "SELECTEDVALUE('Michigan Tracts'[Member Count 5 Mile])", "#,0", None),
        ("Member Count 7 Mile", "SELECTEDVALUE('Michigan Tracts'[Member Count 7 Mile])", "#,0", None),
        ("Support Completeness 3 Mile", "AVERAGE('Michigan Tracts'[Support Completeness 3 Mile])", "0.0%", None),
        ("Support Completeness 5 Mile", "AVERAGE('Michigan Tracts'[Support Completeness 5 Mile])", "0.0%", None),
        ("Support Completeness 7 Mile", "AVERAGE('Michigan Tracts'[Support Completeness 7 Mile])", "0.0%", None),
        ("Support Truncation State", "IF(SELECTEDVALUE('Michigan Tracts'[Any Support Truncation], FALSE()), \"Boundary support truncated\", \"No boundary support truncation\")", None, None),
        ("Computability Detail", "SELECTEDVALUE('Michigan Tracts'[Computability Status], \"Multiple states\")", None, None),
        ("QA / Missingness Detail", "SELECTEDVALUE('Michigan Tracts'[QA / Missingness Status], \"Multiple categories\")", None, None),
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
    measure_text = "\n\n".join(_measure(*measure) for measure in measures)
    return f"""/// Light report presentation measures only; all analytical values remain MODEL-13 authoritative.
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
\t\tsource = #table(type table [Anchor = text], {{{{"PBI-01"}}}})

\tannotation PBI_NavigationStepName = Navigation

\tannotation PBI_ResultType = Table
"""


def write_semantic_model(repository_root: Path) -> None:
    definition = repository_root / "powerbi" / "pbi01" / "project" / "MICustomerGeography.SemanticModel" / "definition"
    tables = definition / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    documents = {
        "Michigan Tracts.tmdl": _csv_table("Michigan Tracts", TRACT_COLUMNS, "__PBI01_TRACT_CSV__"),
        "Seed Context.tmdl": _csv_table("Seed Context", SEED_COLUMNS, "__PBI01_SEED_CSV__"),
        "Metric Selector.tmdl": _metric_selector(),
        "Report Measures.tmdl": _report_measures(),
    }
    for filename, content in documents.items():
        (tables / filename).write_text(content.rstrip() + "\n", encoding="utf-8")
    model_path = definition / "model.tmdl"
    model = model_path.read_text(encoding="utf-8").rstrip()
    refs = "\n\n".join(f"ref table {_quote(name)}" for name in ("Michigan Tracts", "Seed Context", "Metric Selector", "Report Measures"))
    model = model.split("\nref table ", 1)[0].rstrip() + "\n\n" + refs + "\n"
    model_path.write_text(model, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic PBI-01 TMDL semantic-model definitions")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    write_semantic_model(args.repository_root.resolve())
    print('{"state":"READY","tables":4,"protected_paths_embedded":false}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
