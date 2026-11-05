"""Pass 2, semantic correction: what the ontology says of each claim, and whether the source prefers another reading.

On every claim with support (or every claim, `on="all"`): the right hook's checks, from the SDK's schema and the task
profile (hook.schema_checks: domain, range, datatype, self-loop; hook.cardinality: a single-valued property with several
values keeps the one that best outranks its readings), the mail-header rule (hook.header_check: Date:, From:, To:
decide a message's time, sender and recipients), and contrast (hook.contrast_scores): on each passage that supports the
claim, its plain sentence and each competing reading's are scored against the passage followed by the CASE/UCO
definitions in play; the claim fails when a competitor outranks it by more than the margin in log-odds on every such
passage. Competitors are the other readings the profile allows for the same entities, less those the claim entails.

Results go on the claim as `checks` (each check's pass, fail or skip with its reason) and `competitors` (each rival's
sentence and, per passage, both entailments). The pass decides nothing; policy.verdict reads the record. `ambiguous`
is signalled here: contrast passed, but on the claim's best passage a rival is itself entailed and within the margin."""

from __future__ import annotations

from hook import cardinality, contrast_result, contrast_scores, header_check, logit, schema_checks
from reconcile.ingest import classes_of
from reconcile.ledger import Claim, Ledger
from reconcile.source import Source
from reconcile.verify import named_entities

VERDICT_OF = {"supports": "supported", "contradicts": "contradicted", "neutral": "not_enough_evidence"}


def row_of(c: Claim) -> dict:
    """The hook's per-edge row, from the claim's NLI evidence, for its contrast functions."""
    passages = [{**e["cite"], "verdict": VERDICT_OF[e["label"]], "entailment": e["score"]}
                for e in c.evidence if e["method"] == "nli"]
    return {"sentence": c.sentence, "passages": passages}


def near_miss(contrast: dict | None, margin: float) -> bool:
    """On the claim's best passage, is a rival entailed and within the margin?"""
    if not contrast or not contrast.get("passages"):
        return False
    best = max(contrast["passages"], key=lambda s: logit(s["own"]) - logit(max(s.get("rivals", [0.0]))))
    rival = max(best.get("rivals", [0.0]))
    return rival >= 0.5 and 0 <= logit(best["own"]) - logit(rival) <= margin


def readings_pass(led: Ledger, src: Source, verifier, margin: float, claims: list[Claim] | None = None,
                  on: str = "supported") -> None:
    todo = list(claims if claims is not None else led.stated())
    ents = named_entities(led)
    classes = classes_of(led)
    triples = [c.as_triple() for c in todo]
    rows = [row_of(c) for c in todo]
    header = [header_check(t, ents, src.headers) for t in triples]
    active = [on == "all" or any(e["label"] == "supports" and e["method"] == "nli" for e in c.evidence) for c in todo]
    need = [i for i in range(len(todo)) if active[i] and header[i]["result"] == "skip"]
    contrast_scores([rows[i] for i in need], [triples[i] for i in need], ents, classes, verifier)
    card = cardinality(triples, rows, classes, active)
    for i, (c, t, r) in enumerate(zip(todo, triples, rows)):
        if not active[i]:
            continue
        checks = schema_checks(t, classes)
        if card[i]:
            checks["cardinality"] = card[i]
        checks["header"] = header[i]
        if header[i]["result"] == "skip":
            result, alive = contrast_result(r, margin)
            checks["contrast"] = {**result, "near": near_miss(r.get("contrast"), margin), "alive": list(alive)}
        else:
            checks["contrast"] = {"result": "skip", "reason": "decided by the header rule", "near": False,
                                  "alive": list(range(len(r["passages"])))}
        c.checks = checks
        ctr = r.get("contrast")
        if ctr:
            c.competitors = [{"sentence": s, "passages": [{"passage": slot["passage"], "own": slot.get("own"),
                                                           "rival": (slot.get("rivals") or [None] * len(ctr["competitors"]))[k]}
                                                          for slot in ctr["passages"]]}
                             for k, s in enumerate(ctr["competitors"])]
