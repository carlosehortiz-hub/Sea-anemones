-- title: Names whose accepted name differs today (SQL)
-- question: Same as q03: paper names whose WoRMS accepted name is different.
-- why: The relational path needs three joins (taxon -> mapping -> record -> accepted record);
--      in the graph it is a two-hop path. Same answer, required by tests/test_queries.py.
SELECT t.scientific_name   AS name_in_paper,
       w.taxonomic_status  AS worms_status,
       a.scientific_name   AS accepted_name,
       a.lsid              AS accepted_record
FROM taxon t
JOIN taxon_mapping m
  ON m.subject_id = t.taxon_id AND m.object_source = 'worms' AND m.status = 'accepted'
JOIN worms_record w
  ON w.aphia_id = CAST(split_part(m.object_id, ':', 2) AS INTEGER)
JOIN worms_record a
  ON a.aphia_id = w.valid_aphia_id
WHERE a.scientific_name <> t.scientific_name
ORDER BY name_in_paper;
