# Evidence-Grounded Graph Construction: Evaluating the Semantic Fidelity of Machine-Constructed CASE/UCO Graphs

Written 2026-10-27, revised 2026-11-02 for the hook design. Supersedes the arm layout in DIRECTION.md; the critic-loop findings there stand.

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
freeze entry (`harness/FROZEN.md`).

## The design

This repo presents a backward verification hook and tests it on three construction methods. Each
method runs as shipped; the hook reads each method's graphs and is the same for all of them.
Three arms by {baseline, +hook} gives six conditions, on the same 100 cases, PDFs and base model
(Qwen/Qwen3.5-9B on Tinker, temperature 0).

| arm | pipeline | conditions |
|---|---|---|
| A, the SDK as shipped | `pipeline_sdk_agent.py`, arm `a_sdk_agent` | `a_sdk_agent`, `a_sdk_agent+hook` |
| B, direct generation | `pipeline_monolith.py`, arm `b_control` | `b_control`, `b_control+hook` |
| C, EDC | `pipeline_edc.py`, arm `c_edc` | `c_edc`, `c_edc+hook` |

A and B get the same task statement (`llm.SHARED`: model only what the documents state, the core
classes to use, the ten relation kinds). C gets EDC's own prompts, with the same classes and
relation kinds as its target schema.

**A. The SDK as shipped.** A coding agent with the SDK's MCP server follows the SDK's own
workflow: read the evidence, route it and look up classes and recipes, write a serializer with
`CASEGraph`, validate, run the critic loop (deterministic policy), finalize. The harness contributes
a file reader, a "save and run this script" tool, and nothing in the graph. The graph at the
agent's first validation is also scored (`@first_validate`).

**B. Direct generation.** One prompt, the CASE JSON-LD back. No tools, no repair.

**C. EDC.** EDC (Zhang and Soh, 2024) at clear-nus/edc 02aad17, in its target-alignment setting
with its default prompt templates and few-shot examples, no refinement and no schema enrichment.
Per input it extracts open triples, writes a definition for each relation, and canonicalizes each
relation to the target schema: the five most similar schema relations by embedding, then an LLM
choice among them or none. The target schema is the task in CASE/UCO terms: the ten relation
kinds, and `Class.property` for each property of the task classes, each defined from the SDK
registry. Each PDF sentence is one input; EDC leaves chunking to its user. EDC does not type
entities, so a serializer types each entity string by the domain and range of its relations
(most votes, ties to the first), treats identical strings as one entity, writes the string as the
entity's key property (`name`, `addressValue`, `accountIdentifier`, ...), and writes the graph
with the SDK.

## The hook

`hook.py`, applied to every arm's final graph:

1. *Render.* Each edge (each scored triple) becomes one sentence from a template filled with the
   CASE/UCO definitions of its classes and property, from the SDK registry. No LLM. A relation
   reads `S, <class S>, <phrase> O, <class O>.`; a property reads
   `The <property> (<definition>) of S, <class S>, is <value>.`, with ISO date-times in words. A
   subject whose label holds the asserted value is named by its class alone, so no sentence says
   "the name of X is X".
2. *Retrieve.* The sentence is embedded and the top 3 source passages are taken. Passages are the
   sentences of the PDFs the arms read, with document, sentence number and character offsets.
3. *Verify.* A local NLI model labels each (passage, sentence) pair supported (entailment),
   contradicted (contradiction) or not enough evidence (neutral).
4. *Policy.* The edge is kept if any passage supports it, citing the one with the highest
   entailment probability; otherwise it is removed, as its Relationship node or as its value on
   the node and the node's facets.

Per edge, `hook.jsonl` records the triple, the sentence, the three passages with their locations
and verdicts, the edge's verdict and the cited passage. The hook is deterministic apart from its
two models, pinned in `[hook]` of `config.toml`: sentence-transformers/all-MiniLM-L6-v2 at
1110a24 for retrieval, MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli at b3546ea for
NLI.

Hypothesis: checking each edge backward against the source, under CASE/UCO's definitions, removes
unsupported edges from any method's graph at a small cost in true edges.

Ablation: the same hook on the same graphs with the definitions taken out. `labels` keeps the class
and property names (`Oscar Banerjee, a person, is employed by Redfern Components Group, an
organization.`); `plain` keeps no ontology term (`Oscar Banerjee is employed by Redfern Components
Group.`). Scored as `<arm>+hook_labels` and `<arm>+hook_plain`. If the definitions do work, the full
template removes more unsupported edges than `labels` and `plain` at no greater cost in true edges.

