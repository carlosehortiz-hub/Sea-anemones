"""Extraction of Tables 1-3 of González-Muñoz et al. (2016) into tidy, verbatim CSVs.

Extraction is deliberately *verbatim*: no spelling correction, no date or
coordinate parsing, no name matching. Every row carries ``source_page`` and a
``source_ref`` locator. Interpretation happens in the canonicalisation stage,
where every transformation is listed in the source-to-canonical mapping table.

Tables
------
Table 1 (pp. 3-10)
    A presence matrix, 52 taxon rows x 27 locality columns, printed sideways
    and split in two column blocks (pp. 3-6 and pp. 7-10) that repeat the same
    rows. A cell holds comma-separated codes defined in the table legend.
    Bold column headers mark the localities sampled by the authors.
Table 2 (Appendix 1, pp. 26-28)
    128 specimens collected in this study, with field code, MOHBR catalogue
    number, coordinates in degrees-minutes-seconds.
Table 3 (Appendix 2, pp. 29-31)
    84 specimens examined in the MOHBR collection, with previous and current
    identification, date and collector.
"""

from __future__ import annotations

import itertools
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pdfplumber

from anemone_kg.extract.pdf_layout import (
    Word,
    assign_column,
    build_columns,
    group_lines,
    join_text,
)

log = logging.getLogger(__name__)

X_TOL = 1.5  # pdfplumber x_tolerance: 3 (default) merges words in this font
RUNNING_HEADER_X = 740.0  # rotated running header/footer on Table 1 pages
ROW_NUMBER_MAX_X = 72.0
BOLD_FONT_MARK = "sxAdvTT"  # bold face in this PDF; marks sampled localities

TABLE1_CODES = frozenset("abcdefghij*N")
TABLE1_BLOCKS = {"A": range(2, 6), "B": range(6, 10)}  # 0-based page indices
N_TABLE1_ROWS = 52


class ExtractionError(RuntimeError):
    """Raised when the layout does not match what the parser can read reliably."""


def _words(page: pdfplumber.page.Page) -> list[Word]:
    return page.extract_words(x_tolerance=X_TOL, extra_attrs=["fontname"])


def _is_row_number(w: Word) -> bool:
    return w["x0"] < ROW_NUMBER_MAX_X and w["text"].isdigit()


# --------------------------------------------------------------------------- Table 1


@dataclass
class _T1Row:
    row_no: int
    page: int
    top: float
    name_words: list[Word] = field(default_factory=list)
    cell_words: list[Word] = field(default_factory=list)
    order: str = ""
    family: str = ""


def _table1_header(words: list[Word]) -> tuple[list[Word], list[Word], float]:
    """Split the header area into region labels and column-header words."""
    species = next(w for w in words if w["text"] == "Species")
    first_order = min(w["top"] for w in words if w["text"] == "Order")
    region_top = min(w["top"] for w in words if w["text"] in {"West", "East", "Oceanic", "Central"})
    in_hdr = [
        w
        for w in words
        if w["x0"] > species["x1"] + 20
        and w["x0"] < RUNNING_HEADER_X
        and region_top - 1 <= w["top"] < first_order - 2
    ]
    regions = [w for w in in_hdr if abs(w["top"] - region_top) < 1.5]
    cols = [w for w in in_hdr if w["top"] > region_top + 5]
    return regions, cols, species["x0"]


def _region_labels(region_words: list[Word]) -> list[tuple[float, str]]:
    labels: list[tuple[float, str]] = []
    for w in sorted(region_words, key=lambda w: w["x0"]):
        if labels and w["x0"] - labels[-1][2] < 6:
            x, text, _ = labels[-1]
            labels[-1] = (x, f"{text} {w['text']}", w["x1"])
        else:
            labels.append((w["x0"], w["text"], w["x1"]))
    return [(x, t) for x, t, _ in labels]


