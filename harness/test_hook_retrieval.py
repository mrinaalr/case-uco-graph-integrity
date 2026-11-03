"""The hook retrieves the gold sentence for an edge under the full template (#3). For each edge below (dev gold, the
full template's sentence), the sentence that states it must be among the top_k passages retrieved with the query
the mode chooses. Loads only the pinned embedder, on the CPU; no NLI.

    python harness/test_hook_retrieval.py [--query rendered|plain]
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import Counter

from sentence_transformers import SentenceTransformer

from graphkit import HARNESS, graph_triples, load_graph
from hook import render, top_passages
from llm import CONFIG, passages
from score import norm_text, score_case

# Edges lost to definition text alone: the plain template's query retrieves the gold sentence, the full template's
# does not (hook-v1 code). Edges every template misses, such as an email address beside other addresses at its domain,
# are a different cause and are not tested here.
EDGES = {"case_01": ["t14", "t72"], "case_02": ["t50", "t2"], "case_03": ["t8", "t5"]}


def report(embedder: SentenceTransformer, k: int) -> None:
    """Every true edge of every dev gold graph: is its gold sentence in the top k, per template and query mode;
    and do the three templates retrieve the same passages."""
    hits, same, n = Counter(), Counter(), 0
    for case_dir in sorted(p for p in (HARNESS / "data_dev").iterdir() if p.is_dir()):
        graph = case_dir / "gold.jsonld"
        tid_of = {(s, p, o): tid for s, p, o, tid in score_case(case_dir, graph)["matched"]}
        spans = json.loads((case_dir / "spans.json").read_text())
        span_of = {t["tid"]: spans[t["span_id"]] for t in json.loads((case_dir / "gold.json").read_text())["triples"]}
        entities, triples = graph_triples(load_graph(graph))
        triples = [t for t in triples if (t["s"], t["p"], t["o"]) in tid_of]
        source = passages(case_dir)
        for mode in ("rendered", "plain"):
            tops = {}
            for template in ("full", "labels", "plain"):
                queries = [render(t, entities, "plain" if mode == "plain" else template) for t in triples]
                tops[template], _ = top_passages(embedder, queries, source, k)
                for t, top in zip(triples, tops[template]):
                    span = span_of[tid_of[(t["s"], t["p"], t["o"])]]
                    hits[(mode, template)] += any(source[j]["doc"] == span["doc_id"] and norm_text(span["text"]) in
                                                  norm_text(source[j]["text"]) for j in top)
            same[mode] += sum(set(a) == set(b) == set(c) for a, b, c in zip(tops["full"], tops["labels"], tops["plain"]))
        n += len(triples)
    print(f"{n} true edges, {len(list((HARNESS / 'data_dev').iterdir()))} dev gold graphs; gold sentence in top {k}:")
    for mode in ("rendered", "plain"):
        rates = ", ".join(f"{t} {hits[(mode, t)]}/{n} = {hits[(mode, t)] / n:.1%}" for t in ("full", "labels", "plain"))
        print(f"  --query {mode}: {rates}; same top {k} under all three templates: {same[mode]}/{n}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="rendered", choices=("rendered", "plain"))
    ap.add_argument("--report", action="store_true", help="retrieval over every dev gold edge instead of the test")
    args = ap.parse_args()
    with open(CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)["hook"]
    embedder = SentenceTransformer(cfg["embed_model"], revision=cfg["embed_revision"], device="cpu")
    if args.report:
        return report(embedder, cfg["top_k"])
    failures, n = [], 0
    for case, tids in EDGES.items():
        case_dir = HARNESS / "data_dev" / case
        graph = case_dir / "gold.jsonld"
        edge_of = {tid: (s, p, o) for s, p, o, tid in score_case(case_dir, graph)["matched"]}
        spans = json.loads((case_dir / "spans.json").read_text())
        span_of = {t["tid"]: spans[t["span_id"]] for t in json.loads((case_dir / "gold.json").read_text())["triples"]}
        entities, triples = graph_triples(load_graph(graph))
        source = passages(case_dir)
        for tid in tids:
            t = next(x for x in triples if (x["s"], x["p"], x["o"]) == edge_of[tid])
            query = render(t, entities, "plain" if args.query == "plain" else "full")
            top, _ = top_passages(embedder, [query], source, cfg["top_k"])
            got = [source[j] for j in top[0]]
            span = span_of[tid]
            n += 1
            if not any(p["doc"] == span["doc_id"] and norm_text(span["text"]) in norm_text(p["text"]) for p in got):
                failures.append(f"{case} {tid} {t['p']}: gold {span['text'][:50]!r} not in top {cfg['top_k']}; "
                                f"top 1 {got[0]['text'][:40]!r}")
    if failures:
        sys.exit("FAIL\n" + "\n".join(failures))
    print(f"ok: the gold sentence is retrieved for all {n} edges")


if __name__ == "__main__":
    main()