## Left hook and right hook

Written 2026-11-03, before any run of the two stages. The hook above (hook-v1) put the definitions in
the NLI hypothesis, which no passage contains, and cannot catch the right value under the wrong
property, since that value is in the text. It is split in two, applied in order:

- *Left hook (fidelity).* Steps 2 to 4 on the plain rendering (no class or property definitions),
  with mail-header runs as one passage and retrieval by the plain rendering. Per edge: supported,
  contradicted or not enough evidence, and the cited passage and its location. Unsupported edges
  are removed.
- *Right hook (semantics)*, on the edges the left hook kept. Deterministic checks from the SDK's
  schema and registry (domain, range, datatype, cardinality; the ten relation kinds' domain and
  range from the task statement, since CASE/UCO does not define them; no self-loops), each
  reporting the edges it judged and skipped. Then contrast: the edge must not be outranked on its
  supporting passage by another reading the ontology allows for the same entities, with the
  definitions of the readings in the premise, never in the hypothesis. The margin is tuned on
  `data_dev` only.

Conditions: each arm as built, `+left`, `+right` (on every edge, for ablation) and `+lr`.

Hypothesis: the two stages together remove unsupported and mis-modeled edges from any method's
graph at a small cost in true edges, and the right hook adds a gain the left hook alone does not.

Success criteria:

- The right hook removes wrong-property (`misplaced_property`) and wrong-relation edges the left
  hook keeps.
- Little or no added cost in true edges, and no drop in citation accuracy.
- Left+right beats left alone on value precision for every arm.

## Related work

