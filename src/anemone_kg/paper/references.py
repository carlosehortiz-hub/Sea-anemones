"""The manuscript's references: loading, Crossref verification, and BMC-style rendering.

Rule: no reference is cited unless it is real. Entries with a DOI are checked
against their Crossref record (title, year, first author's family name); the
records are cached in paper/references/crossref/ and committed, so the check
runs offline in CI. Entries without a DOI are specifications, software (with the
version actually used) or works cited through the source paper.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import requests
import yaml

CROSSREF = "https://api.crossref.org/works/"


@dataclass(frozen=True)
class Reference:
    key: str
    data: dict

    @property
    def cite_as(self) -> str:
        return self.data["cite_as"]

    @property
    def doi(self) -> str | None:
        return self.data.get("doi")

    def sort_key(self) -> tuple:
        return (_fold(self.data["authors"][0]), self.data["year"])

    def render(self, versions: dict[str, str]) -> str:
        """BMC style, as in the source: Author AB, Author CD. Title. Journal. Year;Vol:pages.

        Journal titles use the NLM abbreviation where `journal_abbrev` is given, as the source
        article does (e.g. "Mar Biodivers Rec").
        """
        d = self.data
        authors = ", ".join(d["authors"])
        title = d["title"]
        for k, v in versions.items():
            title = title.replace("{{ v." + k + " }}", v)
        title = title.rstrip(".")
        parts = [f"{authors.rstrip('.')}. {title}."]
        if d.get("journal"):
            loc = f" {d.get('journal_abbrev', d['journal'])}. {d['year']}"
            if d.get("volume"):
                loc += f";{d['volume']}"
            if d.get("pages"):
                loc += f":{d['pages']}"
            parts.append(loc + ".")
        elif d.get("publisher"):
            parts.append(f" {d['publisher']}; {d['year']}.")
        else:
            parts.append(f" {d['year']}.")
        if d.get("url"):
            parts.append(f" {d['url']}.")
        if d.get("note"):
            parts.append(f" {d['note'][0].upper()}{d['note'][1:]}.")
        if self.doi:
            parts.append(f" doi:{self.doi}.")
        return "".join(parts)


def _fold(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)
    )


def load_references(path: Path) -> dict[str, Reference]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {k: Reference(k, v) for k, v in data.items()}


def cache_path(root: Path, doi: str) -> Path:
    return root / f"{re.sub(r'[^A-Za-z0-9._-]', '_', doi.lower())}.json"


def fetch_crossref(refs: dict[str, Reference], cache_root: Path, offline: bool) -> dict[str, dict]:
    cache_root.mkdir(parents=True, exist_ok=True)
    out = {}
    for ref in refs.values():
        if not ref.doi:
            continue
        p = cache_path(cache_root, ref.doi)
        if not p.exists():
            if offline:
                raise FileNotFoundError(f"no cached Crossref record for {ref.doi}")
            resp = requests.get(
                CROSSREF + ref.doi,
                timeout=30,
                headers={"User-Agent": "anemone-kg manuscript reference check"},
            )
            resp.raise_for_status()
            msg = resp.json()["message"]
            keep = {
                k: msg.get(k)
                for k in ("DOI", "title", "author", "issued", "container-title", "volume", "page")
            }
            p.write_text(
                json.dumps(keep, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        out[ref.key] = json.loads(p.read_text(encoding="utf-8"))
    return out


def verify(refs: dict[str, Reference], records: dict[str, dict]) -> list[str]:
    """Title, year and first author must agree with Crossref."""
    problems = []
    for key, rec in records.items():
        d = refs[key].data

        def norm(s: str) -> str:
            # Crossref titles carry HTML: tags and entities (&amp;) are removed before comparing
            plain = html.unescape(re.sub(r"<[^>]+>", "", s))
            return re.sub(r"[^a-z0-9]+", " ", _fold(plain)).strip()

        cr_title = norm((rec.get("title") or [""])[0])
        if (
            norm(d["title"]) != cr_title
            and not cr_title.startswith(norm(d["title"]))
            and not norm(d["title"]).startswith(cr_title)
        ):
            problems.append(f"{key}: title differs from Crossref: {rec.get('title')}")
        year = (rec.get("issued", {}).get("date-parts") or [[None]])[0][0]
        if year != d["year"]:
            problems.append(f"{key}: year {d['year']} but Crossref says {year}")
        first = _fold((rec.get("author") or [{}])[0].get("family", ""))
        if first and _fold(d["authors"][0].rsplit(" ", 1)[0]) != first:
            problems.append(f"{key}: first author {d['authors'][0]} vs Crossref {first}")
    return problems
