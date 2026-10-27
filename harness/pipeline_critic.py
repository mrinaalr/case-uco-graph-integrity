"""Arm A1+QA (critic): the A1 serializer, then the SDK's critic acceptance loop.

Generation is A1 exactly: the same prompt, one Python script that writes the graph with
CASEGraph. The graph and serializer then go through the case-uco server's critic session,
the SDK's own QA path. start_critic_review runs the deterministic checks (SHACL, graph
integrity, modeling heuristics, relationship lint, serializer AST rules). With
critic.policy = "manual" the same LLM also acts as the critic from the server's
prompt_package. The open findings go back to the originating model, which rewrites the
serializer; the harness runs it and resubmits it with submit_critic_revision. This repeats
for critic.rounds revisions or until nothing is open, then finalize_critic_review runs.

Every pass is snapshotted (graph_passN.jsonld, serializer_passN.py) so each QA adjustment
is scored on its own: pass 1 is the bare A1 graph, pass N+1 is the graph after revision N.
The model-written scripts run locally with a timeout; use this arm only against endpoints you trust.

    python harness/pipeline_critic.py --run-id RUN [--model ollama] [--cases case_01,case_02]
"""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from pathlib import Path

from graphkit import REPO
from llm import SHARED, call_tool, documents, main, server_session
from pipeline_monolith import extract_block
from pipeline_script import PROMPT, generate, run_serializer

ARM = "a1_critic"
MAX_EXAMPLES = 6  # targets listed per rule in the revision prompt

REVISE = """{prompt}

Your previous script is below. A quality review of the graph it wrote reported the findings after it.
Rewrite the script so the findings are addressed. Keep every fact the documents state; do not drop,
rename or invent entities, properties or relationships to satisfy a finding, and do not change facts
the findings do not mention. Reply with the complete script in one ```python code block and nothing else.

=== Previous script ===
```python
{script}
```

=== Review findings ===
{findings}"""

FIX = """{prompt}

The script below crashed when run. Fix the error and reply with the complete script in one ```python
code block and nothing else. Change nothing except what the error requires.

=== Script ===
```python
{script}
```

=== Error ===
{error}"""

CRITIC = """{system_role}

Review the graph and serializer described by the package below, which the case-uco server
produced. The deterministic findings in it are facts. Add your own findings only where the
graph misstates, conflates or omits what the source excerpts say, or models it with the wrong
class, facet, relationship kind or direction. Reply with one JSON object and nothing else:
{{"findings": [...], "scorecard": {{...}}, "notes": "..."}}
Each finding needs: severity (critical|high|medium|low|info), category (one of the package's
categories, e.g. source_fidelity, identity_conflation, relationship_direction), confidence (0-1),
target ({{"node_id": ..., "predicate": ..., "counterpart_id": ...}} with expanded IRIs from the
package, or {{"path": ..., "qualified_name": ...}} for the serializer), evidence (list of short strings
quoting the package), rationale, recommended_change, verification_method. The scorecard holds any of
schema_concept_conformance, source_fidelity, semantic_precision, provenance_custody,
markings_authorization, coverage_completeness, serializer_quality, maintainability_reproducibility,
each as {{"assessed": true, "score": 0-5, "evidence": [...]}}. Assess source_fidelity.

=== Package ===
{package}"""

TARGET_FIELDS = {"path", "line", "node_id", "predicate", "counterpart_id", "json_pointer", "qualified_name"}
SCORECARD_DIMENSIONS = {"schema_concept_conformance", "source_fidelity", "semantic_precision", "provenance_custody",
                        "markings_authorization", "coverage_completeness", "serializer_quality",
                        "maintainability_reproducibility"}
FINDING_FIELDS = ("severity", "category", "confidence", "target", "evidence", "rationale", "recommended_change",
                  "verification_method")


def critic_env(out: Path) -> dict[str, str]:
    """Workspace roots for the server's critic: read the repo, write under this case's results dir."""
    return {"CASE_UCO_MCP_READ_ROOTS": str(REPO), "CASE_UCO_MCP_WRITE_ROOTS": str(out),
            "CASE_UCO_CRITIC_SESSION_ROOT": str(out / "critic-sessions"), "CASE_UCO_MCP_ALLOW_OVERWRITE": "1"}


