"""Extraction of the species accounts (Systematics, pp. 2-25).

Each of the 26 accounts starts with a heading ``Genus species Authority`` on the
line(s) right before a figure reference ``(Fig. 2a)``, and contains labelled
paragraphs (``Short description``, ``Habitat``, ``Distribution``). We extract
the heading and the *Habitat* paragraph verbatim; habitat is described per
species in this paper, not per record, so it belongs to the taxon.

The text is set in two columns. Each column is cropped and read separately, and
columns are concatenated in reading order (page, left, right).

The only text transformation is joining a word hyphenated across a line break
when the next line starts in lower case (``crev-`` + ``ices``). It is counted and
recorded on the row, because it can wrongly join a true compound (``well-`` +
``developed``); reviewers can compare with ``habitat_raw``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pdfplumber

from anemone_kg.extract.tables import ExtractionError

# 0-based page indices: p. 2 and pp. 11-25. Pp. 3-10 hold Table 1, whose own
# Order/Family lines would otherwise leak into the rank context.
SYSTEMATICS_PAGES = (1, *range(10, 25))
COLUMN_MARGIN_TOP, COLUMN_MARGIN_BOTTOM = 60, 40
N_ACCOUNTS = 26

_FIG = re.compile(r"^\(Figs?\. \d+[a-z](?:[-–,]\s?[a-z])?\)$")
_HEADING = re.compile(
    r"^(?P<name>[A-Z][a-z]+ (?:cf\. |aff\. )?[a-z]+) (?P<authority>\(?[A-Za-z].*\d{4}[a-z]?\)?)$"
)
_SECTION = re.compile(r"^(Short description|Habitat|Distribution|Remarks)\b")
_RANKS = ("order", "suborder", "superfamily", "family")
_RANK_LINE = re.compile(r"^(Order|Suborder|Superfamily|Family) ([A-Z]+)")


def _linear_lines(pdf_path: Path) -> list[tuple[int, str]]:
    pdf = pdfplumber.open(pdf_path)
    out: list[tuple[int, str]] = []
    for i in SYSTEMATICS_PAGES:
        page = pdf.pages[i]
        mid = page.width / 2
        for x0, x1 in ((0, mid), (mid, page.width)):
            box = (x0, COLUMN_MARGIN_TOP, x1, page.height - COLUMN_MARGIN_BOTTOM)
            text = page.crop(box).extract_text(x_tolerance=1.5) or ""
            out.extend((i + 1, ln.strip()) for ln in text.splitlines() if ln.strip())
    return out


def _dehyphenate(lines: list[str]) -> tuple[str, int]:
    text, joins = "", 0
    for ln in lines:
        if text.endswith("-") and ln[:1].islower():
            text, joins = text[:-1] + ln, joins + 1
        else:
            text = f"{text} {ln}".strip()
    return text, joins


def extract_accounts(pdf_path: Path) -> pd.DataFrame:
    lines = _linear_lines(pdf_path)
    fig_idx = [i for i, (_, ln) in enumerate(lines) if _FIG.match(ln)]
    records: list[dict] = []
    ranks: dict[str, str] = {}
    rank_cursor = 0

    for n, fi in enumerate(fig_idx):
        # Heading: the line before the figure marker, joined with the one before
        # when the authority wrapped (e.g. "... (Duchassaing & Michelotti," / "1860)").
        heading = lines[fi - 1][1]
        if not _HEADING.match(heading):
            heading = f"{lines[fi - 2][1]} {heading}"
        m = _HEADING.match(heading)
        if not m:
            raise ExtractionError(f"p{lines[fi][0]}: unreadable account heading {heading!r}")

        window = lines[rank_cursor:fi]
        for k, (_, ln) in enumerate(window):
            rm = _RANK_LINE.match(ln)
            if not rm:
                continue
            nxt = window[k + 1][1] if k + 1 < len(window) else ""
            if ln.endswith(",") and re.fullmatch(r"\d{4}[a-z]?", nxt):
                ln = f"{ln} {nxt}"  # authority year wrapped onto the next line
            rank = rm.group(1).lower()
            ranks[rank] = ln
            for lower in _RANKS[_RANKS.index(rank) + 1 :]:
                ranks.pop(lower, None)
        rank_cursor = fi

        end = fig_idx[n + 1] - 2 if n + 1 < len(fig_idx) else len(lines)
        body = lines[fi + 1 : end]
        habitat_lines: list[str] = []
        page = None
        in_hab = False
        for pg, ln in body:
            sec = _SECTION.match(ln)
            if sec:
                in_hab = sec.group(1) == "Habitat"
                if in_hab:
                    page = pg
                    ln = ln[len("Habitat") :].strip()
            if in_hab:
                habitat_lines.append(ln)
        if not habitat_lines:
            raise ExtractionError(f"no Habitat paragraph for {m.group('name')}")
        habitat, joins = _dehyphenate(habitat_lines)
        records.append(
            {
                "account_no": n + 1,
                "verbatim_heading": heading,
                "name_text": m.group("name"),
                "verbatim_authority": m.group("authority"),
                "verbatim_order": ranks.get("order", ""),
                "verbatim_family": ranks.get("family", ""),
                "habitat_text": habitat,
                "habitat_raw": " / ".join(habitat_lines),
                "dehyphenation_joins": joins,
                "source_page": page,
                "source_ref": f"Systematics, account of {m.group('name')}, Habitat",
            }
        )

    df = pd.DataFrame(records)
    if len(df) != N_ACCOUNTS:
        raise ExtractionError(f"expected {N_ACCOUNTS} species accounts, found {len(df)}")
    return df
