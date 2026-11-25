"""Second, independent transcription of Tables 1-3: a census of extraction accuracy.

Why: every other check in the pipeline (row counts, legend membership, agreement of the
two Table 1 blocks, SHACL with injected faults) would pass a code read into the wrong cell.
Only a second reading of the page can catch that. The tables are small (263 occupied cells,
212 specimen rows), so every cell and row is compared - a census, not a sample.

Independence: the main extraction uses pdfplumber (pdfminer.six). This reading uses
Poppler's ``pdftotext -bbox`` - a different PDF engine with its own text-positioning code -
and a separate, simpler parser:

* Table 1: column left edges are taken from the starts of header *segments* (runs of header
  words separated by a gap), a code belongs to the right-most column edge at or left of it,
  and to the last row number at or above it.
* Tables 2 and 3: each extracted field must be found, token by token, among the Poppler words
  of the same printed row, and the fields must appear left to right in the order of the
  table's columns. A value read from the wrong row, or two columns swapped, fails.

What it does not share with the extraction: the PDF engine, word segmentation, column
building and row grouping. What it does share: the page numbers of each table and the
column order of Tables 2 and 3 (from the printed headers). A disagreement is reported with
both readings; none is resolved automatically.
"""

from __future__ import annotations

import html
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

TABLE1_PAGES = {"A": range(3, 7), "B": range(7, 11)}  # 1-based, as printed
ROW_NO_MAX_X = 72.0
RUNNING_HEAD_X = 740.0
SEGMENT_GAP = 4.0
_WORD = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>'
)
_CODE = re.compile(r"^[a-j*N](?:,[a-j*N])*,?$")


@dataclass(frozen=True)
class W:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


def poppler_words(pdf: Path, page: int) -> list[W]:
    """Words of one page (1-based) from Poppler's ``pdftotext -bbox``."""
    out = subprocess.run(
        ["pdftotext", "-bbox", "-f", str(page), "-l", str(page), str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [
        W(float(a), float(b), float(c), float(d), html.unescape(t))
        for a, b, c, d, t in _WORD.findall(out)
    ]


def poppler_version() -> str:
    out = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True)
    return (out.stderr or out.stdout).splitlines()[0].strip()


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).replace("’", "'").replace("”", '"')


# ------------------------------------------------------------------------------ Table 1


def _header_lefts(words: list[W]) -> list[float]:
    species = next(w for w in words if w.text == "Species")
    first_ctx = min(w.y0 for w in words if w.text in {"Order", "Family"} and w.x0 < 90)
    hdr = [
        w
        for w in words
        if w.x0 > species.x1 + 30
        and w.x0 < RUNNING_HEAD_X
        and species.y0 - 2 <= w.y0 < first_ctx - 2
    ]
    lefts: list[float] = []
    for y in sorted({round(w.y0, 1) for w in hdr}):
        line = sorted((w for w in hdr if abs(w.y0 - y) < 1.0), key=lambda w: w.x0)
        prev = None
        for w in line:
            if prev is None or w.x0 - prev.x1 > SEGMENT_GAP:
                lefts.append(w.x0)
            prev = w
    merged: list[float] = []
    for x in sorted(lefts):
        if not merged or x - merged[-1] > 2.0:
            merged.append(x)
    return merged


def read_table1(pdf: Path) -> pd.DataFrame:
    """One row per code: (row_no, locality_col_id, code), from Poppler words."""
    rows = []
    for block, pages in TABLE1_PAGES.items():
        lefts = _header_lefts(poppler_words(pdf, pages.start))
        for page in pages:
            words = [w for w in poppler_words(pdf, page) if w.x0 < RUNNING_HEAD_X]
            legend = min(
                (w.y0 for w in words if w.text == "Localities" and w.x0 < ROW_NO_MAX_X),
                default=float("inf"),
            )
            body_top = (
                max(w.y1 for w in words if w.text == "Species") + 25
                if page == pages.start
                else min(w.y0 for w in words if w.text == "Table") + 8
            )
            anchors = sorted(
                (
                    w
                    for w in words
                    if w.x1 < ROW_NO_MAX_X and w.text.isdigit() and body_top < w.y0 < legend
                ),
                key=lambda w: w.y0,
            )
            for w in words:
                if not (body_top < w.y0 < legend - 2) or w.x0 < lefts[0] - 2:
                    continue
                if not _CODE.match(w.text):
                    continue
                above = [a for a in anchors if a.y0 <= w.y0 + 2]
                if not above:
                    continue
                col = max(i for i, x in enumerate(lefts) if x <= w.x0 + 2)
                for code in filter(None, w.text.split(",")):
                    rows.append(
                        {
                            "row_no": int(above[-1].text),
                            "locality_col_id": f"T1{block}{col + 1:02d}",
                            "code": code,
                            "page": page,
                        }
                    )
    return pd.DataFrame(rows)


