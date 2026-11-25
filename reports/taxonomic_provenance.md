# Taxonomic provenance: acts, NCBI coverage, service releases

## Service releases

| service | release |
|---|---|
| GBIF Backbone Taxonomy | dataset d7dddbf4-2cf0-4f39-9b2a-bb099caae36c, published 2023-08-28, licence CC BY 4.0 |
| NCBI Taxonomy | database last updated 2026/11/24 21:01 |
| ENVO (via OLS) | http://purl.obolibrary.org/obo/envo/releases/2026-10-23/envo.owl |
| WoRMS | no release number; the access date of each cached response is the version |

## Name changes between the article and WoRMS

Relation classified from the WoRMS status, unaccept reason and names; act sources are the WoRMS sources whose use is a new combination, a synonymy or a taxonomy source.

|   aphia_id | name                       | worms_status               | unaccept_reason                                                                                                                                                              | accepted_name                |   accepted_aphia_id | relation                                                                         | act_sources                                                                                               | act_years   | timing                |
|-----------:|:---------------------------|:---------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------|--------------------:|:---------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------|:------------|:----------------------|
|     283486 | Aiptasia pallida           | unaccepted                 | new genus created by Grajales & Rodriguez 2014                                                                                                                               | Exaiptasia diaphana          |             1264073 | synonym                                                                          | unaccept reason: new genus created by Grajales & Rodriguez 2014                                           | 2014        | before 2016           |
|     283343 | Anthopleura cascaia        | nomen nudum                | name unavailable according to ICZN Article 11.1: no description published                                                                                                    | Anthopleura correae          |             1873438 | nomen nudum: unavailable name; the accepted name is the WoRMS editors' judgement |                                                                                                           |             | not dated in WoRMS    |
|     283411 | Bunodosoma cavernata       | unaccepted                 |                                                                                                                                                                              | Bunodosoma cavernatum        |              592952 | gender agreement of the epithet (ICZN Art. 34.2)                                 |                                                                                                           |             | not dated in WoRMS    |
|     592855 | Corynactis caribbeorum     | unaccepted                 |                                                                                                                                                                              | Pseudocorynactis caribbeorum |              101017 | new combination (genus transfer)                                                 | source of synonymy: Fautin, D.G (2011) | taxonomy source: Ocaña, O, den Hartog, J. C., and Brito A (2017) | 2011, 2017  | before and after 2016 |
|     581448 | Epizoanthus cutressi       | unaccepted                 |                                                                                                                                                                              | Bergia cutressi              |              853594 | new combination (genus transfer)                                                 | new combination reference: Swain, T. D.; Schellinger, J. L.; Strimaitis, A. M.; Reuter, K. E (2015)       | 2015        | before 2016           |
|     888637 | Exaiptasia pallida         | alternative representation | subjective synonym; epithet diaphana retains priority over pallida (ICZN Opinion 2404). However, epithet pallida valid until ICZN rules Case 3790 (revision of Opinion 2404) | Exaiptasia diaphana          |             1264073 | alternative representation in WoRMS (see text: ICZN Opinion 2500, 2023)          | source of synonymy: ICZN (2017) | new combination reference: Grajales, A.; Rodríguez, E (2014)            | 2014, 2017  | before and after 2016 |
|     100873 | Haliplanella luciae        | unaccepted                 |                                                                                                                                                                              | Diadumene lineata            |              395099 | synonym                                                                          |                                                                                                           |             | not dated in WoRMS    |
|     101056 | Isaurus duchassaingi       | unaccepted                 | synonym                                                                                                                                                                      | Isaurus tuberculatus         |              101058 | synonym                                                                          |                                                                                                           |             | not dated in WoRMS    |
|     290278 | Lebrunia danae             | unaccepted                 |                                                                                                                                                                              | Lebrunia neglecta            |              742298 | synonym                                                                          |                                                                                                           |             | not dated in WoRMS    |
|     283867 | Parazoanthus catenularis   | unaccepted                 |                                                                                                                                                                              | Bergia catenularis           |              853592 | new combination (genus transfer)                                                 | new combination reference: Montenegro, J.; Low, M. E. Y.; Reimer, J. D (2015)                             | 2015        | before 2016           |
|     283871 | Parazoanthus parasiticus   | unaccepted                 | Moved to genus Umimayanthus                                                                                                                                                  | Umimayanthus parasiticus     |              847839 | new combination (genus transfer)                                                 |                                                                                                           |             | not dated in WoRMS    |
|     488982 | Parazoanthus puertoricense | unaccepted                 |                                                                                                                                                                              | Bergia puertoricense         |              853593 | new combination (genus transfer)                                                 | new combination reference: Montenegro, J.; Low, M. E. Y.; Reimer, J. D (2015)                             | 2015        | before 2016           |
|     590578 | Zoanthus proteus           | unaccepted                 |                                                                                                                                                                              | Zoanthus sociatus            |              288843 | synonym                                                                          |                                                                                                           |             | not dated in WoRMS    |

