"""Geometry helpers for recovering tables from a typeset PDF.

The source tables have no ruling lines between columns, so ``pdfplumber``'s
line-based table finder cannot be used. Instead we work from word bounding
boxes:

* **Columns** are left-aligned in this typesetting. Inside a column header,
  words are separated by a normal space (<= 3 pt); between columns the gap is
  >= 6 pt. ``column_starts`` splits on a gap threshold between the two and
  takes the union over all header lines, because a column's left edge may only
  be visible on one of its header lines.
* **Rows** are anchored on the row number printed in the left margin. A token
  belongs to the last anchor at or above it (with a small tolerance, because
  superscript-like glyphs such as ``'`` and ``"`` in coordinates sit ~2 pt
  higher than the baseline of their row).

Failure mode to watch for: a cell whose text runs past the next column's left
edge would be split across two columns. The extractors guard against this by
validating every cell against a closed vocabulary or an expected pattern, and
raising instead of guessing.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

Word = dict[str, Any]

# Gap (pt) separating two columns in a header line. Intra-column spaces measure
# 2-3 pt and inter-column gaps >= 6 pt in this document (measured, see tests).
COLUMN_GAP_PT = 4.5


@dataclass(frozen=True)
class Column:
    index: int
    x0: float
    header: str


def group_lines(words: Iterable[Word], tol: float = 1.5) -> list[list[Word]]:
    """Group words into visual lines by ``top`` and sort each line left-to-right."""
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def column_starts(header_words: Sequence[Word], gap: float = COLUMN_GAP_PT) -> list[float]:
    """Left edges of columns, from the union of breaks over all header lines."""
    starts: list[float] = []
    for line in group_lines(header_words):
        prev_x1: float | None = None
        for w in line:
            if prev_x1 is None or w["x0"] - prev_x1 > gap:
                starts.append(w["x0"])
            prev_x1 = w["x1"]
    merged: list[float] = []
    for x in sorted(starts):
        if not merged or x - merged[-1] > 2.0:
            merged.append(x)
    return merged


def assign_column(x0: float, starts: Sequence[float], tol: float = 2.0) -> int:
    """Index of the column whose left edge is the last one at or left of ``x0``."""
    idx = -1
    for i, s in enumerate(starts):
        if s <= x0 + tol:
            idx = i
    if idx < 0:
        raise ValueError(f"token at x0={x0:.1f} lies left of the first column")
    return idx


def build_columns(header_words: Sequence[Word], gap: float = COLUMN_GAP_PT) -> list[Column]:
    starts = column_starts(header_words, gap)
    texts: list[list[str]] = [[] for _ in starts]
    for line in group_lines(header_words):
        for w in line:
            texts[assign_column(w["x0"], starts)].append(w["text"])
    return [Column(i, x, " ".join(t)) for i, (x, t) in enumerate(zip(starts, texts, strict=True))]


def join_text(words: Iterable[Word], line_tol: float = 3.0, space_gap: float = 1.0) -> str:
    """Join words in reading order (line by line, left to right).

    ``line_tol`` is wider than for header grouping because prime/second marks in
    coordinates (``53’ 2.51”``) are set ~2 pt above the baseline. Words closer
    than ``space_gap`` pt are glued, so ``53`` + ``’`` reads ``53’`` as printed.
    """
    parts: list[str] = []
    for line in group_lines(words, tol=line_tol):
        prev: Word | None = None
        for w in line:
            if prev is not None:
                parts.append(" " if w["x0"] - prev["x1"] > space_gap else "")
            parts.append(w["text"])
            prev = w
        parts.append(" ")
    return "".join(parts).strip()
