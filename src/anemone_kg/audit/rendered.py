"""Third check of Table 1, from the rendered page instead of the text layer.

The two extractions (pdfplumber and Poppler) both read the PDF's text layer: glyph codes,
Unicode maps and positions. A code that is missing from the text layer, or drawn as a vector
path, would be missed by both, and a missed code leaves a cell empty - exactly what a
"specimen without a code" flag looks like. This check does not read text at all. Each Table 1
page is rasterised (Poppler ``pdftoppm``, which draws glyphs *and* vector paths), and every
cell rectangle - occupied or empty - is tested for ink. A cell is consistent when it has ink
if and only if the extraction found a code in it.

What it shares with the text-based readings: the cell rectangles, which come from the positions
of the printed row numbers and column headers. What it does not share: any glyph, Unicode or
word information inside the cells. It checks presence, not the identity of a code.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from anemone_kg.audit.second_reading import (
    RUNNING_HEAD_X,
    TABLE1_PAGES,
    _header_lefts,
    poppler_words,
)

DPI = 150
DARK = 128  # grey level below which a pixel is ink
MIN_INK = 8  # pixels; a single code letter at 150 dpi has ~50
LINE = 11.0  # points: height of one row of Table 1


def _render(pdf: Path, page: int, out: Path) -> np.ndarray:
    stem = out / f"p{page}"
    subprocess.run(
        [
            "pdftoppm",
            "-r",
            str(DPI),
            "-gray",
            "-png",
            "-f",
            str(page),
            "-l",
            str(page),
            str(pdf),
            str(stem),
        ],
        check=True,
    )
    img = np.array(Image.open(next(out.glob(f"p{page}*.png"))).convert("L"))
    return img


def cell_rectangles(pdf: Path) -> pd.DataFrame:
    """Every Table 1 cell as a rectangle in PDF points: (row_no, locality_col_id, page, box)."""
    rows = []
    for block, pages in TABLE1_PAGES.items():
        lefts = _header_lefts(poppler_words(pdf, pages.start))
        rights = [*(x - 2.0 for x in lefts[1:]), min(RUNNING_HEAD_X, lefts[-1] + 40)]
        for page in pages:
            words = [w for w in poppler_words(pdf, page) if w.x0 < RUNNING_HEAD_X]
            legend = min((w.y0 for w in words if w.text == "Localities" and w.x0 < 72), default=1e9)
            body_top = (
                max(w.y1 for w in words if w.text == "Species") + 25
                if page == pages.start
                else min(w.y0 for w in words if w.text == "Table") + 8
            )
            anchors = sorted(
                (w for w in words if w.x1 < 72 and w.text.isdigit() and body_top < w.y0 < legend),
                key=lambda w: w.y0,
            )
            context = sorted(w.y0 for w in words if w.text in {"Order", "Family"} and w.x0 < 90)
            for i, a in enumerate(anchors):
                stops = [legend] + [y for y in context if y > a.y0 + 1]
                if i + 1 < len(anchors):
                    stops.append(anchors[i + 1].y0)
                # one printed line: below it lie the next row, a context line, the bottom
                # rule or the legend (no code in Table 1 wraps onto a second line)
                bottom = min([*stops, a.y0 + LINE]) - 1.0
                for ci, (x0, x1) in enumerate(zip(lefts, rights, strict=True)):
                    rows.append(
                        {
                            "row_no": int(a.text),
                            "locality_col_id": f"T1{block}{ci + 1:02d}",
                            "page": page,
                            "x0": x0 - 1.0,
                            "x1": x1,
                            "y0": a.y0 - 1.5,
                            "y1": bottom,
                        }
                    )
    return pd.DataFrame(rows)


def ink_census(pdf: Path, interim: Path) -> dict:
    cells = cell_rectangles(pdf)
    scale = DPI / 72
    ink = []
    with tempfile.TemporaryDirectory() as tmp:
        imgs = {p: _render(pdf, p, Path(tmp)) for p in sorted(cells.page.unique())}
        for r in cells.itertuples():
            box = imgs[r.page][
                int(r.y0 * scale) : int(r.y1 * scale), int(r.x0 * scale) : int(r.x1 * scale)
            ]
            ink.append(int((box < DARK).sum()))
    cells["ink"] = ink
    cells["has_ink"] = cells.ink >= MIN_INK
    occ = pd.read_csv(interim / "table1_cells.csv")
    occupied = set(zip(occ.row_no, occ.locality_col_id, strict=True))
    cells["has_code"] = [
        (r, c) in occupied for r, c in zip(cells.row_no, cells.locality_col_id, strict=True)
    ]
    bad = cells[cells.has_ink != cells.has_code]
    return {
        "dpi": DPI,
        "cells": len(cells),
        "occupied": int(cells.has_code.sum()),
        "empty": int((~cells.has_code).sum()),
        "ink_and_code": int((cells.has_ink & cells.has_code).sum()),
        "no_ink_no_code": int((~cells.has_ink & ~cells.has_code).sum()),
        "ink_without_code": bad[bad.has_ink][["row_no", "locality_col_id", "page", "ink"]].to_dict(
            "records"
        ),
        "code_without_ink": bad[~bad.has_ink][["row_no", "locality_col_id", "page", "ink"]].to_dict(
            "records"
        ),
        # pixel extremes depend on the rasteriser build; logged, not written to the reports
        "separated": bool(
            cells.loc[cells.has_code, "ink"].min() > cells.loc[~cells.has_code, "ink"].max()
        ),
    }


def renderer_version() -> str:
    out = subprocess.run(["pdftoppm", "-v"], capture_output=True, text=True)
    return (out.stderr or out.stdout).splitlines()[0].strip()


def crop_sheet(pdf: Path, targets: pd.DataFrame, out_pdf: Path) -> int:
    """A PDF of rendered crops (one per target cell, with its row and two neighbours),
    so that anyone can check the discrepant cells by eye. ``targets``: row_no,
    locality_col_id, label."""
    cells = cell_rectangles(pdf)
    scale = 200 / 72
    pages = []
    with tempfile.TemporaryDirectory() as tmp:
        cache: dict[int, Image.Image] = {}
        for t in targets.itertuples():
            r = cells[(cells.row_no == t.row_no) & (cells.locality_col_id == t.locality_col_id)]
            if not len(r):
                continue
            r = r.iloc[0]
            if r.page not in cache:
                stem = Path(tmp) / f"q{r.page}"
                subprocess.run(
                    [
                        "pdftoppm",
                        "-r",
                        "200",
                        "-png",
                        "-f",
                        str(r.page),
                        "-l",
                        str(r.page),
                        str(pdf),
                        str(stem),
                    ],
                    check=True,
                )
                cache[r.page] = Image.open(next(Path(tmp).glob(f"q{r.page}*.png"))).convert("RGB")
            img = cache[r.page]
            x0 = int(55 * scale)  # from the row number and name, so the row can be read
            x1 = int((r.x1 + 60) * scale)
            y0 = max(0, int((r.y0 - 12) * scale))
            y1 = int((r.y1 + 12) * scale)
            crop = img.crop((x0, y0, x1, y1))
            from PIL import ImageDraw

            canvas = Image.new("RGB", (max(crop.width, 900), crop.height + 40), "white")
            canvas.paste(crop, (0, 40))
            d = ImageDraw.Draw(canvas)
            d.text((6, 6), str(t.label), fill="black")
            bx0, by0 = int(r.x0 * scale) - x0, int(r.y0 * scale) - y0 + 40
            bx1, by1 = int(r.x1 * scale) - x0, int(r.y1 * scale) - y0 + 40
            d.rectangle((bx0, by0, bx1, by1), outline=(235, 104, 52), width=3)
            pages.append(canvas)
    if pages:
        pages[0].save(out_pdf, save_all=True, append_images=pages[1:], resolution=200)
    return len(pages)
