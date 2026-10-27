# case-uco-graph-integrity

An experiment that measures how faithfully an LLM turns source documents into
CASE/UCO knowledge graphs, against gold graphs we generate and control. The
object under test is the [CASE/UCO SDK](https://github.com/vulnmaster/CASE-UCO-SDK)
and its MCP server, pinned as a submodule at `sdk/`.

The experiment is an A/B/C comparison of three ways to build the graph from the same PDF
documents, described in [EXPERIMENT.md](EXPERIMENT.md):
- **A, the SDK as shipped:** a coding agent with the SDK's MCP server follows the SDK's workflow
  (route, look up classes and recipes, write a `CASEGraph` serializer, validate, critic loop).
- **B1 to B4, direct generation:** the model emits CASE JSON-LD in one reply; a 2x2 of
  training (a LoRA on generated training cases) and defenses (validator and critic reports sent
  back for rewrites). B2 and B4 are placeholders until the LoRA is trained.
- **C, evidence-grounded graph compilation:** the model extracts quoted facts per document, a
  verifier keeps the ones the text supports, a resolver maps them to ontology constructs, and a
  deterministic compiler writes the graph with the SDK; everything not asserted sits in a review ledger.

Earlier arms (A1 script, A1+QA, A2 tools) remain runnable; [DIRECTION.md](DIRECTION.md) has what
they showed about the SDK's critic loop.

Details are in [harness/README.md](harness/README.md).

The SDK's MCP server can look up classes and validate graphs, but it has no
tools that write nodes or relationships. Arm A2's write tools therefore live in
the harness, backed by the SDK's own `case_uco.graph.CASEGraph`.

## Setup

```bash
git clone --recurse-submodules <this repo> && cd case-uco-graph-integrity
```

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Put API keys in `harness/.env`, which is gitignored; for example
`TINKER_API_KEY=...` for the `tinker` endpoint in `harness/config.toml`.
`git -C sdk describe --tags` should print the pinned SDK tag (`v1.33.0`).

## Run and score

```bash
.venv/bin/python harness/smoke.py
```

```bash
.venv/bin/python harness/pipeline_sdk_agent.py --run-id RUN --model tinker
```

```bash
.venv/bin/python harness/pipeline_monolith.py --run-id RUN --model tinker
```

```bash
.venv/bin/python harness/pipeline_defended.py --run-id RUN --model tinker
```

```bash
.venv/bin/python harness/pipeline_grounded.py --run-id RUN --model tinker
```

```bash
.venv/bin/python harness/score.py --run-id RUN
```

```bash
.venv/bin/python harness/rule_coverage.py --run-id RUN
```

- Results go to `harness/results/RUN/`. Only the summaries of the tracked runs are in git.
- `--cases case_01,case_02` runs a subset.
- `harness/generate_data.py --validate` regenerates the 100 gold cases and their PDFs.

## Frozen evaluation

Scores are comparable only under the same freeze entry in
[harness/FROZEN.md](harness/FROZEN.md). It holds the SHA-256 hashes of
`score.py`, `generate_data.py`, `graphkit.py` and every `gold.json`. No change
to any of them without a new freeze entry (date, reason, hashes), and runs
scored under different entries are not compared.
