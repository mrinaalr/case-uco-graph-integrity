# QA adjustments: qa-llm-v1

Each row compares the graph before and after one serializer revision made in answer to the critic's findings. `fixed` and `regressed` count gold triples; `d_<class>` is the change in unsupported emitted triples of that class.


## strict scorer

- revisions that produced a graph: 34; revisions whose serializer crashed even after fix attempts: 8
- gold triples fixed: 4, regressed: 26; mean recall 0.241 -> 0.233, mean precision 0.272 -> 0.231
- validity (SHACL conforms) before -> after: 14/34 -> 13/34
- unsupported triples by class, net change: wrong_value +0, wrong_relation +22, wrong_entity +0, cross_document_conflation +0, misplaced_property +0, duplicate_entity +0, invented +280

### Per rule addressed (a revision counts toward every rule it answered)

| rule | revisions | fixed | regressed | d_invented | d_wrong_relation | d_wrong_value |
|---|---|---|---|---|---|---|
| CRIT-G-DANGLING-REF | 2 | 0 | 0 | 27 | 0 | 0 |
| CRIT-H-ORPHAN-TOP-LEVEL | 34 | 4 | 26 | 280 | 22 | 0 |
| CRIT-H-RELATED-TO-OVERUSE | 2 | 0 | 0 | 1 | 0 | 0 |
| CRIT-S-PY-REL-ID-COLLAPSE | 13 | 0 | 0 | 151 | 0 | 0 |
| CRIT-V-NONCONFORMING | 20 | 4 | 21 | 170 | 17 | 0 |
| CRIT-V-RELATIONSHIP-LINT | 34 | 4 | 26 | 280 | 22 | 0 |
| investigation_structure | 9 | 0 | 17 | 73 | 17 | 0 |
| relationship_vocabulary | 12 | 4 | 12 | 101 | 8 | 0 |
| serializer_api | 2 | 0 | 0 | 17 | 0 | 0 |
| source_fidelity | 19 | 4 | 26 | 149 | 22 | 0 |

### Trajectory per case (pass: precision / recall)

| case | status | final outcome | passes |
|---|---|---|---|
| case_01 | ok | not finalized: critic_session_passes_incomplete | p1: 0.29 / 0.2 |
| case_02 | ok | not finalized: critic_session_passes_incomplete | p1: 0.21 / 0.12 |
| case_03 | ok | not finalized: critic_session_passes_incomplete | p1: 0.32 / 0.32 |
| case_04 | error | None |  |
| case_05 | ok | not finalized: critic_session_passes_incomplete | p1: 0.47 / 0.42 |
| case_06 | error | None |  |
| case_07 | ok | not finalized: critic_session_blockers_remain | p1: 0.35 / 0.36; p2: 0.32 / 0.36; p3: 0.32 / 0.36 |
| case_08 | ok | not finalized: critic_session_passes_incomplete | p1: 0.38 / 0.32 |
| case_09 | ok | not finalized: critic_session_blockers_remain | p1: 0.47 / 0.48; p2: 0.42 / 0.48; p3: 0.42 / 0.48 |
| case_10 | error | None |  |
| case_11 | ok | not finalized: critic_session_passes_incomplete | p1: 0.23 / 0.18 |
| case_12 | ok | not finalized: critic_session_passes_incomplete | p1: 0.24 / 0.18; p2: 0.17 / 0.18; p3: 0.17 / 0.18 |
| case_13 | ok | not finalized: critic_session_passes_incomplete | p1: 0.22 / 0.17 |
| case_14 | ok | not finalized: critic_session_validation_incomplete | p1: 0.54 / 0.39; p2: 0.37 / 0.34; p3: 0.42 / 0.39 |
| case_15 | error | None |  |
| case_16 | ok | not finalized: critic_session_validation_incomplete | p1: 0.25 / 0.18; p2: 0.25 / 0.18; p3: 0.17 / 0.18 |
| case_17 | ok | not finalized: critic_session_blockers_remain | p1: 0.45 / 0.46; p2: 0.34 / 0.46; p3: 0.33 / 0.46 |
| case_18 | ok | completed_with_findings | p1: 0.31 / 0.2; p2: 0.29 / 0.2; p3: 0.29 / 0.2 |
| case_19 | ok | not finalized: critic_session_blockers_remain | p1: 0.24 / 0.18; p2: 0.23 / 0.18; p3: 0.2 / 0.18 |
| case_20 | ok | not finalized: critic_session_passes_incomplete | p1: 0.3 / 0.19 |
| case_21 | ok | not finalized: critic_session_passes_incomplete | p1: 0.22 / 0.16; p2: 0.15 / 0.16; p3: 0.15 / 0.16 |
| case_22 | ok | not finalized: critic_session_validation_incomplete | p1: 0.28 / 0.25; p2: 0.21 / 0.25; p3: 0.21 / 0.25 |
| case_23 | ok | not finalized: critic_session_blockers_remain | p1: 0.19 / 0.16; p2: 0.14 / 0.16; p3: 0.14 / 0.16 |
| case_24 | ok | not finalized: critic_session_passes_incomplete | p1: 0.29 / 0.18; p2: 0.19 / 0.18; p3: 0.19 / 0.18 |
| case_25 | ok | completed_with_findings | p1: 0.16 / 0.11; p2: 0.11 / 0.11; p3: 0.11 / 0.11 |
| case_26 | ok | not finalized: critic_session_validation_incomplete | p1: 0.25 / 0.16; p2: 0.18 / 0.16; p3: 0.13 / 0.12 |
| case_27 | ok | not finalized: critic_session_validation_incomplete | p1: 0.55 / 0.49; p2: 0.31 / 0.3; p3: 0.3 / 0.3 |
| case_28 | ok | not finalized: critic_session_validation_incomplete | p1: 0.26 / 0.17; p2: 0.18 / 0.17; p3: 0.23 / 0.17 |
| case_29 | error | None |  |
| case_30 | ok | not finalized: critic_session_validation_incomplete | p1: 0.23 / 0.15; p2: 0.1 / 0.09; p3: 0.1 / 0.09 |

