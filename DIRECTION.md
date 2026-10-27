# Direction: serializer faithfulness and what the QA loop does to it

Written 2026-10-27, after Cory Hall's note on the repo README.

## Where this comes from

Cory Hall is the author of the CASE/UCO SDK under test (the `vulnmaster` GitHub account; every
commit in `sdk/` is his) and a long-standing member of the CASE/UCO community, presenting the
ontologies at DFRWS and AAFS since 2019. Eoghan Casey co-created CASE in 2014 with DC3 and MITRE,
sits on the DFRWS board, created SOLVE-IT, and wrote the standard digital-evidence textbook. Cory
says this repo's measurements could complete a paper he started with Casey earlier this year, and
that a possible job depends on a grant with a lot of competition. The experiment is therefore being
pointed at the question Cory asked, in the SDK's own workflow, with results he can cite.

His recommendation, quoted: study "the faithfulness of the custom serializer generation and
adjustments the QA checks have on it." In the SDK that workflow is explicit (README, "AI-Assisted
Development"): the originating agent builds a serializer and a graph through MCP discovery and
routing, then a critic loop (`start_critic_review`, `submit_critic_revision`,
`finalize_critic_review`) reviews one immutable graph/serializer version at a time with
deterministic SHACL, coverage, heuristic and serializer-AST checks before any model critique.

## Why steer, and what changes

The baseline already measures serializer generation: arm A1 is exactly that, with no discovery and
no QA. Arm A2 (tool-call writes) is not the SDK's workflow; the SDK has no write tools, and A2's
write tools are ours. So A2 stops being a headline arm and becomes a reference point. A1 is the
object of study, and the QA loop is the treatment.

Three facts from the SDK make the treatment worth measuring rather than assuming:

- The critic's scorecard has a `source_fidelity` dimension and a `source_fidelity` finding
  category, but no deterministic rule produces either. On every baseline A1 graph the dimension
  comes back `assessed: false`. Faithfulness to the source is the one thing the QA loop cannot see,
  and the one thing this harness measures against gold.
- On the baseline A1 graphs the deterministic critic fires three rules: `CRIT-H-ORPHAN-TOP-LEVEL`
  on every node (there is no Investigation or Bundle root), `CRIT-V-RELATIONSHIP-LINT` on every
  relationship (none of the ten gold relation kinds is in the UCO relationship vocabularies), and
  `CRIT-S-PY-REL-ID-COLLAPSE` on the serializer. The first two ask for structural changes the gold
  does not contain; the lint in particular pushes the model away from the relation vocabulary the
  task requires. Whether answering them costs faithfulness is an empirical question.
- A2's repair rounds, the closest thing in the baseline to a QA adjustment, raised recall in 11 of
  30 cases and lowered precision in 3. Under the strict scorer the repair stage introduced 71
  unsupported triples. Validation-driven fixes can add errors; the same may hold for critic-driven ones.

## Research questions

1. **RQ1 Serializer faithfulness.** How faithful is the bare generated serializer (A1), per error
   class and per stage, and how does it compare with raw JSON-LD (B) as the control?
2. **RQ2 QA adjustment.** When the SDK's critic findings go back to the originating model and it
   rewrites the serializer, what happens to precision, recall, validity and each error class, pass
   by pass? Which rules' findings fix gold triples, and which regress them?
3. **RQ3 Model critique.** Does adding the LLM as the critic (policy `manual`, from the server's
   prompt package) change the answer to RQ2, and does its `source_fidelity` assessment track the
   measured faithfulness?
4. **RQ4 Fixing at the source.** Which measured error classes could a deterministic source-fidelity
   rule catch (a proposed `CRIT-F-*` family: cited span absent, literal not in cited span, entity
   merged across documents, relation kind outside the task vocabulary), and how much would it have
   changed RQ2?

## Arms

| arm | file | what it measures |
|---|---|---|
| A1 script | `pipeline_script.py` | bare serializer generation (RQ1) |
| A1+QA deterministic | `pipeline_critic.py`, policy `disabled` | the SDK's deterministic critic loop on A1 (RQ2) |
| A1+QA with LLM critic | `pipeline_critic.py`, policy `manual` | the full critic loop, the model also critiques (RQ3) |
| B control | `pipeline_monolith.py` | raw JSON-LD, no SDK |
| A2 tools | `pipeline_sdk.py` | reference only |

