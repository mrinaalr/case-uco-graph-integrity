"""Smoke test: arm B against a stub endpoint that returns the gold graph, then one
deliberately broken gold copy per error class.

    python harness/smoke.py
"""

from __future__ import annotations

import asyncio
import json
import threading
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import llm
import pipeline_monolith
from graphkit import HARNESS, kb_id
from score import SCORERS, score_case, score_run

RUN_ID = "smoke"
CASES = ["case_01", "case_02", "case_03"]


class Stub(BaseHTTPRequestHandler):
    """OpenAI-compatible chat endpoint that answers with the case's gold JSON-LD."""

    def log_message(self, *args) -> None:
        pass

    def do_POST(self) -> None:
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = req["messages"][-1]["content"]
        case = next(d for d in llm.case_dirs(None) if llm.documents(d) in prompt)
        content = "```json\n" + (case / "gold.jsonld").read_text() + "\n```"
        body = json.dumps({"id": "stub", "object": "chat.completion", "created": 0, "model": req["model"],
                           "choices": [{"index": 0, "finish_reason": "stop",
                                        "message": {"role": "assistant", "content": content}}],
                           "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def gold_pass() -> None:
    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = HARNESS / "results" / RUN_ID
    root.mkdir(parents=True, exist_ok=True)
    config = root / "config.toml"
    config.write_text(llm.CONFIG.read_text() + f'\n[models.stub]\nbase_url = "http://127.0.0.1:{server.server_port}/v1"\n'
                      'model = "stub"\napi_key_env = ""\n')
    asyncio.run(llm._run_all("b_control", pipeline_monolith.run_case,
                             Namespace(run_id=RUN_ID, model="stub", cases=",".join(CASES), config=str(config))))
    server.shutdown()
    score_run(RUN_ID)
    for case in CASES:
        r = json.loads((root / "b_control" / case / "score.json").read_text())
        assert r["precision"] == 1.0 and r["recall"] == 1.0, (case, r["precision"], r["recall"])
    print("gold pass ok: arm B precision 1.0 recall 1.0 on", ", ".join(CASES))


# --- Broken copies -------------------------------------------------------------------

def node(graph: dict, eid: str) -> dict:
    return next(n for n in graph["@graph"] if n["@id"] == kb_id(eid))


def rel(graph: dict, kind: str, source: str | None = None) -> dict:
    return next(n for n in graph["@graph"] if n.get("uco-core:kindOfRelationship") == kind
                and (source is None or n["uco-core:source"] == [{"@id": kb_id(source)}]))


def wrong_value(graph, gold):
    node(graph, "event_0")["uco-core:startTime"] = {"@type": "xsd:dateTime", "@value": "2024-01-01T00:00:00Z"}


def wrong_relation(graph, gold):
    rel(graph, "Employed_By")["uco-core:kindOfRelationship"] = "Reports_To"


def wrong_entity(graph, gold):
    rel(graph, "Holds_Account", "person_0")["uco-core:source"] = [{"@id": kb_id("person_1")}]


def conflation(graph, gold):
    # An event placed at the vendor's address, which only the memo mentions.
    ev = next(e["eid"] for e in gold["entities"] if e["class"] == "Event" and "D1" not in e["docs"])
    graph["@graph"].append({"@id": "kb:rel-conflated", "@type": "uco-core:Relationship",
                            "uco-core:source": [{"@id": kb_id(ev)}], "uco-core:target": [{"@id": kb_id("loc_vendor")}],
                            "uco-core:kindOfRelationship": "Located_At",
                            "uco-core:isDirectional": {"@type": "xsd:boolean", "@value": "true"}})


def invented(graph, gold):
    graph["@graph"].append({"@id": "kb:ghost", "@type": "uco-identity:Person", "uco-core:name": "Zed Nobody"})


def conflation_case() -> str:
    """First case with a vendor address in the memo (D1) and an event outside it."""
    for d in llm.case_dirs(None):
        gold = json.loads((d / "gold.json").read_text())
        ents = {e["eid"]: e for e in gold["entities"]}
        if gold["documents"].get("D1") == "memo" and ents.get("loc_vendor", {}).get("docs") == ["D1"] and \
                any(e["class"] == "Event" and "D1" not in e["docs"] for e in ents.values()):
            return d.name
    raise SystemExit("no case fits the conflation fixture")


def broken_pass() -> None:
    out = HARNESS / "results" / RUN_ID / "broken"
    out.mkdir(parents=True, exist_ok=True)
    fixtures = [("wrong_value", wrong_value, "case_01"), ("wrong_relation", wrong_relation, "case_01"),
                ("wrong_entity", wrong_entity, "case_01"), ("cross_document_conflation", conflation, conflation_case()),
                ("invented", invented, "case_01")]
    for label, mutate, case in fixtures:
        case_dir = HARNESS / "data" / case
        graph = json.loads((case_dir / "gold.jsonld").read_text())
        mutate(graph, json.loads((case_dir / "gold.json").read_text()))
        path = out / f"{label}.jsonld"
        path.write_text(json.dumps(graph, indent=1))
        for scorer in SCORERS:
            r = score_case(case_dir, path, scorer=scorer)
            got = sorted({u["class"] for u in r["unsupported"]})
            status = "ok" if got == [label] else "FAIL"
            print(f"{status:4} {scorer:6} {label:26} {case}: unsupported={[(u['p'], u['class']) for u in r['unsupported']]}")
            assert got == [label], (scorer, label, got)
    print("broken copies ok: each label confirmed under both scorers")


if __name__ == "__main__":
    gold_pass()
    broken_pass()
