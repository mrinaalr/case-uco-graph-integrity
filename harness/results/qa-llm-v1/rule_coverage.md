# Candidate source-fidelity rules against qa-llm-v1 (value scorer, final graphs)

Each unsupported triple is tested against the rules proposed in findings/critic-source-fidelity-unassessed.md, using only the graph, the source documents and the task's relation list. A triple can hit several rules; `caught_by_any` counts it once. Date and time literals are not checked by the literal rule here (`time_literals_unchecked`).

| arm | unsupported | caught_by_any | caught_rate | time_literals_unchecked | F-LITERAL-NOT-IN-SOURCE | F-TYPED-VALUE-UNDER-NAME | F-CROSS-DOCUMENT-LINK | F-DUPLICATE-KEY | F-UNANCHORED-ENTITY | F-KIND-OUTSIDE-TASK-VOCAB |
|---|---|---|---|---|---|---|---|---|---|---|
| a1_critic | 885 | 721 | 0.815 | 22 | 99 | 235 | 10 | 29 | 338 | 343 |

## By error class: unsupported triples caught by at least one rule

| arm | cross_document_conflation | duplicate_entity | invented | misplaced_property | wrong_entity | wrong_relation | wrong_value |
|---|---|---|---|---|---|---|---|
| a1_critic | 10/10 | 29/29 | 408/414 | 202/347 | 4/15 | 54/54 | 14/16 |
