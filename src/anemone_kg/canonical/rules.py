"""Transformation rules: the single registry behind mappings/source_to_canonical.csv.

Every canonical value is produced by one of these rules, and the mapping table
cites rules by id. A test asserts both directions (every rule cited exists, and
every rule exists because something cites it), so code and documentation
cannot drift apart.

The functions are pure and small on purpose: each one is a documented,
testable decision. Anything that needs human judgement (typo corrections,
site-to-area crosswalk, dates stated in prose) is *not* a function here but a
curated CSV under mappings/, which the rule applies verbatim.
"""

from __future__ import annotations

import calendar
import re
import uuid
from dataclasses import dataclass

RULES: dict[str, str] = {
    "R_COPY": "Copy the verbatim value unchanged.",
    "R_TRIM": "Collapse internal whitespace and strip; no other change.",
    "R_MISSING": "'-' or empty string -> null (the paper's placeholder for 'not recorded').",
    "R_CONSTANT": "Constant stated once for the whole dataset (e.g. country, institution).",
    "R_UUID5": "Deterministic UUIDv5 from a natural key, namespaced on the source DOI; "
    "specimens are namespaced on the institution, so a lot keeps its id in any later source.",
    "R_DATE_PRECISION": "Day 01 in Table 3 -> year-month (the day looks defaulted); an "
    "impossible date -> year only. Verbatim date always kept.",
    "R_FLAGS": "Table 1 marks after a name: dagger -> flag_invalid, '?' -> flag_doubtful.",
    "R_SPLIT_QUALIFIER": "Split an open-nomenclature qualifier (cf., sp., sp.?) off the name.",
    "R_RANK_FROM_NAME": "Rank from name form: binomial=species, '-idae'=family, else genus.",
    "R_RANK_HEADING": "'Family ACTINIIDAE Rafinesque, 1815' -> 'Actiniidae' + authorship.",
    "R_HIGHER_FROM_T1": "Order of a family-rank name, from the Table 1 order listing that family.",
    "R_ACCOUNT_JOIN": "Authorship from the species account whose heading has the same name.",
    "R_TYPO": "Curated spelling correction from mappings/name_variants.csv (status accepted).",
    "R_INFORMAL": "Informal label (e.g. 'Actinia 1') -> no taxon; kept verbatim with a remark.",
    "R_NOT_IDENTIFIED": "'not identified' -> no taxon; kept verbatim with a remark.",
    "R_STATE": "State spelling from mappings/state_names.csv.",
    "R_DMS": "Degrees-minutes-seconds -> decimal degrees, 6 dp; W and S negative.",
    "R_DATE_DMY": "dd/mm/yyyy -> ISO 8601; impossible calendar dates flagged, verbatim kept.",
    "R_DATE_METHODS": "Event date stated in Methods per park, from mappings/event_dates.csv.",
    "R_PERSON": "Collectors: fix 'Agudo. I.' -> 'Agudo, I.'; ' and ' -> ' | ' (DwC list).",
    "R_CATALOG": "MOHBR catalogue number; non-identifier text ('In progress') -> null + remark.",
    "R_CROSSWALK": "Site -> Table 1 area via mappings/locality_crosswalk.csv (accepted rows only).",
    "R_CODE_KIND": "Table 1 code -> evidence kind and cited reference (legend).",
    "R_NEW_RECORD_FOLD": "Code 'N' sets is_new_record on the '*' record of the same cell.",
    "R_OPEN_SEA": "Table 1 'Open Sea Distribution' column -> no locality, kept as remark.",
    "R_PREVIOUS_ID": "Table 3 previous identification kept only when it differs from current.",
}

QUALIFIERS = ("sp.?", "cf.", "sp.")  # order matters: 'sp.?' before 'sp.'
MISSING_TOKENS = frozenset({"", "-", "–"})


# ------------------------------------------------------------------ identifiers
def namespace_for(doi: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"https://doi.org/{doi}")


# Specimens are keyed on institution + catalogue number. Their namespace is derived from the
# institution code, not from the source DOI, so that the same MOHBR lot cited in a later
# article (or published by the museum) gets the same occurrenceID (round 3, R5 M4 / R7 M4).
SPECIMEN_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:anemone-kg:institution:MOHBR")


def mint_id(namespace: uuid.UUID, kind: str, natural_key: str) -> str:
    """R_UUID5. Same input, same id - across runs, machines and re-orderings."""
    return str(uuid.uuid5(namespace, f"{kind}:{natural_key}"))


# --------------------------------------------------------------------- strings
def trim(value: object) -> str | None:
    """R_TRIM + R_MISSING."""
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    return None if s in MISSING_TOKENS else s


# ----------------------------------------------------------------------- names
@dataclass(frozen=True)
class ParsedName:
    name: str
    qualifier: str | None
    rank: str
    genus: str | None
    specific_epithet: str | None


