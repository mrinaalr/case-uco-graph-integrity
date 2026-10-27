"""Method A: the CASE/UCO SDK as shipped, driven by a coding agent.

The model gets the SDK's MCP server tools and three agent tools (read_file, write_serializer,
finish) and is asked to follow the SDK's documented workflow: read the evidence, route it and look
up classes and recipes, write a serializer that builds the graph with case_uco.graph.CASEGraph,
validate it, run the critic loop (start_critic_review, revise, submit_critic_revision,
finalize_critic_review), and finish. The harness adds nothing of its own to the graph: every
node comes from the serializer the agent wrote. The critic runs its deterministic checks (model
policy "disabled"); a schema-bound manual critic response is beyond the models under test.

The graph is snapshotted at the agent's first validate_graph call (graph_first_validate.jsonld)
so the graph before any QA can be scored too. Model-written scripts run locally with a timeout.

    python harness/pipeline_sdk_agent.py --run-id RUN [--model ollama] [--cases case_01,case_02]
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from openai import BadRequestError

from graphkit import REPO
from llm import SHARED, call_tool, conforms_of, doc_files, main, server_session, tokens_of
from pipeline_critic import critic_env
from pipeline_script import run_serializer

ARM = "a_sdk_agent"
SERVER_TOOLS = {"process_document_file", "route_investigation_content", "guide_mapping", "get_recipe", "get_recipes",
                "search_classes", "get_class_details", "find_classes_for_domain", "suggest_classes_for_input",
                "list_all_facets", "validate_graph", "start_critic_review", "submit_critic_revision",
                "get_critic_review_status", "finalize_critic_review", "cancel_critic_review"}
RESULT_LIMIT = 4000
READ_LIMIT = 6000

AGENT_TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text or PDF file from the evidence folder or the output folder. Returns up to 6000 "
                       "characters from offset.",
        "parameters": {"type": "object", "required": ["path"], "properties": {
            "path": {"type": "string"}, "offset": {"type": "integer", "default": 0}}}}},
    {"type": "function", "function": {
        "name": "write_serializer",
        "description": "Save the serializer script as serializer.py in the output folder and run it with the graph "
                       "output path as sys.argv[1]. Returns the script's output and whether the graph file was written.",
        "parameters": {"type": "object", "required": ["script"], "properties": {"script": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Call once the graph is built, validated and reviewed.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}}}},
]

SYSTEM = """You are a coding agent using the CASE/UCO SDK to model investigation evidence as a CASE/UCO graph.

Evidence files (PDF): {files}
Output folder: {out}
Graph path: {graph}
Serializer path: {serializer}

Follow the SDK's workflow:
1. Read the evidence: read_file on each PDF (text is extracted for you), or process_document_file.
2. Find the right modeling: route_investigation_content with the content, guide_mapping, get_recipes,
   search_classes and get_class_details as needed.
3. Write the serializer with write_serializer: a self-contained Python 3 script that builds the graph with
   case_uco.graph.CASEGraph (from case_uco.graph import CASEGraph; g = CASEGraph(); g.upsert_node(id, types=..., properties=...);
   g.add_property(id, "uco-core:hasFacet", {{"@id": facet_id}}); g.create_relationship(src, dst, kind); g.write(sys.argv[1])).
   It must write the graph to the path in sys.argv[1]. Fix any error the run reports.
4. validate_graph on the graph path and fix what it reports.
5. Run the critic loop: start_critic_review(graph_path, serializer_path, source_paths=[the PDFs], critic_scope="both",
   model_policy="disabled"), revise the serializer for the findings with write_serializer, submit_critic_revision,
   and finalize_critic_review when it can be finalized.
6. Call finish.

