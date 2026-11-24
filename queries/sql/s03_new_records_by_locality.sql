-- title: New records by locality (SQL)
-- question: Same as q02: sampled localities, taxa documented by the survey and new records.
-- why: Shows the relational modelling of the same facts; tests/test_queries.py compares with q02.
SELECT l.locality_name                                      AS locality,
       COUNT(DISTINCT d.taxon_id)                           AS taxa_documented,
       COUNT(*) FILTER (WHERE d.is_new_record)              AS new_records,
       string_agg(DISTINCT CASE WHEN d.is_new_record THEN t.scientific_name END, ', ')
                                                            AS new_record_taxa
FROM distribution d
JOIN locality l ON l.locality_id = d.locality_id
JOIN taxon t    ON t.taxon_id = d.taxon_id
WHERE d.evidence_kind = 'this_survey' AND l.sampled_in_study
GROUP BY l.locality_name
ORDER BY new_records DESC, taxa_documented DESC;
