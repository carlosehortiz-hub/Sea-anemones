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
    assert s.loc["as_curated", "cells"] == len(disc)
    assert s.attrs["uncertain_links"] == 22


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
