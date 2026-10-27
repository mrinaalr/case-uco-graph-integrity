# QA adjustments: qa-det-v1

Each row compares the graph before and after one serializer revision made in answer to the critic's findings. `fixed` and `regressed` count gold triples; `d_<class>` is the change in unsupported emitted triples of that class.


## strict scorer

- revisions that produced a graph: 22; revisions whose serializer crashed even after fix attempts: 8
- gold triples fixed: 1, regressed: 4; mean recall 0.262 -> 0.260, mean precision 0.277 -> 0.246
- validity (SHACL conforms) before -> after: 9/22 -> 9/22
- unsupported triples by class, net change: wrong_value +0, wrong_relation +0, wrong_entity +0, cross_document_conflation +0, misplaced_property +0, duplicate_entity +0, invented +184

### Per rule addressed (a revision counts toward every rule it answered)

| rule | revisions | fixed | regressed | d_invented | d_wrong_relation | d_wrong_value |
|---|---|---|---|---|---|---|
| CRIT-G-DANGLING-REF | 1 | 1 | 0 | 0 | 0 | 0 |
| CRIT-H-ORPHAN-TOP-LEVEL | 21 | 1 | 4 | 184 | 0 | 0 |
| CRIT-H-RELATED-TO-OVERUSE | 1 | 0 | 0 | 1 | 0 | 0 |
| CRIT-S-PY-REL-ID-COLLAPSE | 8 | 1 | 0 | 62 | 0 | 0 |
| CRIT-V-NONCONFORMING | 13 | 1 | 4 | 104 | 0 | 0 |
| CRIT-V-RELATIONSHIP-LINT | 22 | 1 | 4 | 184 | 0 | 0 |

### Trajectory per case (pass: precision / recall)

| case | status | final outcome | passes |
|---|---|---|---|
| case_01 | ok | not finalized: critic_session_passes_incomplete | p1: 0.23 / 0.19; p2: 0.14 / 0.14 |
| case_02 | error | None |  |
| case_03 | error | None |  |
| case_04 | error | None |  |
| case_05 | error | None |  |
| case_06 | error | None |  |
| case_07 | error | None |  |
| case_08 | error | None |  |
| case_09 | ok | not finalized: critic_session_validation_incomplete | p1: 0.46 / 0.45; p2: 0.41 / 0.45; p3: 0.41 / 0.45 |
| case_10 | error | None |  |
| case_11 | ok | not finalized: critic_session_passes_incomplete | p1: 0.22 / 0.18 |
| case_12 | ok | completed_with_findings | p1: 0.24 / 0.18; p2: 0.2 / 0.18; p3: 0.22 / 0.18 |
| case_13 | ok | not finalized: critic_session_passes_incomplete | p1: 0.18 / 0.14 |
| case_14 | ok | not finalized: critic_session_validation_incomplete | p1: 0.4 / 0.39; p2: 0.31 / 0.39; p3: 0.31 / 0.39 |
| case_15 | ok | not finalized: critic_session_passes_incomplete | p1: 0.36 / 0.29 |
| case_16 | ok | not finalized: critic_session_validation_incomplete | p1: 0.51 / 0.48; p2: 0.51 / 0.48; p3: 0.38 / 0.48 |
| case_17 | ok | not finalized: critic_session_passes_incomplete | p1: 0.41 / 0.46 |
| case_18 | ok | completed_with_findings | p1: 0.25 / 0.2; p2: 0.16 / 0.2; p3: 0.16 / 0.2 |
| case_19 | ok | completed_with_findings | p1: 0.24 / 0.26; p2: 0.23 / 0.26; p3: 0.23 / 0.26 |
| case_20 | ok | completed_with_findings | p1: 0.3 / 0.19; p2: 0.2 / 0.19; p3: 0.2 / 0.19 |
| case_21 | error | None |  |
| case_22 | ok | not finalized: critic_session_validation_incomplete | p1: 0.28 / 0.25; p2: 0.22 / 0.25; p3: 0.22 / 0.25 |
| case_23 | ok | not finalized: critic_session_passes_incomplete | p1: 0.22 / 0.17 |
| case_24 | ok | not finalized: critic_session_passes_incomplete | p1: 0.21 / 0.14; p2: 0.23 / 0.16 |
| case_25 | ok | not finalized: critic_session_validation_incomplete | p1: 0.17 / 0.14; p2: 0.14 / 0.14; p3: 0.14 / 0.14 |
| case_26 | error | None |  |
| case_27 | ok | not finalized: critic_session_passes_incomplete | p1: 0.2 / 0.15 |
| case_28 | ok | not finalized: critic_session_validation_incomplete | p1: 0.22 / 0.19; p2: 0.2 / 0.19; p3: 0.2 / 0.19 |
| case_29 | error | None |  |
| case_30 | error | None |  |

