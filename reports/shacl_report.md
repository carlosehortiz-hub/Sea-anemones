# SHACL validation report

**Violations: 0** - 21205 data triples validated against 14 node shapes (pySHACL, `advanced=True` for SPARQL targets and constraints, `inference='none'`, `allow_warnings=True`).

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
| Info | `https://w3id.org/anemone-kg/occurrence/5a21f3aa-528c-5d29-bb56-ea31d0246465` | field code RG-041 | dwc:catalogNumber |
| Warning | `https://w3id.org/anemone-kg/event/1f849e46-170d-577c-9025-af280c60795f` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/event/aa426d71-0539-5846-8202-42dd89b3470e` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/event/b7a92360-d427-5c4c-81c1-56c91fbd4e1d` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/event/fc85bf9a-3dbc-5d41-ad07-e43244730e47` |  | dsw:locatedAt |
| Warning | `https://w3id.org/anemone-kg/habitat/a0c61a95-d204-54a9-be6b-5f99672d12fe` |  | dwciri:habitat \| dwciri:substrate |
| Warning | `https://w3id.org/anemone-kg/habitat/c9425cba-ff74-5fc4-b74b-18eda2659a5a` |  | dwciri:habitat \| dwciri:substrate |
| Warning | `https://w3id.org/anemone-kg/occurrence/742cae0d-8b72-5221-ad6c-38d151a31910` | MOHBR I-955 | dwciri:toTaxon |
| Warning | `https://w3id.org/anemone-kg/occurrence/83bb828c-b06c-5bc1-b188-1881567e80ce` | MOHBR I-896 | dwciri:toTaxon |
| Warning | `https://w3id.org/anemone-kg/occurrence/c89af4d4-a855-5c01-aa25-f44df80ceaa0` | MOHBR I-954 | dwciri:toTaxon |
