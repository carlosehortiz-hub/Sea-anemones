"""Stage 1 - extract: PDF -> verbatim tidy CSVs in data/interim/ + a summary report."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from anemone_kg.cli import stage
from anemone_kg.config import Config
from anemone_kg.extract.accounts import extract_accounts
from anemone_kg.extract.tables import TABLE2, TABLE3, extract_fixed_table, extract_table1
from anemone_kg.logs import log_counts

log = logging.getLogger(__name__)

OUTPUTS = {
    "table1_taxa": "52 taxon rows of Table 1",
    "table1_localities": "27 locality columns of Table 1",
    "table1_cells": "one row per code in a Table 1 cell (taxon x locality x code)",
    "table1_legend": "codes and their meaning, from the Table 1 legend",
    "table2_specimens": "128 specimens collected in the study (Appendix 1)",
    "table3_mohbr_specimens": "84 MOHBR collection specimens examined (Appendix 2)",
    "species_accounts": "26 species accounts: heading, authority, habitat paragraph",
}


def run_extraction(pdf: Path) -> dict[str, pd.DataFrame]:
    t1 = extract_table1(pdf)
    return {
        "table1_taxa": t1["taxa"],
        "table1_localities": t1["localities"],
        "table1_cells": t1["cells"],
        "table1_legend": t1["legend"],
        "table2_specimens": extract_fixed_table(pdf, TABLE2),
        "table3_mohbr_specimens": extract_fixed_table(pdf, TABLE3),
        "species_accounts": extract_accounts(pdf),
    }


def _names(s: pd.Series) -> set[str]:
    return {x.strip() for x in s.dropna() if x.strip()}


def summary_markdown(frames: dict[str, pd.DataFrame]) -> str:
    """A factual summary for human review. Observations, not corrections."""
    t1, cells = frames["table1_taxa"], frames["table1_cells"]
    loc, legend = frames["table1_localities"], frames["table1_legend"]
    t2, t3, acc = (
        frames["table2_specimens"],
        frames["table3_mohbr_specimens"],
        frames["species_accounts"],
    )

    t1_names = _names(t1["name_text"])
    lines = ["# Extraction summary", "", "| file | rows | content |", "|---|---:|---|"]
    lines += [f"| `{k}.csv` | {len(frames[k])} | {v} |" for k, v in OUTPUTS.items()]

    used = set(cells["code"])
    lines += ["", "## Table 1", ""]
    lines.append(
        f"- {t1['row_no'].nunique()} taxon rows, {len(loc)} locality columns "
        f"({int(loc['sampled_in_study'].sum())} in bold = sampled in this study: "
        f"{', '.join(loc.loc[loc['sampled_in_study'], 'verbatim_locality'])})."
    )
    lines.append(
        f"- {len(cells)} codes in {cells.groupby(['row_no', 'locality_col_id']).ngroups} "
        "non-empty cells. Codes per kind:"
    )
    counts = cells["code"].value_counts()
    for r in legend.itertuples():
        if r.code in {"?", "†"}:  # printed after taxon names, not inside cells
            continue
        lines.append(f"  - `{r.code}` {r.meaning}: **{counts.get(r.code, 0)}**")
    unused = sorted(set(legend["code"]) - used - {"?", "†"})
    if unused:
        lines.append(f"- Legend codes never used in a cell: {unused}")
    empty = t1.loc[~t1["row_no"].isin(cells["row_no"]), "verbatim_name"].tolist()
    lines.append(f"- Taxon rows with no code in any cell ({len(empty)}): {', '.join(empty)}")
    lines.append(
        f"- Flags: † (invalid) on {', '.join(t1.loc[t1.flag_invalid, 'verbatim_name'])}; "
        f"? (doubtful) on {', '.join(t1.loc[t1.flag_doubtful, 'verbatim_name'])}."
    )
    new = cells.loc[cells.code == "N"].merge(t1, on="row_no").merge(loc, on="locality_col_id")
    lines.append(
        "- New records (N): "
        + "; ".join(f"{r.verbatim_name} @ {r.verbatim_locality}" for r in new.itertuples())
    )

    lines += ["", "## Tables 2 and 3", ""]
    lines.append(
        f"- Table 2: {len(t2)} specimens, {t2['verbatim_species'].nunique()} distinct names, "
        f"{t2['verbatim_locality'].nunique()} localities in {t2['national_park'].nunique()} "
        "parks/areas."
    )
    lines.append(
        f"- Table 3: {len(t3)} specimens, {t3['previous_identification'].nunique()} previous and "
        f"{t3['current_identification'].nunique()} current identifications; "
        f"{int((t3['previous_identification'] != t3['current_identification']).sum())} specimens "
        "were re-identified."
    )
    lines += ["", "## Names that differ between sources (to resolve in steps 2-3)", ""]
    for label, names in (
        ("Table 2 species", _names(t2["verbatim_species"])),
        ("Table 3 current identification", _names(t3["current_identification"])),
        ("Species account headings", _names(acc["name_text"])),
    ):
        missing = sorted(names - t1_names)
        lines.append(f"- {label} not in Table 1 ({len(missing)}): {', '.join(missing) or '-'}")

    order_t1 = sorted(set(t1["verbatim_order"].str.replace("Order ", "", regex=False)))
    order_acc = sorted({o.split()[1] for o in acc["verbatim_order"]})
    lines.append(f"- Orders in Table 1: {order_t1}; in species accounts: {order_acc}")
    lines.append("")
    return "\n".join(lines)


@stage("extract")
def extract(cfg: Config) -> None:
    frames = run_extraction(cfg.pdf)
    out_dir = cfg.path("interim")
    for name, df in frames.items():
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8")
        log_counts(log, f"extract:{name}", len(df), len(df), str(path.relative_to(cfg.root)))
    report = cfg.path("reports") / "extraction_summary.md"
    report.write_text(summary_markdown(frames), encoding="utf-8")
    log.info("wrote %s", report.relative_to(cfg.root))
