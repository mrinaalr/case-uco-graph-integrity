"""The policy from the record alone: five verdicts, what each policy removes, the proposal bar, repairs gated on the
removal they repair, and cardinality that never lets a proposed value displace a stated one inside the margin."""

from __future__ import annotations

from reconcile.ledger import (AMBIGUOUS, CONTRADICTED, INSUFFICIENT, MALFORMED, PROPOSED, STATED, SUPPORTED, Entity,
                              Ledger)
from reconcile.policy import added, decide, removed
from reconcile.readings import cardinality

CITE = {"doc": "D1", "sentence": 1, "start": 0, "end": 10, "text": "Some prose."}


def ev(label, score, method="nli", passage=0):
    return {"method": method, "label": label, "score": score, "unit": "block", "passage": passage, "cite": CITE, "hypothesis": "x"}


def claim(led, s, p, o, lit=True, origin=STATED, **kw):
    c = led.add_claim(s, p, o, lit, "prop", origin)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_verdicts_in_order():
    led = Ledger()
    a = claim(led, "e1", "name", "A", evidence=[ev("supports", 0.99)], checks={"datatype": {"result": "fail", "reason": "bad"}})
    b = claim(led, "e1", "sentTime", "B", evidence=[ev("supports", 0.99)], checks={"header": {"result": "fail", "reason": "Date: says otherwise"}})
    c = claim(led, "e1", "x", "C", evidence=[ev("supports", 0.99)], checks={"contrast": {"result": "fail", "reason": "outranked"}})
    d = claim(led, "e1", "y", "D", evidence=[ev("neutral", 0.1)])
    e = claim(led, "e1", "z", "E", evidence=[ev("supports", 0.9)], checks={"contrast": {"result": "pass", "reason": "close", "near": True}})
    f = claim(led, "e1", "w", "F", evidence=[ev("supports", 0.9)])
    g = claim(led, "e1", "v", "G", evidence=[ev("contradicts", 0.98), ev("anchors", 1.0, "span")])
    decide(led, "conservative", 2.0)
    assert [x.status for x in (a, b, c, d, e, f)] == [MALFORMED, CONTRADICTED, CONTRADICTED, INSUFFICIENT, AMBIGUOUS, SUPPORTED]
    assert g.status == INSUFFICIENT, "an NLI contradiction label alone contradicts nothing"
    assert {x.id for x in removed(led, "conservative")} == {a.id, b.id, c.id}
    assert {x.id for x in removed(led, "strict")} == {a.id, b.id, c.id, d.id, g.id}
    assert e.id not in {x.id for x in removed(led, "strict")}  # ambiguous is kept, and recorded


def test_facet_literal_is_malformed_only_under_the_hook():
    led = Ledger()
    led.add_entity(Entity("m1", "EmailMessage", {"subject": ["Hello"]}))
    led.meta["classes"] = {"m1": ["EmailMessage", "Message", "ObservableObject"]}
    fail = {"result": "fail", "reason": "subject is a property of EmailMessageFacet"}
    subject = claim(led, "m1", "subject", "Hello", evidence=[ev("supports", 0.99)], checks={"domain": dict(fail)})
    other = claim(led, "m1", "accountIdentifier", "7", evidence=[ev("supports", 0.99)], checks={"domain": dict(fail)})
    decide(led, "conservative", 2.0)
    assert subject.status == SUPPORTED and other.status == MALFORMED
    decide(led, "hook-v1", 2.0)
    assert subject.status == MALFORMED


def test_strict_keeps_an_unverified_key():
    led = Ledger()
    led.add_entity(Entity("p1", "Person", {"name": ["Ada"]}))
    name = claim(led, "p1", "name", "Ada", evidence=[ev("neutral", 0.1)])
    other = claim(led, "p1", "x", "Y", evidence=[ev("neutral", 0.1)])
    decide(led, "strict", 2.0)
    assert name.status == INSUFFICIENT and other.status == INSUFFICIENT
    assert {c.id for c in removed(led, "strict")} == {other.id}
    assert {c.id for c in removed(led, "hook-v1")} == {name.id, other.id}


def test_proposal_bar_and_repair_gating():
    led = Ledger()
    led.meta["add_at"] = 0.9
    for i in ("e1", "e2"):
        led.add_entity(Entity(i, "Person", {"name": [i]}))
    low = claim(led, "e1", "Employed_By", "e2", lit=False, origin=PROPOSED, evidence=[ev("supports", 0.8), ev("anchors", 1.0, "span")])
    high = claim(led, "e1", "Reports_To", "e2", lit=False, origin=PROPOSED, evidence=[ev("supports", 0.95), ev("anchors", 1.0, "span")])
    unanchored = claim(led, "e2", "Reports_To", "e1", lit=False, origin=PROPOSED, evidence=[ev("supports", 0.99, passage=3)])
    stated = claim(led, "e1", "locality", "Boise", evidence=[ev("supports", 0.99)])
    repair = claim(led, "e1", "region", "Boise", origin=PROPOSED, evidence=[ev("supports", 0.99), ev("supports", 1.0, "span")],
                   note=f"repair-of:{stated.id},0000000000000000 reading")
    decide(led, "conservative", 2.0)
    assert low.status == INSUFFICIENT and high.status == SUPPORTED and unanchored.status == INSUFFICIENT
    assert repair.status == SUPPORTED and stated.status == SUPPORTED
    ids = {c.id for c in added(led, "conservative")}
    assert high.id in ids and repair.id not in ids, "a repair is added only when its stated claim is removed"
    stated.checks = {"contrast": {"result": "fail", "reason": "region wins"}}
    decide(led, "conservative", 2.0)
    assert stated.status == CONTRADICTED
    assert repair.id in {c.id for c in added(led, "conservative")}


def test_cardinality_protects_the_stated_value():
    led = Ledger()
    s = claim(led, "e1", "locality", "Boise", evidence=[ev("supports", 0.9)])
    p = claim(led, "e1", "locality", "Nampa", origin=PROPOSED, evidence=[ev("supports", 0.97)])
    rows = [{"sentence": "", "passages": [{**CITE, "verdict": "supported", "entailment": e.evidence[0]["score"]}]} for e in (s, p)]
    classes = {"e1": {"Location", "SimpleAddressFacet"}}
    out = cardinality([s, p], rows, classes, [True, True], 2.0)
    assert out[0]["result"] == "pass" and out[1]["result"] == "fail", out  # 0.97 vs 0.9 is inside the margin
    rows[1]["passages"][0]["entailment"] = 0.9999
    out = cardinality([s, p], rows, classes, [True, True], 2.0)
    assert out[0]["result"] == "fail" and out[1]["result"] == "pass", out  # beyond the margin: the proposal wins
    q = claim(led, "e1", "locality", "Caldwell", origin=PROPOSED, evidence=[ev("supports", 0.97)])
    rows3 = [rows[1], {"sentence": "", "passages": [{**CITE, "verdict": "supported", "entailment": 0.97}]}]
    out = cardinality([p, q], rows3, classes, [True, True], 2.0)
    assert out[0]["result"] == "pass" and out[1]["result"] == "fail"
    rows3[0]["passages"][0]["entailment"] = 0.97
    out = cardinality([p, q], rows3, classes, [True, True], 2.0)
    assert [o["result"] for o in out] == ["fail", "fail"], "two proposals inside the margin: abstain"
