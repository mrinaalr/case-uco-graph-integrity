"""The meaning scorer answers gold's questions from gold exactly, and breaks the questions an edge carries when the
edge is gone. On every dev gold graph: gold scored against itself is exact on every 1- and 2-hop question; with one
Employed_By relation removed, the 1-hop questions about that person's employer and the 2-hop questions through it
lose their answer, and no question gains a wrong one. No model is loaded.

    python harness/test_meaning.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import rdflib
from case_uco.graph import DEFAULT_CONTEXT

from graphkit import HARNESS, graph_triples, load_graph
from hook import remove
from meaning import score_graph


def main() -> None:
    failures = []
    cases = sorted((HARNESS / "data_dev").glob("case_*"))
    for case in cases:
        gold = case / "gold.jsonld"
        full = score_graph(case, gold)
        for h, c in full.items():
            if c["exact"] != c["questions"] or c["produced_right"] != c["produced"]:
                failures.append(f"{case.name} {h}: gold is not exact against itself ({c})")
        g = load_graph(gold)
        _, triples = graph_triples(g)
        edge = next(t for t in triples if t["p"] == "Employed_By")
        remove(g, edge, {str(x): x for x in g.all_nodes() if not isinstance(x, rdflib.Literal)})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.jsonld"
            g.serialize(destination=path, format="json-ld", context=DEFAULT_CONTEXT, indent=2)
            cut = score_graph(case, path)
        for h in full:
            if cut[h]["exact"] >= full[h]["exact"]:
                failures.append(f"{case.name} {h}: removing {edge['p']} broke no question")
            if cut[h]["produced_right"] != cut[h]["produced"]:
                failures.append(f"{case.name} {h}: removing an edge made a wrong answer")
    print(f"{len(cases)} dev gold graphs: {'ok' if not failures else f'{len(failures)} failures'}")
    for f in failures:
        print(" ", f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
