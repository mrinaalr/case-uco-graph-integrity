# Faithfulness run

SDK `v1.33.0`, endpoint `tinker` (model `Qwen/Qwen3.5-9B`).

| arm | scorer | cases | failures | incomplete | capped | valid | precision_macro | recall_macro | precision_micro | recall_micro | tokens_prompt | tokens_completion | wall_s_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 100 | 50 | 1 | 26 | 35 | 0.339 | 0.1448 | 0.3705 | 0.1385 | 85017583 | 3948749 | 11771.1 |
| a_sdk_agent | value | 100 | 50 | 1 | 26 | 35 | 0.4574 | 0.1931 | 0.5055 | 0.1844 | 85017583 | 3948749 | 11771.1 |
| a_sdk_agent@first_validate | strict | 45 | 0 | 1 | 22 | 19 | 0.311 | 0.2525 | 0.3369 | 0.2456 | 42074182 | 1344880 | 4489.2 |
| a_sdk_agent@first_validate | value | 45 | 0 | 1 | 22 | 19 | 0.4177 | 0.3408 | 0.4655 | 0.3319 | 42074182 | 1344880 | 4489.2 |
| b3_defended@raw | strict | 98 | 0 | 0 | 0 | 0 | 0.2619 | 0.2177 | 0.2605 | 0.217 | 2522980 | 2296533 | 7656.5 |
| b3_defended@raw | value | 98 | 0 | 0 | 0 | 0 | 0.586 | 0.4785 | 0.5829 | 0.4765 | 2522980 | 2296533 | 7656.5 |
| b3_defended@validated | strict | 98 | 0 | 0 | 0 | 0 | 0.2626 | 0.218 | 0.2613 | 0.2173 | 2522980 | 2296533 | 7656.5 |
| b3_defended@validated | value | 98 | 0 | 0 | 0 | 0 | 0.5876 | 0.4788 | 0.5845 | 0.4769 | 2522980 | 2296533 | 7656.5 |
| b3_defended | strict | 100 | 2 | 0 | 0 | 54 | 0.2159 | 0.2136 | 0.2091 | 0.2124 | 2564712 | 2362069 | 7832.8 |
| b3_defended | value | 100 | 2 | 0 | 0 | 54 | 0.4849 | 0.4692 | 0.4681 | 0.4662 | 2564712 | 2362069 | 7832.8 |
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
| a_sdk_agent | strict | 99 | 69 | 28 | 10 | 0 | 0 | 1551 | 0.1964 | 0.4594 |
| a_sdk_agent | value | 69 | 130 | 30 | 25 | 276 | 138 | 679 | 0.2652 | 0.6578 |
| a_sdk_agent@first_validate | strict | 77 | 68 | 19 | 4 | 0 | 0 | 1422 | 0.3608 | 0.4279 |
| a_sdk_agent@first_validate | value | 56 | 150 | 21 | 22 | 247 | 88 | 670 | 0.5009 | 0.6329 |
| b3_defended@raw | strict | 39 | 48 | 49 | 7 | 0 | 0 | 4353 | 0.3002 | 0.3589 |
| b3_defended@raw | value | 351 | 96 | 60 | 17 | 1264 | 208 | 489 | 0.7516 | 0.9311 |
| b3_defended@validated | strict | 39 | 48 | 49 | 7 | 0 | 0 | 4340 | 0.3005 | 0.3592 |
| b3_defended@validated | value | 351 | 84 | 60 | 17 | 1264 | 207 | 488 | 0.7519 | 0.9311 |
| b3_defended | strict | 39 | 48 | 50 | 7 | 0 | 0 | 5856 | 0.2945 | 0.3433 |
| b3_defended | value | 348 | 84 | 61 | 17 | 1264 | 243 | 1935 | 0.7368 | 0.8895 |
| b_control | strict | 46 | 54 | 57 | 9 | 0 | 0 | 4248 | 0.3038 | 0.3721 |
| b_control | value | 348 | 103 | 74 | 14 | 1247 | 137 | 492 | 0.7368 | 0.9266 |
| c_compiled | strict | 29 | 72 | 98 | 17 | 0 | 0 | 524 | 0.5599 | 0.8536 |
| c_compiled | value | 32 | 72 | 101 | 17 | 1 | 0 | 232 | 0.6084 | 0.9224 |
| c_grounded@compiled | strict | 112 | 75 | 45 | 1 | 0 | 0 | 745 | 0.6587 | 0.8316 |
| c_grounded@compiled | value | 112 | 86 | 54 | 2 | 0 | 0 | 207 | 0.7492 | 0.9412 |
| c_grounded | strict | 112 | 75 | 45 | 1 | 0 | 0 | 745 | 0.6587 | 0.8316 |
| c_grounded | value | 112 | 86 | 54 | 2 | 0 | 0 | 207 | 0.7492 | 0.9412 |

## Grounding (independent of gold)

Can each emitted assertion be found in the source text? Cells are grounded x gold-supported; grounded_unsupported is the traceable claim modeled wrong. Relations are grounded at sentence or document level. pdf_disagreements counts assertions whose grounding differs between the clean and the PDF-extracted text. ledger_* compares c_grounded's own quote checks with the scorer.

