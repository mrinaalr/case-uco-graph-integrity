"""The ledger reads any graph the harness has produced without loss, and the source index matches the one the hook
and the selector built from gold.json's document list."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphkit import HARNESS, graph_triples
from reconcile import keys
from reconcile.ingest import ingest
from reconcile.ledger import Ledger
from reconcile.source import Source

RESULTS = HARNESS / "results"
SAMPLE_RUNS = [("sel-test", "b_control"), ("sel-test", "a_sdk_agent"), ("edc-dev", "c_edc"), ("sel-dev", "corrupt")]


def graphs() -> list[Path]:
    out = []
    for run, arm in SAMPLE_RUNS:
        out += sorted((RESULTS / run / arm).glob("case_*/graph.jsonld"))[:5]
    return out or pytest.skip("no local result graphs")


def test_ingest_keeps_every_scored_triple(tmp_path):
    for path in graphs():
        led, _ = ingest(path)
        _, triples = graph_triples(path)
        want = {(t["s"], t["p"], t["o"], t["lit"]) for t in triples}
        got = {c.key for c in led.stated()}
        assert got == want, path
        led.write(tmp_path / path.parent.name)
        back = Ledger.read(tmp_path / path.parent.name)
        assert {c.key for c in back.stated()} == want
        assert {e.id: e.cls for e in back.entities.values()} == {e.id: e.cls for e in led.entities.values()}


def test_source_matches_the_hooks_passages(dev_cases):
    from llm import passages
    from hook import header_blocks
    for case in dev_cases[:5]:
        src = Source(case / "docs")
        assert src.passages == passages(case)
        assert src.blocks == header_blocks(passages(case))
        doc_ids = list(json.loads((case / "gold.json").read_text())["documents"])
        assert list(src.docs) == doc_ids


def test_keys_agree_with_the_scorer(dev_cases):
    import score
    assert keys.KEYS == score.KEYS
    for case in dev_cases[:5]:
        src = Source(case / "docs")
        theirs = score.load_source(case, "D*[0-9].txt")
        ours = keys.index_text({p.stem: p.read_text() for p in src.files}) if src.files[0].suffix == ".txt" else \
            keys.index_text({p.stem[:2]: p.read_text() for p in sorted((case / "docs").glob("D*[0-9].txt"))})
        assert ours["sents"] == theirs["sents"]
        for value, prop in (("Granite Federal Credit Union", "name"), ("2025-05-02T10:50:00Z", "sentTime"),
                            ("bank account", "accountType"), ("12 Main St", "street")):
            assert keys.ground_literal(prop, value, ours) == score.ground_literal(prop, value, theirs)
            assert keys.norm(prop, value) == score.norm(prop, value)
