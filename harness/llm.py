"""Config, endpoints, the shared prompt, the case-uco server, and the per-arm run loop."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import time
import tomllib
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

from case_uco.graph import DEFAULT_CONTEXT
from graphkit import HARNESS, REPO, RELATION_KINDS, SCHEMA, case_validate, class_list

CONFIG = HARNESS / "config.toml"
SDK = REPO / "sdk"  # the SDK under test, a submodule pinned to a release tag


def sdk_version() -> str:
    return subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=SDK,
                          capture_output=True, text=True).stdout.strip()
ENV_FILE = HARNESS / ".env"


def load_env_file() -> None:
    """Read KEY=VALUE lines from harness/.env without overriding the real environment."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def load_config(path: Path | None = None, model: str | None = None) -> dict:
    """Merge [llm] defaults with the named [models.<name>] endpoint."""
    with open(path or CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)
    name = model or cfg["llm"]["default_model"]
    endpoint = cfg["models"].get(name)
    if not endpoint or not endpoint.get("base_url") or not endpoint.get("model"):
        raise SystemExit(f"config: [models.{name}] needs base_url and model")
    cfg["llm"] = {**cfg["llm"], **endpoint, "name": name}
    load_env_file()
    env = endpoint.get("api_key_env")
    cfg["llm"]["api_key"] = os.environ.get(env, "") if env else "local"
    return cfg


def client(cfg: dict) -> AsyncOpenAI:
    llm = cfg["llm"]
    return AsyncOpenAI(base_url=llm["base_url"], api_key=llm["api_key"] or "none",
                       timeout=llm.get("request_timeout_s", 600))


def case_dirs(selection: str | None) -> list[Path]:
    """All cases, or a comma-separated list like 'case_01,case_07'."""
    dirs = sorted(p for p in (HARNESS / "data").iterdir() if p.is_dir())
    if selection:
        wanted = set(selection.split(","))
        dirs = [d for d in dirs if d.name in wanted]
    return dirs


def documents(case_dir: Path) -> str:
    gold = json.loads((case_dir / "gold.json").read_text())
    parts = []
    for doc_id, kind in gold["documents"].items():
        text = (case_dir / "docs" / f"{doc_id}.marked.txt").read_text().strip()
        parts.append(f"=== Document {doc_id} ({kind}) ===\n{text}")
    return "\n\n".join(parts)


# --- Prompt shared verbatim by every arm -------------------------------------------

CLASSES = [c for c in (
    "Person", "Organization", "Identity", "Role", "Location", "SimpleAddressFacet", "EmailAddress",
    "EmailAddressFacet", "EmailAccount", "EmailAccountFacet", "Account", "AccountFacet", "DigitalAccountFacet",
    "ApplicationAccount", "ApplicationAccountFacet", "PhoneAccount", "PhoneAccountFacet", "EmailMessage",
    "EmailMessageFacet", "Message", "MessageFacet", "MessageThread", "Event", "Action", "Relationship",
    "Note", "NoteFacet", "File", "FileFacet", "URL", "URLFacet") if c in SCHEMA]

EXAMPLE = {
    "@context": {k: DEFAULT_CONTEXT[k] for k in ("kb", "uco-core", "uco-observable", "xsd")},
    "@graph": [
        {"@id": "kb:file-1", "@type": "uco-observable:File", "uco-core:hasFacet": [{"@id": "kb:file-1-facet"}]},
        {"@id": "kb:file-1-facet", "@type": "uco-observable:FileFacet", "uco-observable:fileName": "report.pdf"},
        {"@id": "kb:rel-1", "@type": "uco-core:Relationship", "uco-core:source": {"@id": "kb:file-1"},
         "uco-core:target": {"@id": "kb:other-node"}, "uco-core:kindOfRelationship": "Located_At",
         "uco-core:isDirectional": {"@type": "xsd:boolean", "@value": "true"}},
    ],
}

RELATIONS = "\n".join(f"- {k}: {v}" for k, v in RELATION_KINDS.items())

