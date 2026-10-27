# Faithfulness harness

Measures how faithfully an LLM turns source documents into a CASE/UCO graph,
against gold graphs we generate. The SDK and its MCP server are the object
under test; every results file records `git describe --tags`.

The case-uco MCP server has lookup and validation tools but no tools that
write nodes or relationships. Arm A2's write tools therefore live in the
harness, backed by the SDK's `case_uco.graph.CASEGraph`.

## Arms

Every arm gets the same task statement (`llm.SHARED`: model only what the documents state, the
core classes, the ten relation kinds), the same PDFs (`[data] source` in `config.toml`; "marked"
switches back to the text files with sentence ids) and temperature 0. They differ in who writes
the ontology. The A/B/C design is in [../EXPERIMENT.md](../EXPERIMENT.md).

- **A, SDK agent** (`pipeline_sdk_agent.py`, arm `a_sdk_agent`): a coding agent with the server's
  tools plus `read_file`, `write_serializer` (saves and runs the script) and `finish`, asked to
  follow the SDK's workflow including the critic loop (deterministic policy). The graph at the
  first `validate_graph` call is scored as `@first_validate`.
- **B, direct** (`pipeline_monolith.py`, arm `b_control`): one prompt, raw JSON-LD back.
- **C, compiled** (`pipeline_compiled.py`, arm `c_compiled`): per-document claim extraction with
  quotes, a deterministic verifier with one repair round (`[compiled] repair_rounds`), cross-document
  entity resolution by key, and a compiler that writes the graph with `GraphWriter`. `claims.json`
  keeps every admitted claim and the entity mapping; `run.json` counts claims, rejections and repairs.

Earlier arms, still runnable:

- **A1 script** (`pipeline_script.py`): the model writes one `CASEGraph` script, run with a timeout.
- **A1+QA** (`pipeline_critic.py`, arm `a1_critic`): A1, then the server's critic session with the
  findings fed back for `critic.rounds` revisions (`CRITIC_POLICY=disabled|manual`); every pass is
  scored as `a1_critic@passN`.
- **A2 tools** (`pipeline_sdk.py`): harness write tools `add_node`, `add_facet`, `add_relationship`,
  `finish` with the server's lookup tools and up to 2 repair rounds.

## Data

`generate_data.py` writes 100 seeded fraud / business-communication cases to
`data/case_NN/`: `gold.json`, `gold.jsonld`, `docs/D*.txt`,
`docs/D*.marked.txt`, `docs/D*.pdf` and `spans.json`.

- The gold graph is authored first, then rendered to 2-4 documents from
  templates with paraphrase pools.
- Every non-type triple sits in exactly one span. An entity counts as stated
  at its first full mention; later mentions are references.
- `--validate` runs `case_validate` on each gold graph. Generation also checks
  that each gold graph converts back to exactly its gold triples.
- Bank accounts are core `Account` + `AccountFacet` with `accountIssuer`,
  because `FinancialAccount` is a CAC class.

## Run

From the repo root, using the SDK venv with `openai` and `scipy` installed:

```bash
.venv/bin/python harness/generate_data.py --validate
```

```bash
.venv/bin/python harness/smoke.py
```

```bash
.venv/bin/python harness/pipeline_script.py --run-id baseline --model ollama
```

```bash
.venv/bin/python harness/pipeline_sdk.py --run-id baseline --model ollama
```

```bash
.venv/bin/python harness/pipeline_monolith.py --run-id baseline --model ollama
```

```bash
CRITIC_POLICY=disabled .venv/bin/python harness/pipeline_critic.py --run-id baseline --model ollama
```

```bash
.venv/bin/python harness/score.py --run-id baseline
```

```bash
.venv/bin/python harness/qa_delta.py --run-id baseline
```

- `--cases case_01,case_02` runs a subset.
- Per-case outputs go to `results/<run_id>/<arm>/<case>/` (gitignored).
- `results/<run_id>/` gets `summary.md`, `summary.csv` and `per_case.csv`.
- `qa_delta.py` compares consecutive critic passes of `a1_critic`: gold
  triples fixed and regressed by each revision, unsupported triples by class,
  attributed to the rules the model was asked to address (`qa_delta.md`, `qa_delta.csv`).
- `score.py --self-test` scores each gold graph against itself and expects
  precision and recall of 1.0.

## Scoring

- **Triples:** Relationship nodes become `(source, kind, target)`, and facet
  properties attach to their owner. Type triples and annotation properties
  (`description`, `body`, ...) are not scored.
- **Alignment:** one-to-one, using the Hungarian method (scipy) over key
  similarity between class-compatible pairs, with threshold 0.85. Alignment
  rates are reported both ways, next to the invented count.
- **Error classes,** checked in this order:
  - `wrong_value`: the subject and property match gold, but the literal differs.
  - `wrong_relation`: the same pair is linked in gold by a different kind or
    in the other direction.
  - `wrong_entity`: the property and one endpoint match a gold fact, and the
    substitute entity appears in that fact's document.
  - `cross_document_conflation`: as above, but the substitute only appears in
    other documents; or an entity merged with another; or a link between
    entities that never share a document.
  - `invented`: everything else, including unaligned endpoints.
- **Stages (A2):** `write_node`, `write_facet`, `write_relationship`, `repair`
  (written after a failed validation) and `final_only`. A1 and B are
  `generation`.
- **Passes (A1+QA):** `a1_critic@pass1` is the graph before any QA, `@passN`
  the graph after revision N-1, and `a1_critic` the final graph. The per-pass
  `valid` column is the critic's SHACL result for that pass.
- **Failures:** `error` and `empty` runs count as zero recall and are listed
  separately. `incomplete` runs are scored but flagged.
- **wall_s** includes the final validation. A2's first-validation row reuses
  the whole run's tokens and wall time.
