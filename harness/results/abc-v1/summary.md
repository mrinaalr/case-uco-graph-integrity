# Faithfulness run

SDK `v1.33.0`, endpoint `tinker` (model `Qwen/Qwen3.5-9B`).

| arm | scorer | cases | failures | incomplete | capped | valid | precision_macro | recall_macro | precision_micro | recall_micro | tokens_prompt | tokens_completion | wall_s_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 41 | 19 | 0 | 11 | 14 | 0.3306 | 0.1536 | 0.3533 | 0.1522 | 34003258 | 1584079 | 4759.8 |
| a_sdk_agent | value | 41 | 19 | 0 | 11 | 14 | 0.4406 | 0.2042 | 0.476 | 0.2009 | 34003258 | 1584079 | 4759.8 |
| a_sdk_agent@first_validate | strict | 20 | 0 | 0 | 10 | 8 | 0.3214 | 0.2453 | 0.3137 | 0.2473 | 19412175 | 560135 | 1881.1 |
| a_sdk_agent@first_validate | value | 20 | 0 | 0 | 10 | 8 | 0.4163 | 0.3203 | 0.4175 | 0.3222 | 19412175 | 560135 | 1881.1 |
| b3_defended@raw | strict | 45 | 0 | 0 | 0 | 0 | 0.2789 | 0.2341 | 0.2764 | 0.2344 | 1170936 | 1074422 | 3662.5 |
| b3_defended@raw | value | 45 | 0 | 0 | 0 | 0 | 0.5775 | 0.4783 | 0.5736 | 0.4762 | 1170936 | 1074422 | 3662.5 |
| b3_defended@validated | strict | 45 | 0 | 0 | 0 | 0 | 0.2798 | 0.2346 | 0.2773 | 0.235 | 1170936 | 1074422 | 3662.5 |
| b3_defended@validated | value | 45 | 0 | 0 | 0 | 0 | 0.5792 | 0.4791 | 0.5751 | 0.4771 | 1170936 | 1074422 | 3662.5 |
| b3_defended | strict | 46 | 1 | 0 | 0 | 27 | 0.2237 | 0.2295 | 0.2154 | 0.2292 | 1191771 | 1107190 | 3772.3 |
| b3_defended | value | 46 | 1 | 0 | 0 | 27 | 0.4663 | 0.4687 | 0.4467 | 0.4654 | 1191771 | 1107190 | 3772.3 |
| b_control | strict | 100 | 2 | 0 | 0 | 91 | 0.2695 | 0.2202 | 0.2703 | 0.219 | 213300 | 537029 | 1979.3 |
| b_control | value | 100 | 2 | 0 | 0 | 91 | 0.5967 | 0.4788 | 0.595 | 0.476 | 213300 | 537029 | 1979.3 |
| c_compiled | strict | 100 | 0 | 0 | 0 | 100 | 0.8279 | 0.4684 | 0.823 | 0.4607 | 297826 | 619012 | 2301.7 |
| c_compiled | value | 100 | 0 | 0 | 0 | 100 | 0.8932 | 0.5061 | 0.8911 | 0.4989 | 297826 | 619012 | 2301.7 |
| c_grounded@compiled | strict | 100 | 0 | 0 | 0 | 100 | 0.8057 | 0.5414 | 0.8041 | 0.5377 | 411011 | 677941 | 2784.1 |
| c_grounded@compiled | value | 100 | 0 | 0 | 0 | 100 | 0.9095 | 0.6104 | 0.9077 | 0.6069 | 411011 | 677941 | 2784.1 |
| c_grounded | strict | 100 | 0 | 0 | 0 | 100 | 0.8057 | 0.5414 | 0.8041 | 0.5377 | 411011 | 677941 | 2784.1 |
| c_grounded | value | 100 | 0 | 0 | 0 | 100 | 0.9095 | 0.6104 | 0.9077 | 0.6069 | 411011 | 677941 | 2784.1 |

## Unsupported triples by class

