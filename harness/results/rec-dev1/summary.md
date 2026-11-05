# Faithfulness run

SDK `v1.33.0`, endpoint `tinker` (model `Qwen/Qwen3.5-9B`).

| arm | scorer | cases | failures | incomplete | capped | valid | valid_rate | precision_macro | recall_macro | precision_micro | recall_micro | tokens_prompt | tokens_completion | wall_s_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.3756 | 0.1109 | 0.3895 | 0.1052 | 7411893 | 423580 | 1320.9 |
| a_sdk_agent | value | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.5159 | 0.1461 | 0.5181 | 0.1379 | 7411893 | 423580 | 1320.9 |
| a_sdk_agent+rec | strict | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.4207 | 0.1245 | 0.4115 | 0.1193 | 7411893 | 423580 | 1530.2 |
| a_sdk_agent+rec | value | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.5559 | 0.1645 | 0.5459 | 0.1565 | 7411893 | 423580 | 1530.2 |
| a_sdk_agent+rec-noadd | strict | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.3816 | 0.0996 | 0.3905 | 0.0949 | 7411893 | 423580 | 1417.6 |
| a_sdk_agent+rec-noadd | value | 20 | 14 | 0 | 3 | 3 | 0.15 | 0.5265 | 0.1322 | 0.5241 | 0.1257 | 7411893 | 423580 | 1417.6 |
| a_sdk_agent+rec-strict | strict | 20 | 14 | 0 | 3 | 5 | 0.25 | 0.4535 | 0.1194 | 0.4453 | 0.1148 | 7411893 | 423580 | 1530.2 |
| a_sdk_agent+rec-strict | value | 20 | 14 | 0 | 3 | 5 | 0.25 | 0.5941 | 0.1573 | 0.5879 | 0.1501 | 7411893 | 423580 | 1530.2 |
| b_control | strict | 20 | 1 | 0 | 0 | 17 | 0.85 | 0.287 | 0.2224 | 0.2912 | 0.2219 | 42981 | 116542 | 300.5 |
| b_control | value | 20 | 1 | 0 | 0 | 17 | 0.85 | 0.622 | 0.4696 | 0.6213 | 0.4682 | 42981 | 116542 | 300.5 |
| b_control+rec | strict | 20 | 1 | 0 | 0 | 16 | 0.8 | 0.2811 | 0.2268 | 0.2827 | 0.2271 | 42981 | 116542 | 923.5 |
| b_control+rec | value | 20 | 1 | 0 | 0 | 16 | 0.8 | 0.5804 | 0.4589 | 0.5795 | 0.458 | 42981 | 116542 | 923.5 |
| b_control+rec-noadd | strict | 20 | 1 | 0 | 0 | 17 | 0.85 | 0.2904 | 0.2062 | 0.2957 | 0.2053 | 42981 | 116542 | 670.3 |
| b_control+rec-noadd | value | 20 | 1 | 0 | 0 | 17 | 0.85 | 0.5974 | 0.4119 | 0.5978 | 0.4099 | 42981 | 116542 | 670.3 |
| b_control+rec-strict | strict | 20 | 1 | 0 | 0 | 17 | 0.85 | 0.3458 | 0.2504 | 0.353 | 0.2527 | 42981 | 116542 | 923.5 |
| b_control+rec-strict | value | 20 | 1 | 0 | 0 | 17 | 0.85 | 0.6187 | 0.437 | 0.6187 | 0.4362 | 42981 | 116542 | 923.5 |
| c_edc | strict | 5 | 0 | 0 | 0 | 1 | 0.2 | 0.4551 | 0.1643 | 0.446 | 0.1623 | 347922 | 9489 | 243.4 |
| c_edc | value | 5 | 0 | 0 | 0 | 1 | 0.2 | 0.5492 | 0.1926 | 0.5448 | 0.1911 | 347922 | 9489 | 243.4 |
| c_edc+rec | strict | 5 | 0 | 0 | 0 | 0 | 0.0 | 0.4479 | 0.3416 | 0.4467 | 0.3403 | 347922 | 9489 | 335.4 |
| c_edc+rec | value | 5 | 0 | 0 | 0 | 0 | 0.0 | 0.647 | 0.4889 | 0.6414 | 0.4869 | 347922 | 9489 | 335.4 |
| c_edc+rec-noadd | strict | 5 | 0 | 0 | 0 | 4 | 0.8 | 0.4365 | 0.1435 | 0.4286 | 0.1414 | 347922 | 9489 | 278.2 |
| c_edc+rec-noadd | value | 5 | 0 | 0 | 0 | 4 | 0.8 | 0.5625 | 0.177 | 0.5537 | 0.1754 | 347922 | 9489 | 278.2 |
| c_edc+rec-strict | strict | 5 | 0 | 0 | 0 | 5 | 1.0 | 0.4738 | 0.3312 | 0.4719 | 0.3298 | 347922 | 9489 | 335.4 |
| c_edc+rec-strict | value | 5 | 0 | 0 | 0 | 5 | 1.0 | 0.6901 | 0.4786 | 0.6842 | 0.4764 | 347922 | 9489 | 335.4 |
| corrupt | strict | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.5993 | 0.6771 | 0.5989 | 0.6761 | 0 | 0 | 0 |
| corrupt | value | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.6004 | 0.6784 | 0.6 | 0.6774 | 0 | 0 | 0 |
| corrupt+rec | strict | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.6058 | 0.8061 | 0.6028 | 0.805 | 0 | 0 | 623.6 |
| corrupt+rec | value | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.6938 | 0.8118 | 0.6926 | 0.8108 | 0 | 0 | 623.6 |
| corrupt+rec-noadd | strict | 20 | 0 | 0 | 0 | 1 | 0.05 | 0.6789 | 0.6625 | 0.6783 | 0.6613 | 0 | 0 | 466.1 |
| corrupt+rec-noadd | value | 20 | 0 | 0 | 0 | 1 | 0.05 | 0.6802 | 0.6638 | 0.6796 | 0.6626 | 0 | 0 | 466.1 |
| corrupt+rec-strict | strict | 20 | 0 | 0 | 0 | 11 | 0.55 | 0.5885 | 0.6003 | 0.5834 | 0.5991 | 0 | 0 | 623.6 |
| corrupt+rec-strict | value | 20 | 0 | 0 | 0 | 11 | 0.55 | 0.8981 | 0.7745 | 0.8973 | 0.7736 | 0 | 0 | 623.6 |
| dropped | strict | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.9902 | 0.8372 | 0.9901 | 0.8371 | 0 | 0 | 0 |
| dropped | value | 20 | 0 | 0 | 0 | 0 | 0.0 | 0.9902 | 0.8372 | 0.9901 | 0.8371 | 0 | 0 | 0 |
| dropped+rec | strict | 20 | 0 | 0 | 0 | 16 | 0.8 | 0.9075 | 0.9092 | 0.9066 | 0.9089 | 0 | 0 | 573.5 |
| dropped+rec | value | 20 | 0 | 0 | 0 | 16 | 0.8 | 0.9262 | 0.9105 | 0.9256 | 0.9102 | 0 | 0 | 573.5 |
| dropped+rec-noadd | strict | 20 | 0 | 0 | 0 | 20 | 1.0 | 0.9854 | 0.8239 | 0.9854 | 0.8236 | 0 | 0 | 369.3 |
| dropped+rec-noadd | value | 20 | 0 | 0 | 0 | 20 | 1.0 | 0.9854 | 0.8239 | 0.9854 | 0.8236 | 0 | 0 | 369.3 |
| dropped+rec-strict | strict | 20 | 0 | 0 | 0 | 18 | 0.9 | 0.9129 | 0.8729 | 0.9121 | 0.8724 | 0 | 0 | 573.5 |
| dropped+rec-strict | value | 20 | 0 | 0 | 0 | 18 | 0.9 | 0.9327 | 0.8742 | 0.9322 | 0.8736 | 0 | 0 | 573.5 |
| gold | strict | 20 | 0 | 0 | 0 | 0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 0 | 0 |
| gold | value | 20 | 0 | 0 | 0 | 0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 0 | 0 |
| gold+rec | strict | 20 | 0 | 0 | 0 | 16 | 0.8 | 0.9319 | 0.9835 | 0.9313 | 0.9833 | 0 | 0 | 451.1 |
| gold+rec | value | 20 | 0 | 0 | 0 | 16 | 0.8 | 0.9497 | 0.9848 | 0.9493 | 0.9846 | 0 | 0 | 451.1 |
| gold+rec-noadd | strict | 20 | 0 | 0 | 0 | 20 | 1.0 | 0.996 | 0.9841 | 0.9961 | 0.984 | 0 | 0 | 541.6 |
| gold+rec-noadd | value | 20 | 0 | 0 | 0 | 20 | 1.0 | 0.996 | 0.9841 | 0.9961 | 0.984 | 0 | 0 | 541.6 |
| gold+rec-strict | strict | 20 | 0 | 0 | 0 | 18 | 0.9 | 0.9294 | 0.9308 | 0.9289 | 0.9301 | 0 | 0 | 451.1 |
| gold+rec-strict | value | 20 | 0 | 0 | 0 | 18 | 0.9 | 0.9481 | 0.9321 | 0.9478 | 0.9314 | 0 | 0 | 451.1 |

