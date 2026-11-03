"""Meaning scorer: does the graph answer the case's questions the way the evidence does?

Competency questions are generated from each gold graph and asked of the gold graph and of the graph under test
alike. A question starts from a value an investigator would query by (an entity's key literal: a person's name, an
address, an account number, a message's subject, an event's type) and follows a path of one or two steps:

- 1-hop: a property or relation out of, or into, the entity. "Who owns account 2622357143?", "When was the message
  'Quarter-end vendor payments' sent?"
- 2-hop: two steps through an intermediate entity. "Which organization employs the sender of message M?" A 2-hop
  question breaks when the graph splits one thing into two nodes, merges two, or links the wrong ones, so it tests the
  graph's structure, which per-edge scores cannot see.

The answer is a set: literal values, or entities (named by their key literal). Each side starts from every entity of
a compatible class whose literals hold the queried value, as a SPARQL query by value would. A produced answer matches
a gold one under the value scorer's rules (score.value_matches, score.address_in). Per question: answer recall (gold
answers found), answer precision (produced answers that are gold answers), and exact (both complete). Owns_Account
and AccountFacet.owner are one fact; Communicated_With is symmetric.

Writes meaning.json per case next to the graph and results/RUN/meaning.md.

    python harness/meaning.py --run-id RUN [--data data_dev] [--arms a,b]
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

from graphkit import HARNESS, graph_triples
from score import COMPATIBLE, KEYS, address_in, linked_keys, norm, norm_kind, value_matches

HOPS = (1, 2)
logging.getLogger("rdflib").setLevel(logging.CRITICAL)  # ill-typed literals in graphs under test are expected


def view(path: Path) -> dict:
    """A graph as entities (class, literals with linked keys), object steps and literal steps."""
    ents, triples = graph_triples(path)
    props = linked_keys({i: e["props"] for i, e in ents.items()},
                        {(t["s"], t["p"]): t["o"] for t in triples if not t["lit"]})
    nxt, lits = defaultdict(set), defaultdict(lambda: defaultdict(set))
    for t in triples:
        if t["lit"]:
            lits[t["s"]][t["p"]].add(t["o"])
            continue
        s, p, o = t["s"], norm_kind(t["p"]) if t["origin"].startswith("rel|") else t["p"], t["o"]
        if p == "owner":  # AccountFacet.owner states owner Owns_Account account
            s, p, o = o, "owns_account", s
        if p == "communicated_with":
            nxt[(s, p, "~")].add(o)
            nxt[(o, p, "~")].add(s)
            continue
        nxt[(s, p, ">")].add(o)
        nxt[(o, p, "<")].add(s)
    return {"ents": {i: {"class": e["class"], "props": props[i]} for i, e in ents.items()}, "next": nxt, "lits": lits}


def compatible(cls: str, gold_cls: str) -> bool:
    return cls == gold_cls or cls in COMPATIBLE.get(gold_cls, set())


def anchor(e: dict) -> tuple[str, str] | None:
    """The entity's key (property, normalized value), as an investigator would query it."""
    keys = KEYS.get(e["class"])
    v = e["props"].get(keys[0]) if keys else None
    return (keys[0], norm(keys[0], v[0])) if v else None


def holds(e: dict, gold_cls: str, gold_props: dict, key: tuple[str, str]) -> bool:
    """Does entity e (any graph) carry this gold key, as the value scorer aligns it?"""
    if not compatible(e["class"], gold_cls):
        return False
    literals = [v for vs in e["props"].values() for v in vs if not v.startswith(("http://", "https://"))]
    if any(value_matches(key[0], key[1], v) for v in literals):
        return True
    return gold_cls == "Location" and any(address_in(gold_props, v) for v in literals)


def start(v: dict, gold_cls: str, gold_props: dict, key: tuple[str, str]) -> set[str]:
    return {i for i, e in v["ents"].items() if holds(e, gold_cls, gold_props, key)}


def walk(v: dict, nodes: set[str], path: tuple) -> tuple[set[str], bool]:
    """(answers, whether they are literals) after following path from nodes."""
    for p, d in path:
        if d == "lit":
            return {x for n in nodes for x in v["lits"].get(n, {}).get(p, ())}, True
        nodes = {x for n in nodes for x in v["next"].get((n, p, d), ())}
    return nodes, False


def steps(v: dict, n: str) -> set[tuple[str, str]]:
    out = {(p, d) for (s, p, d) in v["next"] if s == n}
    return out | {(p, "lit") for p in v["lits"].get(n, {})}


def reverse(step: tuple[str, str]) -> tuple[str, str]:
    p, d = step
    return p, {">": "<", "<": ">"}.get(d, d)


