"""The meaning scorer answers gold's questions from gold exactly, and breaks the questions an edge carries when the
edge is gone (harness/test_meaning.py as a pytest). No model is loaded."""

from __future__ import annotations

import rdflib
from case_uco.graph import DEFAULT_CONTEXT

from graphkit import graph_triples, load_graph
from hook import remove
from meaning import score_graph


def test_gold_is_exact_against_itself(dev_cases):
    for case in dev_cases:
        for h, c in score_graph(case, case / "gold.jsonld").items():
            assert c["exact"] == c["questions"], (case.name, h, c)
            assert c["produced_right"] == c["produced"], (case.name, h, c)


def test_removing_an_edge_breaks_its_questions_only(dev_cases, tmp_path):
    for case in dev_cases:
        gold = case / "gold.jsonld"
        full = score_graph(case, gold)
        g = load_graph(gold)
        _, triples = graph_triples(g)
        edge = next(t for t in triples if t["p"] == "Employed_By")
        remove(g, edge, {str(x): x for x in g.all_nodes() if not isinstance(x, rdflib.Literal)})
        path = tmp_path / f"{case.name}.jsonld"
        g.serialize(destination=path, format="json-ld", context=DEFAULT_CONTEXT, indent=2)
        cut = score_graph(case, path)
        for h in full:
            assert cut[h]["exact"] < full[h]["exact"], (case.name, h)
            assert cut[h]["produced_right"] == cut[h]["produced"], (case.name, h)
