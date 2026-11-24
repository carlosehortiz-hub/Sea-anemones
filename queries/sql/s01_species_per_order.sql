-- title: Species per order (SQL)
-- question: Same as q01, over the canonical tables in DuckDB.
-- why: Two paradigms, one answer; tests/test_queries.py requires q01 and s01 to agree.
SELECT "order",
       COUNT(*)                                           AS species,
       COUNT(*) FILTER (WHERE flag_invalid_in_source)     AS marked_invalid
FROM taxon
WHERE taxon_rank = 'species' AND "order" IS NOT NULL
GROUP BY "order"
ORDER BY species DESC, "order";