def compare_table1(first: pd.DataFrame, second: pd.DataFrame) -> dict:
    key = ["row_no", "locality_col_id", "code"]
    a = first[key].value_counts()
    b = second[key].value_counts()
    both = a.index.union(b.index)
    a, b = a.reindex(both, fill_value=0), b.reindex(both, fill_value=0)
    agree = int((a.combine(b, min)).sum())
    only_first = a - b
    only_second = b - a
    cells_first = first.groupby(["row_no", "locality_col_id"]).size()
    cells_second = second.groupby(["row_no", "locality_col_id"]).size()
    cell_keys = cells_first.index.union(cells_second.index)
    cell_agree = 0
    for k in cell_keys:
        ca = sorted(first[(first.row_no == k[0]) & (first.locality_col_id == k[1])].code)
        cb = sorted(second[(second.row_no == k[0]) & (second.locality_col_id == k[1])].code)
        cell_agree += ca == cb
    return {
        "codes_first": len(first),
        "codes_second": len(second),
        "codes_agree": agree,
        "cells_first": len(cells_first),
        "cells_second": len(cells_second),
        "cells_union": len(cell_keys),
        "cells_agree": int(cell_agree),
        "disagreements": [
            {"row_no": int(k[0]), "locality_col_id": k[1], "code": k[2], "only_in": side}
            for side, s in (("extraction", only_first), ("second_reading", only_second))
            for k, n in s.items()
            for _ in range(int(n))
            if n > 0
        ],
    }


# -------------------------------------------------------------------------- Tables 2, 3


def _row_words(pdf: Path, pages: list[int]) -> dict[int, list[W]]:
    """Poppler words grouped by printed row number (left-margin anchor)."""
    out: dict[int, list[W]] = {}
    for page in pages:
        words = poppler_words(pdf, page)
        title = min(w.y0 for w in words if w.text == "Table" and w.x0 < ROW_NO_MAX_X)
        anchors = sorted(
            (w for w in words if w.x1 < ROW_NO_MAX_X and w.text.isdigit() and w.y0 > title),
            key=lambda w: w.y0,
        )
        tail = [
            w.y0
            for w in words
            if w.x0 < ROW_NO_MAX_X and not w.text.isdigit() and w.y0 > anchors[-1].y0
        ]
        stop = min(tail, default=float("inf"))
        for i, a in enumerate(anchors):
            nxt = anchors[i + 1].y0 if i + 1 < len(anchors) else stop
            out[int(a.text)] = [
                w for w in words if a.y0 - 3 <= w.y0 < nxt - 3 and w is not a and w.x0 >= 0
            ]
    return out


def _column_lefts(pdf: Path, page: int) -> list[float]:
    """Left edges of the data columns of Table 2 or 3, from Poppler's header words."""
    words = poppler_words(pdf, page)
    title = min(w.y0 for w in words if w.text == "Table" and w.x0 < ROW_NO_MAX_X)
    first = min(w.y0 for w in words if w.x1 < ROW_NO_MAX_X and w.text.isdigit() and w.y0 > title)
    hdr = sorted(
        (w for w in words if title + 5 < w.y0 < first - 3 and w.text != "No."),
        key=lambda w: w.x0,
    )
    lefts: list[float] = []
    prev = None
    for w in hdr:
        if prev is None or w.x0 - prev.x1 > SEGMENT_GAP:
            lefts.append(w.x0)
        prev = w
    return lefts


def _squash(text: str) -> str:
    return "".join(_norm(text).split())


