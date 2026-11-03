# Faithfulness harness

Measures how faithfully an LLM turns source documents into a CASE/UCO graph,
against gold graphs we generate. The SDK and its MCP server are the object
under test; every results file records `git describe --tags`.

The case-uco MCP server has lookup and validation tools but no tools that
write nodes or relationships. Arm A2's write tools therefore live in the
harness, backed by the SDK's `case_uco.graph.CASEGraph`.

## Arms

A and B get the same task statement (`llm.SHARED`: model only what the documents state, the
core classes, the ten relation kinds); C gets the same classes and kinds as EDC's target schema.
Every arm reads the same PDFs (`[data] source` in `config.toml`; "marked" switches back to the
text files with sentence ids) at temperature 0. They differ in who writes the ontology. The
design is in [../EXPERIMENT.md](../EXPERIMENT.md).

- **A, SDK agent** (`pipeline_sdk_agent.py`, arm `a_sdk_agent`): a coding agent with the server's
  tools plus `read_file`, `write_serializer` (saves and runs the script) and `finish`, asked to
  follow the SDK's workflow including the critic loop (deterministic policy). The graph at the
  first `validate_graph` call is scored as `@first_validate`.
- **B, direct** (`pipeline_monolith.py`, arm `b_control`): one prompt, raw JSON-LD back.
- **C, EDC** (`pipeline_edc.py`, arm `c_edc`): EDC (the `edc/` submodule) in its target-alignment
  setting, one input per PDF sentence, canonicalizing to the CASE/UCO target schema
  (`target_schema.csv` in the arm folder); a serializer types the entity strings and writes the
  graph with the SDK. Per case: `edc/iter0/` (EDC's stage outputs), `llm_calls.jsonl` (every
  reply), `adapter_edges.json` (the edges the serializer wrote itself). The module docstring lists
  the two EDC fixes and the other adaptations.
- **Hook** (`hook.py --arm <arm>`): reads `results/<run_id>/<arm>/` and writes
  `results/<run_id>/<arm>+hook/`: the hooked `graph.jsonld`, `hook.jsonl` (one row per edge:
  triple, sentence, passages with location and verdict, verdict, cited passage) and `run.json`.
  Models in `[hook]`. `--template labels|plain` writes the ablation (definitions dropped; every
  ontology term dropped) to `<arm>+hook_labels` and `<arm>+hook_plain`.
- **Left and right hooks** (`hook.py --arm <arm> --stage left,right,both`): one model load, three
  outputs. `left` (`<arm>+left`) verifies the plain rendering, with `--passages block` and
  `--query plain` by default; `right` (`<arm>+right`) runs the right hook's checks (domain, range,
  datatype, cardinality, self-loop, contrast) on every edge; `both` (`<arm>+lr`) runs them on the
  edges `left` kept. `hook.jsonl` rows add `left` (kept, cited), `right` (each check's result and
  reason; null where it did not run), `contrast` (competitors and their entailment) and
  `removed_by`. The contrast margin is `contrast_margin` in `[hook]`. Without `--stage`, the hook
  above, unchanged. `--resume` skips finished cases, `--batch 8` halves the NLI batch,
  `HOOK_DEVICE` picks the device (default cuda, then mps, then cpu); a case that fails on the GPU
  is retried on the CPU and `run.json` records `hook_fallback`.

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
`docs/D*.marked.txt`, `docs/D*.pdf` and `spans.json`. `--out data_dev --seed 20260101`
and `--out data_train --seed 20260202` write the development and training sets; `--data` on any
pipeline picks the folder to run on. The benchmark folder is never used for tuning or training.

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
  precision and recall of 1.0, every gold assertion grounded in its own
  documents under both the clean and the PDF-extracted text, and a set of
  fabricated values not grounded. It first writes the PDF text caches a fresh
  clone lacks, and needs no MCP install.

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
- **Grounding** is scored for every emitted assertion without reference to
  gold: can it be found in the case's source text?
  - A literal is grounded when its normalized value occurs in one sentence.
    Times are matched by parsing the text's date spellings (a bare date is
    grounded by any time on that day); `eventType` and `accountType` by word
    containment, or `indirect` when the type's head noun shares a sentence
    with the subject ("account 2622357143 at Granite Federal Credit Union"
    grounds "bank account").
  - An entity is mentioned in every sentence where one of its literals occurs
    (any literal but `accountType`; an `eventType` also by two consecutive
    words of it), and grounded when it is mentioned anywhere.
  - A relation or object property is grounded at `sentence` level when both
    endpoints are mentioned in one sentence, at `document` level when in one
    document, and `indirect` when a Location is named by an entity the graph
    places there ("at Ironleaf's office").
  - Each assertion lands in one cell of grounded x gold-supported
    (`grounded_supported`, `grounded_unsupported`, `ungrounded_supported`,
    `ungrounded_unsupported`). `grounded_unsupported` is the traceable claim
    modeled wrong; `ungrounded_supported` should be near zero and lists the
    normalizer's gaps (`supported_ungrounded` in the per-case score).
  - Grounding is checked against `docs/D*.txt` (reported) and
    `docs/D*.pdf.txt`; `pdf_disagreements` counts assertions on which the two
    differ.
- **Hook:** an `<arm>+hook*` folder is scored like an arm, plus the edges the
  hook removed that gold supports in the graph it read (`hook_removed_true`),
  the share of the other edges removed (`hook_removed_false_rate`), and the
  kept true edges whose cited passage holds the gold triple's sentence from
  `spans.json` (`hook_cited_correct`). `<arm>+left`, `+right` and `+lr` add, per stage, the
  edges removed, the true ones among them, the unsupported ones by error class, and each right
  check's coverage (passed, failed, skipped).
- **Intervals:** each summary row has a 95% bootstrap interval over cases for micro precision and
  recall (`precision_micro_lo`/`_hi`, `recall_micro_lo`/`_hi`).
- **Dev runs:** `score.py --run-id RUN --data data_dev`. `hook_dev_check.py --run-id RUN --stages`
  checks the stages on dev gold and corrupted dev graphs with planted wrong-property and
  wrong-relation edges; `test_hook_stages.py` is the gate (see its docstring).
- **Adapter edges:** for an arm whose cases have `adapter_edges.json` (C),
  `<arm>@no_adapter` scores the same graph and alignment with those edges left
  out of every count.
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
