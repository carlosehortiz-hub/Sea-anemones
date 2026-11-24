"""Stage 2 - canonicalize: verbatim CSVs + curated mappings -> canonical tables."""

from __future__ import annotations

import csv
import hashlib
import logging

import pandas as pd

from anemone_kg.canonical.build import CanonicalBuilder, Inputs, Ledger
from anemone_kg.canonical.rules import RULES
from anemone_kg.cli import stage
from anemone_kg.config import Config
from anemone_kg.logs import log_counts

log = logging.getLogger(__name__)


def canonical_dir(cfg: Config):
    d = cfg.path("processed") / "canonical"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_canonical(cfg: Config) -> tuple[dict[str, pd.DataFrame], Ledger, Inputs]:
    inp = Inputs.load(cfg.path("interim"), cfg.path("mappings"))
    sha = hashlib.sha256(cfg.pdf.read_bytes()).hexdigest()
    builder = CanonicalBuilder(inp, cfg.source, sha)
    return builder.build(), builder.ledger, inp


def _flow(inp: Inputs, t: dict[str, pd.DataFrame]) -> list[tuple[str, int, int, int, str]]:
    """(flow, n_in, n_out, n_merged, note) - record conservation per source table."""
    occ, ident, dist = t["occurrence"], t["identification"], t["distribution"]
    n_cells = len(inp.t1_cells)
    n_new = int((inp.t1_cells["code"] == "N").sum())
    return [
        (
            "Table 2 specimens -> occurrence",
            len(inp.t2),
            int((occ.record_source == "table2").sum()),
            0,
            "one occurrence per specimen",
        ),
        (
            "Table 3 specimens -> occurrence",
            len(inp.t3),
            int((occ.record_source == "table3").sum()),
            0,
            "one occurrence per specimen",
        ),
        (
            "Table 1 codes -> distribution",
            n_cells,
            len(dist),
            n_new,
            "'N' codes folded into is_new_record of the '*' row (R_NEW_RECORD_FOLD)",
        ),
        (
            "Species accounts -> habitat_statement",
            len(inp.accounts),
            len(t["habitat_statement"]),
            0,
            "one statement per account",
        ),
        (
            "Specimens -> current identification",
            len(inp.t2) + len(inp.t3),
            int(ident.is_current.sum()),
            0,
            "one current identification per specimen",
        ),
    ]


def summary_markdown(t: dict[str, pd.DataFrame], ledger: Ledger, inp: Inputs) -> str:
    out = ["# Canonicalisation summary", "", "## Tables", "", "| table | rows |", "|---|---:|"]
    out += [f"| `{k}` | {len(v)} |" for k, v in t.items()]
    out += [
        "",
        "## Record flow (nothing is dropped silently)",
        "",
        "| flow | in | out | merged | dropped | note |",
        "|---|---:|---:|---:|---:|---|",
    ]
    out += [f"| {a} | {b} | {c} | {m} | {b - c - m} | {d} |" for a, b, c, m, d in _flow(inp, t)]
    out += ["", "## Rules applied", "", "| rule | count | definition |", "|---|---:|---|"]
    out += [f"| `{r}` | {n} | {RULES[r]} |" for r, n in sorted(ledger.counts.items())]
    out += ["", "## Individual changes and gaps", "", "| rule | source | detail |", "|---|---|---|"]
    out += [f"| `{e['rule_id']}` | {e['source_ref']} | {e['detail']} |" for e in ledger.events]
    cw = inp.crosswalk
    out += ["", "## Crosswalk rows not applied", ""]
    for status, label in (
        ("needs_review", "awaiting review"),
        ("rejected", "reviewed, kept unlinked"),
    ):
        out += [
            f"- {label}: `{r.verbatim_key}` -> `{r.table1_locality_col_id}`? {r.note}"
            for r in cw[cw.status == status].itertuples()
        ]
    if not len(cw[cw.status != "accepted"]):
        out.append("- none")
    taxa = t["taxon"]
    out += ["", "## Taxa by role", ""]
    for role in ("table1", "table2", "table3_current", "table3_previous", "species_account"):
        out.append(f"- `{role}`: {int(taxa.name_roles.str.contains(role).sum())}")
    only_prev = taxa[taxa.name_roles == "table3_previous"]["scientific_name"].tolist()
    out.append(
        f"- names used only as superseded identifications ({len(only_prev)}): "
        + ", ".join(only_prev)
    )
    out.append("")
    return "\n".join(out)


@stage("canonicalize")
def canonicalize(cfg: Config) -> None:
    tables, ledger, inp = build_canonical(cfg)
    out = canonical_dir(cfg)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    for label, n_in, n_out, merged, note in _flow(inp, tables):
        log_counts(log, f"canonicalize:{label}", n_in, n_out, note, merged=merged)
    for name, df in tables.items():
        log.info("[canonicalize] %s: %d rows", name, len(df))
    (cfg.path("reports") / "canonical_summary.md").write_text(
        summary_markdown(tables, ledger, inp), encoding="utf-8"
    )