## Unsupported triples by class

| arm | scorer | wrong_value | wrong_relation | wrong_entity | cross_document_conflation | misplaced_property | duplicate_entity | invented | gold_aligned_rate | emitted_aligned_rate |
|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 9 | 23 | 33 | 5 | 0 | 0 | 187 | 0.1582 | 0.6769 |
| a_sdk_agent | value | 6 | 22 | 33 | 8 | 50 | 12 | 69 | 0.2179 | 0.9322 |
| a_sdk_agent+rec | strict | 9 | 20 | 28 | 5 | 0 | 0 | 204 | 0.1769 | 0.5956 |
| a_sdk_agent+rec | value | 11 | 19 | 28 | 5 | 44 | 11 | 85 | 0.2449 | 0.8401 |
| a_sdk_agent+rec-noadd | strict | 9 | 19 | 28 | 5 | 0 | 0 | 170 | 0.1561 | 0.6697 |
| a_sdk_agent+rec-noadd | value | 6 | 18 | 28 | 5 | 44 | 13 | 64 | 0.2102 | 0.9065 |
| a_sdk_agent+rec-strict | strict | 9 | 12 | 28 | 5 | 0 | 0 | 169 | 0.1662 | 0.556 |
| a_sdk_agent+rec-strict | value | 11 | 10 | 28 | 5 | 43 | 12 | 55 | 0.2324 | 0.7944 |
| b_control | strict | 6 | 6 | 4 | 2 | 0 | 0 | 824 | 0.2991 | 0.3734 |
| b_control | value | 69 | 7 | 5 | 2 | 248 | 21 | 89 | 0.7212 | 0.9301 |
| b_control+rec | strict | 9 | 11 | 2 | 2 | 0 | 0 | 874 | 0.2962 | 0.3179 |
| b_control+rec | value | 79 | 11 | 6 | 2 | 201 | 27 | 186 | 0.658 | 0.7346 |
| b_control+rec-noadd | strict | 6 | 4 | 2 | 2 | 0 | 0 | 748 | 0.2761 | 0.3443 |
| b_control+rec-noadd | value | 69 | 3 | 5 | 2 | 201 | 21 | 125 | 0.6366 | 0.8234 |
| b_control+rec-strict | strict | 9 | 7 | 0 | 0 | 0 | 0 | 706 | 0.331 | 0.3542 |
| b_control+rec-strict | value | 42 | 8 | 1 | 0 | 198 | 23 | 146 | 0.6549 | 0.7312 |
| c_edc | strict | 3 | 0 | 0 | 0 | 0 | 0 | 74 | 0.2896 | 0.4935 |
| c_edc | value | 8 | 3 | 0 | 0 | 0 | 4 | 46 | 0.3397 | 0.6373 |
| c_edc+rec | strict | 2 | 2 | 0 | 0 | 0 | 0 | 157 | 0.4915 | 0.4677 |
| c_edc+rec | value | 14 | 4 | 0 | 0 | 0 | 1 | 83 | 0.7119 | 0.6863 |
| c_edc+rec-noadd | strict | 0 | 0 | 0 | 0 | 0 | 0 | 72 | 0.2602 | 0.44 |
| c_edc+rec-noadd | value | 5 | 3 | 0 | 0 | 0 | 4 | 42 | 0.3323 | 0.6255 |
| c_edc+rec-strict | strict | 2 | 2 | 0 | 0 | 0 | 0 | 137 | 0.4915 | 0.4677 |
| c_edc+rec-strict | value | 13 | 4 | 0 | 0 | 0 | 1 | 64 | 0.7119 | 0.6863 |
| corrupt | strict | 163 | 204 | 262 | 17 | 0 | 0 | 60 | 1.0 | 1.0 |
| corrupt | value | 163 | 202 | 262 | 17 | 58 | 0 | 2 | 1.0 | 1.0 |
| corrupt+rec | strict | 150 | 72 | 247 | 14 | 0 | 0 | 344 | 0.9981 | 0.7947 |
| corrupt+rec | value | 151 | 68 | 247 | 14 | 20 | 39 | 22 | 1.0 | 0.9787 |
| corrupt+rec-noadd | strict | 144 | 57 | 247 | 14 | 0 | 0 | 27 | 0.9981 | 0.9981 |
| corrupt+rec-noadd | value | 144 | 55 | 247 | 14 | 20 | 0 | 7 | 0.9981 | 0.9981 |
| corrupt+rec-strict | strict | 22 | 20 | 3 | 1 | 0 | 0 | 621 | 0.7901 | 0.6311 |
| corrupt+rec-strict | value | 23 | 27 | 9 | 2 | 20 | 39 | 18 | 1.0 | 0.9787 |
| dropped | strict | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 0.9622 | 0.9622 |
| dropped | value | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 0.9622 | 0.9622 |
| dropped+rec | strict | 5 | 18 | 0 | 0 | 0 | 0 | 123 | 0.9603 | 0.8695 |
| dropped+rec | value | 6 | 17 | 0 | 0 | 0 | 25 | 66 | 0.9622 | 0.9115 |
| dropped+rec-noadd | strict | 0 | 0 | 0 | 0 | 0 | 0 | 19 | 0.9603 | 0.9603 |
| dropped+rec-noadd | value | 0 | 0 | 0 | 0 | 0 | 0 | 19 | 0.9603 | 0.9603 |
| dropped+rec-strict | strict | 5 | 18 | 0 | 0 | 0 | 0 | 108 | 0.9603 | 0.8695 |
| dropped+rec-strict | value | 6 | 17 | 0 | 0 | 0 | 25 | 51 | 0.9622 | 0.9115 |
| gold | strict | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.0 | 1.0 |
| gold | value | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.0 | 1.0 |
| gold+rec | strict | 5 | 17 | 0 | 0 | 0 | 0 | 91 | 0.9981 | 0.9314 |
| gold+rec | value | 6 | 17 | 0 | 0 | 0 | 25 | 34 | 1.0 | 0.9749 |
| gold+rec-noadd | strict | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 0.9981 | 0.9981 |
| gold+rec-noadd | value | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 0.9981 | 0.9981 |
| gold+rec-strict | strict | 5 | 17 | 0 | 0 | 0 | 0 | 89 | 0.9981 | 0.9314 |
| gold+rec-strict | value | 6 | 17 | 0 | 0 | 0 | 25 | 32 | 1.0 | 0.9749 |

