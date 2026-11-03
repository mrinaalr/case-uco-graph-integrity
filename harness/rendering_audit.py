"""Minimal-pair audit of the hook's plain rendering (data_dev only; data/ is test-only).

For each true edge of each dev gold graph that has a confusable reading (a message's sentTime and receivedTime, an
account's issuer and its owner, and the other relation kinds the task allows between the same two entities, either
way round), renders the edge and each competing reading with the plain template and scores both against the passage
that states the edge: its gold sentence, inside its header block (--passages block). The premise is the right hook's
(passage plus the CASE/UCO definitions in play; hook.contrast_scores). Reports, per (true, competing) pair, how often
NLI ranks the true reading above the competitor and by what margin, in log-odds of entailment. Templates are
unchanged; no graph is written.

    python harness/rendering_audit.py [--cases case_01,...] [--run-id rendering-audit]
"""

from __future__ import annotations

import argparse
import json
import statistics
import tomllib
from collections import defaultdict

from graphkit import HARNESS, graph_triples, load_graph
from hook import Verifier, competitors, context, header_blocks, holder_classes, kind_of, label, logit, render
from llm import CONFIG, case_dirs, passages
from score import score_case

TIMES = {"sentTime": "receivedTime"}  # the task's properties (TYPES) give sentTime no competitor
MARGIN = 2.0  # the right hook's contrast margin (config.toml)


def name(t: dict, edge: dict | None = None) -> str:
    """'Reports_To', 'Reports_To reversed' (a relation read the other way round), 'accountIssuer'."""
    reversed_ = edge is not None and kind_of(t) and kind_of(edge) and t["s"] != edge["s"]
    return (kind_of(t) or t["p"]) + (" reversed" if reversed_ else "")


def rivals(t: dict, entities: dict, classes: dict[str, set]) -> list[dict]:
    if t["lit"]:
        return [{**t, "p": TIMES[t["p"]]}] if t["p"] in TIMES else []
    return competitors(t, entities, classes) if kind_of(t) or t["p"] == "accountIssuer" else []


def pairs(case_dir) -> list[dict]:
    """The case's minimal pairs: {case, true, competitor, passage, context, own, rival}."""
    graph = case_dir / "gold.jsonld"
    g = load_graph(graph)
    entities, triples = graph_triples(g)
    classes = {iri: holder_classes(g, iri) for iri in {x for t in triples for x in (t["s"], t["o"]) if not t["lit"] or x == t["s"]}}
    for iri, e in list(entities.items()):  # as in hook.hook_stages: an entity with no literal is named by what it links to
        linked = next((n for vs in e["props"].values() for o in vs if o in entities and (n := label(o, entities))), None)
        if not label(iri, entities) and linked:
            entities[iri] = {**e, "props": {**e["props"], "linked": [linked[1]]}}
    spans = json.loads((case_dir / "spans.json").read_text())
    span_of = {t["tid"]: spans[t["span_id"]] for t in json.loads((case_dir / "gold.json").read_text())["triples"]}
    tid_of = {(s, p, o): tid for s, p, o, tid in score_case(case_dir, graph)["matched"]}
    source = header_blocks(passages(case_dir))
    out = []
    for t in triples:
        tid, rs = tid_of.get((t["s"], t["p"], t["o"])), rivals(t, entities, classes)
        if tid is None or not rs:
            continue
        span = span_of[tid]
        passage = next((p["text"] for p in source if p["doc"] == span["doc_id"] and p["start"] is not None
                        and p["start"] <= span["start"] and span["end"] <= p["end"]), span["text"])
        own, ctx = render(t, entities, "plain"), context(t, rs, entities)
        out += [{"case": case_dir.name, "true": name(t), "competitor": name(r, t), "passage": passage, "context": ctx,
                 "own": own, "rival": render(r, entities, "plain")} for r in rs]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", help="comma-separated case ids (default: all of data_dev)")
    ap.add_argument("--run-id", default="rendering-audit", help="rows go to results/RUN/pairs.jsonl")
    args = ap.parse_args()
    rows = [r for d in case_dirs(args.cases, "data_dev") for r in pairs(d)]
    with open(CONFIG, "rb") as fh:
        verifier = Verifier(tomllib.load(fh)["hook"])
    premises = [f"{r['passage']} {r['context']}".strip() for r in rows]
    own = verifier.entailment(premises, [r["own"] for r in rows])
    rival = verifier.entailment(premises, [r["rival"] for r in rows])
    for r, a, b in zip(rows, own, rival):
        r.update(own_entailment=a, rival_entailment=b, margin=round(logit(a) - logit(b), 2))
    out = HARNESS / "results" / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "pairs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    groups = defaultdict(list)
    for r in rows:
        groups[(r["true"], r["competitor"])].append(r)
    print(f"{len(rows)} minimal pairs from {len({r['case'] for r in rows})} dev cases; margin = log-odds(true) - "
          f"log-odds(competitor); the right hook removes a true edge when the margin is below -{MARGIN}\n")
    print("| true | competitor | n | true ranked higher | median margin | margin < -2 | same sentence |")
    print("|---|---|---|---|---|---|---|")
    for (t, c), rs in sorted(groups.items()):
        m = [r["margin"] for r in rs]
        print(f"| {t} | {c} | {len(rs)} | {sum(x > 0 for x in m)}/{len(rs)} | {statistics.median(m):+.2f} | "
              f"{sum(x < -MARGIN for x in m)} | {sum(r['own'] == r['rival'] for r in rs)} |")


if __name__ == "__main__":
    main()