### Failed revisions

- case_01 1->failed after 1 fix attempt(s): serializer exited 1: luca", "kb:email-luca", "Holds_Account", assertion_id="D1.S2")
    ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^
- case_02 1->failed after 1 fix attempt(s): serializer exited 1: ojects/ProjectVIC/case-uco-graph-integrity/harness/results/qa-llm-v1/a1_critic/case_02/serializer_p
- case_03 1->failed after 1 fix attempt(s): serializer exited 1: graph-integrity/harness/results/qa-llm-v1/a1_critic/case_03/serializer_pass2.py", line 341, in <mod
- case_05 1->failed after 1 fix attempt(s): serializer exited 1: Traceback (most recent call last):
  File "/Users/mrinaalramachandran/Projects/ProjectVIC/case-uco-
- case_08 1->failed after 1 fix attempt(s): serializer exited 1: Traceback (most recent call last):
  File "/Users/mrinaalramachandran/Projects/ProjectVIC/case-uco-
- case_11 1->failed after 0 fix attempt(s): no code block
- case_13 1->failed after 1 fix attempt(s): serializer exited 1: IC/case-uco-graph-integrity/harness/results/qa-llm-v1/a1_critic/case_13/serializer_pass2.py", line 
- case_20 1->failed after 0 fix attempt(s): no code block

## value scorer

- revisions that produced a graph: 34; revisions whose serializer crashed even after fix attempts: 8
- gold triples fixed: 4, regressed: 47; mean recall 0.468 -> 0.451, mean precision 0.534 -> 0.449
- validity (SHACL conforms) before -> after: 14/34 -> 13/34
- unsupported triples by class, net change: wrong_value +0, wrong_relation +43, wrong_entity +0, cross_document_conflation +1, misplaced_property +1, duplicate_entity +20, invented +258

### Per rule addressed (a revision counts toward every rule it answered)

| rule | revisions | fixed | regressed | d_invented | d_wrong_relation | d_wrong_value |
|---|---|---|---|---|---|---|
| CRIT-G-DANGLING-REF | 2 | 0 | 0 | 27 | 0 | 0 |
| CRIT-H-ORPHAN-TOP-LEVEL | 34 | 4 | 47 | 258 | 43 | 0 |
| CRIT-H-RELATED-TO-OVERUSE | 2 | 0 | 0 | -19 | 0 | 0 |
| CRIT-S-PY-REL-ID-COLLAPSE | 13 | 0 | 2 | 150 | 2 | 0 |
| CRIT-V-NONCONFORMING | 20 | 4 | 26 | 147 | 22 | 0 |
| CRIT-V-RELATIONSHIP-LINT | 34 | 4 | 47 | 258 | 43 | 0 |
| investigation_structure | 9 | 0 | 22 | 71 | 22 | 0 |
| relationship_vocabulary | 12 | 4 | 28 | 100 | 24 | 0 |
| serializer_api | 2 | 0 | 2 | 17 | 2 | 0 |
| source_fidelity | 19 | 4 | 47 | 148 | 43 | 0 |

### Trajectory per case (pass: precision / recall)