## Grounding (independent of gold)

Can each emitted assertion be found in the source text? Cells are grounded x gold-supported; grounded_unsupported is the traceable claim modeled wrong. Relations are grounded at sentence or document level. pdf_disagreements counts assertions whose grounding differs between the clean and the PDF-extracted text.

| arm | scorer | grounded_rate_micro | grounded_supported | grounded_unsupported | ungrounded_supported | ungrounded_unsupported | grounded_unsupported_share | rel_sentence_rate | rel_document_rate | rel_indirect_rate | entity_grounded_rate | pdf_disagreements |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_sdk_agent | strict | 0.8717 | 164 | 203 | 0 | 54 | 0.7899 | 0.7815 | 0.1523 | 0.0199 | 0.9844 | 0 |
| a_sdk_agent | value | 0.8699 | 215 | 146 | 0 | 54 | 0.73 | 0.7785 | 0.1544 | 0.0201 | 0.9844 | 0 |
| a_sdk_agent+rec | strict | 0.8518 | 186 | 199 | 0 | 67 | 0.7481 | 0.7593 | 0.0926 | 0.0185 | 0.8994 | 0 |
| a_sdk_agent+rec | value | 0.8501 | 244 | 136 | 0 | 67 | 0.67 | 0.7578 | 0.0932 | 0.0186 | 0.8994 | 0 |
| a_sdk_agent+rec-noadd | strict | 0.8575 | 148 | 177 | 0 | 54 | 0.7662 | 0.7672 | 0.1293 | 0.0259 | 0.9531 | 0 |
| a_sdk_agent+rec-noadd | value | 0.8556 | 196 | 124 | 0 | 54 | 0.6966 | 0.7652 | 0.1304 | 0.0261 | 0.9531 | 0 |
| a_sdk_agent+rec-strict | strict | 0.908 | 179 | 186 | 0 | 37 | 0.8341 | 0.8296 | 0.0593 | 0.0074 | 0.8553 | 0 |
| a_sdk_agent+rec-strict | value | 0.907 | 234 | 127 | 0 | 37 | 0.7744 | 0.8296 | 0.0593 | 0.0074 | 0.8553 | 0 |
| b_control | strict | 0.8611 | 346 | 677 | 0 | 165 | 0.804 | 0.7711 | 0.1265 | 0.0221 | 0.9527 | 0 |
| b_control | value | 0.8596 | 734 | 276 | 0 | 165 | 0.6259 | 0.7737 | 0.1232 | 0.0222 | 0.9527 | 0 |
| b_control+rec | strict | 0.7891 | 354 | 634 | 0 | 264 | 0.706 | 0.6607 | 0.0696 | 0.0179 | 0.7568 | 0 |
| b_control+rec | value | 0.7857 | 720 | 248 | 0 | 264 | 0.4844 | 0.6582 | 0.0673 | 0.0182 | 0.7568 | 0 |
| b_control+rec-noadd | strict | 0.8087 | 320 | 555 | 0 | 207 | 0.7283 | 0.7146 | 0.0837 | 0.0215 | 0.8446 | 0 |
| b_control+rec-noadd | value | 0.8064 | 643 | 219 | 0 | 207 | 0.5141 | 0.7171 | 0.0799 | 0.0216 | 0.8446 | 0 |
| b_control+rec-strict | strict | 0.8306 | 394 | 533 | 0 | 189 | 0.7382 | 0.7631 | 0.0063 | 0.0021 | 0.7529 | 0 |
| b_control+rec-strict | value | 0.828 | 681 | 229 | 0 | 189 | 0.5478 | 0.7591 | 0.0064 | 0.0021 | 0.7529 | 0 |
| c_edc | strict | 0.9065 | 62 | 64 | 0 | 13 | 0.8312 | 0.8667 | 0.0222 | 0.0 | 0.9383 | 0 |
| c_edc | value | 0.903 | 73 | 48 | 0 | 13 | 0.7869 | 0.8667 | 0.0222 | 0.0 | 0.9383 | 0 |
| c_edc+rec | strict | 0.9313 | 130 | 141 | 0 | 20 | 0.8758 | 0.8611 | 0.0069 | 0.0 | 0.875 | 0 |
| c_edc+rec | value | 0.931 | 188 | 82 | 0 | 20 | 0.8039 | 0.8601 | 0.007 | 0.0 | 0.875 | 0 |
| c_edc+rec-noadd | strict | 0.9444 | 54 | 65 | 0 | 7 | 0.9028 | 0.8571 | 0.0 | 0.0 | 0.9259 | 0 |
| c_edc+rec-noadd | value | 0.9421 | 67 | 47 | 0 | 7 | 0.8704 | 0.8571 | 0.0 | 0.0 | 0.9259 | 0 |
| c_edc+rec-strict | strict | 0.9476 | 126 | 127 | 0 | 14 | 0.9007 | 0.8852 | 0.0 | 0.0 | 0.8681 | 0 |
| c_edc+rec-strict | value | 0.9474 | 184 | 68 | 0 | 14 | 0.8293 | 0.8843 | 0.0 | 0.0 | 0.8681 | 0 |
| corrupt | strict | 0.9983 | 1054 | 703 | 0 | 3 | 0.9958 | 0.6129 | 0.349 | 0.0349 | 1.0 | 0 |
| corrupt | value | 0.9983 | 1056 | 701 | 0 | 3 | 0.9957 | 0.6129 | 0.349 | 0.0349 | 1.0 | 0 |
| corrupt+rec | strict | 0.9986 | 1255 | 824 | 0 | 3 | 0.9964 | 0.6915 | 0.2778 | 0.028 | 1.0 | 0 |
| corrupt+rec | value | 0.9984 | 1264 | 558 | 0 | 3 | 0.9947 | 0.6455 | 0.3192 | 0.0322 | 1.0 | 0 |
| corrupt+rec-noadd | strict | 0.998 | 1031 | 486 | 0 | 3 | 0.9939 | 0.5952 | 0.3579 | 0.0429 | 1.0 | 0 |
| corrupt+rec-noadd | value | 0.998 | 1033 | 484 | 0 | 3 | 0.9938 | 0.5952 | 0.3579 | 0.0429 | 1.0 | 0 |
| corrupt+rec-strict | strict | 0.9994 | 934 | 666 | 0 | 1 | 0.9985 | 0.9004 | 0.0984 | 0.0 | 1.0 | 0 |
| corrupt+rec-strict | value | 0.9993 | 1206 | 137 | 0 | 1 | 0.9928 | 0.8775 | 0.1209 | 0.0 | 1.0 | 0 |
| dropped | strict | 0.9901 | 1305 | 0 | 0 | 13 | 0.0 | 0.8162 | 0.1387 | 0.0216 | 0.9624 | 0 |
| dropped | value | 0.9901 | 1305 | 0 | 0 | 13 | 0.0 | 0.8162 | 0.1387 | 0.0216 | 0.9624 | 0 |
| dropped+rec | strict | 0.9795 | 1417 | 114 | 0 | 32 | 0.7808 | 0.8134 | 0.1288 | 0.0158 | 0.9353 | 0 |
| dropped+rec | value | 0.9791 | 1419 | 82 | 0 | 32 | 0.7193 | 0.8068 | 0.1333 | 0.0163 | 0.9353 | 0 |
| dropped+rec-noadd | strict | 0.99 | 1284 | 6 | 0 | 13 | 0.3158 | 0.8145 | 0.14 | 0.0218 | 0.9624 | 0 |
| dropped+rec-noadd | value | 0.99 | 1284 | 6 | 0 | 13 | 0.3158 | 0.8145 | 0.14 | 0.0218 | 0.9624 | 0 |
| dropped+rec-strict | strict | 0.9873 | 1360 | 112 | 0 | 19 | 0.855 | 0.8732 | 0.0994 | 0.0 | 0.9353 | 0 |
| dropped+rec-strict | value | 0.987 | 1362 | 80 | 0 | 19 | 0.8081 | 0.8683 | 0.1033 | 0.0 | 0.9353 | 0 |
| gold | strict | 1.0 | 1559 | 0 | 0 | 0 | None | 0.8317 | 0.1432 | 0.0251 | 1.0 | 0 |
| gold | value | 1.0 | 1559 | 0 | 0 | 0 | None | 0.8317 | 0.1432 | 0.0251 | 1.0 | 0 |
| gold+rec | strict | 1.0 | 1533 | 113 | 0 | 0 | 1.0 | 0.8412 | 0.1351 | 0.0237 | 1.0 | 0 |
| gold+rec | value | 1.0 | 1535 | 82 | 0 | 0 | 1.0 | 0.8364 | 0.1392 | 0.0244 | 1.0 | 0 |
| gold+rec-noadd | strict | 1.0 | 1534 | 6 | 0 | 0 | 1.0 | 0.8297 | 0.1449 | 0.0254 | 1.0 | 0 |
| gold+rec-noadd | value | 1.0 | 1534 | 6 | 0 | 0 | 1.0 | 0.8297 | 0.1449 | 0.0254 | 1.0 | 0 |
| gold+rec-strict | strict | 1.0 | 1450 | 111 | 0 | 0 | 1.0 | 0.9045 | 0.0955 | 0.0 | 1.0 | 0 |
| gold+rec-strict | value | 1.0 | 1452 | 80 | 0 | 0 | 1.0 | 0.9012 | 0.0988 | 0.0 | 1.0 | 0 |