### Failed revisions

- case_01 2->failed after 0 fix attempt(s): no code block
- case_11 1->failed after 1 fix attempt(s): serializer exited 1: s/ProjectVIC/case-uco-graph-integrity/harness/results/qa-det-v1/a1_critic/case_11/serializer_pass2.
- case_13 1->failed after 1 fix attempt(s): serializer exited 1: Traceback (most recent call last):
  File "/Users/mrinaalramachandran/Projects/ProjectVIC/case-uco-
- case_15 1->failed after 1 fix attempt(s): serializer exited 1: n/Projects/ProjectVIC/case-uco-graph-integrity/harness/results/qa-det-v1/a1_critic/case_15/serializ
- case_17 1->failed after 1 fix attempt(s): serializer exited 1: Traceback (most recent call last):
  File "/Users/mrinaalramachandran/Projects/ProjectVIC/case-uco-
- case_23 1->failed after 1 fix attempt(s): serializer exited 1: Traceback (most recent call last):
  File "/Users/mrinaalramachandran/Projects/ProjectVIC/case-uco-
- case_24 2->failed after 1 fix attempt(s): serializer exited 1: /case-uco-graph-integrity/harness/results/qa-det-v1/a1_critic/case_24/serializer_pass3.py", line 16
- case_27 1->failed after 0 fix attempt(s): no code block

## value scorer

- revisions that produced a graph: 22; revisions whose serializer crashed even after fix attempts: 8
- gold triples fixed: 2, regressed: 5; mean recall 0.517 -> 0.515, mean precision 0.554 -> 0.495
- validity (SHACL conforms) before -> after: 9/22 -> 9/22
- unsupported triples by class, net change: wrong_value +0, wrong_relation +1, wrong_entity +0, cross_document_conflation +0, misplaced_property +1, duplicate_entity +1, invented +179

### Per rule addressed (a revision counts toward every rule it answered)

| rule | revisions | fixed | regressed | d_invented | d_wrong_relation | d_wrong_value |
|---|---|---|---|---|---|---|
| CRIT-G-DANGLING-REF | 1 | 1 | 0 | 0 | 0 | 0 |
| CRIT-H-ORPHAN-TOP-LEVEL | 21 | 2 | 5 | 179 | 1 | 0 |
| CRIT-H-RELATED-TO-OVERUSE | 1 | 0 | 0 | 1 | 0 | 0 |
| CRIT-S-PY-REL-ID-COLLAPSE | 8 | 1 | 0 | 62 | 0 | 0 |
| CRIT-V-NONCONFORMING | 13 | 1 | 5 | 101 | 1 | 0 |
| CRIT-V-RELATIONSHIP-LINT | 22 | 2 | 5 | 179 | 1 | 0 |

### Trajectory per case (pass: precision / recall)

