# Faithfulness run

SDK `v1.33.0`, endpoint `tinker` (model `Qwen/Qwen3.5-9B`).

| arm | scorer | cases | failures | incomplete | capped | valid | valid_rate | precision_macro | recall_macro | precision_micro | recall_micro | tokens_prompt | tokens_completion | wall_s_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 100 | 50 | 1 | 26 | 35 | 0.35 | 0.339 | 0.1448 | 0.3705 | 0.1385 | 85017583 | 3948749 | 11771.1 |
| a_sdk_agent | value | 100 | 50 | 1 | 26 | 35 | 0.35 | 0.4574 | 0.1931 | 0.5055 | 0.1844 | 85017583 | 3948749 | 11771.1 |
| a_sdk_agent@first_validate | strict | 45 | 0 | 1 | 22 | 19 | 0.4222 | 0.311 | 0.2525 | 0.3369 | 0.2456 | 42074182 | 1344880 | 4489.2 |
| a_sdk_agent@first_validate | value | 45 | 0 | 1 | 22 | 19 | 0.4222 | 0.4177 | 0.3408 | 0.4655 | 0.3319 | 42074182 | 1344880 | 4489.2 |
| a_sdk_agent+hook | strict | 100 | 50 | 1 | 26 | 39 | 0.39 | 0.3451 | 0.1126 | 0.3761 | 0.1079 | 85017583 | 3948749 | 13572.2 |
| a_sdk_agent+hook | value | 100 | 50 | 1 | 26 | 39 | 0.39 | 0.4974 | 0.1602 | 0.5473 | 0.1533 | 85017583 | 3948749 | 13572.2 |
| a_sdk_agent+hook_labels | strict | 100 | 50 | 1 | 26 | 38 | 0.38 | 0.3062 | 0.1071 | 0.3385 | 0.1027 | 85017583 | 3948749 | 13044.9 |
| a_sdk_agent+hook_labels | value | 100 | 50 | 1 | 26 | 38 | 0.38 | 0.4663 | 0.1607 | 0.5204 | 0.1539 | 85017583 | 3948749 | 13044.9 |
| a_sdk_agent+hook_plain | strict | 100 | 50 | 1 | 26 | 40 | 0.4 | 0.3202 | 0.105 | 0.3582 | 0.1004 | 85017583 | 3948749 | 13012.0 |
| a_sdk_agent+hook_plain | value | 100 | 50 | 1 | 26 | 40 | 0.4 | 0.4941 | 0.1569 | 0.5504 | 0.15 | 85017583 | 3948749 | 13012.0 |
| b_control | strict | 100 | 2 | 0 | 0 | 91 | 0.91 | 0.2695 | 0.2202 | 0.2703 | 0.219 | 213300 | 537029 | 1979.3 |
| b_control | value | 100 | 2 | 0 | 0 | 91 | 0.91 | 0.5967 | 0.4788 | 0.595 | 0.476 | 213300 | 537029 | 1979.3 |
| b_control+hook | strict | 100 | 2 | 0 | 0 | 93 | 0.93 | 0.2765 | 0.1931 | 0.2767 | 0.1912 | 213300 | 537029 | 4306.7 |
| b_control+hook | value | 100 | 2 | 0 | 0 | 93 | 0.93 | 0.6329 | 0.4354 | 0.6316 | 0.4323 | 213300 | 537029 | 4306.7 |
| b_control+hook_labels | strict | 100 | 2 | 0 | 0 | 93 | 0.93 | 0.2641 | 0.1816 | 0.2641 | 0.18 | 213300 | 537029 | 4107.3 |
| b_control+hook_labels | value | 100 | 2 | 0 | 0 | 93 | 0.93 | 0.6347 | 0.4305 | 0.634 | 0.4277 | 213300 | 537029 | 4107.3 |
| b_control+hook_plain | strict | 100 | 2 | 0 | 0 | 93 | 0.93 | 0.2685 | 0.1821 | 0.2675 | 0.1805 | 213300 | 537029 | 4035.5 |
| b_control+hook_plain | value | 100 | 2 | 0 | 0 | 93 | 0.93 | 0.6337 | 0.4242 | 0.6305 | 0.4215 | 213300 | 537029 | 4035.5 |

## Unsupported triples by class