{shared}"""


def openai_tool(tool) -> dict:
    schema = dict(tool.inputSchema or {"type": "object", "properties": {}})
    return {"type": "function", "function": {"name": tool.name, "description": (tool.description or "")[:1500],
                                             "parameters": schema}}


async def run_case(case_dir: Path, out: Path, cfg: dict, llm) -> dict:
    graph, serializer = out / "graph.jsonld", out / "serializer.py"
    files = doc_files(case_dir)
    for stale in (graph, serializer, out / "graph_first_validate.jsonld"):
        stale.unlink(missing_ok=True)
    shutil.rmtree(out / "critic-sessions", ignore_errors=True)
    log: list[dict] = []
    tokens = {"prompt": 0, "completion": 0}
    state = {"finished": False, "validations": [], "serializer_runs": 0, "critic_started": False, "capped": None}
    messages = [{"role": "system", "content": SYSTEM.format(files="\n".join(str(f) for f in files), out=out, graph=graph,
                                                            serializer=serializer, shared=SHARED)},
                {"role": "user", "content": "Model the evidence files as one CASE/UCO graph, then call finish."}]
    allowed_dirs = (case_dir / "docs", out)

    def read_file(path: str, offset: int = 0) -> tuple[str, bool]:
        p = Path(path)
        if not any(p.resolve().is_relative_to(d.resolve()) for d in allowed_dirs) or not p.is_file():
            return "Error: path must be an existing file in the evidence or output folder.", True
        if p.suffix == ".pdf":
            from llm import pdf_text
            text = pdf_text(p)
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
        chunk = text[offset: offset + READ_LIMIT]
        more = f"\n[... {len(text) - offset - READ_LIMIT} more characters; call again with offset={offset + READ_LIMIT}]" \
            if len(text) > offset + READ_LIMIT else ""
        return chunk + more, False

    turn = 0
    with open(out / "log.jsonl", "w", encoding="utf-8") as log_fh, open(out / "server.log", "w") as errlog:
        async with server_session(cfg, errlog, {**critic_env(out), "CASE_UCO_CRITIC_MODEL_POLICY": "disabled"}) as session:
            listed = (await session.list_tools()).tools
            tools = [openai_tool(t) for t in listed if t.name in SERVER_TOOLS] + AGENT_TOOLS

            async def execute(name: str, args: dict) -> tuple[str, bool]:
                if name == "read_file":
                    return read_file(str(args.get("path", "")), int(args.get("offset") or 0))
                if name == "write_serializer":
                    state["serializer_runs"] += 1
                    error = run_serializer(out, str(args.get("script", "")), graph, cfg)
                    tail = (out / "serializer.log").read_text(encoding="utf-8")[-2000:] if (out / "serializer.log").exists() else ""
                    if error:
                        return f"Serializer failed: {error[-2500:]}", True
                    return f"Serializer ran. Graph written to {graph}.\n{tail}", False
                if name == "finish":
                    state["finished"] = True
                    return "Finished.", False
                if name == "validate_graph":
                    if not state["validations"] and graph.exists():
                        shutil.copy(graph, out / "graph_first_validate.jsonld")
                    text, error = await call_tool(session, name, {**args, "graph_path": str(graph)})
                    state["validations"].append(conforms_of(text))
                    return text[:RESULT_LIMIT], error
                if name == "start_critic_review":
                    state["critic_started"] = True
                    args = {**args, "model_policy": "disabled"}
                if name in SERVER_TOOLS:
                    text, error = await call_tool(session, name, args)
                    return text[:RESULT_LIMIT], error
                return f"Unknown tool {name!r}.", True

            nudges, last_prompt = 0, 0
            for turn in range(cfg["run"]["max_turns"]):
                if last_prompt + cfg["llm"]["max_tokens"] > cfg["run"]["max_context_tokens"]:
                    state["capped"] = "context"
                    break
                try:
                    resp = await llm.chat.completions.create(
                        model=cfg["llm"]["model"], messages=messages, tools=tools,
                        temperature=cfg["llm"]["temperature"], max_tokens=cfg["llm"]["max_tokens"],
                        extra_body=cfg["llm"].get("extra_body"))
                except BadRequestError as exc:
                    if "context" not in str(exc):
                        raise
                    state["capped"] = "context"
                    break
                last_prompt = resp.usage.prompt_tokens if resp.usage else last_prompt
                for k, v in tokens_of(resp).items():
                    tokens[k] += v
                msg = resp.choices[0].message
                calls = msg.tool_calls or []
                messages.append({"role": "assistant", "content": msg.content or "", **({"tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in calls]} if calls else {})})
                if not calls:
                    if nudges >= 2:
                        break
                    nudges += 1
                    messages.append({"role": "user", "content": "Continue with the tools. Call finish when the graph is built, "
                                                                "validated and reviewed."})
                    continue
                for call in calls:
                    try:
                        args = json.loads(call.function.arguments or "{}")
                        result, error = await execute(call.function.name, args) if isinstance(args, dict) \
                            else ("Error: arguments must be an object", True)
                    except json.JSONDecodeError as exc:
                        args, result, error = call.function.arguments, f"Error: arguments are not valid JSON ({exc})", True
                    except Exception as exc:  # noqa: BLE001  a tool failure is a result the agent sees, not a crash
                        result, error = f"Error: {type(exc).__name__}: {exc}"[:1500], True
                    log.append({"i": len(log), "turn": turn, "tool": call.function.name,
                                "args": args if call.function.name != "write_serializer" else {"script_chars": len(str(args.get("script", "")))},
                                "result": result[:1000], "error": error})
                    log_fh.write(json.dumps(log[-1], default=str) + "\n")
                    log_fh.flush()
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                    if len(log) >= cfg["run"]["max_tool_calls"] and not state["finished"]:
                        state["capped"] = "tool_calls"
                        break
                if state["finished"] or state["capped"]:
                    break
    (out / "transcript.json").write_text(json.dumps(messages, indent=1, default=str))
    status = "empty" if not graph.exists() else "ok" if state["finished"] else "capped" if state["capped"] else "incomplete"
    return {"status": status, "turns": turn + 1, "tool_calls": len(log), "tokens": tokens,
            "serializer_runs": state["serializer_runs"], "server_validations": state["validations"],
            "critic_started": state["critic_started"], "capped_by": state["capped"],
            "tools_used": sorted({row["tool"] for row in log})}


if __name__ == "__main__":
    main(ARM, run_case)
