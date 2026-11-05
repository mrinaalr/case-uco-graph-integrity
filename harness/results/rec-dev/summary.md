# Faithfulness run

SDK `v1.33.0`, endpoint `tinker` (model `Qwen/Qwen3.5-9B`).

| arm | scorer | cases | failures | incomplete | capped | valid | valid_rate | precision_macro | recall_macro | precision_micro | recall_micro | tokens_prompt | tokens_completion | wall_s_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.3756 | 0.1109 | 0.3895 | 0.1052 | 7411893 | 423580 | 1320.9 |
| a_sdk_agent | value | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.5159 | 0.1461 | 0.5181 | 0.1379 | 7411893 | 423580 | 1320.9 |
| a_sdk_agent+rec | strict | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.4712 | 0.1275 | 0.4668 | 0.1219 | 7411893 | 423580 | 1440.6 |
| a_sdk_agent+rec | value | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.5607 | 0.151 | 0.5572 | 0.1437 | 7411893 | 423580 | 1440.6 |
| a_sdk_agent+rec-noadd | strict | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.3816 | 0.0996 | 0.3905 | 0.0949 | 7411893 | 423580 | 1398.9 |
| a_sdk_agent+rec-noadd | value | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.5265 | 0.1322 | 0.5241 | 0.1257 | 7411893 | 423580 | 1398.9 |
| a_sdk_agent+rec-strict | strict | 20 | 14 | 0 | 3 | 5 | 0.25 | 0.5134 | 0.1217 | 0.5112 | 0.1167 | 7411893 | 423580 | 1440.6 |
| a_sdk_agent+rec-strict | value | 20 | 14 | 0 | 3 | 5 | 0.25 | 0.605 | 0.1432 | 0.6051 | 0.1366 | 7411893 | 423580 | 1440.6 |
| b_control | strict | 20 | 1 | 0 | 0 | 17 | 0.85 | 0.287 | 0.2224 | 0.2912 | 0.2219 | 42981 | 116542 | 300.5 |
| b_control | value | 20 | 1 | 0 | 0 | 17 | 0.85 | 0.622 | 0.4696 | 0.6213 | 0.4682 | 42981 | 116542 | 300.5 |
| b_control+rec | strict | 20 | 1 | 0 | 0 | 15 | 0.75 | 0.369 | 0.283 | 0.3613 | 0.2816 | 42981 | 116542 | 672.3 |
| b_control+rec | value | 20 | 1 | 0 | 0 | 15 | 0.75 | 0.6332 | 0.4884 | 0.633 | 0.4869 | 42981 | 116542 | 672.3 |
| b_control+rec-noadd | strict | 20 | 1 | 0 | 0 | 17 | 0.85 | 0.3075 | 0.2224 | 0.3126 | 0.2219 | 42981 | 116542 | 532.3 |
| b_control+rec-noadd | value | 20 | 1 | 0 | 0 | 17 | 0.85 | 0.6067 | 0.4275 | 0.6069 | 0.4259 | 42981 | 116542 | 532.3 |
| b_control+rec-strict | strict | 20 | 1 | 0 | 0 | 16 | 0.8 | 0.3781 | 0.2678 | 0.3692 | 0.2662 | 42981 | 116542 | 672.3 |
| b_control+rec-strict | value | 20 | 1 | 0 | 0 | 16 | 0.8 | 0.6539 | 0.4667 | 0.6532 | 0.465 | 42981 | 116542 | 672.3 |
| c_edc | strict | 5 | 0 | 0 | 0 | 1 | 0.2 | 0.4551 | 0.1643 | 0.446 | 0.1623 | 347922 | 9489 | 243.4 |
| c_edc | value | 5 | 0 | 0 | 0 | 1 | 0.2 | 0.5492 | 0.1926 | 0.5448 | 0.1911 | 347922 | 9489 | 243.4 |
| c_edc+rec | strict | 5 | 0 | 0 | 0 | 0 | 0.0 | 0.6117 | 0.3388 | 0.5972 | 0.3377 | 347922 | 9489 | 304.8 |
| c_edc+rec | value | 5 | 0 | 0 | 0 | 0 | 0.0 | 0.6632 | 0.3697 | 0.6528 | 0.3691 | 347922 | 9489 | 304.8 |
| c_edc+rec-noadd | strict | 5 | 0 | 0 | 0 | 4 | 0.8 | 0.4344 | 0.1435 | 0.4252 | 0.1414 | 347922 | 9489 | 263.1 |
| c_edc+rec-noadd | value | 5 | 0 | 0 | 0 | 4 | 0.8 | 0.5591 | 0.177 | 0.5492 | 0.1754 | 347922 | 9489 | 263.1 |
| c_edc+rec-strict | strict | 5 | 0 | 0 | 0 | 0 | 0.0 | 0.6685 | 0.3284 | 0.651 | 0.3272 | 347922 | 9489 | 304.8 |
| c_edc+rec-strict | value | 5 | 0 | 0 | 0 | 0 | 0.0 | 0.7226 | 0.3568 | 0.7083 | 0.356 | 347922 | 9489 | 304.8 |
| corrupt | strict | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.5993 | 0.6771 | 0.5989 | 0.6761 | 0 | 0 | 0 |
| corrupt | value | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.6004 | 0.6784 | 0.6 | 0.6774 | 0 | 0 | 0 |
| corrupt+rec | strict | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.6785 | 0.7675 | 0.6778 | 0.7665 | 0 | 0 | 535.9 |
| corrupt+rec | value | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.683 | 0.7727 | 0.6824 | 0.7716 | 0 | 0 | 535.9 |
| corrupt+rec-noadd | strict | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.6524 | 0.665 | 0.6518 | 0.6639 | 0 | 0 | 367.9 |
| corrupt+rec-noadd | value | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.6537 | 0.6663 | 0.653 | 0.6652 | 0 | 0 | 367.9 |
| corrupt+rec-strict | strict | 20 | 0 | 0 | 0 | 8 | 0.4 | 0.8479 | 0.7604 | 0.8469 | 0.7595 | 0 | 0 | 535.9 |
| corrupt+rec-strict | value | 20 | 0 | 0 | 0 | 8 | 0.4 | 0.8529 | 0.7644 | 0.8518 | 0.7633 | 0 | 0 | 535.9 |
| dropped | strict | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.9902 | 0.8372 | 0.9901 | 0.8371 | 0 | 0 | 0 |
| dropped | value | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.9902 | 0.8372 | 0.9901 | 0.8371 | 0 | 0 | 0 |
| dropped+rec | strict | 20 | 0 | 0 | 0 | 12 | 0.6 | 0.9763 | 0.911 | 0.9759 | 0.9108 | 0 | 0 | 419.6 |
| dropped+rec | value | 20 | 0 | 0 | 0 | 12 | 0.6 | 0.9804 | 0.9149 | 0.9801 | 0.9147 | 0 | 0 | 419.6 |
| dropped+rec-noadd | strict | 20 | 0 | 0 | 0 | 20 | 1.0 | 0.9854 | 0.8251 | 0.9854 | 0.8249 | 0 | 0 | 256.5 |
| dropped+rec-noadd | value | 20 | 0 | 0 | 0 | 20 | 1.0 | 0.9854 | 0.8251 | 0.9854 | 0.8249 | 0 | 0 | 256.5 |
| dropped+rec-strict | strict | 20 | 0 | 0 | 0 | 13 | 0.65 | 0.9857 | 0.8735 | 0.9855 | 0.873 | 0 | 0 | 419.6 |
| dropped+rec-strict | value | 20 | 0 | 0 | 0 | 13 | 0.65 | 0.9885 | 0.8761 | 0.9884 | 0.8756 | 0 | 0 | 419.6 |
| gold | strict | 20 | 0 | 0 | 0 | 0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 0 | 0 |
| gold | value | 20 | 0 | 0 | 0 | 0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 0 | 0 |
| gold+rec | strict | 20 | 0 | 0 | 0 | 13 | 0.65 | 0.9893 | 0.9873 | 0.9891 | 0.9872 | 0 | 0 | 405.1 |
| gold+rec | value | 20 | 0 | 0 | 0 | 13 | 0.65 | 0.9932 | 0.9912 | 0.9929 | 0.991 | 0 | 0 | 405.1 |
| gold+rec-noadd | strict | 20 | 0 | 0 | 0 | 20 | 1.0 | 0.996 | 0.9873 | 0.9961 | 0.9872 | 0 | 0 | 331.1 |
| gold+rec-noadd | value | 20 | 0 | 0 | 0 | 20 | 1.0 | 0.996 | 0.9873 | 0.9961 | 0.9872 | 0 | 0 | 331.1 |
| gold+rec-strict | strict | 20 | 0 | 0 | 0 | 13 | 0.65 | 0.99 | 0.9314 | 0.9898 | 0.9307 | 0 | 0 | 405.1 |
| gold+rec-strict | value | 20 | 0 | 0 | 0 | 13 | 0.65 | 0.9927 | 0.934 | 0.9925 | 0.9333 | 0 | 0 | 405.1 |

