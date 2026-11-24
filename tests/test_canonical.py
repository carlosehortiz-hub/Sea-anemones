"""Canonicalisation tests: contract with the LinkML schema, rule governance, and
the specific harmonisation decisions taken in step 2."""

from __future__ import annotations

import pandas as pd
import pytest
from linkml_runtime.utils.schemaview import SchemaView

from anemone_kg.canonical.rules import RULES, dms_to_decimal, parse_dmy, parse_name
from anemone_kg.config import load_config
from anemone_kg.stages.canonicalize import build_canonical

CLASS_FOR_TABLE = {
    "source_document": "SourceDocument",
    "reference": "Reference",
    "taxon": "Taxon",
    "taxon_name_variant": "TaxonNameVariant",
    "locality": "Locality",
    "occurrence": "Occurrence",
    "identification": "Identification",
    "distribution": "Distribution",
    "habitat_statement": "HabitatStatement",
}


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(scope="session")
def built(cfg):
    tables, ledger, _ = build_canonical(cfg)
    return tables, ledger


@pytest.fixture(scope="session")
def sv(cfg):
    return SchemaView(str(cfg.root / cfg.raw["paths"]["schema"]))


def _taxon_id(tables, name):
    t = tables["taxon"]
    return t.loc[t.scientific_name == name, "taxon_id"].item()


# ------------------------------------------------------------ contract
@pytest.mark.parametrize("table", CLASS_FOR_TABLE)
def test_columns_match_linkml_class(built, sv, table):
    tables, _ = built
    expected = {s.name for s in sv.class_induced_slots(CLASS_FOR_TABLE[table])}
    assert set(tables[table].columns) == expected


@pytest.mark.parametrize("table", CLASS_FOR_TABLE)
def test_identifier_is_unique_and_required_fields_present(built, sv, table):
    tables, _ = built
    df = tables[table]
    for s in sv.class_induced_slots(CLASS_FOR_TABLE[table]):
        if s.identifier:
            assert df[s.name].notna().all() and df[s.name].is_unique, s.name
        elif s.required:
            assert df[s.name].notna().all(), f"{table}.{s.name} has nulls"


def test_ids_are_deterministic(cfg, built):
    """UUIDv5 ids must not change between runs (persistent identifiers)."""
    again, _, _ = build_canonical(cfg)
    for name, df in built[0].items():
        pd.testing.assert_frame_equal(df, again[name], check_dtype=False, obj=name)


# ---------------------------------------------------------- governance
def test_mapping_table_and_rule_registry_agree(cfg, built):
    mapping = pd.read_csv(cfg.path("mappings") / "source_to_canonical.csv")
    cited = set(mapping["rule_id"])
    assert cited <= set(RULES), f"unknown rules cited: {cited - set(RULES)}"
    assert set(RULES) <= cited, f"rules never documented: {set(RULES) - cited}"
    fired = set(built[1].counts)
    assert fired <= cited


def test_every_canonical_field_is_documented(cfg, built):
    mapping = pd.read_csv(cfg.path("mappings") / "source_to_canonical.csv")
    documented = set(zip(mapping.target_table, mapping.target_field, strict=True))
    skip = {
        "source_ref",
        "source_page",
        "name_roles",
        "record_source",
        "is_current",
        "identification_remarks",
        "occurrence_remarks",
        "verbatim_locality",
        "locality_level",
        "scientific_name_authorship",
        "family_authorship",
        "identification_id",
        "distribution_id",
        "habitat_statement_id",
        "taxon_id",
        "occurrence_id",
        "locality_id",
        "variant_rule",
        "identification_qualifier",
        "verbatim_name",
        "decimal_latitude",
        "decimal_longitude",
        "region",
        "state_province",
        "parent_locality_id",
        "sampled_in_study",
        "event_date",
        "other_catalog_numbers",
        "recorded_by",
        "verbatim_event_date",
        "catalog_number",
        "institution_code",
        "verbatim_coordinates",
        "country_code",
        "short_citation",
    }
    for table, df in built[0].items():
        for col in df.columns:
            if col in skip:
                continue
            assert (table, col) in documented, f"{table}.{col} missing from mapping table"


# ------------------------------------------------------- decisions
def test_typo_variants_resolve_to_the_same_taxon(built):
    tables, _ = built
    v = tables["taxon_name_variant"].set_index("verbatim_name")
    assert v.loc["Phymantus crucifer", "taxon_id"] == _taxon_id(tables, "Phymanthus crucifer")
    assert v.loc["Phymantus crucifer", "variant_rule"] == "R_TYPO"
    assert "Phymantus crucifer" not in set(tables["taxon"].scientific_name)