A1+QA is scored at every pass: `a1_critic@pass1` is the bare A1 graph, `@pass2` the graph after
revision 1, and so on; `a1_critic` is the final graph. `qa_delta.py` compares consecutive passes
and attributes fixed and regressed gold triples to the rules the model was asked to address.

## Plan of attack

1. Build the A1+QA arm on the real MCP critic session, snapshot every pass, score every pass. Done.
2. Run both policies over all 30 cases on the baseline model (Qwen3.5-9B via Tinker) under a new
   freeze entry. Done: `qa-det-v1` and `qa-llm-v1` (Freeze 3).
3. Read the deltas: by rule, by error class, by pass. Done, see Results below.
4. Draft the source-fidelity rules (RQ4) as findings in `harness/findings/`, each with the measured
   error it would have caught, in the form the SDK's critic expects. Drafted
   (`critic-source-fidelity-unassessed.md`); `rule_coverage.py` measures their reach. Repro cases
   and reference implementations are next.
5. Add guided generation (routing and recipes before the serializer is written) as a second
   treatment, if the QA numbers leave room to attribute gains to it.
6. Write the results up for Cory and Casey: per-arm tables, per-rule delta table, the three SDK
   findings (unassessed source fidelity, relationship-lint conflict with task vocabularies,
   relationship-id collapse), and the proposed rules.

## What to send Cory now

- The summary table from `baseline-v1` for A1 and B, and the critic probe result: three rules fire,
  `source_fidelity` unassessed.
- The design above, so the arms match the workflow he described before more runs are spent.

## Results (2026-10-27, Qwen3.5-9B via Tinker, Freeze 3)

Full tables: `harness/results/qa-det-v1/` and `harness/results/qa-llm-v1/` (`summary.md`,
`qa_delta.md`, `rule_coverage.md`). All deltas below compare consecutive passes of the same case
within one run, because the endpoint is not deterministic at temperature 0 across runs.

**RQ2, deterministic critic (policy `disabled`).** 18 of 30 cases produced a running serializer
(12 crashed even after one traceback round). The critic fired `CRIT-V-RELATIONSHIP-LINT` 1,401
times and `CRIT-H-ORPHAN-TOP-LEVEL` 880 times across all passes, `CRIT-V-NONCONFORMING` 24 times,
and three other rules a handful of times. 22 revisions ran; 8 more crashed even after a fix
attempt. Over the 22 (value scorer): 2 gold triples fixed, 5 regressed, mean recall 0.517 to
0.515, mean precision 0.554 to 0.495, 179 invented triples added, SHACL validity unchanged at 9 of
22. No case ended with zero open findings; 4 finalized as `completed_with_findings`.

**RQ3, LLM as critic (policy `manual`).** 25 of 30 cases ran. The model's critic replies added
249 `source_fidelity` findings and scored source fidelity 1 to 3 of 5 on every pass. 34 revisions
ran, 8 crashed. Over the 34: 4 gold triples fixed, 47 regressed, mean recall 0.468 to 0.451, mean
precision 0.534 to 0.449, 258 invented and 43 wrong-relation triples added, validity 14 to 13 of
34. Revisions answering the model's own `source_fidelity` findings account for 47 of the 47
regressions. The critic that can see the source made the graph less faithful to it.

**Reading.** On this model, the QA loop as shipped moves neither validity nor faithfulness in the
right direction. Two of its rules fire on every node and every relationship of every graph and ask
for structure the task does not contain, so each revision is a rewrite under noise; the rewrite
adds invented triples (a root Investigation, Bundle and Relationship nodes the gold has no place
for) and, with the LLM critic, renames relation kinds. The serializer itself is fragile: 20 of 56
revision attempts crashed, and 17 of 60 initial generations.

**RQ4.** Six deterministic rules computable from the graph and the documents would have flagged
82% of the unsupported triples in both runs' final graphs (69% in `baseline-v1` A1). Of the rules
the critic actually ran, none targets any of those triples.

**What this says for the paper.** Serializer faithfulness is measurable and mostly deterministic
to check; the current critic checks structure and vocabulary instead, and feeding those findings
back costs precision. The fix at the source is a source-fidelity rule family in the critic, a way
to declare the task's relation vocabulary, and the validator's messages in the session record.