## Unsupported triples by class

| arm | scorer | wrong_value | wrong_relation | wrong_entity | cross_document_conflation | misplaced_property | duplicate_entity | invented | gold_aligned_rate | emitted_aligned_rate |
|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 9 | 23 | 33 | 5 | 0 | 0 | 187 | 0.1582 | 0.6769 |
| a_sdk_agent | value | 6 | 22 | 33 | 8 | 50 | 12 | 69 | 0.2179 | 0.9322 |
| a_sdk_agent+rec | strict | 9 | 19 | 28 | 5 | 0 | 0 | 156 | 0.1808 | 0.7346 |
| a_sdk_agent+rec | value | 6 | 18 | 28 | 5 | 44 | 13 | 64 | 0.2219 | 0.9188 |
| a_sdk_agent+rec-noadd | strict | 9 | 19 | 28 | 5 | 0 | 0 | 170 | 0.1561 | 0.6697 |
| a_sdk_agent+rec-noadd | value | 6 | 18 | 28 | 5 | 44 | 13 | 64 | 0.2102 | 0.9065 |
| a_sdk_agent+rec-strict | strict | 9 | 11 | 28 | 5 | 0 | 0 | 121 | 0.1683 | 0.6839 |
| a_sdk_agent+rec-strict | value | 6 | 11 | 28 | 5 | 43 | 12 | 34 | 0.2094 | 0.8681 |
| b_control | strict | 6 | 6 | 4 | 2 | 0 | 0 | 824 | 0.2991 | 0.3734 |
| b_control | value | 69 | 7 | 5 | 2 | 248 | 21 | 89 | 0.7212 | 0.9301 |
| b_control+rec | strict | 10 | 6 | 4 | 2 | 0 | 0 | 754 | 0.3545 | 0.4416 |
| b_control+rec | value | 73 | 4 | 6 | 2 | 201 | 23 | 125 | 0.6525 | 0.8343 |
| b_control+rec-noadd | strict | 6 | 4 | 4 | 2 | 0 | 0 | 745 | 0.2991 | 0.3734 |
| b_control+rec-noadd | value | 69 | 3 | 5 | 2 | 201 | 21 | 125 | 0.6433 | 0.8319 |
| b_control+rec-strict | strict | 10 | 2 | 0 | 0 | 0 | 0 | 697 | 0.3545 | 0.4416 |
| b_control+rec-strict | value | 73 | 1 | 1 | 0 | 198 | 21 | 85 | 0.6494 | 0.8303 |
| c_edc | strict | 3 | 0 | 0 | 0 | 0 | 0 | 74 | 0.2896 | 0.4935 |
| c_edc | value | 8 | 3 | 0 | 0 | 0 | 4 | 46 | 0.3397 | 0.6373 |
| c_edc+rec | strict | 2 | 2 | 0 | 0 | 0 | 0 | 83 | 0.4915 | 0.6574 |
| c_edc+rec | value | 8 | 4 | 0 | 0 | 0 | 0 | 61 | 0.5413 | 0.7195 |
| c_edc+rec-noadd | strict | 0 | 0 | 0 | 0 | 0 | 0 | 73 | 0.2602 | 0.44 |
| c_edc+rec-noadd | value | 5 | 3 | 0 | 0 | 0 | 4 | 43 | 0.3323 | 0.6255 |
| c_edc+rec-strict | strict | 2 | 2 | 0 | 0 | 0 | 0 | 63 | 0.4915 | 0.6574 |
| c_edc+rec-strict | value | 8 | 4 | 0 | 0 | 0 | 0 | 42 | 0.5413 | 0.7195 |
| corrupt | strict | 163 | 204 | 262 | 17 | 0 | 0 | 60 | 1.0 | 1.0 |
| corrupt | value | 163 | 202 | 262 | 17 | 58 | 0 | 2 | 1.0 | 1.0 |
| corrupt+rec | strict | 154 | 121 | 247 | 17 | 0 | 0 | 29 | 0.9981 | 0.9981 |
| corrupt+rec | value | 155 | 120 | 248 | 17 | 20 | 0 | 0 | 1.0 | 1.0 |
| corrupt+rec-noadd | strict | 144 | 118 | 247 | 17 | 0 | 0 | 27 | 0.9981 | 0.9981 |
| corrupt+rec-noadd | value | 144 | 116 | 247 | 17 | 20 | 0 | 7 | 0.9981 | 0.9981 |
| corrupt+rec-strict | strict | 154 | 24 | 9 | 2 | 0 | 0 | 25 | 0.9981 | 0.9981 |
| corrupt+rec-strict | value | 155 | 21 | 9 | 2 | 20 | 0 | 0 | 1.0 | 1.0 |
| dropped | strict | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 0.9622 | 0.9622 |
| dropped | value | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 0.9622 | 0.9622 |
| dropped+rec | strict | 10 | 5 | 0 | 0 | 0 | 0 | 20 | 0.9603 | 0.9603 |
| dropped+rec | value | 11 | 5 | 0 | 0 | 0 | 0 | 13 | 0.9622 | 0.9622 |
| dropped+rec-noadd | strict | 0 | 0 | 0 | 0 | 0 | 0 | 19 | 0.9603 | 0.9603 |
| dropped+rec-noadd | value | 0 | 0 | 0 | 0 | 0 | 0 | 19 | 0.9603 | 0.9603 |
| dropped+rec-strict | strict | 10 | 5 | 0 | 0 | 0 | 0 | 5 | 0.9603 | 0.9603 |
| dropped+rec-strict | value | 11 | 5 | 0 | 0 | 0 | 0 | 0 | 0.9622 | 0.9622 |
| gold | strict | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.0 | 1.0 |
| gold | value | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.0 | 1.0 |
| gold+rec | strict | 10 | 0 | 0 | 0 | 0 | 0 | 7 | 0.9981 | 0.9981 |
| gold+rec | value | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 1.0 | 1.0 |
| gold+rec-noadd | strict | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 0.9981 | 0.9981 |
| gold+rec-noadd | value | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 0.9981 | 0.9981 |
| gold+rec-strict | strict | 10 | 0 | 0 | 0 | 0 | 0 | 5 | 0.9981 | 0.9981 |
| gold+rec-strict | value | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 1.0 | 1.0 |

