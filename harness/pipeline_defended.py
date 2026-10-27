"""Methods B3 and B4: direct generation plus a fixed set of defenses.

B1's prompt and reply, then three documented guards, in order, with the graph snapshotted after
each so every guard's effect is scored on its own:

1. parse retry: when the reply is not parseable JSON-LD, re-ask once with the error (graph_raw.jsonld
   is the first parseable graph);
2. validate and repair: the server's validate_graph report goes back for a rewrite, up to
   defenses.repair_rounds times (graph_validated.jsonld);
3. critic revision: the server's deterministic critic findings (start_critic_review on the graph,
   policy disabled) go back for a rewrite, defenses.critic_rounds times; the final graph is graph.jsonld.

B3 is this pipeline on the base model; B4 is the same pipeline with --model trained. The defenses never
add to the graph themselves: every version of the graph is a model reply.

    python harness/pipeline_defended.py --run-id RUN --arm b3_defended [--model tinker]
    python harness/pipeline_defended.py --run-id RUN --arm b4_trained_defended --model trained
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import rdflib

from llm import SHARED, call_tool, conforms_of, documents, main, server_session, tokens_of
from pipeline_critic import critic_env, load_findings, parse, render
from pipeline_monolith import PROMPT, extract_block

ARM = "b3_defended"

RETRY = """Your previous reply could not be used: {error}
Reply again with the complete CASE JSON-LD document in one ```json code block and nothing else."""

REPAIR = """{prompt}

Your previous graph is below, followed by the validator's report. Rewrite the graph so it validates. Keep every
fact the documents state; do not drop, rename or invent entities, properties or relationships beyond what the
report requires. Reply with the complete JSON-LD document in one ```json code block and nothing else.

=== Previous graph ===
```json
{graph}
```

=== Validation report ===
{report}"""

REVISE = """{prompt}

