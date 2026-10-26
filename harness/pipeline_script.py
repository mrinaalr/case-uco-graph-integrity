"""Arm A1 (script): the model writes a CASEGraph serializer script; the harness runs it.

The script gets the output path as sys.argv[1]. After it runs, the graph is
checked with the case-uco server's validate_graph (recorded, no repair).
The script is model-written code executed locally with a timeout; run this
arm only against endpoints you trust.

    python harness/pipeline_script.py --run-id RUN [--model ollama] [--cases case_01,case_02]
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from graphkit import REPO
from llm import SDK, SHARED, call_tool, conforms_of, documents, main, server_session, tokens_of
from pipeline_monolith import extract_block

PROMPT = """You convert investigation documents into a CASE/UCO knowledge graph by writing a Python script.

{shared}

Write one self-contained Python 3 script that builds this graph with the SDK class
case_uco.graph.CASEGraph and writes it to the path given in sys.argv[1]. Useful calls:
    from case_uco.graph import CASEGraph
    g = CASEGraph()
    g.upsert_node("kb:person-1", types="uco-identity:Person", properties={{"uco-core:name": "..."}})
    g.add_property("kb:person-1", "uco-core:hasFacet", {{"@id": "kb:person-1-facet"}})
    g.create_relationship("kb:person-1", "kb:org-1", "Employed_By")
    g.write(sys.argv[1])
Property keys and values use the compact JSON-LD forms shown above.
Reply with the script in one ```python code block and nothing else.

{documents}"""


async def run_case(case_dir: Path, out: Path, cfg: dict, llm) -> dict:
    resp = await llm.chat.completions.create(
        model=cfg["llm"]["model"], temperature=cfg["llm"]["temperature"], max_tokens=cfg["llm"]["monolith_max_tokens"],
        extra_body=cfg["llm"].get("extra_body"),
        messages=[{"role": "user", "content": PROMPT.format(shared=SHARED, documents=documents(case_dir))}])
    text = resp.choices[0].message.content or ""
    (out / "response.txt").write_text(text, encoding="utf-8")
    script = extract_block(text, "python")
    if not script:
        return {"status": "error", "error": "no python code block in response", "tokens": tokens_of(resp)}
    (out / "serializer.py").write_text(script, encoding="utf-8")
    graph = out / "graph.jsonld"
    try:
        proc = subprocess.run([str(REPO / ".venv" / "bin" / "python"), "serializer.py", str(graph)], cwd=out,
                              capture_output=True, text=True, timeout=cfg["run"]["script_timeout_s"],
                              env={"PYTHONPATH": str(SDK / "python"), "PATH": "/usr/bin:/bin"})
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "serializer timed out", "tokens": tokens_of(resp)}
    (out / "serializer.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode != 0 or not graph.exists():
        return {"status": "error", "error": f"serializer exited {proc.returncode}: {proc.stderr[-1500:]}",
                "tokens": tokens_of(resp)}
    with open(out / "server.log", "w") as errlog:
        async with server_session(cfg, errlog) as session:
            report, _ = await call_tool(session, "validate_graph", {"graph_path": str(graph), "allow_warning": True})
    (out / "validate_graph.json").write_text(report, encoding="utf-8")
    return {"status": "ok", "server_validation": conforms_of(report), "tokens": tokens_of(resp)}


if __name__ == "__main__":
    main("a1_script", run_case)
