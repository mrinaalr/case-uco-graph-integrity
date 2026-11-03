"""The competitors hook.py --contrast sets against an edge are the readings the ontology allows, and only those.
Model-free: renders the competitors of dev case_01 gold edges with the plain template and compares them to the
expected sets.

    python harness/test_hook_contrast.py
"""

from __future__ import annotations

import sys

from graphkit import HARNESS, graph_triples, load_graph
from hook import competitors, header_blocks, render
from llm import passages

CASE = HARNESS / "data_dev" / "case_01"
# Plain rendering of a gold edge -> the plain renderings of its competitors.
EXPECTED = {
    # A person and an event: the other two kinds whose domain and range fit; an event cannot point back to a person.
    "Elena Okafor authorized payment approval.": {"Elena Okafor participated in payment approval.",
                                                 "Elena Okafor initiated payment approval."},
    # Not symmetric: the reverse competes; communicated with fits the same pair.
    "Elena Okafor reports to Dana Fischer.": {"Elena Okafor communicated with Dana Fischer.",
                                              "Dana Fischer reports to Elena Okafor."},
    # An organization and an account: the account's issuer is the other reading of the pair.
    "Oakhaven Freight Co. owns 3274469086.": {"The account issuer of 3274469086 is Oakhaven Freight Co.."},
    # Nothing else fits an organization and a location.
    "Stonebridge Services Group is located at 6563 Lakeview Road.": set(),
}


def main() -> None:
    entities, triples = graph_triples(load_graph(CASE / "gold.jsonld"))
    doc = " ".join(p["text"] for p in header_blocks(passages(CASE)))
    got = {render(t, entities, "plain"): {render(c, entities, "plain") for c in competitors(t, entities, triples, doc)}
           for t in triples}
    failures = [f"{edge}\n  expected {sorted(want)}\n  got      {sorted(got.get(edge, {'(edge not in graph)'}))}"
                for edge, want in EXPECTED.items() if got.get(edge) != want]
    # A single-valued time competes with the other times the graph and the document give; a many-valued one does not.
    sent = [t for t in triples if t["p"] == "sentTime"]
    start = [t for t in triples if t["p"] == "startTime"]
    if not all(any(c["p"] == "sentTime" for c in competitors(t, entities, triples, doc)) for t in sent):
        failures.append("sentTime (single-valued): no competing time")
    if any(c["p"] == "startTime" and c["o"] != t["o"] for t in start for c in competitors(t, entities, triples, doc)):
        failures.append("startTime (many-valued in UCO): competing times")
    if failures:
        sys.exit("FAIL\n" + "\n".join(failures))
    print(f"ok: {len(EXPECTED)} edges have exactly the competitors the ontology allows; sentTime competes, startTime does not")


if __name__ == "__main__":
    main()
