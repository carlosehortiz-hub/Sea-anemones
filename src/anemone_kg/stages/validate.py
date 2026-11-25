"""Stage 4 - validate: Pandera schemas + cross-table rules; stop on critical errors.

Runs before RDF generation. Writes reports/data_quality.md (for people) and
reports/data_quality.json (for code: the README and the manuscript read their
numbers from it). The report is written *before* failing, so a failed run
still explains itself.
"""

from __future__ import annotations

import json
import logging

import pandas as pd
import pandera.pandas as pa

from anemone_kg.audit import second_reading
from anemone_kg.cli import stage
from anemone_kg.config import Config
from anemone_kg.dq import crosstable
from anemone_kg.dq.rules import RULES, Rule, Tables, completeness
from anemone_kg.dq.schemas import TABLE_CLASS, dataframe_schema, load_table, schema_view
from anemone_kg.stages.canonicalize import canonical_dir

log = logging.getLogger(__name__)
MAX_ROWS_SHOWN = 25


class DataQualityError(RuntimeError):
    """At least one critical check failed."""


def load_tables(cfg: Config) -> Tables:
    sv = schema_view(str(cfg.root / cfg.raw["paths"]["schema"]))
    canon = canonical_dir(cfg)
    return {n: load_table(sv, c, canon / f"{n}.csv") for n, c in TABLE_CLASS.items()}


def run_schemas(cfg: Config, tables: Tables) -> pd.DataFrame:
    """One row per (table, failing check, value) - empty when every table conforms."""
    sv = schema_view(str(cfg.root / cfg.raw["paths"]["schema"]))
    fails = []
    for name, cls in TABLE_CLASS.items():
        try:
            dataframe_schema(sv, cls).validate(tables[name], lazy=True)
        except pa.errors.SchemaErrors as e:
            fc = e.failure_cases.assign(table=name)
            fails.append(fc[["table", "column", "check", "failure_case", "index"]])
    cols = ["table", "column", "check", "failure_case", "index"]
    return pd.concat(fails, ignore_index=True) if fails else pd.DataFrame(columns=cols)


def schema_check_count(cfg: Config) -> int:
    sv = schema_view(str(cfg.root / cfg.raw["paths"]["schema"]))
    n = 0
    for cls in TABLE_CLASS.values():
        for col in dataframe_schema(sv, cls).columns.values():
            n += 1 + len(col.checks) + int(not col.nullable) + int(col.unique)  # dtype + ...
    return n


def _humanise(df: pd.DataFrame, t: Tables) -> pd.DataFrame:
    """Swap opaque UUIDs for names so a reviewer can read the failing rows."""
    names = {
        **dict(zip(t["taxon"].taxon_id, t["taxon"].scientific_name, strict=True)),
        **dict(zip(t["locality"].locality_id, t["locality"].locality_name, strict=True)),
    }
    keep = [
        c
        for c in (
            "source_ref",
            "taxon_id",
            "locality_id",
            "area_id",
            "verbatim_name",
            "verbatim_event_date",
            "verbatim_locality",
            "catalog_number",
            "locality_name",
            "scientific_name",
            "n_current",
            "comment",
        )
        if c in df
    ]
    out = df[keep].copy()
    for c in ("taxon_id", "locality_id", "area_id"):
        if c in out:
            out[c] = out[c].map(lambda v: names.get(v, v))
    return out.rename(columns={"taxon_id": "taxon", "locality_id": "locality", "area_id": "area"})


def run_rules(tables: Tables) -> list[tuple[Rule, pd.DataFrame]]:
    return [(r, r.check(tables)) for r in RULES]


def to_markdown(
    tables: Tables,
    schema_fails: pd.DataFrame,
    n_schema_checks: int,
    results: list[tuple[Rule, pd.DataFrame]],
    comp: pd.DataFrame,
) -> str:
    crit = [(r, f) for r, f in results if r.severity == "critical"]
    warn = [(r, f) for r, f in results if r.severity == "warning"]
    n_crit_fail = sum(1 for _, f in crit if len(f)) + int(len(schema_fails) > 0)
    status = "PASS" if n_crit_fail == 0 else "FAIL"
    out = [
        "# Data-quality report",
        "",
        f"**Status: {status}** - {len(tables)} canonical tables, "
        f"{sum(len(df) for df in tables.values())} rows.",
        "",
        "| check family | checks | failing |",
        "|---|---:|---:|",
        f"| Column-level (Pandera, generated from LinkML) | {n_schema_checks} | "
        f"{len(schema_fails)} values |",
        f"| Cross-table critical rules | {len(crit)} | {sum(1 for _, f in crit if len(f))} |",
        f"| Cross-table warnings | {len(warn)} | {sum(1 for _, f in warn if len(f))} rules, "
        f"{sum(len(f) for _, f in warn)} rows |",
        "",
        "Critical failures stop the pipeline before RDF generation. Warnings are "
        "reported with their rows and never altered.",
        "",
        "## Rules",
        "",
        "| id | severity | dimension | rule | failing rows |",
        "|---|---|---|---|---:|",
    ]
    out += [
        f"| {r.rule_id} | {r.severity} | {r.dimension} | {r.description} | {len(f)} |"
        for r, f in results
    ]
    if len(schema_fails):
        out += [
            "",
            "## Column-level failures",
            "",
            schema_fails.head(MAX_ROWS_SHOWN).to_markdown(index=False),
        ]
    out += ["", "## Failing rows", ""]
    for r, f in results:
        if not len(f):
            continue
        h = _humanise(f, tables)
        out += [
            f"### {r.rule_id} - {r.description} ({len(f)})",
            "",
            h.head(MAX_ROWS_SHOWN).to_markdown(index=False),
            "",
        ]
        if len(f) > MAX_ROWS_SHOWN:
            out.append(f"... {len(f) - MAX_ROWS_SHOWN} more rows not shown.\n")
    incomplete = comp[comp.pct < 100].sort_values(["table", "pct"])
    out += [
        "## Completeness (columns below 100 %)",
        "",
        "Optional fields: a gap here is information about the source, not an error.",
        "",
        incomplete.to_markdown(index=False),
        "",
    ]
    return "\n".join(out)