## NCBI Taxonomy: retry of unresolved names

17 names had no node under `[Scientific Name]`. Each was re-queried under all NCBI name classes (`[All Names]`) and under every WoRMS synonym of its accepted name. 3 have a node under another name class or a synonym; they are reported, not linked, because the node does not carry the printed name as its scientific name.

| name                         | order            | family           |   retry | retry_hit                                                                | genus_in_ncbi   |
|:-----------------------------|:-----------------|:-----------------|--------:|:-------------------------------------------------------------------------|:----------------|
| Actinoporus elegans          | Actiniaria       | Capneidae        |       2 | none                                                                     | False           |
| Anemonia sargassensis        | Actiniaria       | Actiniidae       |       2 | none                                                                     | True            |
| Bartholomea werneri          | Actiniaria       | Aiptasiidae      |       1 | none                                                                     | True            |
| Bunodeopsis antilliensis     | Actiniaria       | Boloceroididae   |       2 | Bunodeopsis antilliensis -> NCBI taxid 1499598 (Bunodeopsis globulifera) | True            |
| Bunodosoma kuekenthali       | Actiniaria       | Actiniidae       |       5 | none                                                                     | True            |
| Ceriantheopsis americanus    | Ceriantharia     | Cerianthidae     |       2 | Ceriantheopsis americanus -> NCBI taxid 37515 (Ceriantheopsis americana) | True            |
| Corynactis caribbeorum       | Corallimorpharia | Corallimorphidae |       2 | none                                                                     | True            |
| Homostichantus duerdenii     | nan              | nan              |       7 | Stichodactyla duerdeni -> NCBI taxid 1301368 (Homostichanthus duerdeni)  | False           |
| Isoaulactinia stelloides     | Actiniaria       | Actiniidae       |       4 | none                                                                     | False           |
| Monactis vestita             | Actiniaria       | Hormathiidae     |       2 | none                                                                     | True            |
| Pachycerianthus curacaoensis | Ceriantharia     | Cerianthidae     |       1 | none                                                                     | True            |
| Palythoa caribbeorum         | nan              | nan              |       5 | none                                                                     | True            |
| Palythoa mammillosa          | Zoanthidea       | Sphenopidae      |       8 | none                                                                     | True            |
| Phyllactis praetexta         | nan              | nan              |       4 | none                                                                     | True            |
| Scolanthus curacaoensis      | Actiniaria       | Edwardsiidae     |       5 | none                                                                     | True            |
| Telmatactis rufa             | nan              | nan              |       2 | none                                                                     | True            |
| Telmatactis vernonia         | Actiniaria       | Isophelliidae    |       4 | none                                                                     | True            |

## INSDC nucleotide records per linked taxon

Count of nucleotide records for the taxid and its descendants (`txid[Organism:exp]`). A taxid is a prerequisite for linking sequences by name, not evidence that sequences exist for a useful marker; per-marker counts are out of scope.

