"""Arm A2 (tools): an LLM builds the graph through write tools and the case-uco server.

The model gets the server's lookup tools and validate_graph over MCP stdio,
plus four harness write tools (add_node, add_facet, add_relationship, finish)
backed by case_uco.graph.CASEGraph. finish validates; a failure gives the
model up to repair_rounds more tries. A run stops and is marked "capped" at
max_tool_calls, or when the conversation would pass max_context_tokens (the
same limit for every model; Tinker's Qwen endpoint allows 65,536). The graph and provenance are also
snapshotted at the first validation so it can be scored before repair.
Every tool call is logged with its arguments, the model message that
produced it, and cited span ids.

    python harness/pipeline_sdk.py --run-id RUN [--model ollama] [--cases case_01,case_02]
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from openai import BadRequestError

from graphkit import BuildError, GraphWriter
from llm import SHARED, call_tool, conforms_of, documents, main, server_session, tokens_of

SERVER_TOOLS = {"search_classes", "get_class_details", "find_classes_for_domain", "suggest_classes_for_input",
                "list_all_facets", "list_all_vocabs", "route_investigation_content", "guide_mapping",
                "get_recipes", "validate_graph"}
SPAN_RE = re.compile(r"\bD\d+\.S\d+\b")
RESULT_LIMIT = 4000

_SPANS = {"type": "array", "items": {"type": "string"}, "description": "Sentence ids that state this fact, e.g. D1.S3"}
_PROPS = {"type": "object", "description": "Property name -> value. Reference other nodes by their id."}
HARNESS_TOOLS = [
    {"type": "function", "function": {
        "name": "add_node",
        "description": "Create a graph node, or update its properties if the id exists.",
        "parameters": {"type": "object", "required": ["id", "class_name"], "properties": {
            "id": {"type": "string", "description": "Short stable id you choose, e.g. person-dana"},
            "class_name": {"type": "string", "description": "CASE/UCO class name, e.g. Person"},
            "properties": _PROPS, "span_ids": _SPANS}}}},
    {"type": "function", "function": {
        "name": "add_facet",
        "description": "Attach a facet to a node, or update the facet's properties if it already exists.",
        "parameters": {"type": "object", "required": ["node_id", "facet_class"], "properties": {
            "node_id": {"type": "string"}, "facet_class": {"type": "string"},
            "properties": _PROPS, "span_ids": _SPANS}}}},
    {"type": "function", "function": {
        "name": "add_relationship",
        "description": "Add a uco-core:Relationship from source to target.",
        "parameters": {"type": "object", "required": ["source", "target", "kind"], "properties": {
            "source": {"type": "string"}, "target": {"type": "string"},
            "kind": {"type": "string", "description": "kindOfRelationship"}, "span_ids": _SPANS}}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Call once every document is modeled. Runs validation; if it fails, fix the graph and call again.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}}}},
]
WRITE_TOOLS = {"add_node", "add_facet", "add_relationship"}

SYSTEM = f"""You convert investigation documents into a CASE/UCO knowledge graph.

Write the graph only through add_node, add_facet and add_relationship (use plain class and
property names, e.g. class_name "EmailAddressFacet", property "addressValue"). The case-uco tools
(search_classes, get_class_details, ...; pass scope="core") look up classes and properties.
When every document is modeled, call validate_graph, fix what it reports, then call finish.
Put the cited sentence ids in each write call's span_ids.