## Grounding (independent of gold)

Can each emitted assertion be found in the source text? Cells are grounded x gold-supported; grounded_unsupported is the traceable claim modeled wrong. Relations are grounded at sentence or document level. pdf_disagreements counts assertions whose grounding differs between the clean and the PDF-extracted text.

| arm | scorer | grounded_rate_micro | grounded_supported | grounded_unsupported | ungrounded_supported | ungrounded_unsupported | grounded_unsupported_share | rel_sentence_rate | rel_document_rate | rel_indirect_rate | entity_grounded_rate | pdf_disagreements |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 0.8717 | 164 | 203 | 0 | 54 | 0.7899 | 0.7815 | 0.1523 | 0.0199 | 0.9844 | 0 |
| a_sdk_agent | value | 0.8699 | 215 | 146 | 0 | 54 | 0.73 | 0.7785 | 0.1544 | 0.0201 | 0.9844 | 0 |
| a_sdk_agent+rec | strict | 0.8673 | 190 | 163 | 0 | 54 | 0.7512 | 0.7939 | 0.1145 | 0.0229 | 0.9697 | 0 |
| a_sdk_agent+rec | value | 0.8657 | 224 | 124 | 0 | 54 | 0.6966 | 0.7923 | 0.1154 | 0.0231 | 0.9697 | 0 |
| a_sdk_agent+rec-noadd | strict | 0.8575 | 148 | 177 | 0 | 54 | 0.7662 | 0.7672 | 0.1293 | 0.0259 | 0.9531 | 0 |
| a_sdk_agent+rec-noadd | value | 0.8556 | 196 | 124 | 0 | 54 | 0.6966 | 0.7652 | 0.1304 | 0.0261 | 0.9531 | 0 |
| a_sdk_agent+rec-strict | strict | 0.9326 | 182 | 150 | 0 | 24 | 0.8621 | 0.8942 | 0.0769 | 0.0096 | 0.9167 | 0 |
| a_sdk_agent+rec-strict | value | 0.9318 | 213 | 115 | 0 | 24 | 0.8273 | 0.8942 | 0.0769 | 0.0096 | 0.9167 | 0 |
| b_control | strict | 0.8611 | 346 | 677 | 0 | 165 | 0.804 | 0.7711 | 0.1265 | 0.0221 | 0.9527 | 0 |
| b_control | value | 0.8596 | 734 | 276 | 0 | 165 | 0.6259 | 0.7737 | 0.1232 | 0.0222 | 0.9527 | 0 |
| b_control+rec | strict | 0.8296 | 439 | 569 | 0 | 207 | 0.7332 | 0.7229 | 0.0813 | 0.0208 | 0.8552 | 0 |
| b_control+rec | value | 0.8274 | 765 | 227 | 0 | 207 | 0.523 | 0.7236 | 0.0781 | 0.0211 | 0.8552 | 0 |
| b_control+rec-noadd | strict | 0.813 | 346 | 554 | 0 | 207 | 0.728 | 0.7152 | 0.0835 | 0.0214 | 0.8536 | 0 |
| b_control+rec-noadd | value | 0.8108 | 668 | 219 | 0 | 207 | 0.5141 | 0.7177 | 0.0797 | 0.0216 | 0.8536 | 0 |
| b_control+rec-strict | strict | 0.8496 | 415 | 540 | 0 | 169 | 0.7616 | 0.8564 | 0.0101 | 0.0025 | 0.8508 | 0 |
| b_control+rec-strict | value | 0.8477 | 731 | 210 | 0 | 169 | 0.5541 | 0.855 | 0.0102 | 0.0025 | 0.8508 | 0 |
| c_edc | strict | 0.9065 | 62 | 64 | 0 | 13 | 0.8312 | 0.8667 | 0.0222 | 0.0 | 0.9383 | 0 |
| c_edc | value | 0.903 | 73 | 48 | 0 | 13 | 0.7869 | 0.8667 | 0.0222 | 0.0 | 0.9383 | 0 |
| c_edc+rec | strict | 0.9676 | 129 | 80 | 0 | 7 | 0.9195 | 0.9388 | 0.0 | 0.0 | 0.9423 | 0 |
| c_edc+rec | value | 0.9676 | 143 | 66 | 0 | 7 | 0.9041 | 0.9388 | 0.0 | 0.0 | 0.9423 | 0 |
| c_edc+rec-noadd | strict | 0.9449 | 54 | 66 | 0 | 7 | 0.9041 | 0.8605 | 0.0 | 0.0 | 0.9259 | 0 |
| c_edc+rec-noadd | value | 0.9426 | 67 | 48 | 0 | 7 | 0.8727 | 0.8605 | 0.0 | 0.0 | 0.9259 | 0 |
| c_edc+rec-strict | strict | 0.9948 | 125 | 66 | 0 | 1 | 0.9851 | 1.0 | 0.0 | 0.0 | 0.9327 | 0 |
| c_edc+rec-strict | value | 0.9948 | 138 | 53 | 0 | 1 | 0.9815 | 1.0 | 0.0 | 0.0 | 0.9327 | 0 |
| corrupt | strict | 0.9983 | 1054 | 703 | 0 | 3 | 0.9958 | 0.6129 | 0.349 | 0.0349 | 1.0 | 0 |
| corrupt | value | 0.9983 | 1056 | 701 | 0 | 3 | 0.9957 | 0.6129 | 0.349 | 0.0349 | 1.0 | 0 |
| corrupt+rec | strict | 0.9983 | 1195 | 565 | 0 | 3 | 0.9947 | 0.637 | 0.3272 | 0.0327 | 1.0 | 0 |
| corrupt+rec | value | 0.9983 | 1203 | 557 | 0 | 3 | 0.9946 | 0.637 | 0.3272 | 0.0327 | 1.0 | 0 |
| corrupt+rec-noadd | strict | 0.9981 | 1035 | 550 | 0 | 3 | 0.9946 | 0.5651 | 0.3919 | 0.0393 | 1.0 | 0 |
| corrupt+rec-noadd | value | 0.9981 | 1037 | 548 | 0 | 3 | 0.9946 | 0.5651 | 0.3919 | 0.0393 | 1.0 | 0 |
| corrupt+rec-strict | strict | 1.0 | 1184 | 214 | 0 | 0 | 1.0 | 0.877 | 0.123 | 0.0 | 1.0 | 0 |
| corrupt+rec-strict | value | 1.0 | 1190 | 207 | 0 | 0 | 1.0 | 0.8768 | 0.1232 | 0.0 | 1.0 | 0 |
| dropped | strict | 0.9901 | 1305 | 0 | 0 | 13 | 0.0 | 0.8162 | 0.1387 | 0.0216 | 0.9624 | 0 |
| dropped | value | 0.9901 | 1305 | 0 | 0 | 13 | 0.0 | 0.8162 | 0.1387 | 0.0216 | 0.9624 | 0 |
| dropped+rec | strict | 0.9911 | 1420 | 22 | 0 | 13 | 0.6286 | 0.822 | 0.1418 | 0.0174 | 0.9624 | 0 |
| dropped+rec | value | 0.9911 | 1426 | 16 | 0 | 13 | 0.5517 | 0.822 | 0.1418 | 0.0174 | 0.9624 | 0 |
| dropped+rec-noadd | strict | 0.99 | 1286 | 6 | 0 | 13 | 0.3158 | 0.8152 | 0.1395 | 0.0217 | 0.9624 | 0 |
| dropped+rec-noadd | value | 0.99 | 1286 | 6 | 0 | 13 | 0.3158 | 0.8152 | 0.1395 | 0.0217 | 0.9624 | 0 |
| dropped+rec-strict | strict | 1.0 | 1361 | 20 | 0 | 0 | 1.0 | 0.8891 | 0.1109 | 0.0 | 0.9624 | 0 |
| dropped+rec-strict | value | 1.0 | 1365 | 16 | 0 | 0 | 1.0 | 0.8891 | 0.1109 | 0.0 | 0.9624 | 0 |
| gold | strict | 1.0 | 1559 | 0 | 0 | 0 | None | 0.8317 | 0.1432 | 0.0251 | 1.0 | 0 |
| gold | value | 1.0 | 1559 | 0 | 0 | 0 | None | 0.8317 | 0.1432 | 0.0251 | 1.0 | 0 |
| gold+rec | strict | 1.0 | 1539 | 17 | 0 | 0 | 1.0 | 0.8308 | 0.1439 | 0.0253 | 1.0 | 0 |
| gold+rec | value | 1.0 | 1545 | 11 | 0 | 0 | 1.0 | 0.8308 | 0.1439 | 0.0253 | 1.0 | 0 |
| gold+rec-noadd | strict | 1.0 | 1539 | 6 | 0 | 0 | 1.0 | 0.8308 | 0.1439 | 0.0253 | 1.0 | 0 |
| gold+rec-noadd | value | 1.0 | 1539 | 6 | 0 | 0 | 1.0 | 0.8308 | 0.1439 | 0.0253 | 1.0 | 0 |
| gold+rec-strict | strict | 1.0 | 1451 | 15 | 0 | 0 | 1.0 | 0.8967 | 0.1033 | 0.0 | 1.0 | 0 |
| gold+rec-strict | value | 1.0 | 1455 | 11 | 0 | 0 | 1.0 | 0.8967 | 0.1033 | 0.0 | 1.0 | 0 |

