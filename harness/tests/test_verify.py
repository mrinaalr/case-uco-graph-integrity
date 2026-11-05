"""Pass 1 attaches evidence to every stated claim and decides nothing; the policy decides from the record; emit
leaves the graph as it was when nothing is removed, and never lets a removed claim through. Stub verifier."""

from __future__ import annotations

from graphkit import graph_triples
from reconcile.emit import emit
from reconcile.ingest import ingest
from reconcile.ledger import INSUFFICIENT, SUPPORTED, UNDECIDED, Ledger
from reconcile.policy import POLICIES, decide, kept, removed
from reconcile.source import Source
from reconcile.verify import verify


def test_verify_attaches_evidence_and_decides_nothing(dev_cases, verifier):
    case = dev_cases[0]
    led, _ = ingest(case / "gold.jsonld")
    verify(led, Source(case / "docs"), verifier)
    for c in led.stated():
        assert c.sentence and c.evidence, c.key
        assert all(e["cite"]["doc"] in {"D1", "D2", "D3", "D4"} for e in c.evidence)
        assert c.status == UNDECIDED
    lits = [c for c in led.stated() if c.lit]
    assert any(e["method"] == "span" for c in lits for e in c.evidence)


def test_policy_decides_every_claim_and_emit_respects_it(dev_cases, verifier, tmp_path):
    case = dev_cases[1]
    led, _ = ingest(case / "gold.jsonld")
    verify(led, Source(case / "docs"), verifier)
    decide(led, "conservative", 2.0)
    assert all(c.status != UNDECIDED for c in led)
    assert {c.status for c in led} <= {SUPPORTED, INSUFFICIENT}  # no checks ran: nothing can be contradicted or malformed
    # Conservative keeps insufficient claims; strict removes them.
    assert not removed(led, "conservative")
    gone = removed(led, "strict")
    assert gone and all(c.status == INSUFFICIENT for c in gone)
    info = emit(led, case / "gold.jsonld", tmp_path / "cons", "conservative", {})
    _, before = graph_triples(case / "gold.jsonld")
    _, after = graph_triples(tmp_path / "cons" / "graph.jsonld")
    assert {(t["s"], t["p"], t["o"], t["lit"]) for t in after} == {(t["s"], t["p"], t["o"], t["lit"]) for t in before}
    assert info["removed"] == 0 and (tmp_path / "cons" / "input" / "graph.jsonld").read_bytes() == (case / "gold.jsonld").read_bytes()
    emit(led, case / "gold.jsonld", tmp_path / "strict", "strict", {})
    _, after = graph_triples(tmp_path / "strict" / "graph.jsonld")
    left = {(t["s"], t["p"], t["o"], t["lit"]) for t in after}
    assert left == kept(led, "strict")
    assert not {c.key for c in gone} & left
    back = Ledger.read(tmp_path / "strict" / "ledger")
    assert len(back.decisions) == len(led.decisions) and back.summary() == led.summary()


def test_hook_policies_read_nli_only(dev_cases, verifier):
    case = dev_cases[2]
    led, _ = ingest(case / "gold.jsonld")
    verify(led, Source(case / "docs"), verifier)
    decide(led, "hook-v1", 2.0)
    for c in led.stated():
        nli = any(e["label"] == "supports" and e["method"] == "nli" for e in c.evidence)
        assert (c.status == SUPPORTED) == nli, c.key
    assert POLICIES["hook-v1"]["evidence"] == {"nli"}
