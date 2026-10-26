# case-uco-graph-integrity

An experiment that measures how faithfully an LLM turns source documents into
CASE/UCO knowledge graphs, against gold graphs we generate and control. The
object under test is the [CASE/UCO SDK](https://github.com/vulnmaster/CASE-UCO-SDK)
and its MCP server, pinned as a submodule at `sdk/`.

Three arms get the same documents and prompt, and differ only in how the graph
gets written:
- **A1 script:** the model writes a `CASEGraph` serializer.
- **A2 tools:** the model writes through tool calls, with the SDK's MCP server for lookup and validation.
- **B control:** the model emits raw JSON-LD.

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
.venv/bin/python harness/pipeline_monolith.py --run-id RUN --model tinker
```

```bash
.venv/bin/python harness/pipeline_script.py --run-id RUN --model tinker
```

```bash
.venv/bin/python harness/pipeline_sdk.py --run-id RUN --model tinker
```

```bash
.venv/bin/python harness/score.py --run-id RUN
```

```bash
.venv/bin/python harness/edges.py --run-id RUN
```

- Results go to `harness/results/RUN/`. Only `baseline-v1`'s summaries are tracked.
- `--cases case_01,case_02` runs a subset.
- `harness/generate_data.py --validate` regenerates the 30 gold cases.

## Frozen evaluation

Scores are comparable only under the same freeze entry in
[harness/FROZEN.md](harness/FROZEN.md). It holds the SHA-256 hashes of
`score.py`, `generate_data.py`, `graphkit.py` and every `gold.json`. No change
to any of them without a new freeze entry (date, reason, hashes), and runs
scored under different entries are not compared.
