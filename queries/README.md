# Queries

Run them all with `python -m anemone_kg run query` (or `make run`). Results are written to
`results/*.csv`, and a readable report is written to
[`reports/query_results.md`](../reports/query_results.md). Each file starts with
`title / question / why` comments, and the report is generated from those headers.

## SPARQL (over `data/processed/anemone_kg.ttl`)

| file | question |
|---|---|
| `q01_species_per_order.rq` | Species per order in Table 1, and how many of them are marked invalid |
| `q02_new_records_by_locality.rq` | Sampled localities: taxa documented and new records for Venezuela |
| `q03_accepted_name_differs.rq` | Names in the paper whose WoRMS accepted name is different today |
| `q04_taxa_and_specimens_by_habitat.rq` | Taxa and specimens by ENVO habitat, zone or substrate |
| `q05_provenance_of_a_record.rq` | Where a record comes from in the paper, and how each of its identifiers was resolved |
| `q06_reidentified_specimens.rq` | Re-identified MOHBR specimens: label → 2016 identification → accepted name today |
| `q07_cell_support_by_region.rq` | Table 1 taxon x area cells per region by kind of support (first-hand, literature, Agudo 1987 alone) |
| `q08_taxa_missing_from_ncbi.rq` | Names found in WoRMS but missing from NCBI Taxonomy |

## SQL (DuckDB over `data/processed/canonical/*.csv`)

| file | same question as |
|---|---|
| `sql/s01_species_per_order.sql` | q01 |
| `sql/s02_accepted_name_differs.sql` | q03 |
| `sql/s03_new_records_by_locality.sql` | q02 |

`tests/test_queries.py` requires each SQL query to return exactly the same rows as its
SPARQL counterpart. The two models are different views of one dataset, and the test
checks that they give the same answers.

To run a single SPARQL query by hand:

```bash
uv run python -c "import rdflib; g=rdflib.Graph().parse('data/processed/anemone_kg.ttl'); \
print(g.query(open('queries/q03_accepted_name_differs.rq').read()).serialize(format='csv').decode())"
```