## Bootstrap 95% intervals

Micro precision and recall, 2000 resamples of the cases (seed 0).

| arm | scorer | precision_micro | P 95% CI | recall_micro | R 95% CI |
|---|---|---|---|---|---|
| a_sdk_agent | strict | 0.3895 | 0.2833-0.4825 | 0.1052 | 0.0343-0.1921 |
| a_sdk_agent | value | 0.5181 | 0.4575-0.5697 | 0.1379 | 0.0478-0.2404 |
| a_sdk_agent+rec | strict | 0.4115 | 0.3162-0.5169 | 0.1193 | 0.0418-0.2051 |
| a_sdk_agent+rec | value | 0.5459 | 0.4778-0.6254 | 0.1565 | 0.0521-0.265 |
| a_sdk_agent+rec-noadd | strict | 0.3905 | 0.2917-0.4902 | 0.0949 | 0.0317-0.171 |
| a_sdk_agent+rec-noadd | value | 0.5241 | 0.461-0.593 | 0.1257 | 0.0437-0.2173 |
| a_sdk_agent+rec-strict | strict | 0.4453 | 0.3258-0.5762 | 0.1148 | 0.0409-0.1978 |
| a_sdk_agent+rec-strict | value | 0.5879 | 0.5073-0.6708 | 0.1501 | 0.0505-0.2562 |
| b_control | strict | 0.2912 | 0.2496-0.3388 | 0.2219 | 0.1764-0.2723 |
| b_control | value | 0.6213 | 0.5921-0.6498 | 0.4682 | 0.4031-0.5225 |
| b_control+rec | strict | 0.2827 | 0.2363-0.3355 | 0.2271 | 0.1794-0.2797 |
| b_control+rec | value | 0.5795 | 0.5588-0.6 | 0.458 | 0.3955-0.5113 |
| b_control+rec-noadd | strict | 0.2957 | 0.2521-0.3461 | 0.2053 | 0.1619-0.2534 |
| b_control+rec-noadd | value | 0.5978 | 0.5675-0.6291 | 0.4099 | 0.35-0.4649 |
| b_control+rec-strict | strict | 0.353 | 0.293-0.4169 | 0.2527 | 0.1991-0.309 |
| b_control+rec-strict | value | 0.6187 | 0.5977-0.6393 | 0.4362 | 0.3789-0.4859 |
| c_edc | strict | 0.446 | 0.3356-0.5682 | 0.1623 | 0.1136-0.2145 |
| c_edc | value | 0.5448 | 0.4326-0.6693 | 0.1911 | 0.1386-0.244 |
| c_edc+rec | strict | 0.4467 | 0.3981-0.4948 | 0.3403 | 0.2894-0.3968 |
| c_edc+rec | value | 0.6414 | 0.6127-0.6832 | 0.4869 | 0.4431-0.5221 |
| c_edc+rec-noadd | strict | 0.4286 | 0.3082-0.5556 | 0.1414 | 0.0963-0.2016 |
| c_edc+rec-noadd | value | 0.5537 | 0.4444-0.6757 | 0.1754 | 0.13-0.2358 |
| c_edc+rec-strict | strict | 0.4719 | 0.4103-0.5252 | 0.3298 | 0.2842-0.3861 |
| c_edc+rec-strict | value | 0.6842 | 0.6553-0.7331 | 0.4764 | 0.4381-0.5094 |
| corrupt | strict | 0.5989 | 0.5859-0.6119 | 0.6761 | 0.6611-0.6913 |
| corrupt | value | 0.6 | 0.5868-0.6127 | 0.6774 | 0.6628-0.6922 |
| corrupt+rec | strict | 0.6028 | 0.5845-0.6215 | 0.805 | 0.793-0.8173 |
| corrupt+rec | value | 0.6926 | 0.6805-0.7041 | 0.8108 | 0.7995-0.8225 |
| corrupt+rec-noadd | strict | 0.6783 | 0.6658-0.6909 | 0.6613 | 0.6465-0.6763 |
| corrupt+rec-noadd | value | 0.6796 | 0.6673-0.692 | 0.6626 | 0.6477-0.6777 |
| corrupt+rec-strict | strict | 0.5834 | 0.5502-0.6187 | 0.5991 | 0.5759-0.6239 |
| corrupt+rec-strict | value | 0.8973 | 0.8812-0.9127 | 0.7736 | 0.7604-0.7862 |
| dropped | strict | 0.9901 | 0.9863-0.9939 | 0.8371 | 0.8313-0.8425 |
| dropped | value | 0.9901 | 0.9863-0.9939 | 0.8371 | 0.8313-0.8425 |
| dropped+rec | strict | 0.9066 | 0.889-0.923 | 0.9089 | 0.8972-0.9212 |
| dropped+rec | value | 0.9256 | 0.9111-0.9394 | 0.9102 | 0.899-0.9215 |
| dropped+rec-noadd | strict | 0.9854 | 0.9756-0.9923 | 0.8236 | 0.8135-0.8323 |
| dropped+rec-noadd | value | 0.9854 | 0.9756-0.9923 | 0.8236 | 0.8135-0.8323 |
| dropped+rec-strict | strict | 0.9121 | 0.8958-0.927 | 0.8724 | 0.8582-0.8862 |
| dropped+rec-strict | value | 0.9322 | 0.9191-0.9445 | 0.8736 | 0.859-0.8875 |
| gold | strict | 1.0 | 1.0-1.0 | 1.0 | 1.0-1.0 |
| gold | value | 1.0 | 1.0-1.0 | 1.0 | 1.0-1.0 |
| gold+rec | strict | 0.9313 | 0.9152-0.9443 | 0.9833 | 0.972-0.9913 |
| gold+rec | value | 0.9493 | 0.9356-0.9608 | 0.9846 | 0.9759-0.9913 |
| gold+rec-noadd | strict | 0.9961 | 0.9881-1.0 | 0.984 | 0.9726-0.992 |
| gold+rec-noadd | value | 0.9961 | 0.9881-1.0 | 0.984 | 0.9726-0.992 |
| gold+rec-strict | strict | 0.9289 | 0.9141-0.9413 | 0.9301 | 0.9176-0.9428 |
| gold+rec-strict | value | 0.9478 | 0.9355-0.9588 | 0.9314 | 0.9198-0.9433 |