- [SPIRES](https://doi.org/10.1093/bioinformatics/btae104) (Caufield et al., 2024) has an LLM fill
  a user-defined schema from text and links what it extracts to ontology identifiers; it grounds
  terms in an ontology, where the hook grounds edges in the source text.
- [EDC](https://aclanthology.org/2024.emnlp-main.548) (Zhang and Soh, 2024) is arm C: it
  canonicalizes extracted relations forward to a schema, where the hook checks each finished edge
  backward against the source.
- [GraphRAG](https://arxiv.org/abs/2404.16130) (Edge et al., 2024) builds an entity graph from text
  with an LLM as an index for query-focused summarization; its graph serves retrieval, not a record
  that must be true to the source.
- [Text2KGBench](https://arxiv.org/abs/2308.02357) (Mihindukulasooriya et al., 2023) benchmarks
  ontology-driven graph generation from text against gold facts, with measures of ontology
  conformance and hallucination; this benchmark does the same for CASE/UCO, with each gold
  statement tied to the sentence that states it.

## Disclosures

- The relation phrases are author-written. CASE/UCO does not define the ten relation kinds, so the
  hook's template says each kind with a phrase written for this repo (`RELATION_PHRASES` in
  `graphkit.py`; `Employed_By` is "is employed by", `Holds_Account` is "holds"). C's target schema
  defines each kind with the same phrase.
- C's embedder is swapped. EDC's default, intfloat/e5-mistral-7b-instruct (14 GB), does not fit the
  machine the runs use; C uses the hook's all-MiniLM-L6-v2. EDC accepts any sentence transformer.
- C runs with two fixes in its adapter; the submodule is unchanged. `edc_framework.py:270` logs a
  variable that is unset when a run's first input yields no triples, so EDC raised
  `UnboundLocalError`; before the fix, a probe of each benchmark case's first sentence found about
  12 of 100 cases that would crash. The base model often
  replies with tuples, `[('a', 'b', 'c')]`, which EDC's parser drops whole; before the fix 22.3% of
  input sentences were lost this way and 31.8% yielded no triples, after it 9.5% (148 sentences,
  6 test cases). The other adaptations: LLM calls go to the harness endpoint, an empty reply is
  read as no choice, and a schema-retriever training module EDC does not call here is stubbed.
- C's serializer writes edges EDC does not state: each entity's class, and its name or identifier
  taken from the entity string. Each case lists them (`adapter_edges.json`), and C is also scored
  without them (`c_edc@no_adapter`: the same alignment, those edges left out of every count).
- Header limitation. Gold states each email header fact on its own line (`Date: ...` for
  `sentTime`, `To: ...` for `to` and `Communicated_With`), and the line names neither the message
  nor the sender, so no single-sentence passage entails the edge. The hook removes many of these
  true edges.
- Dev ceiling. On 8 dev gold graphs (613 edges, all true) the hook keeps 88.7%. The losses are
  `Communicated_With` (23% kept), `sentTime` (29%), `to` (35%) and `Located_At` (65%; gold states
  these indirectly, "took place at the Stonebridge Services Group office"); every other property
  keeps more than 80%.
- The NLI model keeps an edge from an entity to itself ("x holds x") whenever a passage names it:
  all 3 such edges from C in testing. A false positive the hook does not catch.
- Some registry definitions read wrong for this use, and the hook uses them as written:
  `observable:from` and `observable:to` on an email message are defined as a phone number.
- A and B are not rerun: their abc-v1 outputs (Freeze 5) are scored here. The pipelines are
  byte-identical, the prompt and document text are the same, and every run used SDK v1.33.0 and
  Qwen/Qwen3.5-9B. C runs fresh.

## Data splits

- `data/`: the 100 benchmark cases (seed 20251025). Test only.
- `data_dev/`: 20 cases (seed 20260101) for prompt and pipeline tuning.
- `data_train/`: 200 cases (seed 20260202), unused in this design.

## Measures

Per condition, over 100 cases: precision and recall against gold (strict and value scorers),
validation pass rate (`case_validate`), unsupported statements by error class, failures (no
graph), cost (tokens, wall time). For each +hook condition: the edges removed, how many of them
gold supports (true edges removed), the share of unsupported edges removed, and for each kept true
edge whether its cited passage is the sentence gold states it in. For C, the same without the serializer's own edges. Grounding, without
reference to gold: the share of emitted assertions found in the source text, and the grounded x
gold-supported cells. For A, the graph at its first validation too.

## Paper

Title: *Evidence-Grounded Graph Construction: Evaluating the Semantic Fidelity of Machine-Constructed
CASE/UCO Graphs*. Two questions: does a backward, ontology-grounded check on the finished graph
make it more faithful to the source, whichever method built it (A, B, C), and what does it cost in
true edges. Reliability is validity and failure rate; fidelity is precision and recall against the
gold graph with the error-class breakdown; for the hook, true edges removed and citation
correctness.

## Results

C's 100-case run is not done yet.

Ablation, run hook-v1 (Freeze 6): the hook and its two ablation templates on the 100 abc-v1
graphs of A and B. Precision and recall are micro. The hook columns (true and unsupported edges
removed, kept true edges citing the gold sentence) are under the strict scorer.

| condition | valid | P strict | R strict | P value | R value | true removed | unsupported removed | cite correct |
|---|---|---|---|---|---|---|---|---|
| A | 35 | 0.371 | 0.139 | 0.506 | 0.184 | | | |
| A+hook | 39 | 0.376 | 0.108 | 0.547 | 0.153 | 17.5% | 26.7% | 75.1% |
| A+hook_labels | 38 | 0.339 | 0.103 | 0.520 | 0.154 | 15.3% | 20.9% | 82.9% |
| A+hook_plain | 40 | 0.358 | 0.100 | 0.550 | 0.150 | 17.4% | 29.5% | 78.0% |
| B | 91 | 0.270 | 0.219 | 0.595 | 0.476 | | | |
| B+hook | 93 | 0.277 | 0.191 | 0.632 | 0.432 | 10.1% | 16.4% | 66.8% |
| B+hook_labels | 93 | 0.264 | 0.180 | 0.634 | 0.428 | 12.5% | 17.2% | 77.9% |
| B+hook_plain | 93 | 0.268 | 0.181 | 0.631 | 0.422 | 12.9% | 18.1% | 68.1% |

The hook trades recall for precision, by a few points. With the full template, value precision
rises 4.2 points on A and 3.7 on B, recall falls 3.1 and 4.4, and 4 more A graphs and 2 more B
graphs validate. It separates unsupported from true edges only weakly: it removes 26.7% of A's
unsupported edges and 17.5% of its true ones (B: 16.4% and 10.1%).

The definitions show no consistent effect. `plain` removes more unsupported edges than the full
template on both arms (29.5% against 26.7% on A, 18.1% against 16.4% on B), at the same cost in
true edges on A and a higher one on B. The full template has the highest strict precision on both
arms and keeps the most true edges on B. The precision gaps between templates are under 4 points,
from one run with no significance test. The definitions lower citation accuracy: with class and property names but no
definitions, 82.9% (A) and 77.9% (B) of kept true edges cite the gold sentence, against 75.1% and
66.8% with them.

On this benchmark, this NLI model and this embedder, the effect comes from checking each edge
backward against the source, not from the CASE/UCO definitions in the sentence.

### Left and right hooks

Six conditions on the 100 cases: pending the GPU run.

Dev, under Freeze 9 (contrast margin 2.0 in log-odds, chosen on dev case_01 to case_10): the 20 dev gold
graphs, `hook_dev_check.py`'s corrupted copies with planted wrong-property and wrong-relation edges, and C's
graphs on 5 dev cases. Value scorer; intervals are the bootstrap 95% over cases. Each cell is `+left` / `+lr`.

| sample | P value | R value | true edges removed by the right hook | planted wrong property kept | planted wrong relation kept | kept true citing gold | valid |
|---|---|---|---|---|---|---|---|
| dev gold | 0.987 / 0.985 | 0.924 / 0.913 | 14 of 1,459 | | | 86.4% / 86.2% | 20 / 20 |
| dev corrupted | 0.822 (0.807-0.838) / 0.928 (0.914-0.943) | 0.621 / 0.611 | 14 of 981 | 59 / 20 of 80 | 94 / 10 of 202 | 80.0% / 79.8% | 0 / 15 |
| C, 5 dev cases | 0.651 (0.532-0.776) / 0.670 (0.552-0.800) | 0.186 / 0.170 | 2 of 62 | | | 65.8% / 64.9% | 1 / 5 |

The left hook keeps 93.6% of the true dev gold edges. An entity with no literal of its own (a gold email
account) is named by the address it links to; named by its IRI, the left hook kept 83.4%. The account's
`emailAddress` edge then reads close to a tautology and is checked only weakly.

The right hook removes most of the planted edges the left hook keeps: every accountIdentifier written as a name,
street written as locality, Employed_By and Located_At reversed; 19 of 20 Initiated written as Authorized; 17 of
20 owners written as issuers; 15 of 21 swapped senders and recipients. It removes none of the 20 sentTimes
written as receivedTime: the NLI model does not separate the two on a `Date:` line. On C it removes malformed
times (`13:10:00` as a dateTime), a person typed against Employed_By's domain and an inverted Holds_Account, and
two true address parts that contrast reads as the locality; one of those is a Location's street, its alignment
key, so the scorer loses its other edges too, which is most of C's drop in recall. Of 2,575 edges the right hook
keeps, 1 cites a different passage than the left hook; the small drops in citation accuracy come from which true
edges it removes.

### Rendering audit

The hook's NLI step can only separate readings its sentences separate. A dev-only diagnostic, run after the dev
results above with no success criterion set beforehand (`rendering_audit.py`, Freeze 10): for each true dev gold
edge with a confusable reading, the plain sentence of the edge and of the competitor, scored against the passage
that states the edge with the right hook's premise. Margin is log-odds(true) - log-odds(competitor); the right hook
removes a true edge below -2.

| true | competitor | n | true ranked higher | median margin | margin < -2 |
|---|---|---|---|---|---|
| sentTime | receivedTime | 39 | 0/39 | -0.92 | 0 |
| accountIssuer | Owns_Account | 56 | 46/56 | +4.40 | 3 |
| Owns_Account | accountIssuer | 40 | 40/40 | +2.04 | 0 |
| Initiated | Participated_In | 114 | 93/114 | +1.21 | 0 |
| Initiated | Authorized | 114 | 114/114 | +3.15 | 0 |
| Authorized | Initiated | 9 | 9/9 | +6.55 | 0 |
| Authorized | Participated_In | 9 | 9/9 | +2.50 | 0 |
| Participated_In | Initiated | 17 | 17/17 | +13.51 | 0 |
| Participated_In | Authorized | 17 | 17/17 | +10.51 | 0 |
| Holds_Account | Owns_Account | 93 | 93/93 | +6.75 | 0 |
| Reports_To | Communicated_With | 8 | 8/8 | +1.13 | 0 |
| Reports_To | Reports_To reversed | 8 | 8/8 | +8.08 | 0 |
| Communicated_With | Reports_To | 53 | 53/53 | +9.21 | 0 |
| Communicated_With | Reports_To reversed | 53 | 53/53 | +10.66 | 0 |
| Transferred_To | Transferred_To reversed | 3 | 3/3 | +10.87 | 0 |

NLI ranks receivedTime above sentTime on every `Date:` line, by a small margin; this is why the right hook keeps
every planted receivedTime. The line does not say "sent", and the definitions in the premise do not settle it. The
ten issuers ranked below Owns_Account are all on "account N at Bank X is registered to Person". The Initiated
losses are on "started the ...", which entails participating, so the competitor is not a wrong reading. The other
relation kinds separate by wide margins. Employed_By and Located_At have no competing reading the task allows and
are not tested.