## Bootstrap 95% intervals

Micro precision and recall, 2000 resamples of the cases (seed 0).

| arm | scorer | precision_micro | P 95% CI | recall_micro | R 95% CI |
|---|---|---|---|---|---|
| a_sdk_agent | strict | 0.3895 | 0.2833-0.4825 | 0.1052 | 0.0343-0.1921 |
| a_sdk_agent | value | 0.5181 | 0.4575-0.5697 | 0.1379 | 0.0478-0.2404 |
| a_sdk_agent+rec | strict | 0.4668 | 0.3831-0.5548 | 0.1219 | 0.0422-0.2102 |
| a_sdk_agent+rec | value | 0.5572 | 0.4949-0.6326 | 0.1437 | 0.0506-0.246 |
| a_sdk_agent+rec-noadd | strict | 0.3905 | 0.2917-0.4902 | 0.0949 | 0.0317-0.171 |
| a_sdk_agent+rec-noadd | value | 0.5241 | 0.461-0.593 | 0.1257 | 0.0437-0.2173 |
| a_sdk_agent+rec-strict | strict | 0.5112 | 0.4043-0.625 | 0.1167 | 0.0421-0.2007 |
| a_sdk_agent+rec-strict | value | 0.6051 | 0.5298-0.6826 | 0.1366 | 0.0482-0.2331 |
| b_control | strict | 0.2912 | 0.2496-0.3388 | 0.2219 | 0.1764-0.2723 |
| b_control | value | 0.6213 | 0.5921-0.6498 | 0.4682 | 0.4031-0.5225 |
| b_control+rec | strict | 0.3613 | 0.2966-0.4312 | 0.2816 | 0.224-0.3397 |
| b_control+rec | value | 0.633 | 0.6058-0.6595 | 0.4869 | 0.4172-0.5445 |
| b_control+rec-noadd | strict | 0.3126 | 0.2689-0.3615 | 0.2219 | 0.1764-0.2723 |
| b_control+rec-noadd | value | 0.6069 | 0.5779-0.6357 | 0.4259 | 0.3655-0.4793 |
| b_control+rec-strict | strict | 0.3692 | 0.2999-0.4474 | 0.2662 | 0.2096-0.3224 |
| b_control+rec-strict | value | 0.6532 | 0.6298-0.6763 | 0.465 | 0.3995-0.5195 |
| c_edc | strict | 0.446 | 0.3356-0.5682 | 0.1623 | 0.1136-0.2145 |
| c_edc | value | 0.5448 | 0.4326-0.6693 | 0.1911 | 0.1386-0.244 |
| c_edc+rec | strict | 0.5972 | 0.5391-0.6774 | 0.3377 | 0.2894-0.3887 |
| c_edc+rec | value | 0.6528 | 0.5992-0.7105 | 0.3691 | 0.3178-0.4236 |
| c_edc+rec-noadd | strict | 0.4252 | 0.3014-0.5556 | 0.1414 | 0.0963-0.2016 |
| c_edc+rec-noadd | value | 0.5492 | 0.44-0.6757 | 0.1754 | 0.13-0.2358 |
| c_edc+rec-strict | strict | 0.651 | 0.5907-0.7351 | 0.3272 | 0.2842-0.3808 |
| c_edc+rec-strict | value | 0.7083 | 0.658-0.7733 | 0.356 | 0.3101-0.4085 |
| corrupt | strict | 0.5989 | 0.5859-0.6119 | 0.6761 | 0.6611-0.6913 |
| corrupt | value | 0.6 | 0.5868-0.6127 | 0.6774 | 0.6628-0.6922 |
| corrupt+rec | strict | 0.6778 | 0.6644-0.6918 | 0.7665 | 0.752-0.7821 |
| corrupt+rec | value | 0.6824 | 0.6702-0.6951 | 0.7716 | 0.7582-0.7859 |
| corrupt+rec-noadd | strict | 0.6518 | 0.6385-0.6656 | 0.6639 | 0.6497-0.6785 |
| corrupt+rec-noadd | value | 0.653 | 0.6403-0.6667 | 0.6652 | 0.6514-0.6794 |
| corrupt+rec-strict | strict | 0.8469 | 0.8315-0.8628 | 0.7595 | 0.7446-0.7743 |
| corrupt+rec-strict | value | 0.8518 | 0.8364-0.8674 | 0.7633 | 0.7495-0.7771 |
| dropped | strict | 0.9901 | 0.9863-0.9939 | 0.8371 | 0.8313-0.8425 |
| dropped | value | 0.9901 | 0.9863-0.9939 | 0.8371 | 0.8313-0.8425 |
| dropped+rec | strict | 0.9759 | 0.9644-0.9853 | 0.9108 | 0.8992-0.9226 |
| dropped+rec | value | 0.9801 | 0.9714-0.9873 | 0.9147 | 0.9035-0.9252 |
| dropped+rec-noadd | strict | 0.9854 | 0.9756-0.9923 | 0.8249 | 0.8147-0.8334 |
| dropped+rec-noadd | value | 0.9854 | 0.9756-0.9923 | 0.8249 | 0.8147-0.8334 |
| dropped+rec-strict | strict | 0.9855 | 0.9753-0.9936 | 0.873 | 0.8585-0.8872 |
| dropped+rec-strict | value | 0.9884 | 0.9802-0.9944 | 0.8756 | 0.8604-0.8897 |
| gold | strict | 1.0 | 1.0-1.0 | 1.0 | 1.0-1.0 |
| gold | value | 1.0 | 1.0-1.0 | 1.0 | 1.0-1.0 |
| gold+rec | strict | 0.9891 | 0.9787-0.9968 | 0.9872 | 0.9757-0.9948 |
| gold+rec | value | 0.9929 | 0.9872-0.9974 | 0.991 | 0.987-0.9949 |
| gold+rec-noadd | strict | 0.9961 | 0.9881-1.0 | 0.9872 | 0.9757-0.9948 |
| gold+rec-noadd | value | 0.9961 | 0.9881-1.0 | 0.9872 | 0.9757-0.9948 |
| gold+rec-strict | strict | 0.9898 | 0.9811-0.9966 | 0.9307 | 0.9185-0.9431 |
| gold+rec-strict | value | 0.9925 | 0.9864-0.9972 | 0.9333 | 0.9222-0.9448 |