def extract_table1(pdf_path: Path) -> dict[str, pd.DataFrame]:
    """Return ``taxa``, ``localities``, ``cells`` and ``legend`` frames for Table 1."""
    pdf = pdfplumber.open(pdf_path)
    all_cells: list[dict] = []
    localities: list[dict] = []
    taxa_by_block: dict[str, list[_T1Row]] = {}
    legend_words: list[Word] = []

    for block, pages in TABLE1_BLOCKS.items():
        first_words = _words(pdf.pages[pages.start])
        regions, header_words, _ = _table1_header(first_words)
        columns = build_columns(header_words)
        starts = [c.x0 for c in columns]
        labels = _region_labels(regions)
        bold_x = {round(w["x0"]) for w in header_words if BOLD_FONT_MARK in w["fontname"]}
        for c in columns:
            region = [t for x, t in labels if x <= c.x0 + 2][-1]
            localities.append(
                {
                    "locality_col_id": f"T1{block}{c.index + 1:02d}",
                    "block": block,
                    "column_index": c.index + 1,
                    "verbatim_locality": c.header,
                    "region": region,
                    "sampled_in_study": any(abs(c.x0 - b) <= 2 for b in bold_x),
                    "source_page": pages.start + 1,
                    "source_ref": f"Table 1, header, block {block} col {c.index + 1}",
                }
            )

        rows: list[_T1Row] = []
        order = family = ""
        for pidx in pages:
            words = [w for w in _words(pdf.pages[pidx]) if w["x0"] < RUNNING_HEADER_X]
            title_top = min(w["top"] for w in words if w["text"] == "Table")
            body_top = (
                max(w["bottom"] for w in header_words) if pidx == pages.start else title_top + 8
            )
            # The legend under the last rows starts with "Localities sampled ...".
            stop = min(
                (
                    w["top"]
                    for w in words
                    if w["text"] == "Localities" and w["x0"] < ROW_NUMBER_MAX_X
                ),
                default=float("inf"),
            )
            if block == "A" and stop < float("inf"):
                legend_words.extend(w for w in words if w["top"] >= stop - 4)
            body = [w for w in words if body_top + 2 < w["top"] < stop - 4]
            anchors = sorted((w for w in body if _is_row_number(w)), key=lambda w: w["top"])
            # Order/Family lines span the full width (their authority can overrun
            # into the first locality columns), so classify whole lines first.
            context_ids: set[int] = set()
            context_lines: list[list[Word]] = []
            for line in group_lines(w for w in body if not _is_row_number(w)):
                if line[0]["x0"] < starts[0] - 2 and line[0]["text"] in {"Order", "Family"}:
                    context_lines.append(line)
                    context_ids.update(id(w) for w in line)
            name_lines = sorted(
                context_lines
                + group_lines(
                    w
                    for w in body
                    if not _is_row_number(w)
                    and w["x0"] < starts[0] - 2
                    and id(w) not in context_ids
                ),
                key=lambda ln: ln[0]["top"],
            )
            # Walk name-column lines top-down; Order/Family lines update context,
            # other lines continue the latest row (or start one at its anchor).
            page_rows: list[_T1Row] = []
            for line in name_lines:
                top = line[0]["top"]
                first = line[0]["text"]
                if first in {"Order", "Family"}:
                    text = join_text(line)
                    if first == "Order":
                        order, family = text, ""
                    else:
                        family = text
                    continue
                anchor = next((a for a in anchors if abs(a["top"] - top) <= 3), None)
                if anchor is not None and not any(r.top == anchor["top"] for r in page_rows):
                    page_rows.append(
                        _T1Row(
                            int(anchor["text"]), pidx + 1, anchor["top"], order=order, family=family
                        )
                    )
                if not page_rows:
                    raise ExtractionError(
                        f"p{pidx + 1}: name line before any row: {join_text(line)!r}"
                    )
                if top - page_rows[-1].top > 14:
                    raise ExtractionError(
                        f"p{pidx + 1}: orphan name line {join_text(line)!r} under row "
                        f"{page_rows[-1].row_no}"
                    )
                page_rows[-1].name_words.extend(line)
            for w in body:
                if _is_row_number(w) or w["x0"] < starts[0] - 2 or id(w) in context_ids:
                    continue
                owner = [r for r in page_rows if r.top <= w["top"] + 3]
                if not owner or w["top"] - owner[-1].top > 14:
                    continue
                owner[-1].cell_words.append(w)
            rows.extend(page_rows)

        if [r.row_no for r in rows] != list(range(1, N_TABLE1_ROWS + 1)):
            raise ExtractionError(f"Table 1 block {block}: row numbers {[r.row_no for r in rows]}")
        taxa_by_block[block] = rows

        for r in rows:
            by_col: dict[int, list[Word]] = {}
            for w in r.cell_words:
                by_col.setdefault(assign_column(w["x0"], starts), []).append(w)
            for ci, ws in sorted(by_col.items()):
                verbatim = join_text(ws)
                codes = [c for c in re.split(r"[,\s]+", verbatim) if c]
                bad = [c for c in codes if c not in TABLE1_CODES]
                if bad:
                    raise ExtractionError(
                        f"Table 1 row {r.row_no} col {ci + 1}: unknown codes {bad} in {verbatim!r}"
                    )
                for code in codes:
                    all_cells.append(
                        {
                            "row_no": r.row_no,
                            "locality_col_id": f"T1{block}{ci + 1:02d}",
                            "cell_verbatim": verbatim,
                            "code": code,
                            "source_page": r.page,
                            "source_ref": f"Table 1, row {r.row_no}, block {block} col {ci + 1}",
                        }
                    )

    a, b = taxa_by_block["A"], taxa_by_block["B"]
    names_a = [_taxon_name(r.name_words) for r in a]
    names_b = [_taxon_name(r.name_words) for r in b]
    if names_a != names_b:
        diff = [
            (i + 1, x, y) for i, (x, y) in enumerate(zip(names_a, names_b, strict=True)) if x != y
        ]
        raise ExtractionError(f"Table 1 blocks disagree on taxon names: {diff}")

    taxa = pd.DataFrame(
        {
            "row_no": [r.row_no for r in a],
            "verbatim_name": [n["verbatim_name"] for n in names_a],
            "name_text": [n["name_text"] for n in names_a],
            "flag_invalid": [n["flag_invalid"] for n in names_a],
            "flag_doubtful": [n["flag_doubtful"] for n in names_a],
            "verbatim_order": [r.order for r in a],
            "verbatim_family": [r.family for r in a],
            "source_page": [r.page for r in a],
            "source_ref": [f"Table 1, row {r.row_no}" for r in a],
        }
    )
    return {
        "taxa": taxa,
        "localities": pd.DataFrame(localities),
        "cells": pd.DataFrame(all_cells),
        "legend": _parse_table1_legend(join_text(legend_words)),
    }


