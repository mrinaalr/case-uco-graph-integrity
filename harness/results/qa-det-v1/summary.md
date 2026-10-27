# Faithfulness run

SDK `v1.33.0`, endpoint `tinker` (model `Qwen/Qwen3.5-9B`).

| arm | scorer | cases | failures | incomplete | capped | valid | precision_macro | recall_macro | precision_micro | recall_micro | tokens_prompt | tokens_completion | wall_s_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a1_critic@pass1 | strict | 18 | 0 | 0 | 0 | 7 | 0.2836 | 0.2458 | 0.2889 | 0.2438 | 329851 | 260311 | 909.3 |
| a1_critic@pass1 | value | 18 | 0 | 0 | 0 | 7 | 0.6035 | 0.5063 | 0.6086 | 0.5056 | 329851 | 260311 | 909.3 |
| a1_critic@pass2 | strict | 12 | 0 | 0 | 0 | 5 | 0.2458 | 0.2507 | 0.2427 | 0.2494 | 243380 | 184659 | 672.5 |
| a1_critic@pass2 | value | 12 | 0 | 0 | 0 | 5 | 0.4962 | 0.5015 | 0.4919 | 0.5022 | 243380 | 184659 | 672.5 |
| a1_critic | strict | 30 | 12 | 0 | 0 | 8 | 0.2455 | 0.1464 | 0.2468 | 0.1441 | 426450 | 348149 | 1229.2 |
| a1_critic | value | 30 | 12 | 0 | 0 | 8 | 0.5313 | 0.3027 | 0.522 | 0.3003 | 426450 | 348149 | 1229.2 |
| a1_critic@pass3 | strict | 10 | 0 | 0 | 0 | 4 | 0.2467 | 0.2711 | 0.2482 | 0.2676 | 196014 | 143209 | 514.2 |
| a1_critic@pass3 | value | 10 | 0 | 0 | 0 | 4 | 0.4939 | 0.5318 | 0.4921 | 0.5287 | 196014 | 143209 | 514.2 |

## Unsupported triples by class

| arm | scorer | wrong_value | wrong_relation | wrong_entity | cross_document_conflation | misplaced_property | duplicate_entity | invented | gold_aligned_rate | emitted_aligned_rate |
|---|---|---|---|---|---|---|---|---|---|---|
| a1_critic@pass1 | strict | 21 | 2 | 6 | 0 | 0 | 0 | 776 | 0.3301 | 0.3671 |
| a1_critic@pass1 | value | 35 | 11 | 10 | 2 | 242 | 19 | 117 | 0.8224 | 0.9306 |
| a1_critic@pass2 | strict | 15 | 2 | 6 | 0 | 0 | 0 | 679 | 0.3436 | 0.3699 |
| a1_critic@pass2 | value | 22 | 8 | 10 | 2 | 161 | 9 | 256 | 0.8328 | 0.8882 |
| a1_critic | strict | 21 | 2 | 6 | 0 | 0 | 0 | 960 | 0.1997 | 0.3591 |
| a1_critic | value | 35 | 12 | 10 | 2 | 243 | 20 | 296 | 0.4962 | 0.9088 |
| a1_critic@pass3 | strict | 15 | 2 | 6 | 0 | 0 | 0 | 598 | 0.3596 | 0.3784 |
| a1_critic@pass3 | value | 18 | 9 | 10 | 2 | 140 | 3 | 236 | 0.8753 | 0.9058 |

## Unsupported triples by first stage

| arm | scorer | generation |
|---|---|---|
| a1_critic@pass1 | strict | 805 |
| a1_critic@pass1 | value | 436 |
| a1_critic@pass2 | strict | 702 |
| a1_critic@pass2 | value | 468 |
| a1_critic | strict | 989 |
| a1_critic | value | 618 |
| a1_critic@pass3 | strict | 621 |
| a1_critic@pass3 | value | 418 |

## Failures (zero recall)

- a1_critic@pass1: none
- a1_critic@pass2: none
- a1_critic: case_02 case_03 case_04 case_05 case_06 case_07 case_08 case_10 case_21 case_26 case_29 case_30
- a1_critic@pass3: none
