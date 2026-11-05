"""Forward recovery: duplicates merge onto one entity with every claim rewritten; a message gains its header facts
by rule; a proposal is held to the proposal bar and never added when a stated claim entails it; a provisional entity
with no accepted link leaves. Stub verifier; the selector's dev `dropped` graphs when they are there."""

from __future__ import annotations

import json

import pytest

from graphkit import HARNESS, graph_triples
from reconcile.ingest import ingest
from reconcile.ledger import PROPOSED, STATED, SUPPORTED
from reconcile.policy import added, decide
from reconcile.propose import from_headers, from_llm, from_readings, propose_pass
from reconcile.readings import readings_pass
from reconcile.resolve import Resolver, drop_unlinked, merge_duplicates
from reconcile.source import Source
from reconcile.verify import verify

DROPPED = HARNESS / "results" / "sel-dev" / "dropped"


def test_merge_rewrites_claims_onto_one_entity(dev_cases, tmp_path):
    case = dev_cases[0]
    path = tmp_path / "dup.jsonld"
    text = (case / "gold.jsonld").read_text()
    doc = json.loads(text)
    # Duplicate the first Person node under a new IRI with the same name.
    person = next(n for n in doc["@graph"] if n.get("@type") == "uco-identity:Person" and "uco-core:name" in n)
    twin = {**person, "@id": person["@id"] + "-twin"}
    doc["@graph"].append(twin)
    path.write_text(json.dumps(doc))
    led, _ = ingest(path)
    n_before = len(led.entities)
    merged = merge_duplicates(led)
    assert merged and len(led.entities) == n_before - 1
    keep = merged[0][0]
    assert all(c.s != person["@id"] + "-twin" for c in led.claims.values())
    assert any(c.s == keep for c in led.stated())


def test_header_facts_are_proposed_and_decided_by_rule(dev_cases, verifier, tmp_path):
    case = dev_cases[0]
    doc = json.loads((case / "gold.jsonld").read_text())
    # Strip every sentTime from the gold graph: the header rule should propose them back.
    for n in doc["@graph"]:
        n.pop("uco-observable:sentTime", None)
    path = tmp_path / "nosent.jsonld"
    path.write_text(json.dumps(doc))
    led, _ = ingest(path)
    src = Source(case / "docs")
    verify(led, src, verifier)
    made = from_headers(led, src)
    sent = [c for c in made if c.p == "sentTime"]
    assert sent
    verify(led, src, verifier, made)
    readings_pass(led, src, verifier, 2.0, claims=list(led), on="all")
    led.meta["add_at"] = 0.9
    decide(led, "conservative", 2.0)
    for c in sent:
        assert c.checks["header"]["result"] == "pass", c.checks["header"]
        assert c.status == SUPPORTED and c in added(led, "conservative")


def test_implied_readings_are_not_added(dev_cases, verifier):
    case = dev_cases[0]
    led, _ = ingest(case / "gold.jsonld")
    src = Source(case / "docs")
    verify(led, src, verifier)
    made = from_readings(led)
    initiated = {(c.s, c.o) for c in led.stated() if c.p == "Initiated"}
    assert not any(c.p == "Participated_In" and (c.s, c.o) in initiated for c in made)
    assert all(c.origin == PROPOSED for c in made)
    linked = {frozenset((c.s, c.o)) for c in led.stated() if not c.lit}
    assert made and all((c.note or "").startswith("repair-of:") == (frozenset((c.s, c.o)) in linked) for c in made), \
        "a reading of a pair the graph already links is a repair of that link"


def test_llm_facts_resolve_or_are_rejected_with_a_reason(dev_cases, verifier):
    case = dev_cases[0]
    led, _ = ingest(case / "gold.jsonld")
    src = Source(case / "docs")
    verify(led, src, verifier)
    person = next(e for e in led.entities.values() if e.cls == "Person")
    name = person.props["name"][0]
    proposal = {"docs": [{"doc": "D1", "facts": [
        [f"Person: {name}", "name", name],                       # states the key: no new claim
        [f"Person: {name}", "Employed_By", "Organization: Nowhere Holdings"],  # key not a span: rejected
        ["Person: Zz", "name", "Zz"],                            # not a span
    ]}]}
    made, rejected = from_llm(led, src, proposal)
    reasons = " ".join(r["why"] for r in rejected)
    assert "not a span" in reasons
    assert all(c.origin == PROPOSED for c in made)
    res = Resolver(led, src)
    assert res.resolve(None, f"Person: {name}")[0] == person.id
    assert isinstance(res.resolve(None, "Person: Nobody At All"), str)
    where = next(e for e in led.entities.values() if e.cls == "Location" and e.props.get("street"))
    assert res.resolve(None, f"Location: {where.props['street'][0]}, Nowhere, XX 00000")[0] == where.id, \
        "an address names its location by its street"
    r = res.resolve(None, f"Event: {name}")  # a span of the source that names no event
    assert isinstance(r, str) and "not proposed new" in r
    assert not any(e.cls == "Event" and e.origin == PROPOSED for e in led.entities.values())


def test_dropped_edges_can_be_recovered(verifier):
    if not DROPPED.exists():
        pytest.skip("no sel-dev dropped graphs locally")
    case = sorted(DROPPED.glob("case_*"))[0]
    gone = json.loads((case / "dropped.json").read_text())
    led, _ = ingest(case / "graph.jsonld")
    src = Source(HARNESS / "data_dev" / case.name / "docs")
    verify(led, src, verifier)
    propose_pass(led, src, verifier, 2.0, 0.9)
    readings_pass(led, src, verifier, 2.0, claims=list(led), on="all")
    decide(led, "conservative", 2.0)
    drop_unlinked(led, {c.id for c in added(led, "conservative")})
    proposed = {(c.s, c.p, c.o) for c in led.by_origin(PROPOSED)}
    missing = {(d["s"], d["p"], d["o"]) for d in gone} if isinstance(gone, list) and gone and "s" in gone[0] else set()
    if missing:
        assert proposed & missing, "none of the dropped edges was even proposed"
