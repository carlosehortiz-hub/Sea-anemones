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


def _locate(field: str, words: list[W], used: set[int]) -> float | None:
    """x of the field's first token if every token is found among unused row words."""
    tokens = _norm(field).split()
    xs = []
    for tok in tokens:
        hit = next(
            (
                i
                for i, w in enumerate(words)
                if i not in used
                and (_norm(w.text) == tok or (len(tok) >= 4 and tok in _norm(w.text)))
            ),
            None,
        )
        if hit is None:
            # The two engines may split one printed token differently (e.g. 2.51" vs 2.51 ").
            joined = "".join(_norm(w.text) for i, w in enumerate(words) if i not in used)
            if len(tok) >= 3 and tok in joined:
                xs.append(None)
                continue
            return None
        used.add(hit)
        xs.append(words[hit].x0)
    first = next((x for x in xs if x is not None), None)
    return first if first is not None else -1.0


def compare_fixed(df: pd.DataFrame, fields: list[str], pdf: Path) -> dict:
    pages = sorted(df.source_page.unique().tolist())
    by_row = _row_words(pdf, pages)
    checked = agree = 0
    problems = []
    for rec in df.to_dict("records"):
        words = by_row.get(int(rec["no"]), [])
        used: set[int] = set()
        last_x = -1.0
        for f in fields:
            val = rec[f]
            if pd.isna(val) or str(val).strip() == "":
                continue
            checked += 1
            x = _locate(str(val), words, used)
            ok = x is not None and (x < 0 or x > last_x - 1)
            if ok:
                agree += 1
                if x is not None and x >= 0:
                    last_x = x
            else:
                problems.append(
                    {
                        "row": int(rec["no"]),
                        "field": f,
                        "extracted": str(val),
                        "printed_row": " ".join(w.text for w in words),
                    }
                )
    return {
        "rows": len(df),
        "rows_second": len(by_row),
        "fields_checked": checked,
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


def to_markdown(r: dict) -> str:
    t1, t2, t3 = r["table1"], r["table2"], r["table3"]
    status = "AGREE" if n_disagreements(r) == 0 else "DISAGREE"
    out = [
        "# Extraction census: second, independent transcription",
        "",
        f"**Status: {status}** - every occupied cell of Table 1 and every field of Tables 2 "
        "and 3 was read a second time, with a different PDF engine and parser, and compared "
        "with the extraction.",
        "",
        f"First reading: {r['engine_first']} (the pipeline's extraction). "
        f"Second reading: {r['engine_second']} with a separate parser "
        "(`anemone_kg.audit.second_reading`).",
        "",
        "| table | unit | extraction | second reading | agree |",
        "|---|---|---:|---:|---:|",
        f"| Table 1 | occupied cells | {t1['cells_first']} | {t1['cells_second']} | "
        f"{t1['cells_agree']} |",
        f"| Table 1 | evidence codes | {t1['codes_first']} | {t1['codes_second']} | "
        f"{t1['codes_agree']} |",
        f"| Table 2 | rows | {t2['rows']} | {t2['rows_second']} | - |",
        f"| Table 2 | non-empty fields | {t2['fields_checked']} | - | {t2['fields_agree']} |",
        f"| Table 3 | rows | {t3['rows']} | {t3['rows_second']} | - |",
        f"| Table 3 | non-empty fields | {t3['fields_checked']} | - | {t3['fields_agree']} |",
        "",
        "A Table 1 code agrees when both readings put it in the same row and column. A field "
        "of Tables 2 and 3 agrees when all its tokens are found in the same printed row and "
        "the fields appear left to right in column order. The check detects a column shift, "
        "a value read into the wrong row, two columns swapped and a changed digit "
        "(tests/test_second_reading.py injects each of these).",
        "",
        "## Disagreements",
        "",
    ]
    rows = [{"table": "Table 1", **d} for d in t1["disagreements"]] + [
        {"table": t, **d} for t, k in (("Table 2", t2), ("Table 3", t3)) for d in k["disagreements"]
    ]
    out.append(pd.DataFrame(rows).to_markdown(index=False) if rows else "None.")
    return "\n".join(out) + "\n"