def test_qualifiers_are_split_not_lost(built):
    tables, _ = built
    v = tables["taxon_name_variant"].set_index("verbatim_name")
    assert v.loc["Zoanthus cf. pulchellus", "identification_qualifier"] == "cf."
    assert v.loc["Zoanthus cf. pulchellus", "taxon_id"] == _taxon_id(tables, "Zoanthus pulchellus")
    assert v.loc["Phymactis sp.?", "identification_qualifier"] == "sp.?"
    assert "Phymactis sp." not in v.index  # the '?' must not be silently dropped
    t = tables["taxon"].set_index("scientific_name")
    assert t.loc["Phymactis", "flag_doubtful_in_source"]
    assert t.loc["Actiniidae", "taxon_rank"] == "family"
    assert t.loc["Actiniidae", "order"] == "Actiniaria"


def test_impossible_date_is_null_with_verbatim_kept(built):
    occ = built[0]["occurrence"].set_index("catalog_number")
    row = occ.loc["I-1201"]
    assert pd.isna(row["event_date"]) and row["verbatim_event_date"] == "31/04/2012"
    assert "impossible" in row["occurrence_remarks"]


def test_open_sea_has_no_locality(built):
    d = built[0]["distribution"]
    open_sea = d[d.occurrence_remarks.fillna("").str.contains("Open Sea")]
    assert len(open_sea) == 2 and open_sea.locality_id.isna().all()


def test_new_records_fold_into_survey_rows(built):
    tables, _ = built
    d = tables["distribution"]
    new = d[d.is_new_record]
    assert len(new) == 2 and (new.evidence_kind == "this_survey").all()
    assert set(new.taxon_id) == {
        _taxon_id(tables, "Anthopleura pallida"),
        _taxon_id(tables, "Telmatactis vernonia"),
    }


def test_not_identified_has_no_taxon(built):
    i = built[0]["identification"]
    ni = i[i.verbatim_name == "not identified"]
    assert len(ni) == 3 and ni.taxon_id.isna().all() and ni.is_current.all()


def test_reidentifications_keep_both_names(built):
    tables, _ = built
    i = tables["identification"]
    occ = tables["occurrence"].set_index("catalog_number")
    rows = i[i.occurrence_id == occ.loc["I-547", "occurrence_id"]].set_index("is_current")
    assert rows.loc[False, "verbatim_name"] == "Aiptasia pallida"
    assert rows.loc[True, "verbatim_name"] == "Exaiptasia pallida"


def test_only_accepted_crosswalk_rows_are_applied(cfg, built):
    """Rows the author kept unlinked (status 'rejected') must not create a parent link."""
    cw = pd.read_csv(cfg.path("mappings") / "locality_crosswalk.csv")
    assert set(cw.status) <= {"accepted", "rejected", "needs_review"}
    loc = built[0]["locality"].set_index("locality_name")
    for key in cw.loc[cw.status != "accepted", "verbatim_key"]:
        assert pd.isna(loc.loc[key, "parent_locality_id"]), key


def test_table2_event_dates_follow_methods(built):
    tables, _ = built
    occ = tables["occurrence"].merge(tables["locality"], on="locality_id")
    t2 = occ[occ.record_source == "table2"]
    cubagua = (
        t2.parent_locality_id
        == tables["locality"].set_index("locality_name").loc["Isla de Cubagua", "locality_id"]
    )
    assert t2.loc[cubagua, "event_date"].isna().all()
    assert (t2.loc[~cubagua, "event_date"] == "2012-11").all()


# --------------------------------------------------------- pure rules
@pytest.mark.parametrize(
    ("verbatim", "hemi", "expected"),
    [("10° 53’ 2.51”", "N", 10.884031), ("68°12’ 43.66”", "W", -68.212128)],
)
def test_dms(verbatim, hemi, expected):
    assert dms_to_decimal(verbatim, hemi) == expected


def test_dms_rejects_out_of_range_minutes():
    with pytest.raises(ValueError):
        dms_to_decimal("10° 61’ 2.51”", "N")


def test_parse_dmy_and_names():
    assert parse_dmy("29/02/2012") == ("2012-02-29", None)
    assert parse_dmy("29/02/2013")[0] is None
    assert parse_name("Bunodosoma cavernatum").rank == "species"