def parse(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def load_findings(out: Path, session_id: str, pass_no: int, fallback: dict) -> list[dict]:
    """Open findings of one pass: the session's review file, else the tool result's ledger."""
    path = out / "critic-sessions" / session_id / f"review-pass-{pass_no}.json"
    review = json.loads(path.read_text()) if path.exists() else {}
    findings = review.get("merged_findings") or review.get("deterministic_findings") or []
    if not findings:
        ledger = fallback.get("assessment_ledger") or {}
        findings = ledger.get("findings") or ledger.get("entries") or (ledger if isinstance(ledger, list) else [])
    return [f for f in findings if isinstance(f, dict) and f.get("status") != "resolved"]


def render(findings: list[dict]) -> str:
    """Group findings by rule so twenty orphan-node findings read as one item with examples."""
    groups: dict[str, list[dict]] = {}
    for f in findings:
        groups.setdefault(f.get("rule_id") or f.get("category") or "finding", []).append(f)
    lines = []
    for rule, group in groups.items():
        first = group[0]
        lines.append(f"- {rule} [{first.get('severity')}] x{len(group)}: {first.get('rationale')}")
        lines.append(f"  Recommended: {first.get('recommended_change')}")
        targets = []
        for f in group[:MAX_EXAMPLES]:
            t = f.get("target") or {}
            targets.append(t.get("node_id") or t.get("qualified_name") or t.get("path") or "")
        targets = [t for t in targets if t]
        if targets:
            lines.append("  Targets: " + ", ".join(targets) + (" ..." if len(group) > MAX_EXAMPLES else ""))
    return "\n".join(lines) or "(none)"


def bind(response: dict, package: dict, hashes: dict, session_id: str, pass_no: int) -> dict:
    """Shape the critic's reply to the response schema the server bound into its prompt package."""
    schema = package.get("response_schema") or {}
    item = (schema.get("properties") or {}).get("findings", {}).get("items") or {}
    allowed = set((item.get("properties") or {}).keys()) or set(FINDING_FIELDS) | {"claim_type"}
    claim = (item.get("properties") or {}).get("claim_type") or {}
    claim_default = (claim.get("enum") or ["inference"])[0]
    findings = []
    for f in response.get("findings") or []:
        if not isinstance(f, dict):
            continue
        f = {k: f.get(k) for k in FINDING_FIELDS}
        f["target"] = {k: v for k, v in (f["target"] or {}).items() if k in TARGET_FIELDS} if isinstance(f["target"], dict) else {}
        f["evidence"] = [str(e)[:500] for e in (f["evidence"] if isinstance(f["evidence"], list) else [f["evidence"]])][:8]
        try:
            f["confidence"] = min(1.0, max(0.0, float(f["confidence"])))
        except (TypeError, ValueError):
            f["confidence"] = 0.5
        for k in ("rationale", "recommended_change", "verification_method"):
            f[k] = str(f[k] or "")[:2000]
        if f["severity"] not in ("critical", "high", "medium", "low", "info"):
            f["severity"] = "medium"
        f["category"] = str(f["category"] or "source_fidelity")
        f["claim_type"] = claim_default if not claim.get("enum") else \
            (f.get("claim_type") if f.get("claim_type") in claim["enum"] else claim_default)
        findings.append({k: v for k, v in f.items() if k in allowed})
    scorecard = response.get("scorecard") if isinstance(response.get("scorecard"), dict) else {}
    scorecard = {k: {"assessed": bool(v.get("assessed", True)), "score": v.get("score"), "evidence": [str(e) for e in v.get("evidence", [])][:8]}
                 for k, v in scorecard.items() if isinstance(v, dict) and k in SCORECARD_DIMENSIONS} or \
        {"source_fidelity": {"assessed": True, "score": 3, "evidence": ["critic reply had no scorecard"]}}
    for v in scorecard.values():
        if not isinstance(v["score"], int) or not 0 <= v["score"] <= 5:
            v["score"] = 3
    full = {"schema_version": package.get("response_schema_version") or "1.2.0", "session_id": session_id,
            "pass_number": pass_no, "graph_sha256": hashes.get("graph_sha256"),
            "serializer_sha256": hashes.get("serializer_sha256"), "prompt_package_hash": package.get("prompt_package_hash"),
            "review_request_sha256": package.get("review_request_sha256"),
            "review_config_sha256": package.get("review_config_sha256"), "findings": findings, "scorecard": scorecard,
            "notes": str(response.get("notes") or "")[:2000]}
    top = set((schema.get("properties") or {}).keys())
    return {k: v for k, v in full.items() if not top or k in top}


async def run_case(case_dir: Path, out: Path, cfg: dict, llm) -> dict:
    crit = {**cfg["critic"], "policy": os.environ.get("CRITIC_POLICY") or cfg["critic"]["policy"]}
    tokens = Counter()
    base_prompt = PROMPT.format(shared=SHARED, documents=documents(case_dir))
    text, used = await generate(llm, cfg, [{"role": "user", "content": base_prompt}])
    tokens.update(used)
    (out / "response_pass1.txt").write_text(text, encoding="utf-8")
    script = extract_block(text, "python")
    if not script:
        return {"status": "error", "error": "no python code block in response", "tokens": dict(tokens)}
    graph, serializer = out / "graph.jsonld", out / "serializer.py"
    pass1_fixes: list[str] = []
    error = run_serializer(out, script, out / "graph_pass1.jsonld", cfg, tag="_pass1")
    for attempt in range(int(crit.get("fix_attempts", 1))):
        if not error:
            break
        pass1_fixes.append(error[:300])
        reply, used = await generate(llm, cfg, [{"role": "user", "content": FIX.format(
            prompt=base_prompt, script=script, error=error[-1500:])}])
        tokens.update(used)
        (out / f"response_pass1_fix{attempt + 1}.txt").write_text(reply, encoding="utf-8")
        fixed = extract_block(reply, "python")
        if not fixed:
            break
        script = fixed
        error = run_serializer(out, script, out / "graph_pass1.jsonld", cfg, tag="_pass1")
    if error:
        return {"status": "error", "error": error, "tokens": dict(tokens), "pass1_fix_attempts": pass1_fixes}
    shutil.copy(out / "graph_pass1.jsonld", graph)
    shutil.copy(out / "serializer_pass1.py", serializer)
    docs = sorted(str(p) for p in (case_dir / "docs").glob("D*.marked.txt"))
    shutil.rmtree(out / "critic-sessions", ignore_errors=True)
    passes: list[dict] = []
    info: dict = {"status": "ok", "critic_policy": crit["policy"], "pass1_fix_attempts": pass1_fixes}

    def record(pass_no: int, result: dict, findings: list[dict]) -> dict:
        review = result.get("review") or {}
        entry = {"pass": pass_no, "conforms": (review.get("validation") or {}).get("conforms"),
                 "analysis_status": review.get("analysis_status"),
                 "open": (review.get("finding_counts") or {}).get("open"),
                 "critical_high_open": (review.get("finding_counts") or {}).get("critical_high_open"),
                 "rules": dict(Counter(f.get("rule_id") or f.get("category") or "?" for f in findings)),
                 "scorecard": {k: v.get("score") for k, v in (review.get("scorecard") or {}).items() if isinstance(v, dict)}}
        passes.append(entry)
        return entry

    with open(out / "server.log", "w") as errlog:
        async with server_session(cfg, errlog, critic_env(out)) as session:
            args = {"graph_path": str(graph), "serializer_path": str(serializer), "source_paths": docs,
                    "critic_scope": "both", "model_policy": crit["policy"], "serializer_mode": "casegraph_raw",
                    "additional_iterations": max(0, int(crit["rounds"]) - 1)}
            text, _ = await call_tool(session, "start_critic_review", args)
            result = parse(text)
            (out / "critic_pass1.json").write_text(text, encoding="utf-8")
            if not result.get("ok"):
                return {**info, "status": "error", "error": f"start_critic_review: {result.get('error') or text[:500]}",
                        "tokens": dict(tokens), "passes": passes}
            session_id = result["session_id"]
            info["session_id"] = session_id
            pass_no, revisions = 1, 0
            while True:
                critic_findings: list[dict] = []
                critic_scorecard: dict = {}
                critic_error = False
                if result.get("state") == "awaiting_critic_response":  # policy manual: the LLM is the critic
                    package = result.get("prompt_package") or {}
                    hashes = (result.get("review") or {}).get("artifact_hashes") or {}
                    shown = {k: v for k, v in package.items() if k not in ("response_schema", "system_role")}
                    reply, used = await generate(llm, cfg, [{"role": "user", "content": CRITIC.format(
                        system_role=package.get("system_role", ""), package=json.dumps(shown, indent=0)[:120000])}])
                    tokens.update(used)
                    (out / f"critic_reply_pass{pass_no}.txt").write_text(reply, encoding="utf-8")
                    parsed = parse(extract_block(reply, "json") or reply[reply.find("{"): reply.rfind("}") + 1])
                    response = bind(parsed, package, hashes, session_id, pass_no)
                    text, _ = await call_tool(session, "submit_manual_critic_response",
                                              {"session_id": session_id, "response": response})
                    submitted = parse(text)
                    (out / f"critic_response_pass{pass_no}.json").write_text(text, encoding="utf-8")
                    if submitted.get("ok"):
                        critic_findings = response["findings"]
                        critic_scorecard = {k: v.get("score") for k, v in response["scorecard"].items()}
                    else:  # keep the session moving with an attested empty review
                        critic_error = True
                        empty = {"scorecard": {"source_fidelity": {"assessed": True, "score": 3,
                                                                   "evidence": ["critic reply was not schema-valid"]}}}
                        text, _ = await call_tool(session, "submit_manual_critic_response", {
                            "session_id": session_id, "response": bind(empty, package, hashes, session_id, pass_no)})
                        submitted = parse(text)
                    result = {**result, **{k: v for k, v in submitted.items() if k in ("state", "review", "assessment_ledger")}}
                findings = load_findings(out, session_id, pass_no, result) + critic_findings
                for f in findings:  # the critic reports only a violation count; attach the validator's report
                    if f.get("rule_id") == "CRIT-V-NONCONFORMING":
                        report, _ = await call_tool(session, "validate_graph", {"graph_path": str(graph), "allow_warning": True})
                        (out / f"validate_graph_pass{pass_no}.json").write_text(report, encoding="utf-8")
                        f["recommended_change"] = (f.get("recommended_change") or "") + "\nvalidate_graph report:\n" + report[:4000]
                        break
                entry = record(pass_no, result, findings)
                entry["critic_findings"], entry["critic_response_error"] = len(critic_findings), critic_error
                entry["critic_scorecard"] = critic_scorecard
                if not findings or revisions >= int(crit["rounds"]):
                    break
                reply, used = await generate(llm, cfg, [{"role": "user", "content": REVISE.format(
                    prompt=base_prompt, script=script, findings=render(findings))}])
                tokens.update(used)
                (out / f"response_pass{pass_no + 1}.txt").write_text(reply, encoding="utf-8")
                revised = extract_block(reply, "python")
                entry["addressed_rules"] = sorted(entry["rules"])
                if not revised:
                    entry["revision"] = "no code block"
                    break
                error = run_serializer(out, revised, out / f"graph_pass{pass_no + 1}.jsonld", cfg, tag=f"_pass{pass_no + 1}")
                for attempt in range(int(crit.get("fix_attempts", 1))):
                    if not error:
                        break
                    entry.setdefault("fix_attempts", []).append(error[:300])
                    reply, used = await generate(llm, cfg, [{"role": "user", "content": FIX.format(
                        prompt=base_prompt, script=revised, error=error[-1500:])}])
                    tokens.update(used)
                    (out / f"response_pass{pass_no + 1}_fix{attempt + 1}.txt").write_text(reply, encoding="utf-8")
                    fixed = extract_block(reply, "python")
                    if not fixed:
                        break
                    revised = fixed
                    error = run_serializer(out, revised, out / f"graph_pass{pass_no + 1}.jsonld", cfg, tag=f"_pass{pass_no + 1}")
                if error:
                    entry["revision"] = error[:500]
                    break
                script = revised
                revisions += 1
                shutil.copy(out / f"graph_pass{pass_no + 1}.jsonld", graph)
                shutil.copy(out / f"serializer_pass{pass_no + 1}.py", serializer)
                entry["revision"] = "ok"
                text, _ = await call_tool(session, "submit_critic_revision", {
                    "session_id": session_id, "graph_path": str(graph), "serializer_path": str(serializer),
                    "source_paths": docs, "change_summary": f"revision {revisions} addressing {', '.join(entry['addressed_rules'])}",
                    "addressed_finding_ids": [f["finding_id"] for f in findings if f.get("finding_id")][:200]})
                result = parse(text)
                pass_no += 1
                (out / f"critic_pass{pass_no}.json").write_text(text, encoding="utf-8")
                if not result.get("ok"):
                    entry["submit_error"] = result.get("error") or text[:300]
                    break
            text, _ = await call_tool(session, "finalize_critic_review", {"session_id": session_id})
            final = parse(text)
            (out / "critic_final.json").write_text(text, encoding="utf-8")
            info["final_outcome"] = final.get("outcome") if final.get("ok") else \
                f"not finalized: {final.get('code') or final.get('error')}"
    info["passes"] = passes
    info["pass_validations"] = [p.get("conforms") for p in passes]
    info["qa_rounds"] = sum(1 for p in passes if p.get("revision") == "ok")
    info["tokens"] = dict(tokens)
    return info


if __name__ == "__main__":
    main(ARM, run_case)