def _taxon_name(words: list[Word]) -> dict[str, object]:
    """Split a Table 1 name cell into text and legend flags.

    The dagger is set ~2 pt above the baseline, so reading order by ``top`` puts
    it first. In print, both flags always *follow* the name, so the verbatim form
    is rebuilt as name + flags. ``Phymactis sp.?`` keeps its ``?`` in the text as
    well as raising the flag, because there the mark is ambiguous between
    "doubtful record" and an open-nomenclature query; canonicalisation decides.
    """
    tokens = [w["text"] for w in words]
    invalid = "†" in tokens
    doubtful = any(t == "?" or t.endswith("?") for t in tokens)
    text_tokens = [t for t in tokens if t not in {"†", "?"}]
    name_text = " ".join(text_tokens)
    flags = " ".join(f for f, on in (("†", invalid), ("?", "?" in tokens)) if on)
    return {
        "verbatim_name": f"{name_text} {flags}".strip(),
        "name_text": name_text.rstrip("?"),
        "flag_invalid": invalid,
        "flag_doubtful": doubtful,
    }


_LEGEND_SYMBOL = re.compile(r"\((\*|\?|†|N)\)\s*([^,(]+?)(?=,\s*\(|\.\s|$)")
_LEGEND_SOURCE = re.compile(r"\(([a-j])\)\s*(.+?)(?=,\s*\([a-j]\)|$)")


def _parse_table1_legend(text: str) -> pd.DataFrame:
    """Parse the legend under Table 1 into (code, kind, meaning) rows."""
    if "Citation of previous" not in text:
        raise ExtractionError(f"Table 1 legend not found in: {text[:120]!r}")
    head, tail = text.split("Citation of previous", 1)
    rows = [
        {"code": m.group(1), "kind": "flag", "meaning": m.group(2).strip()}
        for m in _LEGEND_SYMBOL.finditer(head)
    ]
    tail = tail.split(":", 1)[1].strip()
    rows += [
        {"code": m.group(1), "kind": "source", "meaning": m.group(2).strip()}
        for m in _LEGEND_SOURCE.finditer(tail)
    ]
    df = pd.DataFrame(rows)
    df["source_page"] = 6
    df["source_ref"] = "Table 1, legend"
    df.attrs["verbatim"] = text
    return df