| arm | scorer | wrong_value | wrong_relation | wrong_entity | cross_document_conflation | misplaced_property | duplicate_entity | invented | gold_aligned_rate | emitted_aligned_rate |
|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 99 | 69 | 28 | 10 | 0 | 0 | 1551 | 0.1964 | 0.4594 |
| a_sdk_agent | value | 69 | 130 | 30 | 25 | 276 | 137 | 680 | 0.2652 | 0.6578 |
| a_sdk_agent@first_validate | strict | 77 | 68 | 19 | 4 | 0 | 0 | 1422 | 0.3608 | 0.4279 |
| a_sdk_agent@first_validate | value | 56 | 150 | 21 | 22 | 246 | 89 | 670 | 0.5009 | 0.6329 |
| a_sdk_agent+hook | strict | 88 | 45 | 17 | 1 | 0 | 0 | 1186 | 0.1707 | 0.3991 |
| a_sdk_agent+hook | value | 28 | 94 | 19 | 1 | 265 | 101 | 439 | 0.2457 | 0.6 |
| a_sdk_agent+hook_labels | strict | 61 | 48 | 17 | 3 | 0 | 0 | 1370 | 0.1652 | 0.384 |
| a_sdk_agent+hook_labels | value | 29 | 99 | 24 | 10 | 269 | 110 | 518 | 0.2546 | 0.6273 |
| a_sdk_agent+hook_plain | strict | 61 | 49 | 15 | 2 | 0 | 0 | 1217 | 0.163 | 0.38 |
| a_sdk_agent+hook_plain | value | 28 | 90 | 16 | 2 | 270 | 111 | 398 | 0.2563 | 0.6268 |
| b_control | strict | 46 | 54 | 57 | 9 | 0 | 0 | 4248 | 0.3038 | 0.3721 |
| b_control | value | 349 | 103 | 74 | 14 | 1247 | 136 | 492 | 0.7368 | 0.9266 |
| b_control+hook | strict | 25 | 24 | 15 | 1 | 0 | 0 | 3667 | 0.2904 | 0.3558 |
| b_control+hook | value | 116 | 82 | 25 | 6 | 1196 | 97 | 357 | 0.7181 | 0.9035 |
| b_control+hook_labels | strict | 36 | 26 | 11 | 2 | 0 | 0 | 3670 | 0.2746 | 0.3368 |
| b_control+hook_labels | value | 107 | 82 | 21 | 4 | 1217 | 79 | 332 | 0.7293 | 0.9152 |
| b_control+hook_plain | strict | 24 | 29 | 6 | 1 | 0 | 0 | 3632 | 0.2768 | 0.3395 |
| b_control+hook_plain | value | 131 | 82 | 11 | 2 | 1214 | 95 | 309 | 0.727 | 0.9131 |

## Grounding (independent of gold)

Can each emitted assertion be found in the source text? Cells are grounded x gold-supported; grounded_unsupported is the traceable claim modeled wrong. Relations are grounded at sentence or document level. pdf_disagreements counts assertions whose grounding differs between the clean and the PDF-extracted text.