| case | status | final outcome | passes |
|---|---|---|---|
| case_01 | ok | not finalized: critic_session_passes_incomplete | p1: 0.55 / 0.38 |
| case_02 | ok | not finalized: critic_session_passes_incomplete | p1: 0.61 / 0.34 |
| case_03 | ok | not finalized: critic_session_passes_incomplete | p1: 0.65 / 0.64 |
| case_04 | error | None |  |
| case_05 | ok | not finalized: critic_session_passes_incomplete | p1: 0.66 / 0.58 |
| case_06 | error | None |  |
| case_07 | ok | not finalized: critic_session_blockers_remain | p1: 0.7 / 0.72; p2: 0.64 / 0.72; p3: 0.64 / 0.72 |
| case_08 | ok | not finalized: critic_session_passes_incomplete | p1: 0.64 / 0.55 |
| case_09 | ok | not finalized: critic_session_blockers_remain | p1: 0.76 / 0.77; p2: 0.68 / 0.77; p3: 0.68 / 0.77 |
| case_10 | error | None |  |
| case_11 | ok | not finalized: critic_session_passes_incomplete | p1: 0.59 / 0.44 |
| case_12 | ok | not finalized: critic_session_passes_incomplete | p1: 0.6 / 0.44; p2: 0.42 / 0.44; p3: 0.42 / 0.44 |
| case_13 | ok | not finalized: critic_session_passes_incomplete | p1: 0.61 / 0.49 |
| case_14 | ok | not finalized: critic_session_validation_incomplete | p1: 0.64 / 0.46; p2: 0.45 / 0.41; p3: 0.5 / 0.46 |
| case_15 | error | None |  |
| case_16 | ok | not finalized: critic_session_validation_incomplete | p1: 0.69 / 0.49; p2: 0.69 / 0.49; p3: 0.47 / 0.49 |
| case_17 | ok | not finalized: critic_session_blockers_remain | p1: 0.71 / 0.72; p2: 0.53 / 0.72; p3: 0.52 / 0.72 |
| case_18 | ok | completed_with_findings | p1: 0.57 / 0.37; p2: 0.55 / 0.37; p3: 0.55 / 0.37 |
| case_19 | ok | not finalized: critic_session_blockers_remain | p1: 0.49 / 0.37; p2: 0.48 / 0.37; p3: 0.42 / 0.37 |
| case_20 | ok | not finalized: critic_session_passes_incomplete | p1: 0.57 / 0.35 |
| case_21 | ok | not finalized: critic_session_passes_incomplete | p1: 0.68 / 0.52; p2: 0.47 / 0.52; p3: 0.47 / 0.52 |
| case_22 | ok | not finalized: critic_session_validation_incomplete | p1: 0.61 / 0.53; p2: 0.45 / 0.53; p3: 0.45 / 0.53 |
| case_23 | ok | not finalized: critic_session_blockers_remain | p1: 0.53 / 0.44; p2: 0.39 / 0.44; p3: 0.38 / 0.44 |
| case_24 | ok | not finalized: critic_session_passes_incomplete | p1: 0.54 / 0.33; p2: 0.33 / 0.3; p3: 0.33 / 0.3 |
| case_25 | ok | completed_with_findings | p1: 0.46 / 0.32; p2: 0.32 / 0.32; p3: 0.32 / 0.32 |
| case_26 | ok | not finalized: critic_session_validation_incomplete | p1: 0.57 / 0.37; p2: 0.4 / 0.37; p3: 0.35 / 0.33 |
| case_27 | ok | not finalized: critic_session_validation_incomplete | p1: 0.71 / 0.62; p2: 0.38 / 0.36; p3: 0.37 / 0.36 |
| case_28 | ok | not finalized: critic_session_validation_incomplete | p1: 0.66 / 0.43; p2: 0.45 / 0.43; p3: 0.58 / 0.43 |
| case_29 | error | None |  |
| case_30 | ok | not finalized: critic_session_validation_incomplete | p1: 0.5 / 0.33; p2: 0.1 / 0.09; p3: 0.1 / 0.09 |

### Failed revisions

- case_01 1->failed after 1 fix attempt(s): serializer exited 1: luca", "kb:email-luca", "Holds_Account", assertion_id="D1.S2")
    ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^
- case_02 1->failed after 1 fix attempt(s): serializer exited 1: ojects/ProjectVIC/case-uco-graph-integrity/harness/results/qa-llm-v1/a1_critic/case_02/serializer_p
- case_03 1->failed after 1 fix attempt(s): serializer exited 1: graph-integrity/harness/results/qa-llm-v1/a1_critic/case_03/serializer_pass2.py", line 341, in <mod
- case_05 1->failed after 1 fix attempt(s): serializer exited 1: Traceback (most recent call last):
  File "/Users/mrinaalramachandran/Projects/ProjectVIC/case-uco-
- case_08 1->failed after 1 fix attempt(s): serializer exited 1: Traceback (most recent call last):
  File "/Users/mrinaalramachandran/Projects/ProjectVIC/case-uco-
- case_11 1->failed after 0 fix attempt(s): no code block
- case_13 1->failed after 1 fix attempt(s): serializer exited 1: IC/case-uco-graph-integrity/harness/results/qa-llm-v1/a1_critic/case_13/serializer_pass2.py", line 
- case_20 1->failed after 0 fix attempt(s): no code block