| case | status | final outcome | passes |
|---|---|---|---|
| case_01 | ok | not finalized: critic_session_passes_incomplete | p1: 0.51 / 0.41; p2: 0.36 / 0.35 |
| case_02 | error | None |  |
| case_03 | error | None |  |
| case_04 | error | None |  |
| case_05 | error | None |  |
| case_06 | error | None |  |
| case_07 | error | None |  |
| case_08 | error | None |  |
| case_09 | ok | not finalized: critic_session_validation_incomplete | p1: 0.72 / 0.7; p2: 0.63 / 0.7; p3: 0.63 / 0.7 |
| case_10 | error | None |  |
| case_11 | ok | not finalized: critic_session_passes_incomplete | p1: 0.57 / 0.44 |
| case_12 | ok | completed_with_findings | p1: 0.59 / 0.44; p2: 0.5 / 0.44; p3: 0.55 / 0.44 |
| case_13 | ok | not finalized: critic_session_passes_incomplete | p1: 0.56 / 0.43 |
| case_14 | ok | not finalized: critic_session_validation_incomplete | p1: 0.67 / 0.64; p2: 0.52 / 0.64; p3: 0.52 / 0.64 |
| case_15 | ok | not finalized: critic_session_passes_incomplete | p1: 0.71 / 0.56 |
| case_16 | ok | not finalized: critic_session_validation_incomplete | p1: 0.76 / 0.72; p2: 0.76 / 0.72; p3: 0.56 / 0.72 |
| case_17 | ok | not finalized: critic_session_passes_incomplete | p1: 0.72 / 0.72 |
| case_18 | ok | completed_with_findings | p1: 0.55 / 0.44; p2: 0.37 / 0.45; p3: 0.37 / 0.45 |
| case_19 | ok | completed_with_findings | p1: 0.62 / 0.67; p2: 0.58 / 0.67; p3: 0.58 / 0.67 |
| case_20 | ok | completed_with_findings | p1: 0.57 / 0.35; p2: 0.37 / 0.35; p3: 0.37 / 0.35 |
| case_21 | error | None |  |
| case_22 | ok | not finalized: critic_session_validation_incomplete | p1: 0.61 / 0.53; p2: 0.48 / 0.53; p3: 0.48 / 0.53 |
| case_23 | ok | not finalized: critic_session_passes_incomplete | p1: 0.59 / 0.45 |
| case_24 | ok | not finalized: critic_session_passes_incomplete | p1: 0.47 / 0.32; p2: 0.49 / 0.33 |
| case_25 | ok | not finalized: critic_session_validation_incomplete | p1: 0.47 / 0.36; p2: 0.38 / 0.36; p3: 0.37 / 0.35 |
| case_26 | error | None |  |
| case_27 | ok | not finalized: critic_session_passes_incomplete | p1: 0.62 / 0.47 |
| case_28 | ok | not finalized: critic_session_validation_incomplete | p1: 0.57 / 0.48; p2: 0.51 / 0.48; p3: 0.51 / 0.48 |
| case_29 | error | None |  |
| case_30 | error | None |  |

### Failed revisions

- case_01 2->failed after 0 fix attempt(s): no code block
- case_11 1->failed after 1 fix attempt(s): serializer exited 1: s/ProjectVIC/case-uco-graph-integrity/harness/results/qa-det-v1/a1_critic/case_11/serializer_pass2.
- case_13 1->failed after 1 fix attempt(s): serializer exited 1: Traceback (most recent call last):
  File "/Users/mrinaalramachandran/Projects/ProjectVIC/case-uco-
- case_15 1->failed after 1 fix attempt(s): serializer exited 1: n/Projects/ProjectVIC/case-uco-graph-integrity/harness/results/qa-det-v1/a1_critic/case_15/serializ
- case_17 1->failed after 1 fix attempt(s): serializer exited 1: Traceback (most recent call last):
  File "/Users/mrinaalramachandran/Projects/ProjectVIC/case-uco-
- case_23 1->failed after 1 fix attempt(s): serializer exited 1: Traceback (most recent call last):
  File "/Users/mrinaalramachandran/Projects/ProjectVIC/case-uco-
- case_24 2->failed after 1 fix attempt(s): serializer exited 1: /case-uco-graph-integrity/harness/results/qa-det-v1/a1_critic/case_24/serializer_pass3.py", line 16
- case_27 1->failed after 0 fix attempt(s): no code block