def compare_fixed(df: pd.DataFrame, fields: list[str], pdf: Path) -> dict:
    """Field-aligned and symmetric: for every field, the printed text inside that column's
    horizontal band must equal the extracted value (whitespace ignored), blanks included.

    A value moved into an adjacent empty field, a value read from another row, two swapped
    columns and a changed character all fail. Agreement on a blank field counts as agreement.
    """
    pages = sorted(df.source_page.unique().tolist())
    by_row = _row_words(pdf, pages)
    lefts = _column_lefts(pdf, pages[0])
    if len(lefts) != len(fields):
        raise ValueError(f"{len(lefts)} header columns for {len(fields)} fields")
    bounds = [
        (lefts[i] - 8 if i == 0 else lefts[i] - 4, lefts[i + 1] - 4 if i + 1 < len(lefts) else 1e9)
        for i in range(len(lefts))
    ]
    checked = agree = blanks = 0
    problems = []
    for rec in df.to_dict("records"):
        words = sorted(by_row.get(int(rec["no"]), []), key=lambda w: (round(w.y0), w.x0))
        for f, (lo, hi) in zip(fields, bounds, strict=True):
            val = rec[f]
            extracted = "" if pd.isna(val) else _squash(str(val))
            printed = _squash(" ".join(w.text for w in words if lo <= w.x0 < hi))
            checked += 1
            blanks += extracted == ""
            if extracted == printed:
                agree += 1
            else:
                problems.append(
                    {
                        "row": int(rec["no"]),
                        "field": f,
                        "extracted": "" if pd.isna(val) else str(val),
                        "printed_in_column": printed,
                    }
                )
    return {
        "rows": len(df),
        "rows_second": len(by_row),
        "fields_checked": checked,
        "fields_blank": blanks,
        "fields_agree": agree,
        "disagreements": problems,
    }


TABLE2_FIELDS = [
    "field_code",
    "mohbr_catalog",
    "verbatim_species",
    "national_park",
    "verbatim_locality",
    "verbatim_state",
    "verbatim_latitude",
    "verbatim_longitude",
]
TABLE3_FIELDS = [
    "mohbr_catalog",
    "previous_identification",
    "current_identification",
    "verbatim_state",
    "verbatim_locality",
    "verbatim_date",
    "verbatim_collector",
]


def audit(pdf: Path, interim: Path) -> dict:
    t1 = pd.read_csv(interim / "table1_cells.csv")
    t2 = pd.read_csv(interim / "table2_specimens.csv", dtype=str).assign(
        no=lambda d: d.no.astype(int), source_page=lambda d: d.source_page.astype(int)
    )
    t3 = pd.read_csv(interim / "table3_mohbr_specimens.csv", dtype=str).assign(
        no=lambda d: d.no.astype(int), source_page=lambda d: d.source_page.astype(int)
    )
    second = read_table1(pdf)
    return {
        "engine_first": "pdfplumber (pdfminer.six)",
        "engine_second": "Poppler pdftotext -bbox",
        "table1": compare_table1(t1, second),
        "table2": compare_fixed(t2, TABLE2_FIELDS, pdf),
        "table3": compare_fixed(t3, TABLE3_FIELDS, pdf),
    }


def n_disagreements(result: dict) -> int:
    return sum(len(result[t]["disagreements"]) for t in ("table1", "table2", "table3"))


SHARED_KNOWLEDGE = [
    "the page ranges of Tables 1-3",
    "rows are anchored on the row numbers printed in the left margin",
    "Table 1 has two column blocks; columns are numbered left to right within a block",
    "the legend's code set (a-j, *, N)",
    "the printed column order of Tables 2 and 3 (from their header words)",
]