| arm | scorer | grounded_rate_micro | grounded_supported | grounded_unsupported | ungrounded_supported | ungrounded_unsupported | grounded_unsupported_share | rel_sentence_rate | rel_document_rate | rel_indirect_rate | entity_grounded_rate | pdf_disagreements |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 0.785 | 1034 | 1157 | 0 | 600 | 0.6585 | 0.5843 | 0.1481 | 0.0048 | 0.7246 | 0 |
| a_sdk_agent | value | 0.7816 | 1377 | 752 | 0 | 595 | 0.5583 | 0.5832 | 0.1488 | 0.0048 | 0.7246 | 0 |
| a_sdk_agent@first_validate | strict | 0.7627 | 808 | 1021 | 0 | 569 | 0.6421 | 0.564 | 0.1463 | 0.0048 | 0.7075 | 0 |
| a_sdk_agent@first_validate | value | 0.7592 | 1092 | 689 | 0 | 565 | 0.5494 | 0.5645 | 0.1465 | 0.0049 | 0.7075 | 0 |
| a_sdk_agent+hook | strict | 0.8357 | 806 | 985 | 0 | 352 | 0.7367 | 0.6703 | 0.0504 | 0.0022 | 0.6634 | 0 |
| a_sdk_agent+hook | value | 0.8341 | 1145 | 600 | 0 | 347 | 0.6336 | 0.6715 | 0.0509 | 0.0022 | 0.6634 | 0 |
| a_sdk_agent+hook_labels | strict | 0.8129 | 767 | 1075 | 0 | 424 | 0.7171 | 0.6503 | 0.0551 | 0.005 | 0.6922 | 0 |
| a_sdk_agent+hook_labels | value | 0.8102 | 1149 | 640 | 0 | 419 | 0.6043 | 0.6505 | 0.0557 | 0.0051 | 0.6922 | 0 |
| a_sdk_agent+hook_plain | strict | 0.8577 | 750 | 1046 | 0 | 298 | 0.7783 | 0.778 | 0.0012 | 0.0012 | 0.6958 | 0 |
| a_sdk_agent+hook_plain | value | 0.8555 | 1120 | 621 | 0 | 294 | 0.6787 | 0.7787 | 0.0012 | 0.0012 | 0.6958 | 0 |
| b_control | strict | 0.8547 | 1635 | 3535 | 0 | 879 | 0.8009 | 0.7828 | 0.1494 | 0.0108 | 0.9646 | 0 |
| b_control | value | 0.8542 | 3558 | 1544 | 0 | 871 | 0.6393 | 0.7864 | 0.1453 | 0.0109 | 0.9646 | 0 |
| b_control+hook | strict | 0.893 | 1428 | 3180 | 0 | 552 | 0.8521 | 0.8951 | 0.0506 | 0.0032 | 0.9366 | 0 |
| b_control+hook | value | 0.892 | 3232 | 1327 | 0 | 552 | 0.7062 | 0.8949 | 0.0507 | 0.0033 | 0.9366 | 0 |
| b_control+hook_labels | strict | 0.9051 | 1344 | 3262 | 0 | 483 | 0.871 | 0.9172 | 0.0353 | 0.0075 | 0.9486 | 0 |
| b_control+hook_labels | value | 0.9041 | 3196 | 1359 | 0 | 483 | 0.7378 | 0.9175 | 0.0349 | 0.0075 | 0.9486 | 0 |
| b_control+hook_plain | strict | 0.9002 | 1348 | 3189 | 0 | 503 | 0.8638 | 0.9572 | 0.0133 | 0.0029 | 0.9472 | 0 |
| b_control+hook_plain | value | 0.8992 | 3147 | 1341 | 0 | 503 | 0.7272 | 0.9571 | 0.0133 | 0.003 | 0.9472 | 0 |

## Verification hook

Edges the hook read, its verdicts, and what it removed. true: edges gold supports in the graph the hook read; removed_true: of those, removed; removed_false_rate: the share of the other edges removed; cited_correct: kept true edges whose cited passage is the sentence gold states them in.

| arm | scorer | edges | supported | contradicted | not_enough_evidence | removed | true | removed_true | kept_true | cited_correct | removed_true_rate | removed_false_rate | cite_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent+hook | strict | 2793 | 2143 | 264 | 386 | 650 | 1035 | 181 | 854 | 641 | 0.1749 | 0.2668 | 0.7506 |
| a_sdk_agent+hook | value | 2793 | 2143 | 264 | 386 | 650 | 1427 | 215 | 1212 | 956 | 0.1507 | 0.3184 | 0.7888 |
| a_sdk_agent+hook_labels | strict | 2793 | 2267 | 240 | 286 | 526 | 1035 | 158 | 877 | 727 | 0.1527 | 0.2093 | 0.829 |
| a_sdk_agent+hook_labels | value | 2793 | 2267 | 240 | 286 | 526 | 1427 | 217 | 1210 | 1042 | 0.1521 | 0.2262 | 0.8612 |
| a_sdk_agent+hook_plain | strict | 2793 | 2094 | 288 | 411 | 699 | 1035 | 180 | 855 | 667 | 0.1739 | 0.2952 | 0.7801 |
| a_sdk_agent+hook_plain | value | 2793 | 2094 | 288 | 411 | 699 | 1427 | 251 | 1176 | 982 | 0.1759 | 0.328 | 0.835 |
| b_control+hook | strict | 6054 | 5163 | 270 | 621 | 891 | 1638 | 166 | 1472 | 983 | 0.1013 | 0.1642 | 0.6678 |
| b_control+hook | value | 6054 | 5163 | 270 | 621 | 891 | 3629 | 302 | 3327 | 2782 | 0.0832 | 0.2429 | 0.8362 |
| b_control+hook_labels | strict | 6054 | 5092 | 301 | 661 | 962 | 1638 | 204 | 1434 | 1117 | 0.1245 | 0.1716 | 0.7789 |
| b_control+hook_labels | value | 6054 | 5092 | 301 | 661 | 962 | 3629 | 360 | 3269 | 2889 | 0.0992 | 0.2482 | 0.8838 |
| b_control+hook_plain | strict | 6054 | 5043 | 365 | 646 | 1011 | 1638 | 212 | 1426 | 971 | 0.1294 | 0.1809 | 0.6809 |
| b_control+hook_plain | value | 6054 | 5043 | 365 | 646 | 1011 | 3629 | 409 | 3220 | 2747 | 0.1127 | 0.2482 | 0.8531 |