def to_json(
    tables: Tables,
    schema_fails: pd.DataFrame,
    n_schema_checks: int,
    results: list[tuple[Rule, pd.DataFrame]],
) -> dict:
    return {
        "status": "pass"
        if not len(schema_fails) and not any(len(f) for r, f in results if r.severity == "critical")
        else "fail",
        "rows": {n: len(df) for n, df in tables.items()},
        "schema_checks": n_schema_checks,
        "schema_failures": len(schema_fails),
        "rules": [
            {
                "id": r.rule_id,
                "severity": r.severity,
                "dimension": r.dimension,
                "description": r.description,
                "failing_rows": len(f),
            }
            for r, f in results
        ],
    }


@stage("validate")
def validate(cfg: Config) -> None:
    tables = load_tables(cfg)
    schema_fails = run_schemas(cfg, tables)
    n_checks = schema_check_count(cfg)
    results = run_rules(tables)
    comp = completeness(tables)
    reports = cfg.path("reports")
    (reports / "data_quality.md").write_text(
        to_markdown(tables, schema_fails, n_checks, results, comp), encoding="utf-8"
    )
    summary = to_json(tables, schema_fails, n_checks, results)
    crosswalk = pd.read_csv(cfg.path("mappings") / "locality_crosswalk.csv")
    review = crosstable.classify(tables, crosswalk)
    sens = crosstable.sensitivity(tables, crosswalk)
    cells = crosstable.cell_support(tables)
    (reports / "cross_table_review.md").write_text(
        crosstable.to_markdown(review, sens, cells), encoding="utf-8"
    )
    review.to_csv(reports / "cross_table_review.csv", index=False)
    summary["cross_table"] = {
        "rows": len(review),
        "by_cause": review.cause.value_counts().sort_index().to_dict(),
        "by_rule_cause": {
            f"{r}:{c}": int(n) for (r, c), n in review.groupby(["rule", "cause"]).size().items()
        },
        "rests_on_curated_link": int(review.rests_on_curated_link.sum()),
        "shift_pairs": int(review.shift_pair.sum()),
        "sensitivity": sens.set_index("scenario").to_dict(orient="index"),
        "uncertain_links": sens.attrs["uncertain_links"],
        "cells": len(cells),
        "cell_support": cells.support.value_counts().sort_index().to_dict(),
        "cell_support_by_region": pd.crosstab(cells.region, cells.support).to_dict(orient="index"),
    }
    census = second_reading.audit(cfg.pdf, cfg.path("interim"))
    (reports / "extraction_audit.md").write_text(
        second_reading.to_markdown(census), encoding="utf-8"
    )
    (reports / "extraction_audit.json").write_text(
        json.dumps(census, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    n_census = second_reading.n_disagreements(census)
    log.info("[validate] extraction census: %d disagreements", n_census)
    summary["extraction_census"] = {
        k: {kk: vv for kk, vv in v.items() if kk != "disagreements"}
        for k, v in census.items()
        if k.startswith("table")
    }
    summary["extraction_census"]["disagreements"] = n_census
    if n_census:
        summary["status"] = "fail"
    (reports / "data_quality.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for r, f in results:
        (log.error if r.severity == "critical" and len(f) else log.warning if len(f) else log.info)(
            "[validate] %s %s: %d", r.rule_id, r.severity, len(f)
        )
    if summary["status"] != "pass":
        failed = [r.rule_id for r, f in results if r.severity == "critical" and len(f)]
        raise DataQualityError(
            f"critical data-quality failures: rules {failed}, {n_census} extraction-census "
            "disagreements (reports/extraction_audit.md), "
            f"{len(schema_fails)} column-level failures - see reports/data_quality.md"
        )
    log.info("[validate] PASS: %d column checks, %d rules", n_checks, len(results))
