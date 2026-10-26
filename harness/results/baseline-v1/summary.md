# Faithfulness run

SDK `v1.33.0`, endpoint `tinker` (model `Qwen/Qwen3.5-9B`).

| arm | scorer | cases | failures | incomplete | capped | valid | precision_macro | recall_macro | precision_micro | recall_micro | tokens_prompt | tokens_completion | wall_s_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a1_script | strict | 30 | 13 | 0 | 0 | 9 | 0.2833 | 0.1315 | 0.2857 | 0.1308 | 74627 | 108542 | 314.3 |
| a1_script | value | 30 | 13 | 0 | 0 | 9 | 0.6065 | 0.275 | 0.6067 | 0.2758 | 74627 | 108542 | 314.3 |
| a2_tools@first_validate | strict | 30 | 0 | 8 | 0 | 18 | 0.3611 | 0.3253 | 0.3707 | 0.3207 | 8509906 | 351364 | 1446.2 |
| a2_tools@first_validate | value | 30 | 0 | 8 | 0 | 18 | 0.642 | 0.553 | 0.6392 | 0.5494 | 8509906 | 351364 | 1446.2 |
| a2_tools | strict | 30 | 0 | 8 | 0 | 22 | 0.3953 | 0.383 | 0.4041 | 0.3768 | 8509906 | 351364 | 1446.2 |
| a2_tools | value | 30 | 0 | 8 | 0 | 22 | 0.65 | 0.6018 | 0.6475 | 0.5974 | 8509906 | 351364 | 1446.2 |
| b_control | strict | 30 | 1 | 0 | 0 | 28 | 0.2404 | 0.177 | 0.2364 | 0.1757 | 69707 | 166650 | 442.2 |
| b_control | value | 30 | 1 | 0 | 0 | 28 | 0.5601 | 0.4123 | 0.5522 | 0.4097 | 69707 | 166650 | 442.2 |

## Unsupported triples by class

| arm | scorer | wrong_value | wrong_relation | wrong_entity | cross_document_conflation | misplaced_property | duplicate_entity | invented | gold_aligned_rate | emitted_aligned_rate |
|---|---|---|---|---|---|---|---|---|---|---|
| a1_script | strict | 4 | 3 | 10 | 0 | 0 | 0 | 718 | 0.1771 | 0.3484 |
| a1_script | value | 28 | 15 | 12 | 6 | 233 | 10 | 98 | 0.474 | 0.9411 |
| a2_tools@first_validate | strict | 25 | 13 | 16 | 3 | 0 | 0 | 1167 | 0.4493 | 0.501 |
| a2_tools@first_validate | value | 69 | 19 | 20 | 15 | 435 | 9 | 130 | 0.8452 | 0.9639 |
| a2_tools | strict | 36 | 26 | 20 | 5 | 0 | 0 | 1162 | 0.5013 | 0.5572 |
| a2_tools | value | 86 | 26 | 23 | 15 | 435 | 9 | 137 | 0.8524 | 0.9662 |
| b_control | strict | 0 | 6 | 7 | 5 | 0 | 0 | 1258 | 0.2594 | 0.3166 |
| b_control | value | 65 | 50 | 9 | 8 | 363 | 10 | 242 | 0.7377 | 0.9033 |

## Unsupported triples by first stage

| arm | scorer | final_only | generation | repair | write_facet | write_node | write_relationship |
|---|---|---|---|---|---|---|---|
| a1_script | strict | 0 | 735 | 0 | 0 | 0 | 0 |
| a1_script | value | 0 | 402 | 0 | 0 | 0 | 0 |
| a2_tools@first_validate | strict | 132 | 0 | 0 | 135 | 709 | 248 |
| a2_tools@first_validate | value | 29 | 0 | 0 | 85 | 561 | 22 |
| a2_tools | strict | 111 | 0 | 71 | 115 | 709 | 243 |
| a2_tools | value | 26 | 0 | 45 | 77 | 561 | 22 |
| b_control | strict | 0 | 1276 | 0 | 0 | 0 | 0 |
| b_control | value | 0 | 747 | 0 | 0 | 0 | 0 |

## Failures (zero recall)

- a1_script: case_03 case_04 case_07 case_08 case_10 case_11 case_12 case_16 case_26 case_27 case_28 case_29 case_30
- a2_tools@first_validate: none
- a2_tools: none
- b_control: case_13
