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
gold supports (true edges removed), and for each kept true edge whether its cited passage is the
sentence gold states it in. For C, the same without the serializer's own edges. Grounding, without
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

Filled in when the runs finish.
