"""Build the canonical tables from the verbatim extraction.

Inputs: data/interim/*.csv (stage 1) and the curated tables in mappings/.
Output: one DataFrame per LinkML class, plus a ledger of which rule fired on
which source row, so the summary can say exactly what was changed and why.

Policy, in order of precedence:
1. Never invent: a value is either copied, derived by a documented rule, or
   taken from a curated mapping row that cites its evidence.
2. Never drop silently: a row that cannot be mapped is kept with a null and a
   remark, and appears in the ledger.
3. Fail loudly on contradictions (e.g. 'N' without '*' in the same cell).
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from anemone_kg.canonical.rules import (
    RULES,
    SPECIMEN_NAMESPACE,
    dms_to_decimal,
    event_date_with_precision,
    is_informal,
    mint_id,
    namespace_for,
    normalise_people,
    parse_catalog,
    parse_name,
    parse_rank_heading,
    trim,
)

log = logging.getLogger(__name__)

COUNTRY_CODE = "VE"  # whole paper is about Venezuela (title)
INSTITUTION = "MOHBR"  # Museo Oceanológico Hermano Benigno Román (p. 2)
OPEN_SEA_COL = "Open Sea Distribution"
CODE_KIND = {"*": "this_survey", "a": "mohbr_collection"}  # b-j -> literature


@dataclass
class Ledger:
    """Counts of rule applications plus the individual non-trivial events."""

    counts: Counter = field(default_factory=Counter)
    events: list[dict] = field(default_factory=list)

    def hit(self, rule: str, n: int = 1) -> None:
        assert rule in RULES, rule
        self.counts[rule] += n

    def note(self, rule: str, source_ref: str, detail: str) -> None:
        self.hit(rule)
        self.events.append({"rule_id": rule, "source_ref": source_ref, "detail": detail})


@dataclass
class Inputs:
    t1_taxa: pd.DataFrame
    t1_localities: pd.DataFrame
    t1_cells: pd.DataFrame
    t1_legend: pd.DataFrame
    t2: pd.DataFrame
    t3: pd.DataFrame
    accounts: pd.DataFrame
    name_variants: pd.DataFrame
    crosswalk: pd.DataFrame
    states: pd.DataFrame
    event_dates: pd.DataFrame

    @classmethod
    def load(cls, interim: Path, mappings: Path) -> Inputs:
        def r(p: Path) -> pd.DataFrame:
            return pd.read_csv(p, dtype=str, keep_default_na=False)

        return cls(
            t1_taxa=r(interim / "table1_taxa.csv"),
            t1_localities=r(interim / "table1_localities.csv"),
            t1_cells=r(interim / "table1_cells.csv"),
            t1_legend=r(interim / "table1_legend.csv"),
            t2=r(interim / "table2_specimens.csv"),
            t3=r(interim / "table3_mohbr_specimens.csv"),
            accounts=r(interim / "species_accounts.csv"),
            name_variants=r(mappings / "name_variants.csv"),
            crosswalk=r(mappings / "locality_crosswalk.csv"),
            states=r(mappings / "state_names.csv"),
            event_dates=r(mappings / "event_dates.csv"),
        )


class CanonicalBuilder:
    def __init__(self, inp: Inputs, source: dict, sha256: str) -> None:
        self.inp = inp
        self.source = source
        self.sha256 = sha256
        self.ns = namespace_for(source["doi"])
        self.ledger = Ledger()
        self.taxa: dict[str, dict] = {}  # scientific_name -> row
        self.variants: dict[str, dict] = {}  # verbatim -> row
        self.typos = {
            r.verbatim_name: r.canonical_name
            for r in inp.name_variants.itertuples()
            if r.status == "accepted"
        }
        self.state_map = dict(
            zip(inp.states.verbatim_state, inp.states.state_province, strict=True)
        )
        accepted = inp.crosswalk[inp.crosswalk.status == "accepted"]
        self.crosswalk = {
            (r.source_table, r.verbatim_key): (r.table1_locality_col_id or None)
            for r in accepted.itertuples()
        }
        self.family_order: dict[str, str] = {}
        self.area_ids: dict[str, str] = {}  # Table 1 column id -> locality_id

    # -------------------------------------------------------------- taxa
    def _taxon(
        self, verbatim: str, role: str, source_ref: str, page: int
    ) -> tuple[str, str | None]:
        """Return (taxon_id, qualifier) for a verbatim name, creating the taxon if new."""
        corrected = self.typos.get(verbatim, verbatim)
        parsed = parse_name(corrected)
        if parsed.qualifier:
            self.ledger.hit("R_SPLIT_QUALIFIER")
        rule = "R_TYPO" if corrected != verbatim else "R_COPY"
        if rule == "R_TYPO":
            self.ledger.note("R_TYPO", source_ref, f"{verbatim!r} -> {corrected!r}")
        row = self.taxa.get(parsed.name)
        if row is None:
            self.ledger.hit("R_RANK_FROM_NAME")
            row = {
                "taxon_id": mint_id(self.ns, "taxon", parsed.name),
                "scientific_name": parsed.name,
                "scientific_name_authorship": None,
                "taxon_rank": parsed.rank,
                "genus": parsed.genus,
                "specific_epithet": parsed.specific_epithet,
                "family": parsed.name if parsed.rank == "family" else None,
                "family_authorship": None,
                "order": self.family_order.get(parsed.name) if parsed.rank == "family" else None,
                "name_roles": set(),
                "table1_row": None,
                "flag_invalid_in_source": False,
                "flag_doubtful_in_source": False,
                "source_ref": source_ref,
                "source_page": int(page),
            }
            if row["order"]:
                self.ledger.hit("R_HIGHER_FROM_T1")
            self.taxa[parsed.name] = row
        row["name_roles"].add(role)
        self.variants.setdefault(
            verbatim,
            {
                "verbatim_name": verbatim,
                "taxon_id": row["taxon_id"],
                "identification_qualifier": parsed.qualifier,
                "variant_rule": "R_SPLIT_QUALIFIER" if parsed.qualifier else rule,
                "source_ref": source_ref,
            },
        )
        return row["taxon_id"], parsed.qualifier

    def build_taxa_from_table1(self) -> None:
        for r in self.inp.t1_taxa.itertuples():
            order, _ = parse_rank_heading(r.verbatim_order)
            family, fam_auth = parse_rank_heading(r.verbatim_family)
            self.ledger.hit("R_RANK_HEADING", 2)
            self.family_order[family] = order
            # Strip only the free-standing legend marks (' †', ' ?'). A '?' glued to
            # 'sp.' is kept: 'Phymactis sp.?' -> qualifier 'sp.?' AND doubtful flag
            # (decision confirmed by the author in step 1).
            name = re.sub(r"(\s+[†?])+$", "", r.verbatim_name)
            tid, _ = self._taxon(name, "table1", r.source_ref, int(r.source_page))
            row = next(t for t in self.taxa.values() if t["taxon_id"] == tid)
            row.update(
                order=order,
                family=family,
                family_authorship=fam_auth,
                table1_row=int(r.row_no),
                flag_invalid_in_source=r.flag_invalid == "True",
                flag_doubtful_in_source=r.flag_doubtful == "True",
            )
            self.ledger.hit("R_FLAGS")
            if r.verbatim_name != name:  # keep the printed form with its marks
                self.variants.setdefault(
                    r.verbatim_name,
                    {
                        "verbatim_name": r.verbatim_name,
                        "taxon_id": tid,
                        "identification_qualifier": parse_name(name).qualifier,
                        "variant_rule": "R_FLAGS",
                        "source_ref": r.source_ref,
                    },
                )

    def attach_accounts(self) -> pd.DataFrame:
        rows = []
        for r in self.inp.accounts.itertuples():
            tid, _ = self._taxon(r.name_text, "species_account", r.source_ref, int(r.source_page))
            taxon = next(t for t in self.taxa.values() if t["taxon_id"] == tid)
            taxon["scientific_name_authorship"] = r.verbatim_authority
            self.ledger.hit("R_ACCOUNT_JOIN")
            rows.append(
                {
                    "habitat_statement_id": mint_id(self.ns, "habitat", taxon["scientific_name"]),
                    "taxon_id": tid,
                    "habitat_text": r.habitat_text,
                    "source_ref": r.source_ref,
                    "source_page": int(r.source_page),
                }
            )
        return pd.DataFrame(rows)

    # ---------------------------------------------------------- localities
    def build_areas(self) -> list[dict]:
        rows = []
        for r in self.inp.t1_localities.itertuples():
            if r.verbatim_locality == OPEN_SEA_COL:
                self.ledger.note("R_OPEN_SEA", r.source_ref, "column not modelled as a locality")
                continue
            lid = mint_id(self.ns, "locality:area", r.verbatim_locality)
            self.area_ids[r.locality_col_id] = lid
            rows.append(
                {
                    "locality_id": lid,
                    "locality_name": trim(r.verbatim_locality),
                    "verbatim_locality": r.verbatim_locality,
                    "locality_level": "area",
                    "parent_locality_id": None,
                    "region": r.region,
                    "state_province": None,
                    "country_code": COUNTRY_CODE,
                    "decimal_latitude": None,
                    "decimal_longitude": None,
                    "verbatim_coordinates": None,
                    "sampled_in_study": r.sampled_in_study == "True",
                    "source_ref": r.source_ref,
                    "source_page": int(r.source_page),
                }
            )
        return rows

    def _parent(self, table: str, key: str, source_ref: str) -> str | None:
        if (table, key) in self.crosswalk:
            col = self.crosswalk[(table, key)]
            self.ledger.hit("R_CROSSWALK")
            return self.area_ids[col] if col else None
        self.ledger.note("R_CROSSWALK", source_ref, f"no accepted area for {key!r} ({table})")
        return None

    def _state(self, verbatim: str, source_ref: str) -> str | None:
        v = trim(verbatim)
        if v is None:
            return None
        if v not in self.state_map:
            raise ValueError(f"{source_ref}: state {v!r} missing from mappings/state_names.csv")
        if self.state_map[v] != v:
            self.ledger.note("R_STATE", source_ref, f"{v!r} -> {self.state_map[v]!r}")
        return self.state_map[v]

    # ---------------------------------------------------------- occurrences
    def build_table2(self, sites: dict[str, dict]) -> tuple[list[dict], list[dict]]:
        dates = dict(
            zip(self.inp.event_dates.national_park, self.inp.event_dates.event_date, strict=True)
        )
        occ, ident = [], []
        for r in self.inp.t2.itertuples():
            lat = dms_to_decimal(r.verbatim_latitude, "N")
            lon = dms_to_decimal(r.verbatim_longitude, "W")
            self.ledger.hit("R_DMS", 2)
            key = f"{r.national_park}|{r.verbatim_locality}|{lat}|{lon}"
            if key not in sites:
                sites[key] = {
                    "locality_id": mint_id(self.ns, "locality:site", key),
                    "locality_name": trim(r.verbatim_locality),
                    "verbatim_locality": r.verbatim_locality,
                    "locality_level": "site",
                    "parent_locality_id": self._parent("table2", r.national_park, r.source_ref),
                    "region": None,
                    "state_province": self._state(r.verbatim_state, r.source_ref),
                    "country_code": COUNTRY_CODE,
                    "decimal_latitude": lat,
                    "decimal_longitude": lon,
                    "verbatim_coordinates": f"{r.verbatim_latitude} N, {r.verbatim_longitude} W",
                    "sampled_in_study": None,
                    "source_ref": r.source_ref,
                    "source_page": int(r.source_page),
                }
            catalog, remark = parse_catalog(r.mohbr_catalog)
            if remark:
                self.ledger.note("R_CATALOG", r.source_ref, remark)
            event_date = trim(dates.get(r.national_park))
            self.ledger.hit("R_DATE_METHODS")
            # Natural key: institution + catalogue number, as for Table 3, so that a lot keeps its
            # identifier wherever it is cited; the field code only where no number was assigned
            # yet ('In progress', RG-041).
            oid = mint_id(
                SPECIMEN_NAMESPACE,
                "occurrence",
                f"{INSTITUTION}:{catalog}" if catalog else f"field:{r.field_code}",
            )
            occ.append(
                {
                    "occurrence_id": oid,
                    "basis_of_record": "PreservedSpecimen",
                    "record_source": "table2",
                    "institution_code": INSTITUTION,
                    "catalog_number": catalog,
                    "other_catalog_numbers": r.field_code,
                    "locality_id": sites[key]["locality_id"],
                    "event_date": event_date,
                    "verbatim_event_date": None,
                    "recorded_by": None,
                    "occurrence_remarks": remark,
                    "source_ref": r.source_ref,
                    "source_page": int(r.source_page),
                }
            )
            tid, qual = self._taxon(r.verbatim_species, "table2", r.source_ref, int(r.source_page))
            ident.append(
                self._identification(oid, tid, r.verbatim_species, qual, True, None, r.source_ref)
            )
        return occ, ident

    def build_table3(self, sites: dict[str, dict]) -> tuple[list[dict], list[dict]]:
        occ, ident = [], []
        for r in self.inp.t3.itertuples():
            loc_name = trim(r.verbatim_locality)
            state = self._state(r.verbatim_state, r.source_ref)
            locality_id = None
            if loc_name is None:
                self.ledger.note("R_MISSING", r.source_ref, "locality not recorded ('-')")
            else:
                key = f"table3|{state}|{loc_name}"
                if key not in sites:
                    sites[key] = {
                        "locality_id": mint_id(self.ns, "locality:site", key),
                        "locality_name": loc_name,
                        "verbatim_locality": r.verbatim_locality,
                        "locality_level": "site",
                        "parent_locality_id": self._parent("table3", loc_name, r.source_ref),
                        "region": None,
                        "state_province": state,
                        "country_code": COUNTRY_CODE,
                        "decimal_latitude": None,
                        "decimal_longitude": None,
                        "verbatim_coordinates": None,
                        "sampled_in_study": None,
                        "source_ref": r.source_ref,
                        "source_page": int(r.source_page),
                    }
                locality_id = sites[key]["locality_id"]
            iso, problem = event_date_with_precision(r.verbatim_date)
            self.ledger.hit("R_DATE_DMY")
            if problem:
                self.ledger.note(
                    "R_DATE_PRECISION", r.source_ref, f"{r.verbatim_date!r}: {problem}"
                )
            catalog, remark = parse_catalog(r.mohbr_catalog)
            people = normalise_people(r.verbatim_collector)
            if people and people.replace(" | ", " and ") != trim(r.verbatim_collector):
                self.ledger.note(
                    "R_PERSON", r.source_ref, f"{r.verbatim_collector!r} -> {people!r}"
                )
            # Natural key: institution + catalogue number (never the identification). Every
            # Table 3 row has one; the fallback (row number) is not stable and is never used.
            if not catalog:
                raise ValueError(f"{r.source_ref}: Table 3 specimen without a catalogue number")
            oid = mint_id(SPECIMEN_NAMESPACE, "occurrence", f"{INSTITUTION}:{catalog}")
            occ.append(
                {
                    "occurrence_id": oid,
                    "basis_of_record": "PreservedSpecimen",
                    "record_source": "table3",
                    "institution_code": INSTITUTION,
                    "catalog_number": catalog,
                    "other_catalog_numbers": None,
                    "locality_id": locality_id,
                    "event_date": iso,
                    "verbatim_event_date": trim(r.verbatim_date),
                    "recorded_by": people,
                    "occurrence_remarks": f"eventDate: {problem}" if problem else remark,
                    "source_ref": r.source_ref,
                    "source_page": int(r.source_page),
                }
            )
            ident.append(self._current_t3(oid, r))
            prev, curr = trim(r.previous_identification), trim(r.current_identification)
            if prev and prev != curr:
                self.ledger.hit("R_PREVIOUS_ID")
                ident.append(self._name_or_none(oid, prev, False, "table3_previous", r))
        return occ, ident

    def _current_t3(self, oid: str, r) -> dict:
        curr = trim(r.current_identification)
        if curr == "not identified":
            self.ledger.note(
                "R_NOT_IDENTIFIED", r.source_ref, f"previous: {r.previous_identification!r}"
            )
            return self._identification(
                oid,
                None,
                curr,
                None,
                True,
                "Identification could not be corroborated due to the poor condition of the"
                " preserved specimen (Discussion, p. 25).",
                r.source_ref,
            )
        return self._name_or_none(oid, curr, True, "table3_current", r)

    def _name_or_none(self, oid: str, name: str, current: bool, role: str, r) -> dict:
        # The reason for a change (spelling, name update, determination, unverified) is
        # classified later against WoRMS (anemone_kg.dq.crosstable.identification_changes).
        remark = None if current else "Previous identification (Table 3, Appendix 2)"
        if is_informal(name):
            self.ledger.note("R_INFORMAL", r.source_ref, f"{name!r} is not a scientific name")
            return self._identification(
                oid,
                None,
                name,
                None,
                current,
                "Informal collection label, not a scientific name",
                r.source_ref,
            )
        tid, qual = self._taxon(name, role, r.source_ref, int(r.source_page))
        return self._identification(oid, tid, name, qual, current, remark, r.source_ref)

    def _identification(self, oid, tid, verbatim, qual, current, remark, source_ref) -> dict:
        return {
            "identification_id": mint_id(self.ns, "identification", f"{oid}|{verbatim}|{current}"),
            "occurrence_id": oid,
            "taxon_id": tid,
            "verbatim_name": verbatim,
            "identification_qualifier": qual,
            "is_current": current,
            "identification_remarks": remark,
            "source_ref": source_ref,
        }

    # -------------------------------------------------------- distribution
    def build_distribution(self) -> pd.DataFrame:
        cells = self.inp.t1_cells
        taxa_by_row = {
            t["table1_row"]: t["taxon_id"] for t in self.taxa.values() if t["table1_row"]
        }
        legend = self.inp.t1_legend.set_index("code")["meaning"]
        open_sea = set(
            self.inp.t1_localities.loc[
                self.inp.t1_localities.verbatim_locality == OPEN_SEA_COL, "locality_col_id"
            ]
        )
        rows = []
        for (row_no, col), grp in cells.groupby(["row_no", "locality_col_id"], sort=False):
            codes = list(grp["code"])
            new = "N" in codes
            if new and "*" not in codes:
                raise ValueError(f"Table 1 row {row_no} {col}: 'N' without '*' in the same cell")
            if new:
                self.ledger.hit("R_NEW_RECORD_FOLD")
            for code in (c for c in codes if c != "N"):
                first = grp.iloc[0]
                kind = CODE_KIND.get(code, "literature")
                self.ledger.hit("R_CODE_KIND")
                remark = None
                if col in open_sea:
                    remark = "Table 1 column 'Open Sea Distribution' (not a locality)"
                    self.ledger.hit("R_OPEN_SEA")
                rows.append(
                    {
                        "distribution_id": mint_id(
                            self.ns, "distribution", f"{row_no}|{col}|{code}"
                        ),
                        "taxon_id": taxa_by_row[int(row_no)],
                        "locality_id": self.area_ids.get(col),
                        "evidence_kind": kind,
                        "reference_code": None if code == "*" else code,
                        # MaterialCitation only where the legend cites material (code 'a');
                        # literature and survey codes may rest on no specimen at all.
                        "basis_of_record": "MaterialCitation"
                        if kind == "mohbr_collection"
                        else "Occurrence",
                        "is_new_record": new and code == "*",
                        "occurrence_remarks": remark,
                        "source_ref": f"{first.source_ref}, code '{code}' ({legend[code]})",
                        "source_page": int(first.source_page),
                    }
                )
        return pd.DataFrame(rows)

    def build_references(self) -> pd.DataFrame:
        leg = self.inp.t1_legend
        src = leg[leg.kind == "source"]
        return pd.DataFrame(
            {
                "reference_code": src["code"],
                "short_citation": src["meaning"],
                "evidence_kind": [CODE_KIND.get(c, "literature") for c in src["code"]],
                "source_ref": src["source_ref"],
                "source_page": src["source_page"].astype(int),
            }
        )

    # ---------------------------------------------------------------- run
    def build(self) -> dict[str, pd.DataFrame]:
        self.build_taxa_from_table1()
        areas = self.build_areas()
        sites: dict[str, dict] = {}
        occ2, id2 = self.build_table2(sites)
        occ3, id3 = self.build_table3(sites)
        habitat = self.attach_accounts()
        distribution = self.build_distribution()

        taxa = pd.DataFrame(self.taxa.values())
        taxa["name_roles"] = taxa["name_roles"].map(lambda s: "|".join(sorted(s)))
        taxa["table1_row"] = taxa["table1_row"].astype("Int64")
        return {
            "source_document": pd.DataFrame(
                [
                    {
                        "doi": self.source["doi"],
                        "bibliographic_citation": " ".join(self.source["citation"].split()),
                        "license": self.source["license"],
                        "sha256": self.sha256,
                    }
                ]
            ),
            "reference": self.build_references(),
            "taxon": taxa,
            "taxon_name_variant": pd.DataFrame(self.variants.values()),
            "locality": pd.DataFrame(areas + list(sites.values())),
            "occurrence": pd.DataFrame(occ2 + occ3),
            "identification": pd.DataFrame(id2 + id3),
            "distribution": distribution,
            "habitat_statement": habitat,
        }