{SHARED}"""


def openai_tool(tool) -> dict:
    schema = dict(tool.inputSchema or {"type": "object", "properties": {}})
    if tool.name == "validate_graph":  # the harness always validates the working graph
        schema = {**schema, "required": [], "properties": {k: v for k, v in schema.get("properties", {}).items()
                                                            if k != "graph_path"}}
    return {"type": "function", "function": {"name": tool.name, "description": (tool.description or "")[:1500],
                                             "parameters": schema}}


async def run_case(case_dir: Path, out: Path, cfg: dict, llm) -> dict:
    graph_path = out / "graph.jsonld"
    writer = GraphWriter()
    writer.write(graph_path)
    log: list[dict] = []
    tokens = {"prompt": 0, "completion": 0}
    state = {"finished": False, "repairs_left": cfg["run"]["repair_rounds"], "failed_validation": False,
             "validations": []}
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Model these documents as one CASE/UCO graph.\n\n" + documents(case_dir)}]
    turn = 0
    with open(out / "log.jsonl", "w", encoding="utf-8") as log_fh, open(out / "server.log", "w") as errlog:
        async with server_session(cfg, errlog) as session:
            listed = (await session.list_tools()).tools
            tools = [openai_tool(t) for t in listed if t.name in SERVER_TOOLS] + HARNESS_TOOLS

            async def validate() -> tuple[str, bool | None]:
                if not state["validations"]:  # score the pre-repair graph too
                    shutil.copy(graph_path, out / "graph_first_validate.jsonld")
                    (out / "prov_first_validate.json").write_text(json.dumps(writer.prov))
                text, _ = await call_tool(session, "validate_graph", {"graph_path": str(graph_path), "allow_warning": True})
                conforms = conforms_of(text)
                state["validations"].append(conforms)
                state["failed_validation"] = state["failed_validation"] or conforms is False
                return text, conforms

            async def execute(name: str, args: dict, idx: int) -> tuple[str, bool]:
                try:
                    if name == "add_node":
                        ref = writer.add_node(args["id"], args["class_name"], args.get("properties"), call=idx)
                    elif name == "add_facet":
                        ref = writer.add_facet(args["node_id"], args["facet_class"], args.get("properties"), call=idx)
                    elif name == "add_relationship":
                        ref = writer.add_relationship(args["source"], args["target"], args["kind"], call=idx)
                    elif name == "finish":
                        text, conforms = await validate()
                        if conforms is False and state["repairs_left"] > 0:
                            state["repairs_left"] -= 1
                            return ("Not finished: validation failed. Fix the graph with the write tools, "
                                    "then call finish again.\n" + text[:RESULT_LIMIT], True)
                        state["finished"] = True
                        return "Finished.", False
                    elif name == "validate_graph":
                        text, _ = await validate()
                        return text[:RESULT_LIMIT], False
                    elif name in SERVER_TOOLS:
                        text, error = await call_tool(session, name, args)
                        return text[:RESULT_LIMIT], error
                    else:
                        return f"Unknown tool {name!r}.", True
                except (BuildError, KeyError, TypeError, ValueError) as exc:  # CASEGraph raises ValueError/KeyError
                    return f"Error: {exc}", True
                writer.write(graph_path)
                return f"ok: {ref}", False

            nudges = 0
            last_prompt = 0
            for turn in range(cfg["run"]["max_turns"]):
                if last_prompt + cfg["llm"]["max_tokens"] > cfg["run"]["max_context_tokens"]:
                    state["capped"] = "context"
                    break
                try:
                    resp = await llm.chat.completions.create(
                        model=cfg["llm"]["model"], messages=messages, tools=tools,
                        temperature=cfg["llm"]["temperature"], max_tokens=cfg["llm"]["max_tokens"],
                        extra_body=cfg["llm"].get("extra_body"))
                except BadRequestError as exc:  # the endpoint's own context limit
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
                    messages.append({"role": "user", "content": "Continue using the tools. Call finish when the graph is complete."})
                    continue
                for call in calls:
                    idx = len(log)
                    try:
                        args = json.loads(call.function.arguments or "{}")
                        result, error = await execute(call.function.name, args, idx) if isinstance(args, dict) \
                            else ("Error: arguments must be an object", True)
                    except json.JSONDecodeError as exc:
                        args, result, error = call.function.arguments, f"Error: arguments are not valid JSON ({exc})", True
                    spans = args.get("span_ids") if isinstance(args, dict) else None
                    cited = sorted(set(spans if isinstance(spans, list) else []) | set(SPAN_RE.findall(msg.content or "")))
                    log.append({"i": idx, "turn": turn, "tool": call.function.name,
                                "side": "harness" if call.function.name in WRITE_TOOLS | {"finish"} else "server",
                                "args": args, "assistant_text": msg.content or "", "cited_spans": cited,
                                "doc_ids": sorted({s.split(".")[0] for s in cited}), "result": result[:1000],
                                "error": error, "after_failed_validation": state["failed_validation"]})
                    log_fh.write(json.dumps(log[-1], default=str) + "\n")
                    log_fh.flush()
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                    if len(log) >= cfg["run"]["max_tool_calls"] and not state["finished"]:
                        state["capped"] = "tool_calls"
                        break
                if state["finished"] or state.get("capped"):
                    break

    (out / "prov.json").write_text(json.dumps(writer.prov, indent=1))
    (out / "transcript.json").write_text(json.dumps(messages, indent=1, default=str))
    status = "empty" if not writer.object_count() else "ok" if state["finished"] else \
        "capped" if state.get("capped") else "incomplete"
    return {"status": status,
            "turns": turn + 1, "tool_calls": len(log), "tokens": tokens, "server_validations": state["validations"],
            "capped_by": state.get("capped") or None}


if __name__ == "__main__":
    main("a2_tools", run_case)
