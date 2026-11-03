<h1 align="center">Evidence-Grounded Graph Construction</h1>
<h3 align="center">Evaluating the Semantic Fidelity of Machine-Constructed CASE/UCO Graphs</h3>

<p align="center">
  <em>Data in. Graphs out. True to the source.</em>
</p>

<p align="center">
  <a href="#the-problem">Problem</a> ·
  <a href="#the-hook">Hook</a> ·
  <a href="#the-methods">Methods</a> ·
  <a href="#how-we-benchmark">Benchmark</a> ·
  <a href="#run-it">Run it</a> ·
  <a href="#whats-next">What's next</a>
</p>

---

## The problem

Making graphs that represent concepts from data is hard. Making knowledge graphs that faithfully reflect digital evidence is even harder.

When a language model turns case documents into [CASE](https://caseontology.org/)/[UCO](https://unifiedcyberontology.org/) graphs, the graphs can be *valid* (they pass the ontology's SHACL checks) without being ***correct***. A graph can be well-formed in every way the ontology can check and still represent things the documents never said.

This repo presents a backward verification hook: every edge of a finished graph is checked against the source documents and kept only if a source passage supports it. The hook is tested on three construction methods to determine whether verification improves the reliability and semantic fidelity of CASE/UCO graphs. Here those terms mean:

- **Reliability**: does the method produce a graph at all, and does the graph validate?
- **Semantic fidelity**: do the assertions in the graph trace to the source material, and does the graph, interpreted under CASE/UCO's definitions, mean what the evidence means?


Every method is benchmarked the same way, with and without the hook, using the same PDF documents, base model, and scorer against gold graphs we author ourselves, and therefore know completely.

The graph builders under test are Cory Hall's [CASE/UCO SDK](https://github.com/vulnmaster/CASE-UCO-SDK); direct generation by the base model, Qwen3.5-9B; and [EDC](https://github.com/clear-nus/edc).

## The hook

`harness/hook.py` works backward from a finished graph to the source, one edge at a time. It is the same for every method and uses no LLM; its two models are pinned in `harness/config.toml`: all-MiniLM-L6-v2 for retrieval and DeBERTa-v3-large NLI (MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli).

1. **Render**: each edge becomes one sentence, from a template filled with the CASE/UCO definitions of its classes and property (from the SDK's registry).
2. **Retrieve**: the sentence is embedded, and the 3 most similar source passages (sentences of the PDFs) are taken.
3. **Verify**: a local NLI model labels each (passage, sentence) pair as supported, contradicted, or not enough evidence.
4. **Keep or remove**: the edge stays if any passage supports it, citing that passage and its location; otherwise it is removed.

One sentence of evidence, from an incident summary (benchmark case_18, document D2):

> Account 2622357143 at Granite Federal Credit Union belongs to Summit Peak Packaging Inc.

states four edges of the gold graph:

```mermaid
flowchart LR
    O[Summit Peak Packaging Inc.<br/>Organization] -->|Owns_Account| A[2622357143<br/>Account]
    A -->|accountIssuer| B[Granite Federal Credit Union<br/>Organization]
    A -.->|accountIdentifier| I["2622357143"]
    A -.->|accountType| T["bank account"]
```

The issuer edge, in parts:

```
Claim:  The account issuer of 2622357143 is Granite Federal Credit Union.
Where:  2622357143 is an Account (an arrangement with an entity to enable and control the provision of some capability or service).
        Granite Federal Credit Union is an Organization (a grouping of identifying characteristics unique to a group of people who work together in an organized way for a shared purpose).
        "account issuer" is accountIssuer (the issuer of this account).
```

The sentence NLI reads (`hook.render`, full template):

```
The account issuer (the issuer of this account) of 2622357143, an account (an arrangement with an entity to enable and control the provision of some capability or service), is Granite Federal Credit Union, an organization (a grouping of identifying characteristics unique to a group of people who work together in an organized way for a shared purpose).
```

**Hypothesis.** Checking each edge backward against the source removes unsupported edges from any method's graph at a small cost in true edges.

## The methods

Every method gets the same task (the core classes; ten relation kinds), the same PDFs, and the same base model at temperature 0. A and B get the task as one statement (model only what the documents state); C gets it as EDC's target schema. The methods differ in how the graph is constructed. Each graph is scored with and without the hook: three arms by {baseline, +hook}, six conditions.

| arm | name | how the graph is constructed |
|---|---|---|
| **A** | SDK as shipped | the model writes a serializer script with the SDK, then revises it in the critic loop |
| **B** | direct | the model, in one reply |
| **C** | EDC | EDC extracts open triples, defines their relations, and canonicalizes them to the CASE/UCO schema |

### A. The SDK as shipped

A coding agent gets the SDK's MCP server tools plus a file reader and a "save and run this script" tool, and is asked to follow the SDK's documented workflow. The harness adds nothing to the graph; every node comes from the serializer the agent wrote.

```mermaid
flowchart LR
    PDF[PDF evidence] --> AG[Coding agent]
    AG -->|route, guide_mapping,<br/>search_classes, recipes| MCP[(SDK MCP server)]
    AG -->|write_serializer| SER[serializer.py<br/>CASEGraph]
    SER --> G1[graph.jsonld]
    G1 -->|validate_graph| MCP
    G1 -->|start_critic_review| CR[Critic loop<br/>deterministic checks]
    CR -->|findings| AG
    AG -->|revise, submit_critic_revision| SER
    CR -->|finalize| OUT[final graph]
```

`harness/pipeline_sdk_agent.py`, arm `a_sdk_agent`. The graph at the agent's first validation is also scored (`@first_validate`), so the QA loop's effect is visible.

### B. Direct generation

The model reads the documents and writes the CASE JSON-LD in one reply. No tools, no repair.

`harness/pipeline_monolith.py`, arm `b_control`.

### C. EDC

[EDC](https://aclanthology.org/2024.emnlp-main.548) (Extract, Define, Canonicalize; Zhang and Soh, 2024) in its target-alignment setting: open triples from each input, a definition for each relation, then each relation canonicalized to a target schema by embedding retrieval and an LLM choice. The target schema is the task in CASE/UCO terms: the ten relation kinds, and `Class.property` for each task property, defined from the SDK's registry. Each PDF sentence is one input. EDC does not type entities, so a thin serializer types each entity string from the domain and range of its relations and writes the graph with the SDK.

```mermaid
flowchart LR
    PDF[PDF sentences] --> OIE[Extract<br/>open triples]
    OIE --> SD[Define<br/>each relation]
    SD --> SC[Canonicalize<br/>to the CASE/UCO schema]
    SC --> SER[Serializer<br/>type entities<br/>write with the SDK]
    SER --> OUT[graph]
```

`harness/pipeline_edc.py`, arm `c_edc`; EDC is the submodule at `edc/`. C is also scored without the edges its serializer writes itself (`c_edc@no_adapter`). [EXPERIMENT.md](EXPERIMENT.md) lists every adaptation.

## How we benchmark

**100 cases, gold first.** Each case is a fraud or business-communication scenario. The gold graph is authored by a seeded generator, then rendered into 2 to 4 documents (memo, email, chat export, incident report) in which every gold statement is spoken in exactly one sentence. Each document is a PDF with no annotations. The methods receive the PDFs and nothing else.

**Scoring.** The scorer aligns the produced graph to gold entity by entity, counts supported statements, and classes every unsupported one: wrong value, wrong relation, wrong entity, conflation across documents, misplaced property, duplicate entity, invented. Strict and value-tolerant scores are both reported. Failures (no graph) count as zero recall. For a +hook condition, the scorer also counts the true edges the hook removed and checks each kept true edge's cited passage against the sentence that states it in gold.

**Grounding.** Separately, and without reference to gold, the scorer checks whether each assertion can be found in the source: a literal by its value in a sentence, a relation by its two endpoints in one sentence or one document. Every assertion falls into one cell of grounded by gold-supported. The grounded-but-unsupported cell holds the claims a method traced to the evidence and still modeled wrong.

**Frozen protocol.** `harness/FROZEN.md` hashes the scorer, the generator, every gold graph and every pipeline. Scores are comparable only between runs under the same entry.

**Splits.** `harness/data/` is the benchmark and is test only. `harness/data_dev/` (20 cases) is for prompt and pipeline tuning. Different seeds, no shared case.

**Per-stage rows.** A snapshot a pipeline leaves (`graph_<stage>.jsonld`) is scored as `<arm>@<stage>`, hooked graphs as `<arm>+hook`.

```mermaid
flowchart LR
    GEN[generate_data.py<br/>seeded gold graph] --> GOLD[gold.jsonld]
    GEN --> DOCS[docs: txt + PDF]
    DOCS --> A & B & C
    A & B & C --> GR[graph.jsonld per case]
    GR --> HK[hook.py<br/>keep supported edges]
    DOCS --> HK
    HK --> GH[graph.jsonld per case, +hook]
    GR & GH --> SC[score.py<br/>align, class every error]
    GOLD --> SC
    SC --> SUM[summary.md · per_case.csv]
```

## Run it

```bash
git clone --recurse-submodules https://github.com/mrinaalr/case-uco-graph-integrity.git && cd case-uco-graph-integrity
```

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Put API keys in `harness/.env` (gitignored), named by `api_key_env` in `harness/config.toml`; the default endpoint is Tinker's OpenAI-compatible API serving Qwen3.5-9B.

```bash
.venv/bin/python harness/pipeline_sdk_agent.py --run-id RUN --model tinker
```

```bash
.venv/bin/python harness/pipeline_monolith.py --run-id RUN --model tinker
```

```bash
.venv/bin/python harness/pipeline_edc.py --run-id RUN --model tinker
```

```bash
for arm in a_sdk_agent b_control c_edc; do .venv/bin/python harness/hook.py --run-id RUN --arm $arm; done
```

```bash
.venv/bin/python harness/score.py --run-id RUN
```

- `--cases case_01,case_02` runs a subset; `--data data_dev` runs on the dev set.
- Results go to `harness/results/RUN/`; `summary.md` has the per-arm table. The hook writes `<arm>+hook/` next to each arm and downloads its two models on first use.
- `harness/generate_data.py --validate` regenerates the benchmark and its PDFs.
- [harness/README.md](harness/README.md) documents every arm, the data, and the scorer in detail.

## What's next

- Run C and its hook on the 100 cases to complete the six conditions; A and B with the hook are in `harness/results/hook-v1/`.
- Passages that span an email header block, so header facts can be checked.
- An adversarial set: the same 100 cases with one injected attack per case (instruction, false fact, format, tool) and an "injected" error class in the scorer, to measure which method lets poisoned evidence into the graph and which leaves a trail to it.
- Tests with fixtures and mocked model replies, starting with the one that matters: an edge the hook removes cannot reach the hooked graph.

## Limitations

The cases are synthetic. They test mechanics and known failure modes; they do not establish fidelity on real case documents, which needs independently reviewed source-to-claim annotations. One base model so far.

The hook checks that a passage supports an edge, not that the edge is true: a false statement physically in a document passes, though every kept edge cites the passage that supports it. Support is also weaker than role: in hook-v1 the hook kept all 16 issuer edges from A and B that named the account's owner, because the passage names both organizations. And it reads one sentence at a time, so a true fact spread over lines, as in an email header, is removed.

## History

[DIRECTION.md](DIRECTION.md) records the study of the SDK's critic loop that led here, and [EXPERIMENT.md](EXPERIMENT.md) the design of this experiment. `harness/findings/` holds the SDK findings sent upstream.