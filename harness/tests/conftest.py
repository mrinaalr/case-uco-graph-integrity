"""pytest setup: the harness modules import each other by bare name (`from graphkit import ...`), as the scripts do
when run from harness/, so harness/ goes on sys.path. Tests here load no model; a test that needs the NLI model or the
embedder takes the `verifier` fixture, which is a stub unless RECONCILE_TEST_MODELS=1."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

HARNESS = Path(__file__).resolve().parents[1]
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

DEV = HARNESS / "data_dev"


class StubVerifier:
    """hook.Verifier's interface without its models: every (passage, sentence) pair is `supported` with entailment 0.99
    when the passage holds every word of the sentence longer than three letters, else `not_enough_evidence` at 0.01.
    Retrieval is word overlap. Deterministic, and wrong in the ways tests should not rely on."""

    verdicts = ["supported", "not_enough_evidence", "contradicted"]
    supported = 0
    device = "stub"

    def __init__(self, top_k: int = 3) -> None:
        self.top_k = top_k

    @staticmethod
    def _words(text: str) -> set[str]:
        return {w.strip(".,;:()\"'").lower() for w in text.split() if len(w) > 3}

    def check(self, sentences, source, queries=None):
        out = []
        for i, s in enumerate(sentences):
            q = self._words((queries or sentences)[i])
            ranked = sorted(range(len(source)), key=lambda j: (-len(q & self._words(source[j]["text"])), j))[: self.top_k]
            rows = []
            for j in ranked:
                p = source[j]
                e = 0.99 if self._words(s) <= self._words(p["text"]) else 0.01
                rows.append({**p, "similarity": round(len(q & self._words(p["text"])) / max(len(q), 1), 4),
                             "verdict": "supported" if e > 0.5 else "not_enough_evidence", "entailment": e})
            out.append(rows)
        return out

    def probs(self, premises, hypotheses):
        rows = []
        for p, h in zip(premises, hypotheses):
            e = 0.99 if self._words(h) <= self._words(p) else 0.01
            rows.append([e, 1 - e, 0.0])
        return np.array(rows) if rows else np.zeros((0, 3))

    def entailment(self, premises, hypotheses):
        return [round(float(p[0]), 4) for p in self.probs(premises, hypotheses)]


@pytest.fixture(scope="session")
def verifier():
    if os.environ.get("RECONCILE_TEST_MODELS") == "1":
        import tomllib

        from hook import Verifier
        from llm import CONFIG

        with open(CONFIG, "rb") as fh:
            return Verifier(tomllib.load(fh)["hook"])
    return StubVerifier()


@pytest.fixture(scope="session")
def dev_cases() -> list[Path]:
    return sorted(p for p in DEV.glob("case_*") if p.is_dir())
