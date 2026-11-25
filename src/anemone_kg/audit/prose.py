"""An independent check of Table 3 from the article's own prose.

The Results of the source list, for the MOHBR specimens identified to species, each species with
its number of specimens ("Actinostella flosculifera (11 specimens), ..."). That list is typeset
as running text, far from Appendix 2, so it is a reading of the same facts that shares nothing
with the table parser: comparing the two tests the extracted *current identification* column.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

import pandas as pd

START = "Of the 84 specimens examined"
END = "The other three specimens"
ENTRY = re.compile(r"([A-Z][a-z]+ [a-z]+)[^()]*?\((\d+) specimens?\)")
CLAIM = re.compile(r"belong\s+to\s+(\d+)\s+species")


def prose_counts(pdf: Path) -> tuple[dict[str, int], int | None]:
    """(species -> specimens) as printed in the Results, and the species total it states."""
    text = subprocess.run(
        ["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True
    ).stdout
    i, j = text.index(START), text.index(END)
    para = re.sub(r"(\w)-\n(\w)", r"\1\2", text[i:j])  # rejoin hyphenated line breaks
    para = re.sub(r"\s+", " ", para)
    claim = CLAIM.search(para)
    listing = para.split("species:", 1)[1]  # the enumeration after "belong to N species:"
    return (
        {m.group(1): int(m.group(2)) for m in ENTRY.finditer(listing)},
        int(claim.group(1)) if claim else None,
    )


def compare(pdf: Path, interim: Path) -> dict:
    prose, claimed = prose_counts(pdf)
    t3 = pd.read_csv(interim / "table3_mohbr_specimens.csv", dtype=str)
    table = Counter(
        " ".join(str(n).split()[:2])
        for n in t3.current_identification
        if isinstance(n, str) and n != "not identified"
    )
    names = sorted(set(prose) | set(table))
    rows = [{"species": n, "prose": prose.get(n, 0), "table3": table.get(n, 0)} for n in names]
    bad = [r for r in rows if r["prose"] != r["table3"]]
    return {
        "species_listed": len(prose),
        "species_claimed": claimed,
        "specimens_listed": sum(prose.values()),
        "table3_identified": sum(table.values()),
        "agree": len(rows) - len(bad),
        "disagreements": bad,
    }
