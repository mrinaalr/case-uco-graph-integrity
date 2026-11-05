"""Pass 2 fills checks from the schema and the header rule without a model's help, and the policy turns a failed check
into `malformed` or `contradicted`, never `supported`. Stub verifier; the corrupted dev graphs from hook_dev_check
(results/fix-dev/corrupt) when they are there."""

from __future__ import annotations

import json

import pytest

from graphkit import HARNESS
from reconcile.ingest import ingest
from reconcile.ledger import CONTRADICTED, MALFORMED, SUPPORTED
from reconcile.policy import decide
from reconcile.readings import readings_pass
from reconcile.source import Source
from reconcile.verify import verify

CORRUPT = HARNESS / "results" / "fix-dev" / "corrupt"


def test_schema_checks_fill_without_a_model(dev_cases, verifier):
    case = dev_cases[0]
    led, _ = ingest(case / "gold.jsonld")
    src = Source(case / "docs")
    verify(led, src, verifier)
    readings_pass(led, src, verifier, 2.0, on="all")
    for c in led.stated():
        assert {"domain", "header", "contrast"} <= set(c.checks), c.key
        assert all(v["result"] in ("pass", "fail", "skip") for v in c.checks.values())
    decide(led, "lr", 2.0)
    for c in led.stated():
        if any(v["result"] == "fail" for k, v in c.checks.items() if k not in ("header", "contrast")):
            assert c.status == MALFORMED
        elif c.checks["header"]["result"] == "fail":
            assert c.status == CONTRADICTED


def test_header_rule_catches_a_planted_received_time(verifier):
    if not CORRUPT.exists():
        pytest.skip("no fix-dev corrupt graphs locally")
    case = next(p for p in sorted(CORRUPT.glob("case_*")) if (p / "plants.json").exists())
    plants = json.loads((case / "plants.json").read_text())
    received = [p for p in plants if p.get("p") == "receivedTime"]
    if not received:
        pytest.skip("no receivedTime plant in this case")
    docs = HARNESS / "data_dev" / case.name / "docs"
    led, _ = ingest(case / "graph.jsonld")
    src = Source(docs)
    verify(led, src, verifier)
    readings_pass(led, src, verifier, 2.0, on="all")
    decide(led, "lr", 2.0)
    planted = [c for c in led.stated() if c.p == "receivedTime"]
    assert planted
    for c in planted:
        if c.checks["header"]["result"] == "fail":
            assert c.status == CONTRADICTED and c.decided_by == "header"
            assert c.status != SUPPORTED
