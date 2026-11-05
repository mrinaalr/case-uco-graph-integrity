"""Emit: a provisional entity reaches the graph only with an accepted link, and then with its class, facet and key;
the original is kept byte for byte; provenance names every removal and addition. Stub verifier."""

from __future__ import annotations

import json

from graphkit import graph_triples
from reconcile.emit import emit
from reconcile.ingest import ingest
from reconcile.ledger import PROPOSED, SUPPORTED, Entity
from reconcile.policy import added
from reconcile.source import Source
from reconcile.verify import verify


def test_provisional_entity_enters_with_its_link_only(dev_cases, verifier, tmp_path):
    case = dev_cases[0]
    led, _ = ingest(case / "gold.jsonld")
    verify(led, Source(case / "docs"), verifier)
    person = next(e for e in led.entities.values() if e.cls == "Person")
    new = led.add_entity(Entity("http://example.org/kb/rec-organization-1", "Organization", {"name": ["Nowhere Holdings"]},
                                ["http://example.org/kb/rec-organization-1"], PROPOSED))
    link = led.add_claim(person.id, "Employed_By", new.id, False, "rel", PROPOSED)
    link.status = SUPPORTED
    orphan = led.add_entity(Entity("http://example.org/kb/rec-organization-2", "Organization", {"name": ["Orphan Ltd"]},
                                   ["http://example.org/kb/rec-organization-2"], PROPOSED))
    for c in led.stated():
        c.status = SUPPORTED
    assert link in added(led, "conservative")
    info = emit(led, case / "gold.jsonld", tmp_path, "conservative", {})
    ents, triples = graph_triples(tmp_path / "graph.jsonld")
    assert new.id in ents and ents[new.id]["class"] == "Organization" and ents[new.id]["props"]["name"] == ["Nowhere Holdings"]
    assert orphan.id not in ents
    assert any(t["s"] == person.id and t["p"] == "Employed_By" and t["o"] == new.id for t in triples)
    assert info["added"] == 1 and info["removed"] == 0
    assert (tmp_path / "input" / "graph.jsonld").read_bytes() == (case / "gold.jsonld").read_bytes()
    prov = json.loads((tmp_path / "provenance.jsonld").read_text())
    kinds = [n["@type"] for n in prov["@graph"]]
    assert "case-investigation:InvestigativeAction" in kinds
    assert any(n["@id"].startswith("kb:added-") for n in prov["@graph"])
