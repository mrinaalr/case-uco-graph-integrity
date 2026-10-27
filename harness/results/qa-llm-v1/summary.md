# Faithfulness run

SDK `v1.33.0`, endpoint `tinker` (model `Qwen/Qwen3.5-9B`).

| arm | scorer | cases | failures | incomplete | capped | valid | precision_macro | recall_macro | precision_micro | recall_micro | tokens_prompt | tokens_completion | wall_s_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a1_critic@pass1 | strict | 25 | 0 | 0 | 0 | 12 | 0.3082 | 0.2474 | 0.3189 | 0.2489 | 996718 | 514688 | 1962.0 |
| a1_critic@pass1 | value | 25 | 0 | 0 | 0 | 12 | 0.6114 | 0.4806 | 0.6187 | 0.481 | 996718 | 514688 | 1962.0 |
| a1_critic | strict | 30 | 5 | 0 | 0 | 13 | 0.2525 | 0.1963 | 0.2557 | 0.2002 | 1040023 | 548267 | 2077.3 |
| a1_critic | value | 30 | 5 | 0 | 0 | 13 | 0.4966 | 0.3812 | 0.4954 | 0.3866 | 1040023 | 548267 | 2077.3 |
| a1_critic@pass2 | strict | 17 | 0 | 0 | 0 | 6 | 0.2331 | 0.2326 | 0.235 | 0.2326 | 756880 | 373635 | 1408.0 |
| a1_critic@pass2 | value | 17 | 0 | 0 | 0 | 6 | 0.4543 | 0.4512 | 0.4546 | 0.4499 | 756880 | 373635 | 1408.0 |
| a1_critic@pass3 | strict | 17 | 0 | 0 | 0 | 7 | 0.229 | 0.2327 | 0.2322 | 0.2334 | 756880 | 373635 | 1408.0 |
| a1_critic@pass3 | value | 17 | 0 | 0 | 0 | 7 | 0.4443 | 0.4514 | 0.4485 | 0.4507 | 756880 | 373635 | 1408.0 |

## Unsupported triples by class

| arm | scorer | wrong_value | wrong_relation | wrong_entity | cross_document_conflation | misplaced_property | duplicate_entity | invented | gold_aligned_rate | emitted_aligned_rate |
|---|---|---|---|---|---|---|---|---|---|---|
| a1_critic@pass1 | strict | 16 | 4 | 8 | 0 | 0 | 0 | 980 | 0.3231 | 0.3633 |
| a1_critic@pass1 | value | 16 | 11 | 15 | 9 | 346 | 9 | 156 | 0.8372 | 0.9365 |
| a1_critic | strict | 16 | 26 | 8 | 0 | 0 | 0 | 1260 | 0.2692 | 0.3525 |
| a1_critic | value | 16 | 54 | 15 | 10 | 347 | 29 | 414 | 0.6977 | 0.9112 |
| a1_critic@pass2 | strict | 8 | 23 | 0 | 0 | 0 | 0 | 913 | 0.3269 | 0.3498 |
| a1_critic@pass2 | value | 4 | 53 | 7 | 6 | 232 | 2 | 369 | 0.8392 | 0.8906 |
| a1_critic@pass3 | strict | 8 | 22 | 0 | 0 | 0 | 0 | 932 | 0.3269 | 0.3487 |
| a1_critic@pass3 | value | 4 | 52 | 7 | 6 | 232 | 22 | 368 | 0.8392 | 0.8895 |

## Unsupported triples by first stage

| arm | scorer | generation |
|---|---|---|
| a1_critic@pass1 | strict | 1008 |
| a1_critic@pass1 | value | 562 |
| a1_critic | strict | 1310 |
| a1_critic | value | 885 |
| a1_critic@pass2 | strict | 944 |
| a1_critic@pass2 | value | 673 |
| a1_critic@pass3 | strict | 962 |
| a1_critic@pass3 | value | 691 |

## Failures (zero recall)

- a1_critic@pass1: none
- a1_critic: case_04 case_06 case_10 case_15 case_29
- a1_critic@pass2: none
- a1_critic@pass3: none
