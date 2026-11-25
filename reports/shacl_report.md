# SHACL validation report

**Violations: 0** - 20678 data triples validated against 14 node shapes (pySHACL, `advanced=True` for SPARQL targets and constraints, `inference='none'`, `allow_warnings=True`).

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
| Warning | `https://w3id.org/anemone-kg/event/0b0883e5-04dd-5d2a-bd12-94c885becba2` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/event/1f849e46-170d-577c-9025-af280c60795f` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/event/9f301ed8-3c25-5741-b990-a673c20cf045` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/event/aa426d71-0539-5846-8202-42dd89b3470e` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/habitat/a0c61a95-d204-54a9-be6b-5f99672d12fe` |  | dwciri:habitat \| dwciri:substrate |
| Warning | `https://w3id.org/anemone-kg/habitat/c9425cba-ff74-5fc4-b74b-18eda2659a5a` |  | dwciri:habitat \| dwciri:substrate |
| Warning | `https://w3id.org/anemone-kg/occurrence/211cc241-5efc-5e72-b6dc-6f1914e113f0` | MOHBR I-896 | dwciri:toTaxon |
| Warning | `https://w3id.org/anemone-kg/occurrence/d23283b8-5d04-503a-9570-d80bca12d86e` | MOHBR I-955 | dwciri:toTaxon |
| Warning | `https://w3id.org/anemone-kg/occurrence/e545e28a-c6c5-5cf1-88fd-c48a5882495f` | MOHBR I-954 | dwciri:toTaxon |