| arm | scorer | grounded_rate_micro | grounded_supported | grounded_unsupported | ungrounded_supported | ungrounded_unsupported | grounded_unsupported_share | rel_sentence_rate | rel_document_rate | rel_indirect_rate | entity_grounded_rate | pdf_disagreements | ledger_asserted | ledger_scorer_ungrounded | ledger_not_in_graph |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 0.785 | 1034 | 1157 | 0 | 600 | 0.6585 | 0.5843 | 0.1481 | 0.0048 | 0.7246 | 0 | None | None | None |
| a_sdk_agent | value | 0.7816 | 1377 | 752 | 0 | 595 | 0.5583 | 0.5832 | 0.1488 | 0.0048 | 0.7246 | 0 | None | None | None |
| a_sdk_agent@first_validate | strict | 0.7627 | 808 | 1021 | 0 | 569 | 0.6421 | 0.564 | 0.1463 | 0.0048 | 0.7075 | 0 | None | None | None |
| a_sdk_agent@first_validate | value | 0.7592 | 1092 | 689 | 0 | 565 | 0.5494 | 0.5645 | 0.1465 | 0.0049 | 0.7075 | 0 | None | None | None |
| b3_defended@raw | strict | 0.8508 | 1584 | 3589 | 0 | 907 | 0.7983 | 0.7893 | 0.1396 | 0.0107 | 0.9681 | 0 | None | None | None |
| b3_defended@raw | value | 0.8495 | 3482 | 1587 | 0 | 898 | 0.6386 | 0.792 | 0.1362 | 0.0108 | 0.9681 | 0 | None | None | None |
| b3_defended@validated | strict | 0.8507 | 1586 | 3577 | 0 | 906 | 0.7979 | 0.7887 | 0.1402 | 0.0108 | 0.9681 | 0 | None | None | None |
| b3_defended@validated | value | 0.8494 | 3485 | 1574 | 0 | 897 | 0.637 | 0.7914 | 0.1369 | 0.0109 | 0.9681 | 0 | None | None | None |
| b3_defended | strict | 0.7407 | 1586 | 4033 | 0 | 1967 | 0.6722 | 0.541 | 0.1995 | 0.0097 | 0.9354 | 0 | None | None | None |
| b3_defended | value | 0.7404 | 3485 | 2021 | 0 | 1931 | 0.5114 | 0.5463 | 0.1973 | 0.0098 | 0.9354 | 0 | None | None | None |
| b_control | strict | 0.8547 | 1635 | 3535 | 0 | 879 | 0.8009 | 0.7828 | 0.1494 | 0.0108 | 0.9646 | 0 | None | None | None |
| b_control | value | 0.8542 | 3558 | 1544 | 0 | 871 | 0.6393 | 0.7864 | 0.1453 | 0.0109 | 0.9646 | 0 | None | None | None |
| c_compiled | strict | 0.9902 | 3440 | 699 | 0 | 41 | 0.9446 | 0.9001 | 0.0779 | 0.0 | 0.9852 | 0 | None | None | None |
| c_compiled | value | 0.9902 | 3725 | 414 | 0 | 41 | 0.9099 | 0.9001 | 0.0779 | 0.0 | 0.9852 | 0 | None | None | None |
| c_grounded@compiled | strict | 0.9914 | 4015 | 935 | 0 | 43 | 0.956 | 0.9155 | 0.0773 | 0.0 | 0.9948 | 0 | 5201 | 47 | 31 |
| c_grounded@compiled | value | 0.9914 | 4532 | 418 | 0 | 43 | 0.9067 | 0.9155 | 0.0773 | 0.0 | 0.9948 | 0 | 5201 | 47 | 31 |
| c_grounded | strict | 0.9914 | 4015 | 935 | 0 | 43 | 0.956 | 0.9155 | 0.0773 | 0.0 | 0.9948 | 0 | 5201 | 47 | 31 |
| c_grounded | value | 0.9914 | 4532 | 418 | 0 | 43 | 0.9067 | 0.9155 | 0.0773 | 0.0 | 0.9948 | 0 | 5201 | 47 | 31 |

## Unsupported triples by first stage

| arm | scorer | generation |
|---|---|---|
| a_sdk_agent | strict | 1757 |
| a_sdk_agent | value | 1347 |
| a_sdk_agent@first_validate | strict | 1590 |
| a_sdk_agent@first_validate | value | 1254 |
| b3_defended@raw | strict | 4496 |
| b3_defended@raw | value | 2485 |
| b3_defended@validated | strict | 4483 |
| b3_defended@validated | value | 2471 |
| b3_defended | strict | 6000 |
| b3_defended | value | 3952 |
| b_control | strict | 4414 |
| b_control | value | 2415 |
| c_compiled | strict | 740 |
| c_compiled | value | 455 |
| c_grounded@compiled | strict | 978 |
| c_grounded@compiled | value | 461 |
| c_grounded | strict | 978 |
| c_grounded | value | 461 |

## Failures (zero recall)

- a_sdk_agent: case_01 case_02 case_08 case_09 case_10 case_100 case_11 case_16 case_17 case_18 case_20 case_22 case_25 case_26 case_31 case_32 case_34 case_37 case_40 case_41 case_44 case_45 case_46 case_47 case_49 case_51 case_54 case_57 case_58 case_59 case_62 case_63 case_65 case_66 case_68 case_73 case_74 case_76 case_78 case_79 case_80 case_81 case_86 case_91 case_92 case_94 case_95 case_96 case_97 case_98
- a_sdk_agent@first_validate: none
- b3_defended@raw: none
- b3_defended@validated: none
- b3_defended: case_14 case_75
- b_control: case_14 case_75
- c_compiled: none
- c_grounded@compiled: none
- c_grounded: none
