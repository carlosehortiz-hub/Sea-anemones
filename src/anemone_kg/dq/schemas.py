"""Pandera schemas generated from the LinkML schema - one contract, two enforcers.

LinkML (schema/anemone_kg.yaml) is the single source of truth. This module
turns each class into a :class:`pandera.DataFrameSchema`:

==================  =========================================================
LinkML              Pandera
==================  =========================================================
range               column dtype (string / Int64 / Float64 / boolean)
identifier: true    unique=True, nullable=False
required: true      nullable=False
pattern             Check.str_matches
enum range          Check.isin(permissible values)
minimum/maximum     Check.ge / Check.le
==================  =========================================================

The same mapping drives the CSV loader, so a column is read with the dtype
the schema declares instead of whatever pandas infers (e.g. an integer
column with gaps would otherwise come back as float).

These are *column-level* (within-table) rules. Rules that join tables -
referential integrity, cross-source consistency - live in dq/rules.py.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pandas as pd
import pandera.pandas as pa
from linkml_runtime.utils.schemaview import SchemaView

TABLE_CLASS = {
    "source_document": "SourceDocument",
    "reference": "Reference",
    "taxon": "Taxon",
    "taxon_name_variant": "TaxonNameVariant",
    "locality": "Locality",
    "occurrence": "Occurrence",
    "identification": "Identification",
    "distribution": "Distribution",
    "habitat_statement": "HabitatStatement",
    "taxon_mapping": "TaxonMapping",
    "worms_record": "WormsRecord",
    "habitat_annotation": "HabitatAnnotation",
}

_DTYPE = {"integer": "Int64", "decimal": "Float64", "float": "Float64", "boolean": "boolean"}


@cache
def schema_view(path: str) -> SchemaView:
    return SchemaView(path)


def _dtype(sv: SchemaView, rng: str | None) -> str:
    return _DTYPE.get(rng or "string", "string")


def dtypes_for(sv: SchemaView, cls: str) -> dict[str, str]:
    return {s.name: _dtype(sv, s.range) for s in sv.class_induced_slots(cls)}


def load_table(sv: SchemaView, cls: str, path: Path) -> pd.DataFrame:
    """Read a canonical CSV with the dtypes LinkML declares."""
    return pd.read_csv(path, dtype=dtypes_for(sv, cls), keep_default_na=True)


def dataframe_schema(sv: SchemaView, cls: str) -> pa.DataFrameSchema:
    columns: dict[str, pa.Column] = {}
    enums = sv.all_enums()
    for s in sv.class_induced_slots(cls):
        checks: list[pa.Check] = []
        if s.pattern:
            checks.append(pa.Check.str_matches(s.pattern, name=f"pattern {s.pattern}"))
        if s.range in enums:
            allowed = list(sv.get_enum(s.range).permissible_values)
            checks.append(pa.Check.isin(allowed, name=f"enum {s.range}"))
        if s.minimum_value is not None:
            checks.append(pa.Check.ge(s.minimum_value, name=f">= {s.minimum_value}"))
        if s.maximum_value is not None:
            checks.append(pa.Check.le(s.maximum_value, name=f"<= {s.maximum_value}"))
        columns[s.name] = pa.Column(
            _dtype(sv, s.range),
            checks=checks,
            nullable=not (s.identifier or s.required),
            unique=bool(s.identifier),
            required=True,
            description=s.description,
        )
    return pa.DataFrameSchema(columns, name=cls, strict=True, ordered=False)