def questions(gold: dict) -> list[dict]:
    """Every 1- and 2-hop question from a gold entity's key, deduplicated by (class, key, path)."""
    out = {}
    for x, e in gold["ents"].items():
        key = anchor(e)
        if not key:
            continue
        for s1 in steps(gold, x):
            if s1 == (key[0], "lit"):
                continue
            out.setdefault((e["class"], key, (s1,)), x)
            if s1[1] == "lit":
                continue
            for y in gold["next"].get((x, *s1), ()):
                y_key = anchor(gold["ents"].get(y, {"class": "", "props": {}}))
                for s2 in steps(gold, y):
                    if s2 == reverse(s1) or (y_key and s2 == (y_key[0], "lit")):
                        continue
                    out.setdefault((e["class"], key, (s1, s2)), x)
    return [{"class": c, "key": k, "path": p, "from": x} for (c, k, p), x in out.items()]


def ask(q: dict, gold: dict, test: dict) -> dict:
    """One question against both graphs: gold answers, produced answers, and how they match."""
    gold_props = gold["ents"][q["from"]]["props"]
    g_ans, lit = walk(gold, start(gold, q["class"], gold_props, q["key"]), q["path"])
    t_ans, _ = walk(test, start(test, q["class"], gold_props, q["key"]), q["path"])
    if lit:
        p = q["path"][-1][0]
        g_norm = {norm(p, a) for a in g_ans}
        hit = {g for g in g_norm if any(value_matches(p, g, a) for a in t_ans)}
        ok = {a for a in t_ans if any(value_matches(p, g, a) for g in g_norm)}
        n_gold = len(g_norm)
    else:
        def is_answer(t_iri: str, g_iri: str) -> bool:
            ge = gold["ents"].get(g_iri)
            k = anchor(ge) if ge else None
            return bool(k) and holds(test["ents"].get(t_iri, {"class": "", "props": {}}), ge["class"], ge["props"], k)
        hit = {g for g in g_ans if any(is_answer(t, g) for t in t_ans)}
        ok = {t for t in t_ans if any(is_answer(t, g) for g in g_ans)}
        n_gold = len(g_ans)
    return {"hops": len(q["path"]), "gold": n_gold, "produced": len(t_ans), "gold_found": len(hit),
            "produced_right": len(ok), "exact": len(hit) == n_gold and len(ok) == len(t_ans)}


def score_graph(case_dir: Path, graph: Path | None) -> dict:
    gold = view(case_dir / "gold.jsonld")
    empty = {"ents": {}, "next": {}, "lits": {}}
    test = view(graph) if graph and graph.exists() else empty
    rows = [ask(q, gold, test) for q in questions(gold)]
    rows = [r for r in rows if r["gold"]]  # a path whose gold answer is empty asks nothing
    out = {}
    for h in HOPS:
        rs = [r for r in rows if r["hops"] == h]
        out[f"hop{h}"] = {k: sum(r[k] for r in rs) for k in ("gold", "produced", "gold_found", "produced_right", "exact")} | \
            {"questions": len(rs)}
    return out


def rates(c: dict) -> dict:
    return {"questions": c["questions"],
            "exact": c["exact"] / c["questions"] if c["questions"] else None,
            "recall": c["gold_found"] / c["gold"] if c["gold"] else None,
            "precision": c["produced_right"] / c["produced"] if c["produced"] else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--arms", help="comma-separated arm folders (default: all)")
    args = ap.parse_args()
    root = HARNESS / "results" / args.run_id
    arms = args.arms.split(",") if args.arms else sorted(p.name for p in root.iterdir() if p.is_dir())
    lines = [f"# Meaning: {args.run_id}", "",
             "Competency questions from each gold graph, asked of the graph under test. exact: the answer set is "
             "complete and has nothing wrong. Micro over questions and answers.", "",
             "| arm | cases | 1-hop questions | 1-hop exact | 1-hop recall | 1-hop precision | 2-hop questions | "
             "2-hop exact | 2-hop recall | 2-hop precision |", "|---|---|---|---|---|---|---|---|---|---|"]
    for arm in arms:
        totals = {f"hop{h}": defaultdict(int) for h in HOPS}
        cases = 0
        for run_dir in sorted((root / arm).glob("case_*")):
            if not (run_dir / "run.json").exists():
                continue
            meta = json.loads((run_dir / "run.json").read_text())
            graph = run_dir / "graph.jsonld" if meta.get("status") not in ("error", "empty") else None
            r = score_graph(HARNESS / args.data / run_dir.name, graph)
            (run_dir / "meaning.json").write_text(json.dumps(r, indent=1))
            cases += 1
            for h, c in r.items():
                for k, v in c.items():
                    totals[h][k] += v
        if not cases:
            continue
        cells = []
        for h in HOPS:
            m = rates(totals[f"hop{h}"])
            cells += [str(m["questions"])] + [f"{m[k]:.3f}" if m[k] is not None else "-" for k in ("exact", "recall", "precision")]
        lines.append(f"| {arm} | {cases} | " + " | ".join(cells) + " |")
    (root / "meaning.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