## Unsupported triples by first stage

| arm | scorer | generation |
|---|---|---|
| a_sdk_agent | strict | 257 |
| a_sdk_agent | value | 200 |
| a_sdk_agent+rec | strict | 266 |
| a_sdk_agent+rec | value | 203 |
| a_sdk_agent+rec-noadd | strict | 231 |
| a_sdk_agent+rec-noadd | value | 178 |
| a_sdk_agent+rec-strict | strict | 223 |
| a_sdk_agent+rec-strict | value | 164 |
| b_control | strict | 842 |
| b_control | value | 441 |
| b_control+rec | strict | 898 |
| b_control+rec | value | 512 |
| b_control+rec-noadd | strict | 762 |
| b_control+rec-noadd | value | 426 |
| b_control+rec-strict | strict | 722 |
| b_control+rec-strict | value | 418 |
| c_edc | strict | 77 |
| c_edc | value | 61 |
| c_edc+rec | strict | 161 |
| c_edc+rec | value | 102 |
| c_edc+rec-noadd | strict | 72 |
| c_edc+rec-noadd | value | 54 |
| c_edc+rec-strict | strict | 141 |
| c_edc+rec-strict | value | 82 |
| corrupt | strict | 706 |
| corrupt | value | 704 |
| corrupt+rec | strict | 827 |
| corrupt+rec | value | 561 |
| corrupt+rec-noadd | strict | 489 |
| corrupt+rec-noadd | value | 487 |
| corrupt+rec-strict | strict | 667 |
| corrupt+rec-strict | value | 138 |
| dropped | strict | 13 |
| dropped | value | 13 |
| dropped+rec | strict | 146 |
| dropped+rec | value | 114 |
| dropped+rec-noadd | strict | 19 |
| dropped+rec-noadd | value | 19 |
| dropped+rec-strict | strict | 131 |
| dropped+rec-strict | value | 99 |
| gold | strict | 0 |
| gold | value | 0 |
| gold+rec | strict | 113 |
| gold+rec | value | 82 |
| gold+rec-noadd | strict | 6 |
| gold+rec-noadd | value | 6 |
| gold+rec-strict | strict | 111 |
| gold+rec-strict | value | 80 |

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