## Unsupported triples by first stage

| arm | scorer | generation |
|---|---|---|
| a_sdk_agent | strict | 1757 |
| a_sdk_agent | value | 1347 |
| a_sdk_agent@first_validate | strict | 1590 |
| a_sdk_agent@first_validate | value | 1254 |
| a_sdk_agent+hook | strict | 1337 |
| a_sdk_agent+hook | value | 947 |
| a_sdk_agent+hook_labels | strict | 1499 |
| a_sdk_agent+hook_labels | value | 1059 |
| a_sdk_agent+hook_plain | strict | 1344 |
| a_sdk_agent+hook_plain | value | 915 |
| b_control | strict | 4414 |
| b_control | value | 2415 |
| b_control+hook | strict | 3732 |
| b_control+hook | value | 1879 |
| b_control+hook_labels | strict | 3745 |
| b_control+hook_labels | value | 1842 |
| b_control+hook_plain | strict | 3692 |
| b_control+hook_plain | value | 1844 |

## Failures (zero recall)

- a_sdk_agent: case_01 case_02 case_08 case_09 case_10 case_100 case_11 case_16 case_17 case_18 case_20 case_22 case_25 case_26 case_31 case_32 case_34 case_37 case_40 case_41 case_44 case_45 case_46 case_47 case_49 case_51 case_54 case_57 case_58 case_59 case_62 case_63 case_65 case_66 case_68 case_73 case_74 case_76 case_78 case_79 case_80 case_81 case_86 case_91 case_92 case_94 case_95 case_96 case_97 case_98
- a_sdk_agent@first_validate: none
- a_sdk_agent+hook: case_01 case_02 case_08 case_09 case_10 case_100 case_11 case_16 case_17 case_18 case_20 case_22 case_25 case_26 case_31 case_32 case_34 case_37 case_40 case_41 case_44 case_45 case_46 case_47 case_49 case_51 case_54 case_57 case_58 case_59 case_62 case_63 case_65 case_66 case_68 case_73 case_74 case_76 case_78 case_79 case_80 case_81 case_86 case_91 case_92 case_94 case_95 case_96 case_97 case_98
- a_sdk_agent+hook_labels: case_01 case_02 case_08 case_09 case_10 case_100 case_11 case_16 case_17 case_18 case_20 case_22 case_25 case_26 case_31 case_32 case_34 case_37 case_40 case_41 case_44 case_45 case_46 case_47 case_49 case_51 case_54 case_57 case_58 case_59 case_62 case_63 case_65 case_66 case_68 case_73 case_74 case_76 case_78 case_79 case_80 case_81 case_86 case_91 case_92 case_94 case_95 case_96 case_97 case_98
- a_sdk_agent+hook_plain: case_01 case_02 case_08 case_09 case_10 case_100 case_11 case_16 case_17 case_18 case_20 case_22 case_25 case_26 case_31 case_32 case_34 case_37 case_40 case_41 case_44 case_45 case_46 case_47 case_49 case_51 case_54 case_57 case_58 case_59 case_62 case_63 case_65 case_66 case_68 case_73 case_74 case_76 case_78 case_79 case_80 case_81 case_86 case_91 case_92 case_94 case_95 case_96 case_97 case_98
- b_control: case_14 case_75
- b_control+hook: case_14 case_75
- b_control+hook_labels: case_14 case_75
- b_control+hook_plain: case_14 case_75