## Unsupported triples by first stage

| arm | scorer | generation |
|---|---|---|
| a_sdk_agent | strict | 257 |
| a_sdk_agent | value | 200 |
| a_sdk_agent+rec | strict | 217 |
| a_sdk_agent+rec | value | 178 |
| a_sdk_agent+rec-noadd | strict | 231 |
| a_sdk_agent+rec-noadd | value | 178 |
| a_sdk_agent+rec-strict | strict | 174 |
| a_sdk_agent+rec-strict | value | 139 |
| b_control | strict | 842 |
| b_control | value | 441 |
| b_control+rec | strict | 776 |
| b_control+rec | value | 434 |
| b_control+rec-noadd | strict | 761 |
| b_control+rec-noadd | value | 426 |
| b_control+rec-strict | strict | 709 |
| b_control+rec-strict | value | 379 |
| c_edc | strict | 77 |
| c_edc | value | 61 |
| c_edc+rec | strict | 87 |
| c_edc+rec | value | 73 |
| c_edc+rec-noadd | strict | 73 |
| c_edc+rec-noadd | value | 55 |
| c_edc+rec-strict | strict | 67 |
| c_edc+rec-strict | value | 54 |
| corrupt | strict | 706 |
| corrupt | value | 704 |
| corrupt+rec | strict | 568 |
| corrupt+rec | value | 560 |
| corrupt+rec-noadd | strict | 553 |
| corrupt+rec-noadd | value | 551 |
| corrupt+rec-strict | strict | 214 |
| corrupt+rec-strict | value | 207 |
| dropped | strict | 13 |
| dropped | value | 13 |
| dropped+rec | strict | 35 |
| dropped+rec | value | 29 |
| dropped+rec-noadd | strict | 19 |
| dropped+rec-noadd | value | 19 |
| dropped+rec-strict | strict | 20 |
| dropped+rec-strict | value | 16 |
| gold | strict | 0 |
| gold | value | 0 |
| gold+rec | strict | 17 |
| gold+rec | value | 11 |
| gold+rec-noadd | strict | 6 |
| gold+rec-noadd | value | 6 |
| gold+rec-strict | strict | 15 |
| gold+rec-strict | value | 11 |