| arm | scorer | wrong_value | wrong_relation | wrong_entity | cross_document_conflation | misplaced_property | duplicate_entity | invented | gold_aligned_rate | emitted_aligned_rate |
|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 53 | 42 | 13 | 4 | 0 | 0 | 739 | 0.2241 | 0.5142 |
| a_sdk_agent | value | 30 | 77 | 14 | 17 | 119 | 43 | 376 | 0.2918 | 0.7048 |
| a_sdk_agent@first_validate | strict | 40 | 34 | 8 | 4 | 0 | 0 | 708 | 0.3824 | 0.4718 |
| a_sdk_agent@first_validate | value | 23 | 71 | 9 | 17 | 104 | 41 | 395 | 0.5076 | 0.6723 |
| b3_defended@raw | strict | 30 | 19 | 27 | 3 | 0 | 0 | 1994 | 0.3174 | 0.3755 |
| b3_defended@raw | value | 156 | 56 | 30 | 9 | 571 | 119 | 255 | 0.7551 | 0.9275 |
| b3_defended@validated | strict | 30 | 19 | 27 | 3 | 0 | 0 | 1990 | 0.3181 | 0.376 |
| b3_defended@validated | value | 156 | 51 | 30 | 9 | 571 | 119 | 255 | 0.7558 | 0.9275 |
| b3_defended | strict | 30 | 19 | 28 | 3 | 0 | 0 | 2812 | 0.3111 | 0.3581 |
| b3_defended | value | 156 | 51 | 31 | 9 | 571 | 130 | 1049 | 0.7394 | 0.8814 |
| b_control | strict | 46 | 54 | 57 | 9 | 0 | 0 | 4248 | 0.3038 | 0.3721 |
| b_control | value | 348 | 103 | 74 | 14 | 1247 | 137 | 492 | 0.7368 | 0.9266 |
| c_compiled | strict | 29 | 72 | 98 | 17 | 0 | 0 | 524 | 0.5599 | 0.8536 |
| c_compiled | value | 32 | 72 | 101 | 17 | 1 | 0 | 232 | 0.6084 | 0.9224 |
| c_grounded@compiled | strict | 112 | 75 | 45 | 1 | 0 | 0 | 745 | 0.6587 | 0.8316 |
| c_grounded@compiled | value | 112 | 86 | 54 | 2 | 0 | 0 | 207 | 0.7492 | 0.9412 |
| c_grounded | strict | 112 | 75 | 45 | 1 | 0 | 0 | 745 | 0.6587 | 0.8316 |
| c_grounded | value | 112 | 86 | 54 | 2 | 0 | 0 | 207 | 0.7492 | 0.9412 |

## Unsupported triples by first stage

| arm | scorer | generation |
|---|---|---|
| a_sdk_agent | strict | 851 |
| a_sdk_agent | value | 676 |
| a_sdk_agent@first_validate | strict | 794 |
| a_sdk_agent@first_validate | value | 660 |
| b3_defended@raw | strict | 2073 |
| b3_defended@raw | value | 1196 |
| b3_defended@validated | strict | 2069 |
| b3_defended@validated | value | 1191 |
| b3_defended | strict | 2892 |
| b3_defended | value | 1997 |
| b_control | strict | 4414 |
| b_control | value | 2415 |
| c_compiled | strict | 740 |
| c_compiled | value | 455 |
| c_grounded@compiled | strict | 978 |
| c_grounded@compiled | value | 461 |
| c_grounded | strict | 978 |
| c_grounded | value | 461 |

## Failures (zero recall)

- a_sdk_agent: case_01 case_02 case_08 case_09 case_10 case_100 case_11 case_16 case_17 case_18 case_20 case_22 case_25 case_26 case_31 case_32 case_34 case_37 case_40
- a_sdk_agent@first_validate: none
- b3_defended@raw: none
- b3_defended@validated: none
- b3_defended: case_14
- b_control: case_14 case_75
- c_compiled: none
- c_grounded@compiled: none
- c_grounded: none
