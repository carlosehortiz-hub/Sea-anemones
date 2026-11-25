# SHACL validation report

**Violations: 0** - 20780 data triples validated against 14 node shapes (pySHACL, `advanced=True` for SPARQL targets and constraints, `inference='none'`, `allow_warnings=True`).

`sh:conforms` under the SHACL Recommendation (section 3.6): **false** - it is false whenever the report holds any result, whatever its severity. The pipeline gate is weaker on purpose: with `allow_warnings=True` pySHACL returns conforms only if there is no Violation (here: true), and only Violations stop the run.

| severity | results |
|---|---:|
| Violation | 0 |
| Warning | 9 |
| Info | 1 |

Violations stop the pipeline. Warnings and Info record gaps in the source that the data-quality stage also reports; they are not errors in the graph.

## Results by message

| severity | message | count |
|---|---|---:|
| Info | Specimen without a MOHBR catalogue number (as printed in the source). | 1 |
| Warning | Event without a location ('-' in the source, or Open Sea Distribution). | 4 |
| Warning | Habitat statement with no ENVO term. | 2 |
| Warning | Specimen whose current identification has no taxon ('not identified'). | 3 |

## Focus nodes

| severity | focus node | label | path |
|---|---|---|---|
| Info | `https://w3id.org/anemone-kg/occurrence/59843dea-418c-5e2c-b895-456f0489fa82` | field code RG-041 | dwc:catalogNumber |
| Warning | `https://w3id.org/anemone-kg/event/1f849e46-170d-577c-9025-af280c60795f` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/event/62664db1-4f89-559a-bdcf-862c89b86f8c` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/event/9322a71a-cd77-5600-b657-9a7bb9ee8be2` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/event/aa426d71-0539-5846-8202-42dd89b3470e` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/habitat/a0c61a95-d204-54a9-be6b-5f99672d12fe` |  | dwciri:habitat \| dwciri:substrate |
| Warning | `https://w3id.org/anemone-kg/habitat/c9425cba-ff74-5fc4-b74b-18eda2659a5a` |  | dwciri:habitat \| dwciri:substrate |
| Warning | `https://w3id.org/anemone-kg/occurrence/8eeefb68-1c8b-5a15-9b86-7c445281e5a6` | MOHBR I-955 | dwciri:toTaxon |
| Warning | `https://w3id.org/anemone-kg/occurrence/92f0bb70-11be-5769-b947-dc4f43bb9a51` | MOHBR I-896 | dwciri:toTaxon |
| Warning | `https://w3id.org/anemone-kg/occurrence/c2db172b-6f05-5e97-af75-f408a267794b` | MOHBR I-954 | dwciri:toTaxon |