def parse_name(verbatim: str) -> ParsedName:
    """R_SPLIT_QUALIFIER + R_RANK_FROM_NAME.

    >>> parse_name("Zoanthus cf. pulchellus")
    ParsedName(name='Zoanthus pulchellus', qualifier='cf.', rank='species', genus='Zoanthus', specific_epithet='pulchellus')
    >>> parse_name("Actiniidae sp.").rank
    'family'
    >>> parse_name("Phymactis sp.?").qualifier
    'sp.?'
    """  # noqa: E501
    tokens = (trim(verbatim) or "").split()
    qualifier = next((q for q in QUALIFIERS if q in tokens), None)
    tokens = [t for t in tokens if t != qualifier]
    s = " ".join(tokens)
    if len(tokens) == 2 and tokens[1].islower():
        return ParsedName(s, qualifier, "species", tokens[0], tokens[1])
    if len(tokens) == 1 and tokens[0].endswith("idae"):
        return ParsedName(s, qualifier, "family", None, None)
    if len(tokens) == 1:
        return ParsedName(s, qualifier, "genus", tokens[0], None)
    raise ValueError(f"cannot parse scientific name {verbatim!r}")


def is_informal(verbatim: str) -> bool:
    """R_INFORMAL: a genus followed by a number or other non-epithet token."""
    tokens = verbatim.split()
    return len(tokens) == 2 and not tokens[1].isalpha()


def parse_rank_heading(heading: str) -> tuple[str, str | None]:
    """R_RANK_HEADING.

    >>> parse_rank_heading("Family ACTINIIDAE Rafinesque, 1815")
    ('Actiniidae', 'Rafinesque, 1815')
    >>> parse_rank_heading("Family Cerianthidae")
    ('Cerianthidae', None)
    """
    m = re.match(r"^(?:Order|Suborder|Superfamily|Family)\s+([A-Za-z]+)\s*(.*)$", heading.strip())
    if not m:
        raise ValueError(f"not a rank heading: {heading!r}")
    return m.group(1).capitalize(), (m.group(2).strip() or None)


# ------------------------------------------------------------------ coordinates
_DMS = re.compile(r"^(\d{1,3})°\s*(\d{1,2})’\s*(\d{1,2}(?:\.\d+)?)”$")


def dms_to_decimal(verbatim: str, hemisphere: str) -> float:
    """R_DMS. Tolerates the missing space in '68°12’ 43.66”' (Table 2 row 7).

    >>> dms_to_decimal("10° 53’ 2.51”", "N")
    10.884031
    >>> dms_to_decimal("68°12’ 43.66”", "W")
    -68.212128
    """
    m = _DMS.match(verbatim.strip())
    if not m:
        raise ValueError(f"unparseable coordinate {verbatim!r}")
    d, mnt, sec = int(m.group(1)), int(m.group(2)), float(m.group(3))
    if mnt >= 60 or sec >= 60:
        raise ValueError(f"minutes/seconds out of range in {verbatim!r}")
    value = round(d + mnt / 60 + sec / 3600, 6)
    return -value if hemisphere in {"W", "S"} else value


# ------------------------------------------------------------------------ dates
def event_date_with_precision(verbatim: str | None) -> tuple[str | None, str | None]:
    """R_DATE_PRECISION. (eventDate, remark): day 01 becomes year-month, an impossible date
    keeps its year.

    23 of the 81 parseable Table 3 dates fall on day 01, against about 3 expected if days were
    uniform: the pattern of a defaulted day. Publishing them at day precision would invent
    information (round 3, R7 M3).

    >>> event_date_with_precision("01/08/1987")
    ('1987-08', 'day given as 01, published as year-month (the day looks defaulted)')
    >>> event_date_with_precision("31/04/2012")
    ('2012', 'impossible calendar date; published as year only')
    >>> event_date_with_precision("23/02/1995")
    ('1995-02-23', None)
    """
    iso, problem = parse_dmy(verbatim)
    if problem == "impossible calendar date":
        return trim(verbatim)[-4:], "impossible calendar date; published as year only"
    if iso and iso.endswith("-01"):
        return iso[:7], "day given as 01, published as year-month (the day looks defaulted)"
    return iso, problem


def parse_dmy(verbatim: str | None) -> tuple[str | None, str | None]:
    """R_DATE_DMY + R_MISSING. Returns (iso_date, problem).

    >>> parse_dmy("23/02/1995")
    ('1995-02-23', None)
    >>> parse_dmy("31/04/2012")
    (None, 'impossible calendar date')
    >>> parse_dmy("-")
    (None, None)
    """
    s = trim(verbatim)
    if s is None:
        return None, None
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if not m:
        return None, "unrecognised date format"
    d, mo, y = (int(x) for x in m.groups())
    if not 1 <= mo <= 12 or not 1 <= d <= calendar.monthrange(y, mo)[1]:
        return None, "impossible calendar date"
    return f"{y:04d}-{mo:02d}-{d:02d}", None


# ---------------------------------------------------------------------- people
def normalise_people(verbatim: str | None) -> str | None:
    """R_PERSON + R_MISSING.

    >>> normalise_people("Carrasquel, M. and Méndez, E.")
    'Carrasquel, M. | Méndez, E.'
    >>> normalise_people("Agudo. I.")
    'Agudo, I.'
    """
    s = trim(verbatim)
    if s is None:
        return None
    people = [p.strip() for p in re.split(r"\s+and\s+", s)]
    people = [re.sub(r"^([^\s,.]+)\.\s+([A-Z]\.)$", r"\1, \2", p) for p in people]
    return " | ".join(people)


# --------------------------------------------------------------------- catalog
def parse_catalog(verbatim: str | None) -> tuple[str | None, str | None]:
    """R_CATALOG. Returns (catalog_number, remark)."""
    s = trim(verbatim)
    if s is None:
        return None, None
    if re.fullmatch(r"I-\d+", s):
        return s, None
    return None, f"MOHBR catalogue number given as '{s}' in the source"
