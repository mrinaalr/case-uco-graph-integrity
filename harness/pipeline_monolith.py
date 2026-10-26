"""Arm B (control): one prompt per case, raw CASE JSON-LD out, no tools, no repair.

    python harness/pipeline_monolith.py --run-id RUN [--model ollama] [--cases case_01,case_02]
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import rdflib

from llm import SHARED, documents, main, tokens_of

PROMPT = """You convert investigation documents into a CASE/UCO knowledge graph, as CASE JSON-LD.

{shared}

Reply with the complete JSON-LD document in one ```json code block and nothing else.

{documents}"""


def extract_block(text: str, lang: str) -> str | None:
    match = re.search(rf"```(?:{lang})?\s*\n(.*?)```", text, re.S)
    return match.group(1) if match else None


async def run_case(case_dir: Path, out: Path, cfg: dict, llm) -> dict:
    resp = await llm.chat.completions.create(
        model=cfg["llm"]["model"], temperature=cfg["llm"]["temperature"], max_tokens=cfg["llm"]["monolith_max_tokens"],
        extra_body=cfg["llm"].get("extra_body"),
        messages=[{"role": "user", "content": PROMPT.format(shared=SHARED, documents=documents(case_dir))}])
    text = resp.choices[0].message.content or ""
    (out / "response.txt").write_text(text, encoding="utf-8")
    block = extract_block(text, "json") or text[text.find("{"): text.rfind("}") + 1]
    try:
        doc = json.loads(block)
    except json.JSONDecodeError:
        return {"status": "error", "error": "no parseable JSON in response", "tokens": tokens_of(resp)}
    (out / "graph.jsonld").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    try:
        n = len(rdflib.Graph().parse(out / "graph.jsonld", format="json-ld"))
    except Exception as exc:  # rdflib raises many types on bad JSON-LD
        return {"status": "error", "error": f"JSON-LD does not parse: {exc}"[:2000], "tokens": tokens_of(resp)}
    return {"status": "ok" if n else "empty", "tokens": tokens_of(resp)}


if __name__ == "__main__":
    main("b_control", run_case)
