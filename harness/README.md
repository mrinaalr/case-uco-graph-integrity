# Faithfulness harness

Measures how faithfully an LLM turns source documents into a CASE/UCO graph,
against gold graphs we generate. The SDK and its MCP server are the object
under test; every results file records `git describe --tags`.

The case-uco MCP server has lookup and validation tools but no tools that
write nodes or relationships. Arm A2's write tools therefore live in the
harness, backed by the SDK's `case_uco.graph.CASEGraph`.

## Arms

Every arm gets the same documents with sentence ids, class list, JSON-LD
example, 10-relation vocabulary with directions, and temperature 0
(`llm.SHARED`). The arms differ only in how the graph gets written and which
tools are available.

- **A1 script** (`pipeline_script.py`): the model writes a Python script that
  uses `CASEGraph`. The harness runs it with a timeout, then calls the server's
  `validate_graph` (no repair). This executes model-written code locally.
- **A2 tools** (`pipeline_sdk.py`): `add_node`, `add_facet`,
  `add_relationship` and `finish` are backed by `CASEGraph`, alongside the
  server's lookup tools and `validate_graph`, with up to 2 repair rounds. A2 is
  scored at its first validation (`a2_tools@first_validate`) and at the end.
- **B control** (`pipeline_monolith.py`): one prompt and raw JSON-LD back, with
  no tools and no repair.

Every arm's final graph is checked with `case_validate --allow-info`. The
harness starts its own server copy with `CASE_UCO_EXTENSIONS=legalproc,cryptoinv`.
Endpoints are defined under `[models]` in `config.toml`; pick one per run with
`--model` (default `ollama`). API keys go in `harness/.env` (gitignored), named
by each entry's `api_key_env`; an entry's `extra_body` is sent with every request.

## Data

`generate_data.py` writes 30 seeded fraud / business-communication cases to
`data/case_NN/`: `gold.json`, `gold.jsonld`, `docs/D*.txt`,
`docs/D*.marked.txt` and `spans.json`.

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
.venv/bin/python harness/score.py --run-id baseline
```

- `--cases case_01,case_02` runs a subset.
- Per-case outputs go to `results/<run_id>/<arm>/<case>/` (gitignored).
- `results/<run_id>/` gets `summary.md`, `summary.csv` and `per_case.csv`.
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
- **Failures:** `error` and `empty` runs count as zero recall and are listed
  separately. `incomplete` runs are scored but flagged.
- **wall_s** includes the final validation. A2's first-validation row reuses
  the whole run's tokens and wall time.
