# Candidate source-fidelity rules against qa-det-v1 (value scorer, final graphs)

Each unsupported triple is tested against the rules proposed in findings/critic-source-fidelity-unassessed.md, using only the graph, the source documents and the task's relation list. A triple can hit several rules; `caught_by_any` counts it once. Date and time literals are not checked by the literal rule here (`time_literals_unchecked`).

| arm | unsupported | caught_by_any | caught_rate | time_literals_unchecked | F-LITERAL-NOT-IN-SOURCE | F-TYPED-VALUE-UNDER-NAME | F-CROSS-DOCUMENT-LINK | F-DUPLICATE-KEY | F-UNANCHORED-ENTITY | F-KIND-OUTSIDE-TASK-VOCAB |
|---|---|---|---|---|---|---|---|---|---|---|
| a1_critic | 618 | 508 | 0.822 | 24 | 118 | 158 | 2 | 20 | 247 | 201 |

## By error class: unsupported triples caught by at least one rule

| arm | cross_document_conflation | duplicate_entity | invented | misplaced_property | wrong_entity | wrong_relation | wrong_value |
|---|---|---|---|---|---|---|---|
| a1_critic | 2/2 | 20/20 | 286/296 | 157/243 | 0/10 | 12/12 | 31/35 |