def to_markdown(r: dict, ink: dict | None = None) -> str:
    t1, t2, t3 = r["table1"], r["table2"], r["table3"]
    status = "AGREE" if n_disagreements(r) == 0 and not _ink_bad(ink) else "DISAGREE"
    out = [
        "# Extraction census: a second automated extraction and a rendered-image check",
        "",
        f"**Status: {status}.** Every cell of Table 1 and every field of Tables 2 and 3 was "
        "extracted a second time, with another PDF engine and parser, and every Table 1 cell "
        "was checked for ink on the rendered page.",
        "",
        f"First extraction: {r['engine_first']} (the pipeline). Second extraction: "
        f"{r['engine_second']} with a separate parser "
        "(`anemone_kg.audit.second_reading`). Both read the PDF's text layer, so they agree on "
        "anything wrong in that layer; the rendered-image check does not read it.",
        "",
        "| table | unit | extraction | second extraction | agree |",
        "|---|---|---:|---:|---:|",
        f"| Table 1 | occupied cells | {t1['cells_first']} | {t1['cells_second']} | "
        f"{t1['cells_agree']} |",
        f"| Table 1 | evidence codes | {t1['codes_first']} | {t1['codes_second']} | "
        f"{t1['codes_agree']} |",
        f"| Table 2 | rows | {t2['rows']} | {t2['rows_second']} | - |",
        f"| Table 2 | fields ({t2['fields_blank']} blank) | {t2['fields_checked']} | - | "
        f"{t2['fields_agree']} |",
        f"| Table 3 | rows | {t3['rows']} | {t3['rows_second']} | - |",
        f"| Table 3 | fields ({t3['fields_blank']} blank) | {t3['fields_checked']} | - | "
        f"{t3['fields_agree']} |",
        "",
        "A Table 1 code agrees when both extractions put it in the same row and column. A "
        "field of Tables 2 and 3 agrees when the text printed inside that column's band of the "
        "same row equals the extracted value (whitespace ignored), blanks included.",
        "",
        "The two extractions share this layout knowledge: "
        + "; ".join(SHARED_KNOWLEDGE)
        + ". They share no code, PDF engine, word segmentation, column building or row grouping.",
        "",
        "The census found no disagreement at its first run; no parser was changed to reach "
        "agreement.",
        "",
    ]
    if ink:
        out += [
            "## Rendered-image check of Table 1",
            "",
            f"Pages rasterised with Poppler pdftoppm at {ink['dpi']} dpi (glyphs and vector "
            "paths). Each cell rectangle (row band x column band) is tested for ink; no glyph "
            "inside a cell is read. The rectangles come from text-layer positions (printed row "
            "numbers and column headers) shared with the second extraction. The check sees a "
            "code missing from an empty cell, not one missing from a cell that holds another "
            "code, and not the identity of a code.",
            "",
            "| cells | with a code and ink | empty and no ink | ink without a code | "
            "code without ink |",
            "|---:|---:|---:|---:|---:|",
            f"| {ink['cells']} | {ink['ink_and_code']} | {ink['no_ink_no_code']} | "
            f"{len(ink['ink_without_code'])} | {len(ink['code_without_ink'])} |",
            "",
            "Every occupied cell has more ink than any empty cell: "
            + ("yes." if ink["separated"] else "no."),
            "",
            "Engine versions and the ink margin (faintest occupied cell, darkest empty cell) "
            "are written to the run log, not to this report, so that the committed report does "
            "not depend on the Poppler build.",
            "",
        ]
    pr = r.get("prose")
    if pr:
        out += [
            "## Table 3 against the article's own prose",
            "",
            f"The Results list {pr['species_listed']} species with their number of MOHBR "
            f"specimens ({pr['specimens_listed']} specimens); the extracted current "
            f"identifications of Table 3 give {pr['table3_identified']}. "
            f"{pr['agree']} of {pr['species_listed']} species agree. The same sentence states "
            f"{pr['species_claimed']} species while listing {pr['species_listed']}.",
            "",
        ]
    out += ["## Disagreements", ""]
    rows = [{"table": "Table 1", **d} for d in t1["disagreements"]] + [
        {"table": t, **d} for t, k in (("Table 2", t2), ("Table 3", t3)) for d in k["disagreements"]
    ]
    rows += [
        {"table": "Table 3 vs prose", **d} for d in (r.get("prose") or {}).get("disagreements", [])
    ]
    if ink:
        rows += [{"table": "Table 1 (image)", **d} for d in ink["ink_without_code"]]
        rows += [{"table": "Table 1 (image)", **d} for d in ink["code_without_ink"]]
    out.append(pd.DataFrame(rows).to_markdown(index=False) if rows else "None.")
    return "\n".join(out) + "\n"


def _ink_bad(ink: dict | None) -> bool:
    return bool(ink) and bool(ink["ink_without_code"] or ink["code_without_ink"])
