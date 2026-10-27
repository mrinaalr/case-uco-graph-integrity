# Evidence-Grounded Graph Construction: Evaluating Reliability and Fidelity in CASE/UCO Representations

Written 2026-10-27. Supersedes the arm layout in DIRECTION.md; the critic-loop findings there stand.

## The problem

Modeling evidence as a CASE/UCO graph is slow by hand and unreliable by machine. When a language
model does it, the graph is valid more often than it is true: in the baseline runs the best method
got six in ten of its statements right. The goal is to make graph construction from documents
easier and trustworthy enough to use, and to measure what moves it.

## The benchmark

100 generated cases, each a fraud or business-communication scenario with a gold graph authored
first and then rendered into 2 to 4 documents (memo, email, chat export, incident report). Every
gold triple is stated in exactly one sentence. Each document is a PDF with no annotations; the
methods receive the PDFs and nothing else about the case. Gold graphs validate under
`case_validate`. The scorer aligns the produced graph to gold entity by entity and classes every
unsupported statement (wrong value, wrong relation, wrong entity, conflation across documents,
misplaced property, duplicate entity, invented). Scores are comparable only under the same
freeze entry (`harness/FROZEN.md`, Freeze 4).

## The methods

All arms get the same task statement (`llm.SHARED`: model only what the documents state, the core
classes to use, the ten relation kinds), the same PDFs and the same base model. They differ in who
writes the ontology and what checks what. B1 to B4 are a 2x2 factorial (training x defenses) on
direct generation; A is the engineering baseline; C is the architecture under test.

| arm | pipeline | status |
|---|---|---|
| A, the SDK as shipped | `pipeline_sdk_agent.py`, arm `a_sdk_agent` | built, running |
| B1, direct, raw | `pipeline_monolith.py`, arm `b_control` (alias `b1_raw`) | built, running |
| B2, direct, trained | `pipeline_monolith.py --model trained --arm b2_trained` | placeholder: training data built, LoRA not trained |
| B3, direct, raw + defenses | `pipeline_defended.py`, arm `b3_defended` | built, running |
| B4, direct, trained + defenses | `pipeline_defended.py --model trained --arm b4_trained_defended` | placeholder, as B2 |
| C v1, grounded claims, compiled | `pipeline_compiled.py`, arm `c_compiled` | built, running (single-shot reader; ablation of C) |
| C v2, evidence-grounded compilation | `pipeline_grounded.py`, arm `c_grounded` | built, running (the method) |

**A. The SDK as shipped.** A coding agent with the SDK's MCP server follows the SDK's own
workflow: read the evidence, route it and look up classes and recipes, write a serializer with
`CASEGraph`, validate, run the critic loop (deterministic policy), finalize. The harness contributes
a file reader, a "save and run this script" tool, and nothing in the graph. The graph at the
agent's first validation is also scored (`@first_validate`).

**B1. Direct generation.** One prompt, the CASE JSON-LD back. No tools, no repair.

**B2. Trained.** B1 with a LoRA of the same base model, fine-tuned on 200 generated training
cases (`data_train`, seed 20260202; `make_training_set.py` builds the pairs) that share no case
with the benchmark. `train_lora.py` holds the training plan; the Tinker training call is not
implemented yet, so this arm is a placeholder until the checkpoint exists.

**B3. Defenses.** B1, then a fixed, documented set of guards, each snapshotted and scored on its
own: a parse retry, the SDK validator's report sent back for a rewrite (up to 2 rounds), and the
SDK's deterministic critic findings sent back for a rewrite (1 round). The defenses never add to
the graph; every version is a model reply. (`@raw`, `@validated`, final.)

**B4. Trained + defenses.** B3 on the B2 checkpoint. Placeholder until B2 exists.

**C. Evidence-grounded graph compilation.** The model never writes ontology. In one sentence:
*the model extracts quoted facts, a verifier keeps only the ones the text supports, and a compiler
turns them into CASE/UCO; we test whether separating reading from modeling, and enforcing
provenance at construction time, makes the graph more faithful than letting the model model.*

Hypothesis: separating evidence extraction from ontology mapping, and enforcing provenance at
graph-construction time, reduces unsupported assertions and incorrect relationships without
sacrificing useful coverage.

C v2 (`pipeline_grounded.py`) has five stages, PDF in, graph out, every assertion auditable:

1. *Extract.* Per document, the model lists the entities it names (with a quote each), then the
   attributes and relations among those entities (with a quote each). Two calls, so relations
   cannot cite entities that were never declared.
2. *Admit.* A deterministic gate: the quote is in the document, the value is in the quote, the
   relation kind is in the vocabulary, the endpoints are declared. Rejected claims go back once
   with the reasons, then stay rejected.
3. *Resolve.* Entities merge across documents by normalized key (first-name references attach to
   the one matching full name). Each admitted claim maps to its ontology construct from a rule
   table and the SDK schema: class, object-or-facet placement and typed range for a property,
   Relationship node with kind for a relation. A relation stated against the kind's direction is
   normalized; one whose endpoint types do not fit the kind is left unresolved, not forced.
4. *Compile.* Resolved assertions are written with the SDK.
5. *Gate.* The graph is validated; assertions on violating nodes are quarantined and the graph
   compiled again once.

Nothing is dropped silently: rejected, unresolved, quarantined and failed assertions sit in the
ledger with status `needs_review`. `ledger.jsonl` has one row per assertion with its passage,
claim, mapping, checks and status; `run.json` carries the counts and the review-queue size.

C v1 (`pipeline_compiled.py`) is the single-shot version (one reader call per document, no
domain/range resolution, no ledger, no gate) and serves as the ablation.

Why C is shaped this way: the baseline error analysis showed that most of what the model gets
wrong is modeling, not reading. Of A1's unsupported statements, 58% were the right value on the
right entity under the wrong property, and most of the rest were unanchored or invented nodes. A
compiler cannot misplace a property, and a verifier cannot admit a value the text does not
contain. The model is left with the part it is good at.

## Data splits

- `data/`: the 100 benchmark cases (seed 20251025). Test only.
- `data_dev/`: 20 cases (seed 20260101) for prompt and pipeline tuning.
- `data_train/`: 200 cases (seed 20260202) for B2/B4 training pairs.

## Measures

Per method, over 100 cases: precision and recall against gold (strict and value scorers), SHACL
validity, unsupported statements by error class, failures (no graph), cost (tokens, wall time).
For A, the same before and after its QA loop. For C, how many claims the verifier rejected and
how many came back admitted after the repair round.

## Paper

Title: *Evidence-Grounded Graph Construction: Evaluating Reliability and Fidelity in CASE/UCO
Representations*. Two questions: which existing approach produces the most reliable graphs (A
versus B1 to B4), and whether a different construction architecture improves reliability beyond
training or defending a model (C). Reliability is validity and failure rate; fidelity is precision
and recall against gold with the error-class breakdown; for C, the review-queue size is the cost
of the gate.

## Results

Filled in from `harness/results/abc-v1/` when the runs finish.
