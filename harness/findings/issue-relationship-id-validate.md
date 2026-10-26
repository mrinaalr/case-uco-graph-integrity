# create_relationship output fails CASEGraph.validate() but passes MCP validate_graph

## What happens

A graph built only through the SDK's own API fails one SDK validation path and passes the other. `CASEGraph.create_relationship` mints relationship IRIs of the form `kb:rel-<kind>-<12 hex>`, which UCO reports at `sh:Info` because they do not end in a UUID. `CASEGraph.validate()` raises `RuntimeError` on that result, while the MCP server's `validate_graph` reports the same file as conforming. This was found during a faithfulness-harness run against the SDK.

## Minimal repro

From the repo root, with case-utils installed and `case_validate` on PATH:

```python
# repro.py  (run: PYTHONPATH=python python repro.py)
from case_uco.graph import CASEGraph

a = "kb:person-7f9c2a3e-1b4d-4c6e-9a8f-0d1e2f3a4b5c"
b = "kb:org-2c4e6a8b-3d5f-4a7c-8e9f-1a2b3c4d5e6f"
g = CASEGraph()
g.upsert_node(a, types="uco-identity:Person", properties={"uco-core:name": "A"})
g.upsert_node(b, types="uco-identity:Organization", properties={"uco-core:name": "B"})
print(g.create_relationship(a, b, "Employed_By")["@id"])  # kb:rel-Employed_By-127f1809d1d7
g.write("repro.jsonld")
try:
    g.validate()
    print("CASEGraph.validate(): passed")
except RuntimeError as exc:
    print("CASEGraph.validate(): RuntimeError:", str(exc).splitlines()[0])
```

```bash
case_validate repro.jsonld
case_validate --allow-info repro.jsonld
PYTHONPATH=python:mcp_server python -c "import json, server; print(json.dumps(server.validate_graph('repro.jsonld')))"
```

The last command calls the same function the MCP `validate_graph` tool exposes, with its defaults.

| Validator | Command | Result | Finding |
|---|---|---|---|
| case_validate default | `case_validate repro.jsonld` | `Conforms: False`, exit 1 | One result: `sh:Info`, focus node `kb:rel-Employed_By-127f1809d1d7`, "UcoThings are suggested to end with a UUID." |
| case_validate --allow-info | `case_validate --allow-info repro.jsonld` | `Conforms: True`, exit 0 | None |
| CASEGraph.validate() | `g.validate()` | `RuntimeError: Validation failed` | Same Info result. The method runs `case_validate --built-version <v>` and raises on any non-zero exit (`python/case_uco/graph.py:582-584`). Its only parameter is `case_version`. |
| MCP validate_graph | `validate_graph(graph_path="repro.jsonld")` | `conforms: true`, 0 warnings, 0 violations | None. With the default `allow_warning=True` it passes `--allow-warning` (`python/case_uco/validation/graph.py:497-498`), under which Warning and Info results do not affect conformance. |

## Environment

- SDK: v1.33.0 (`git describe --tags`)
- Commit: a2dc8bc96f5001c58af63e587593dbf6385b24cf (main)
- Python: 3.13.9
- case-utils: 0.18.0 (pyshacl 0.40.1), built version case-1.5.0 (UCO 1.5.0)
- OS: macOS (Darwin 25.2.0)

## Notes

- The relationship ID is deterministic by design: the hex is the first 12 characters of a SHA-256 of source, target and kind (`python/case_uco/graph.py:1381-1388`).
- All four language SDKs mint the same format: `python/case_uco/graph.py:1388`, `csharp/CaseUco/CaseGraph.cs:1970`, `java/src/main/java/org/caseontology/CaseGraph.java:1803`, `rust/src/graph.rs:1489`.
- The UCO rule is `core:UcoThing-identifier-regex-shape`, severity `sh:Info`.
- Node IDs from `_mint_id` (`uuid4`) and derived inline facet IDs (`deterministic_uuid`) already end in a UUID (`python/case_uco/graph.py:1366`, `1372`).