Your previous graph is below, followed by a quality review's findings. Rewrite the graph so the findings are
addressed. Keep every fact the documents state; do not drop, rename or invent entities, properties or relationships
to satisfy a finding. Reply with the complete JSON-LD document in one ```json code block and nothing else.

=== Previous graph ===
```json
{graph}
```

=== Review findings ===
{findings}"""


def parse_graph(text: str) -> tuple[dict | None, str | None]:
    block = extract_block(text, "json") or text[text.find("{"): text.rfind("}") + 1]
    try:
        doc = json.loads(block)
    except json.JSONDecodeError as exc:
        return None, f"not parseable JSON ({exc})"
    if not isinstance(doc, dict):
        return None, "the reply is not a JSON object"
    try:
        n = len(rdflib.Graph().parse(data=json.dumps(doc), format="json-ld"))
    except Exception as exc:  # noqa: BLE001  rdflib raises many types on bad JSON-LD
        return None, f"JSON-LD does not parse ({str(exc)[:300]})"
    if not n:
        return None, "the graph has no triples"
    return doc, None


async def ask(llm, cfg: dict, messages: list[dict]) -> tuple[str, dict]:
    resp = await llm.chat.completions.create(
        model=cfg["llm"]["model"], temperature=cfg["llm"]["temperature"], max_tokens=cfg["llm"]["monolith_max_tokens"],
        extra_body=cfg["llm"].get("extra_body"), messages=messages)
    return resp.choices[0].message.content or "", tokens_of(resp)


async def run_case(case_dir: Path, out: Path, cfg: dict, llm) -> dict:
    d = cfg["defenses"]
    tokens = Counter()
    prompt = PROMPT.format(shared=SHARED, documents=documents(case_dir))
    graph = out / "graph.jsonld"
    for stale in out.glob("graph*.jsonld"):
        stale.unlink()
    shutil.rmtree(out / "critic-sessions", ignore_errors=True)
    stages: dict[str, dict] = {}
    validations: dict[str, bool | None] = {}

    def save(doc: dict, name: str) -> None:
        (out / name).write_text(json.dumps(doc, indent=2), encoding="utf-8")

    # 0 + 1: generation with a parse retry
    messages = [{"role": "user", "content": prompt}]
    text, used = await ask(llm, cfg, messages)
    tokens.update(used)
    (out / "response_raw.txt").write_text(text, encoding="utf-8")
    doc, error = parse_graph(text)
    retries = 0
    while error and retries < int(d["parse_retries"]):
        retries += 1
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": RETRY.format(error=error)}]
        text, used = await ask(llm, cfg, messages)
        tokens.update(used)
        (out / f"response_raw_retry{retries}.txt").write_text(text, encoding="utf-8")
        doc, error = parse_graph(text)
    stages["raw"] = {"parse_retries": retries, "error": error}
    if doc is None:
        return {"status": "error", "error": error, "tokens": dict(tokens), "stages": stages}
    save(doc, "graph_raw.jsonld")
    save(doc, "graph.jsonld")

    with open(out / "server.log", "w") as errlog:
        async with server_session(cfg, errlog, critic_env(out)) as session:
            # 2: validate and repair
            rounds = 0
            report, _ = await call_tool(session, "validate_graph", {"graph_path": str(graph), "allow_warning": True})
            conforms = conforms_of(report)
            validations["raw"] = conforms
            while conforms is False and rounds < int(d["repair_rounds"]):
                rounds += 1
                text, used = await ask(llm, cfg, [{"role": "user", "content": REPAIR.format(
                    prompt=prompt, graph=json.dumps(doc, indent=1)[:60000], report=report[:6000])}])
                tokens.update(used)
                (out / f"response_repair{rounds}.txt").write_text(text, encoding="utf-8")
                candidate, error = parse_graph(text)
                if candidate is None:
                    stages.setdefault("validated", {})["repair_error"] = error
                    break
                doc = candidate
                save(doc, "graph.jsonld")
                report, _ = await call_tool(session, "validate_graph", {"graph_path": str(graph), "allow_warning": True})
                conforms = conforms_of(report)
            stages["validated"] = {**stages.get("validated", {}), "repair_rounds": rounds, "conforms": conforms}
            validations["validated"] = conforms
            save(doc, "graph_validated.jsonld")

            # 3: critic revision (deterministic findings on the graph alone)
            res = parse((await call_tool(session, "start_critic_review", {
                "graph_path": str(graph), "critic_scope": "graph", "model_policy": "disabled",
                "additional_iterations": max(0, int(d["critic_rounds"]) - 1)}))[0])
            crit: dict = {"started": bool(res.get("ok")), "revisions": 0}
            if res.get("ok"):
                session_id = res["session_id"]
                findings = load_findings(out, session_id, 1, res)
                crit["findings_pass1"] = dict(Counter(f.get("rule_id") or "?" for f in findings))
                for i in range(int(d["critic_rounds"])):
                    if not findings:
                        break
                    text, used = await ask(llm, cfg, [{"role": "user", "content": REVISE.format(
                        prompt=prompt, graph=json.dumps(doc, indent=1)[:60000], findings=render(findings))}])
                    tokens.update(used)
                    (out / f"response_revise{i + 1}.txt").write_text(text, encoding="utf-8")
                    candidate, error = parse_graph(text)
                    if candidate is None:
                        crit["revise_error"] = error
                        break
                    doc = candidate
                    save(doc, "graph.jsonld")
                    crit["revisions"] += 1
                    sub = parse((await call_tool(session, "submit_critic_revision", {
                        "session_id": session_id, "graph_path": str(graph),
                        "addressed_finding_ids": [f["finding_id"] for f in findings if f.get("finding_id")][:200]}))[0])
                    if not sub.get("ok"):
                        crit["submit_error"] = sub.get("error")
                        break
                    findings = load_findings(out, session_id, i + 2, sub)
                    crit[f"findings_pass{i + 2}"] = dict(Counter(f.get("rule_id") or "?" for f in findings))
                final = parse((await call_tool(session, "finalize_critic_review", {"session_id": session_id}))[0])
                crit["final_outcome"] = final.get("outcome") if final.get("ok") else f"not finalized: {final.get('code')}"
            else:
                crit["error"] = res.get("error")
            stages["critic"] = crit
    return {"status": "ok", "tokens": dict(tokens), "stages": stages, "stage_validations": validations}


if __name__ == "__main__":
    main(ARM, run_case)
