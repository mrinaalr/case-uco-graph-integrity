"""LLM proposals: the facts each document states, listed by a language model, cached per case for propose.from_llm.

One call per document, graph-independent, so one proposal file serves every arm and every policy. The model names
each entity "Class: key" and copies values character for character; what it lists is a proposal and nothing more:
propose.from_llm admits a value only as an exact span of a passage and a name only when it resolves to an entity,
and every claim then earns its evidence like a stated one. The vocabulary in the prompt is the profile's.

    python harness/reconcile/propose_llm.py --out results/RUN/proposals --data data_dev [--cases ...] [--model tinker]
                                            [--concurrency 8] [--resume]

Writes <out>/<case>.json: {"docs": [{"doc", "reply", "facts", "error", "tokens"}], "facts", "tokens"}."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/, for the bare-name imports

from graphkit import HARNESS, RELATION_KINDS  # noqa: E402
from llm import client, load_config, tokens_of  # noqa: E402
from reconcile import keys  # noqa: E402
from reconcile.ontology import KIND_CLASSES, LITERAL_PROPS, PROP_CLASSES  # noqa: E402
from reconcile.source import Source  # noqa: E402

PROMPT = """You extract a CASE/UCO knowledge graph from one investigation document, as a list of facts.

Classes, each with its key value and its other values:
{classes}

Links (source -> target):
{links}

Each fact is [subject, property, object]. Name every entity as "Class: key value", e.g. "Person: Dana Fischer",
"Event: vendor onboarding", "EmailMessage: Quarter-end vendor payments", "EmailAccount: dana.fischer@stonebridge.com".
The object of a link is an entity; the object of a value is the value.

Rules:
- Copy every key and value character for character from the document. Write dates and times exactly as the text
  writes them (e.g. "October 4, 2025 at 16:45 UTC", "Thu, 23 Oct 2025 16:00:00 +0000").
- Name an entity the same way in every fact.
- A person who uses an email address holds it (Holds_Account) and holds its EmailAccount, which links to the address
  by emailAddress.
- A message's From:, To: and Date: lines give its from, to and sentTime. Two people communicated when one wrote to
  the other.
- Only what the document states. Do not infer.

Reply with one ```json code block holding the list of facts and nothing else, e.g.
[["Event: vendor onboarding", "startTime", "October 15, 2025 at 09:15 UTC"],
 ["Person: Mei Holloway", "Initiated", "Event: vendor onboarding"]]

=== Document {doc} ===
{text}"""


def vocabulary() -> tuple[str, str]:
    lines = []
    for cls, props in LITERAL_PROPS.items():
        key = keys.KEYS.get(cls, [None])[0]
        rest = [p for p in props if p != key and (cls, p) not in PROP_CLASSES]
        lines.append(f"- {cls}: key {key}" + (f"; {', '.join(rest)}" if rest else ""))
    lines.append("- EmailAccount: key: the address of its emailAddress")
    links = [f"- {k} ({RELATION_KINDS[k]}): {' or '.join(sorted(d))} -> {' or '.join(sorted(r))}" for k, (d, r) in KIND_CLASSES.items()]
    links += [f"- {p}: {c} -> {' or '.join(sorted(r))}" for (c, p), r in PROP_CLASSES.items()]
    links.append("- emailAddress: EmailAccount -> EmailAddress")
    return "\n".join(lines), "\n".join(links)


def parse_reply(text: str) -> tuple[list[list[str]], str | None]:
    import re
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.S)
    block = m.group(1) if m else text[text.find("["): text.rfind("]") + 1]
    try:
        doc = json.loads(block)
    except json.JSONDecodeError:
        return [], "no parseable JSON"
    if isinstance(doc, dict):
        doc = next((v for v in doc.values() if isinstance(v, list)), [])
    facts = [[str(x) for x in f] for f in doc if isinstance(f, list) and len(f) == 3] if isinstance(doc, list) else []
    return facts, None


async def propose(src: Source, cfg: dict, llm, gate: asyncio.Semaphore) -> dict:
    classes, links = vocabulary()

    async def one(doc: str, text: str) -> dict:
        prompt = PROMPT.format(classes=classes, links=links, doc=doc, text=text)
        async with gate:
            resp = await llm.chat.completions.create(
                model=cfg["llm"]["model"], temperature=cfg["llm"]["temperature"], max_tokens=cfg["llm"]["max_tokens"],
                extra_body=cfg["llm"].get("extra_body"), messages=[{"role": "user", "content": prompt}])
        reply = resp.choices[0].message.content or ""
        facts, error = parse_reply(reply)
        return {"doc": doc, "reply": reply, "facts": facts, "error": error, "tokens": tokens_of(resp)}

    docs = await asyncio.gather(*(one(d, t) for d, t in src.docs.items()))
    return {"docs": list(docs), "facts": [f for d in docs for f in d["facts"]],
            "tokens": {k: sum(d["tokens"][k] for d in docs) for k in ("prompt", "completion")},
            "model": cfg["llm"]["model"], "prompt_version": "reconcile/propose_llm.py"}


async def propose_all(cfg: dict, todo: list[tuple[Path, Path]], concurrency: int) -> None:
    llm, gate = client(cfg), asyncio.Semaphore(concurrency)

    async def one(docs: Path, path: Path) -> None:
        try:
            p = await propose(Source(docs, cfg.get("data", {}).get("source", "pdf")), cfg, llm, gate)
        except Exception as exc:  # a failed call is a recorded outcome: the graph is left as it is
            p = {"docs": [], "facts": [], "error": f"{type(exc).__name__}: {exc}", "tokens": {"prompt": 0, "completion": 0}}
        path.write_text(json.dumps(p, indent=1))
        print(f"proposed {docs.parent.name}: {len(p['facts'])} facts "
              f"{[d['error'] for d in p['docs'] if d['error']] or p.get('error', '')}", flush=True)

    await asyncio.gather(*(one(*x) for x in todo))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--cases")
    ap.add_argument("--model", default="tinker")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    cfg = load_config(model=args.model)
    out = args.out if args.out.is_absolute() else HARNESS / args.out
    out.mkdir(parents=True, exist_ok=True)
    wanted = set(args.cases.split(",")) if args.cases else None
    cases = sorted(p for p in (HARNESS / args.data).iterdir() if p.is_dir() and (not wanted or p.name in wanted))
    asyncio.run(propose_all(cfg, [(c / "docs", out / f"{c.name}.json") for c in cases
                                  if not (args.resume and (out / f"{c.name}.json").exists())], args.concurrency))


if __name__ == "__main__":
    main()
