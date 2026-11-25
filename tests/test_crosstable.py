"""Cross-table review per cell; evidence tiers by identification status; link scenarios."""

from __future__ import annotations

import pandas as pd
import pytest

from anemone_kg.config import load_config
from anemone_kg.dq import crosstable as ct
from anemone_kg.stages.validate import load_tables


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def t(cfg):
    return load_tables(cfg)


@pytest.fixture(scope="module")
def cw(cfg):
    return pd.read_csv(cfg.path("mappings") / "locality_crosswalk.csv")


@pytest.fixture(scope="module")
def disc(t, cw):
    return ct.discrepancies(t, cw)


def test_one_definition_of_uncertain_link(cw):
    """Review finding (round 2): three different notions of 'uncertain link' were used."""
    un = ct.uncertain_links(cw)
    assert len(un) == 22
    assert set(un.rule) == {"names_area", "article_variant", "geographic_knowledge"}


def test_cells_are_unique_and_every_cell_has_a_kind(disc):
    assert not disc.duplicated(["aphia_id", "area"]).any()
    assert disc[list(ct.KINDS)].any(axis=1).all()


def test_one_cell_is_not_filed_twice(disc):
    """Bug once (round 2): the Bunodeopsis antilliensis Morrocoy cell was filed as explained in
    one row (W09) and unexplained in another (W10). As one cell it carries both kinds, and the
    same presence under another code is a code-level difference, not an explanation."""
    r = disc[(disc.taxon == "Bunodeopsis antilliensis") & disc.area.str.startswith("Morrocoy")]
    assert len(r) == 1
    assert r.museum_code_no_specimen.item() and r.survey_specimen_no_code.item()
    assert r.code_level_only.item() and not r.explained.item()


def test_area_unconditioned_comparison_reaches_areas_without_specimens(disc):
    """W08/W10 only compare areas the specimen table covers; the cell review does not."""
    assert disc.area_without_specimens.any()


def test_link_dependence_is_a_condition_not_a_cause(disc):
    assert "link" not in ct.CAUSES
    assert disc.link_dependent.any()


def test_reidentification_both_sides(disc):
    """The Playa Azul re-identification appears on the code side and the specimen side."""
    pa = disc[disc.area.str.startswith("Playa Azul") & disc.reidentified]
    assert set(pa.taxon) == {"Homostichanthus duerdeni", "Actinoporus elegans"}


def test_scenarios_bracket_the_curated_count(t, cw, disc):
    s = ct.scenario_counts(t, cw).set_index("scenario")
    assert s.loc["as_curated", "cells"] == disc.comparable.sum()
    assert s.attrs["uncertain_links"] == 22
    share = s.specimen_share
    assert share.all_unlinked <= share.as_curated <= share.all_linked


def test_tiers_depend_on_identification_status(t):
    """Review finding (round 2): a museum code traced only through a previous identification
    was ranked with confirmed specimens."""
    tiers = ct.evidence_tiers(t)
    assert tiers.notna().all() and len(tiers) == len(t["distribution"])
    c = tiers.value_counts()
    assert c["MuseumReidentified"] >= 1 and c["MuseumUnconfirmed"] >= 1
    assert sum(c.get(k, 0) for k in c.index if k.startswith("Museum")) == 56
    assert sum(c.get(k, 0) for k in c.index if k.startswith("Survey")) == 57
    assert c["LiteratureRecord"] == 229


def test_tier_and_rule_counts_reconcile(t):
    """15 unvouchered survey codes vs W08 = 13: the 2 others lie in areas with no Table 2
    specimen at all, which W08 does not compare."""
    x = ct.tier_rule_crosstab(t)
    unv = x[x.tier == "SurveyUnvouchered"]
    assert unv[unv.flagged].assertions.sum() == 13
    assert unv[~unv.area_has_specimens].assertions.sum() == 2


def test_best_tier_partitions_the_cells(t):
    cells = ct.cell_support(t)
    assert set(cells.best_tier) <= set(ct.BEST_TIER)
    d = t["distribution"]
    assert len(cells) == d[d.locality_id.notna()].groupby(["taxon_id", "locality_id"]).ngroups


def test_accepted_name_cells_merge_synonyms(t):
    by_name, by_acc = ct.cell_support(t), ct.cell_support(t, by="accepted")
    assert len(by_acc) < len(by_name)


def test_above_species_never_explains_a_specimen_without_a_code(disc):
    """Bug once (round 3): the rule was direction-blind, so unrelated Actiniidae sp. at
    Cubagua 'explained' a species-level Condylactis gigantea specimen missing from Table 1."""
    r = disc[(disc.taxon == "Condylactis gigantea") & (disc.area == "Isla de Cubagua")]
    assert len(r) == 1 and r.survey_specimen_no_code.item()
    assert not r.above_species.item() and r.unexplained.item()
    spec = disc[disc.survey_specimen_no_code | disc.museum_specimen_no_code]
    assert not (
        spec.above_species & ~spec.survey_code_no_voucher & ~spec.museum_code_no_specimen
    ).any()


def test_family_level_cells_are_not_comparable(disc):
    """Actiniidae sp. has no Table 1 row, so its cells cannot disagree with Table 1."""
    nc = disc[~disc.comparable]
    assert set(nc.taxon) == {"Actiniidae"} and len(nc) == 3
    assert disc.comparable.sum() == 40


def test_classes_partition_the_comparable_cells(disc):
    comp = disc[disc.comparable]
    assert (comp[list(ct.CLASSES)].sum(axis=1) == 1).all()
    assert comp[list(ct.CLASSES)].sum().to_dict() == {
        "explained": 5,
        "possible": 1,
        "code_level_only": 9,
        "unexplained": 25,
    }


def test_rejected_links_drive_the_link_dependent_residual(t, cw, disc):
    s = ct.scenario_counts(t, cw).set_index("scenario")
    comp = disc[disc.comparable]
    dep = int((comp.unexplained & comp.link_dependent).sum())
    assert s.loc["as_curated", "unexplained"] - s.loc["rejected_linked", "unexplained"] == dep
    conc = ct.rejected_link_concordance(t, cw).set_index("table3_locality")
    assert conc.loc["Laguna de Punta de Piedras, Isla Margarita", "taxa_with_a_code_in_area"] == 4


def test_every_traced_assertion_cites_its_specimen(t):
    """Bug once (round 3): assertions traced only through a previous identification had no
    link, so those organisms were counted twice."""
    tiers = ct.evidence_tiers(t)
    traced = set(
        tiers[
            tiers.isin(
                [
                    "SurveyVouchered",
                    "SurveyVoucheredQualified",
                    "MuseumConfirmed",
                    "MuseumReidentified",
                    "MuseumUnconfirmed",
                ]
            )
        ].index
    )
    assert traced <= set(ct.supporting_specimens(t)) and len(traced) == 88


def test_identification_changes_are_coded(t):
    """Bug once (round 3): every previous identification was stamped 're-identified'."""
    from collections import Counter

    c = Counter(ct.identification_changes(t).values())
    assert c["unverified"] == 3 and sum(c.values()) == 25
    assert c["nomenclatural"] + c["orthographic"] > c["determination"]
