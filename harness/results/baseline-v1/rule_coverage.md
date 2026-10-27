# Candidate source-fidelity rules against baseline-v1 (value scorer, final graphs)

Each unsupported triple is tested against the rules proposed in findings/critic-source-fidelity-unassessed.md, using only the graph, the source documents and the task's relation list. A triple can hit several rules; `caught_by_any` counts it once. Date and time literals are not checked by the literal rule here (`time_literals_unchecked`).

| arm | unsupported | caught_by_any | caught_rate | time_literals_unchecked | F-LITERAL-NOT-IN-SOURCE | F-TYPED-VALUE-UNDER-NAME | F-CROSS-DOCUMENT-LINK | F-DUPLICATE-KEY | F-UNANCHORED-ENTITY | F-KIND-OUTSIDE-TASK-VOCAB |
|---|---|---|---|---|---|---|---|---|---|---|
| a1_script | 402 | 278 | 0.692 | 11 | 64 | 152 | 6 | 10 | 49 | 37 |
| a2_tools | 731 | 470 | 0.643 | 2 | 97 | 262 | 15 | 9 | 61 | 65 |
| b_control | 747 | 607 | 0.813 | 9 | 117 | 219 | 8 | 10 | 211 | 147 |

## By error class: unsupported triples caught by at least one rule

| arm | cross_document_conflation | duplicate_entity | invented | misplaced_property | wrong_entity | wrong_relation | wrong_value |
|---|---|---|---|---|---|---|---|
| a1_script | 6/6 | 10/10 | 91/98 | 132/233 | 2/12 | 15/15 | 22/28 |
| a2_tools | 15/15 | 9/9 | 128/137 | 239/435 | 13/23 | 20/26 | 46/86 |
| b_control | 8/8 | 10/10 | 241/242 | 239/363 | 9/9 | 50/50 | 50/65 |