## Failures (zero recall)

- a_sdk_agent: case_01 case_02 case_04 case_05 case_06 case_08 case_10 case_12 case_13 case_14 case_15 case_16 case_17 case_20
- a_sdk_agent+rec: case_01 case_02 case_04 case_05 case_06 case_08 case_10 case_12 case_13 case_14 case_15 case_16 case_17 case_20
- a_sdk_agent+rec-noadd: case_01 case_02 case_04 case_05 case_06 case_08 case_10 case_12 case_13 case_14 case_15 case_16 case_17 case_20
- a_sdk_agent+rec-strict: case_01 case_02 case_04 case_05 case_06 case_08 case_10 case_12 case_13 case_14 case_15 case_16 case_17 case_20
- b_control: case_20
- b_control+rec: case_20
- b_control+rec-noadd: case_20
- b_control+rec-strict: case_20
- c_edc: none
- c_edc+rec: none
- c_edc+rec-noadd: none
- c_edc+rec-strict: none
- corrupt: none
- corrupt+rec: none
- corrupt+rec-noadd: none
- corrupt+rec-strict: none
- dropped: none
- dropped+rec: none
- dropped+rec-noadd: none
- dropped+rec-strict: none
- gold: none
- gold+rec: none
- gold+rec-noadd: none
- gold+rec-strict: none