# --------------------------------------------------------------------- Tables 2 and 3


@dataclass(frozen=True)
class _FixedTableSpec:
    name: str
    title: str
    columns: tuple[str, ...]
    implicit_first: str | None  # a left column without a header word (Table 3 'No.')
    n_rows: int


TABLE2 = _FixedTableSpec(
    "table2",
    "Table 2",
    (
        "no",
        "field_code",
        "mohbr_catalog",
        "verbatim_species",
        "national_park",
        "verbatim_locality",
        "verbatim_state",
        "verbatim_latitude",
        "verbatim_longitude",
    ),
    None,
    128,
)
TABLE3 = _FixedTableSpec(
    "table3",
    "Table 3",
    (
        "no",
        "mohbr_catalog",
        "previous_identification",
        "current_identification",
        "verbatim_state",
        "verbatim_locality",
        "verbatim_date",
        "verbatim_collector",
    ),
    "no",
    84,
)


def _table_pages(pdf: pdfplumber.PDF, title: str) -> list[int]:
    """Pages whose left-margin caption starts with e.g. ``Table 2`` (incl. continued)."""
    label, number = title.split()
    pages = []
    for i, page in enumerate(pdf.pages):
        ws = sorted(_words(page), key=lambda w: (round(w["top"]), w["x0"]))
        for a, b in itertools.pairwise(ws):
            if a["text"] == label and b["text"] == number and a["x0"] < ROW_NUMBER_MAX_X:
                pages.append(i)
                break
    if not pages:
        raise ExtractionError(f"{title} not found")
    return pages


def extract_fixed_table(pdf_path: Path, spec: _FixedTableSpec) -> pd.DataFrame:
    pdf = pdfplumber.open(pdf_path)
    pages = _table_pages(pdf, spec.title)
    first = _words(pdf.pages[pages[0]])
    title_top = next(w["top"] for w in first if w["text"] == "Table" and w["x0"] < ROW_NUMBER_MAX_X)
    first_anchor_top = min(w["top"] for w in first if _is_row_number(w) and w["top"] > title_top)
    header = [w for w in first if title_top + 5 < w["top"] < first_anchor_top - 6]
    starts = [c.x0 for c in build_columns(header)]
    if spec.implicit_first:
        starts = [0.0, *starts]
    if len(starts) != len(spec.columns):
        raise ExtractionError(
            f"{spec.title}: found {len(starts)} columns, expected {len(spec.columns)}: "
            f"{[c.header for c in build_columns(header)]}"
        )

    records: list[dict] = []
    for pidx in pages:
        words = _words(pdf.pages[pidx])
        t_top = next(w["top"] for w in words if w["text"] == "Table" and w["x0"] < ROW_NUMBER_MAX_X)
        anchors = sorted(
            (w for w in words if _is_row_number(w) and w["top"] > t_top), key=lambda w: w["top"]
        )
        # Table ends at the first left-margin word below the anchors that is not a row number.
        stop = min(
            (
                w["top"]
                for w in words
                if w["x0"] < ROW_NUMBER_MAX_X
                and not w["text"].isdigit()
                and w["top"] > anchors[-1]["top"]
            ),
            default=float("inf"),
        )
        body = [w for w in words if anchors[0]["top"] - 3 <= w["top"] < stop]
        cells: dict[int, dict[int, list[Word]]] = {int(a["text"]): {} for a in anchors}
        for w in body:
            owner = [a for a in anchors if a["top"] <= w["top"] + 3]
            if not owner or w["top"] - owner[-1]["top"] > 20:
                continue
            col = assign_column(w["x0"], starts)
            cells[int(owner[-1]["text"])].setdefault(col, []).append(w)
        for no, by_col in cells.items():
            rec = {name: join_text(by_col.get(i, [])) for i, name in enumerate(spec.columns)}
            rec["no"] = no
            rec["source_page"] = pidx + 1
            rec["source_ref"] = f"{spec.title}, row {no}"
            records.append(rec)

    df = pd.DataFrame(records)
    if df["no"].tolist() != list(range(1, spec.n_rows + 1)):
        raise ExtractionError(f"{spec.title}: row numbers are not 1..{spec.n_rows}")
    return df