| name                          | order            | ncbi_result       |   taxid |   nucleotide_records |
|:------------------------------|:-----------------|:------------------|--------:|---------------------:|
| Actinia bermudensis           | Actiniaria       | exact_accepted    | 1078900 |                    2 |
| Actiniidae                    | Actiniaria       | exact_accepted    |   42822 |               306378 |
| Actinostella flosculifera     | Actiniaria       | exact_accepted    | 3034631 |                  137 |
| Aiptasia pallida              | nan              | via_accepted_name | 2652724 |               111833 |
| Anthopleura cascaia           | Actiniaria       | exact_accepted    | 2805811 |                   65 |
| Anthopleura krebsi            | Actiniaria       | exact_accepted    |  478384 |                   18 |
| Anthopleura pallida           | Actiniaria       | exact_accepted    | 2022716 |                    4 |
| Bartholomea annulata          | Actiniaria       | exact_accepted    |  478392 |                   63 |
| Bunodosoma caissarum          | Actiniaria       | exact_accepted    |   31165 |                    3 |
| Bunodosoma cangicum           | Actiniaria       | exact_accepted    |  138296 |                    4 |
| Bunodosoma cavernata          | nan              | via_accepted_name | 2022721 |                   13 |
| Bunodosoma cavernatum         | Actiniaria       | exact_accepted    | 2022721 |                   13 |
| Bunodosoma granuliferum       | Actiniaria       | exact_accepted    |   31164 |                   15 |
| Calliactis tricolor           | Actiniaria       | exact_accepted    |  656065 |                   18 |
| Ceriantheomorphe brasiliensis | Ceriantharia     | exact_accepted    | 1048506 |                   63 |
| Condylactis gigantea          | Actiniaria       | exact_accepted    |   47073 |                   55 |
| Diadumene lineata             | Actiniaria       | exact_accepted    | 1789172 |                   99 |
| Discosoma carlgreni           | Corallimorpharia | exact_accepted    |  541188 |                   15 |
| Epizoanthus cutressi          | Zoanthidea       | via_accepted_name |  518606 |                    7 |
| Exaiptasia pallida            | Actiniaria       | via_accepted_name | 2652724 |               111833 |
| Haliplanella luciae           | nan              | via_accepted_name | 1789172 |                   99 |
| Homostichanthus duerdeni      | Actiniaria       | exact_accepted    | 1301368 |                    0 |
| Isarachnanthus nocturnus      | Ceriantharia     | exact_accepted    | 1240238 |                   94 |
| Isaurus duchassaingi          | Zoanthidea       | via_accepted_name |  167633 |                   73 |
| Laviactis lucida              | Actiniaria       | exact_accepted    | 1720311 |                   30 |
| Lebrunia coralligens          | Actiniaria       | exact_accepted    | 1326991 |                    9 |
| Lebrunia danae                | nan              | via_accepted_name |  338257 |                   16 |
| Lebrunia neglecta             | Actiniaria       | exact_accepted    |  338257 |                   16 |
| Palythoa caribaeorum          | Zoanthidea       | exact_accepted    |  134933 |                  173 |
| Palythoa grandis              | Zoanthidea       | exact_accepted    |  862612 |                   18 |
| Palythoa variabilis           | Zoanthidea       | exact_accepted    |   86597 |                    4 |
| Parazoanthus catenularis      | Zoanthidea       | exact_accepted    |  518607 |                   14 |
| Parazoanthus parasiticus      | Zoanthidea       | via_accepted_name | 2608291 |                   37 |
| Parazoanthus puertoricense    | Zoanthidea       | via_accepted_name | 2608285 |                   20 |
| Parazoanthus swiftii          | Zoanthidea       | exact_accepted    |  328570 |                   68 |
| Phymactis                     | Actiniaria       | exact_accepted    | 1078902 |                    6 |
| Phymanthus crucifer           | Actiniaria       | exact_accepted    | 1291152 |                   76 |
| Rhodactis osculifera          | Corallimorpharia | exact_accepted    | 2751898 |                   36 |
| Stichodactyla helianthus      | Actiniaria       | exact_accepted    |    6123 |                   22 |
| Telmatactis cricoides         | Actiniaria       | exact_accepted    | 1143180 |                    4 |
| Zoanthus proteus              | Zoanthidea       | via_accepted_name |  134931 |                  128 |
| Zoanthus pulchellus           | Zoanthidea       | exact_accepted    |  504656 |                  141 |
| Zoanthus sociatus             | Zoanthidea       | exact_accepted    |  134931 |                  128 |
| Zoanthus solanderi            | Zoanthidea       | exact_accepted    |  487818 |                   23 |

## Sequences citing the MOHBR collection

- `MOHBR[All Fields]` in INSDC nucleotide: 0 records
- `"Hermano Benigno"[All Fields]` in INSDC nucleotide: 0 records