SHARED = f"""Modeling rules:
- Model only facts the documents state. Do not infer, summarize, or add commentary.
- One node per real-world thing, even when it appears in several documents.
- Use core CASE/UCO classes only (no extension ontologies).
- Observable objects (email addresses, accounts, messages) carry their data in facets.
- Connect things with uco-core:Relationship nodes whose kindOfRelationship is exactly one of:
{RELATIONS}
- Write dates and times as ISO 8601 in UTC, e.g. 2025-03-04T10:15:00Z.
- Every sentence in the documents carries an id like [D1.S3]; cite the ids that state each fact.

Available classes (prefix:Class (kind): property<range>, ...):
{class_list(CLASSES)}

CASE JSON-LD shape (illustrative only):
{json.dumps(EXAMPLE, indent=1)}

Typed literals: dateTime and boolean values are {{"@type": "xsd:dateTime", "@value": ...}}."""


# --- case-uco MCP server -------------------------------------------------------------

def server_params(cfg: dict) -> StdioServerParameters:
    srv = cfg["server"]
    return StdioServerParameters(
        command=str(REPO / srv["python"]), args=[str(REPO / srv["script"])],
        env={"PYTHONPATH": f"{SDK / 'python'}:{SDK / 'mcp_server'}", "PATH": f"{REPO / '.venv' / 'bin'}:/usr/bin:/bin",
             "CASE_UCO_EXTENSIONS": srv.get("extensions", "")})


@asynccontextmanager
async def server_session(cfg: dict, errlog):
    async with stdio_client(server_params(cfg), errlog=errlog) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


async def call_tool(session: ClientSession, name: str, args: dict) -> tuple[str, bool]:
    res = await session.call_tool(name, args)
    return "\n".join(getattr(c, "text", "") for c in res.content), bool(res.isError)


def conforms_of(validate_text: str) -> bool | None:
    try:
        return json.loads(validate_text).get("conforms")
    except (json.JSONDecodeError, AttributeError):
        return None


# --- Per-arm run loop ----------------------------------------------------------------

def tokens_of(resp) -> dict:
    u = resp.usage
    return {"prompt": (u.prompt_tokens or 0) if u else 0, "completion": (u.completion_tokens or 0) if u else 0}


async def _run_all(arm: str, run_case, args) -> None:
    cfg = load_config(Path(args.config) if args.config else None, args.model)
    llm = client(cfg)
    meta = {"arm": arm, "endpoint": cfg["llm"]["name"], "model": cfg["llm"]["model"], "base_url": cfg["llm"]["base_url"],
            "temperature": cfg["llm"].get("temperature", 0), "sdk_version": sdk_version()}
    cases = case_dirs(args.cases)
    run_start = time.monotonic()
    for done, case_dir in enumerate(cases, 1):
        out = HARNESS / "results" / args.run_id / arm / case_dir.name
        out.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        try:
            info = await asyncio.wait_for(run_case(case_dir, out, cfg, llm), cfg["run"]["case_timeout_s"])
        except Exception as exc:  # any failure is a recorded outcome, not a crash of the run
            while isinstance(exc, BaseExceptionGroup) and exc.exceptions:  # MCP task groups wrap the cause
                exc = exc.exceptions[0]
            info = {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:2000]}
        info.setdefault("tokens", {"prompt": 0, "completion": 0})
        graph = out / "graph.jsonld"
        ok = info["status"] not in ("error", "empty") and graph.exists()
        info["final_validation"] = case_validate(graph)["conforms"] if ok else None
        info["wall_s"] = round(time.monotonic() - start, 1)
        (out / "run.json").write_text(json.dumps({"case_id": case_dir.name, **meta, **info}, indent=1))
        elapsed = time.monotonic() - run_start
        eta_min = (len(cases) - done) * elapsed / done / 60  # mean time per case so far
        print(f"{arm} {case_dir.name}: {info['status']} valid={info['final_validation']} wall={info['wall_s']}s "
              f"[{done}/{len(cases)}, {elapsed / 60:.1f} min elapsed, ~{eta_min:.1f} min left]", flush=True)


def main(arm: str, run_case) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--model", help="endpoint name from [models] in config.toml (default: llm.default_model)")
    ap.add_argument("--cases", help="comma-separated case ids (default: all)")
    ap.add_argument("--config")
    asyncio.run(_run_all(arm, run_case, ap.parse_args()))
