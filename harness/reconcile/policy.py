"""The verdict on each claim, from its record alone, and what each policy does with it.

Verdicts (ledger.VERDICTS), in the order they are tested:

- `malformed`: a deterministic check failed (domain, range, datatype, self-loop, cardinality). This is about the
  graph, not the source.
- `contradicted`: the header rule says otherwise; or on every passage that supports the claim a reading that cannot
  hold with it outranks it by more than the contrast margin (log-odds of entailment); or no passage supports it and
  one that names its subject labels it contradiction.
- `supported`: some passage supports it (NLI entailment, or a literal found beside its subject), and nothing above.
  `ambiguous` instead when, on its best passage, a reading that cannot hold with it is also entailed and within the
  margin: the source does not separate the two, and the ledger keeps both.
- `insufficient`: no passage supports it and none contradicts it. Not false: unverified.

Policies name the verdicts a stated claim is removed for, and whether verified proposals are added:

- `hook-v1`: removes all but `supported` and `ambiguous`; adds nothing. With `template="full"` and sentence
  passages this is the published hook (hook-v1) decided from the ledger.
- `lr`: the same, after the ontology checks and contrast; the left and right hooks (fix-dev).
- `conservative`: removes `contradicted` and `malformed` only; `insufficient` stays and is flagged; adds verified
  proposals. The default.
- `strict`: removes `insufficient` too; adds verified proposals."""

from __future__ import annotations

from reconcile.ledger import (AMBIGUOUS, CONTRADICTED, INSUFFICIENT, MALFORMED, PROPOSED, STATED, SUPPORTED, UNDECIDED,
                              Claim, Ledger)

SCHEMA_CHECKS = ("domain", "range", "datatype", "self_loop", "cardinality")
# `evidence`: the methods whose `supports` count. The hook policies read NLI alone, as the hook did; the others also
# take a literal found verbatim beside its subject.
POLICIES = {
    "hook-v1": {"remove": {CONTRADICTED, INSUFFICIENT, MALFORMED}, "add": False, "evidence": {"nli"}},
    "lr": {"remove": {CONTRADICTED, INSUFFICIENT, MALFORMED}, "add": False, "evidence": {"nli"}},
    "conservative": {"remove": {CONTRADICTED, MALFORMED}, "add": True, "evidence": {"nli", "span"}},
    "strict": {"remove": {CONTRADICTED, INSUFFICIENT, MALFORMED}, "add": True, "evidence": {"nli", "span"}},
}


def supports(c: Claim, methods: set[str] = frozenset({"nli", "span"})) -> list[dict]:
    return [e for e in c.evidence if e["label"] == "supports" and e["method"] in methods]


def verdict(c: Claim, margin: float, methods: set[str] = frozenset({"nli", "span"})) -> tuple[str, str, str]:
    """(verdict, rule, reason) for one claim from its record."""
    failed = [k for k in SCHEMA_CHECKS if c.checks.get(k, {}).get("result") == "fail"]
    if failed:
        return MALFORMED, f"check:{failed[0]}", c.checks[failed[0]]["reason"]
    header = c.checks.get("header", {})
    if header.get("result") == "fail":
        return CONTRADICTED, "header", header["reason"]
    sup = supports(c, methods)
    contrast = c.checks.get("contrast", {})
    if contrast.get("result") == "fail":
        return CONTRADICTED, "contrast", contrast["reason"]
    if not sup:
        anchored = {e["passage"] for e in c.evidence if e["label"] == "anchors"}
        contra = [e for e in c.evidence if e["label"] == "contradicts" and (not anchored or e["passage"] in anchored)]
        if contra and anchored:
            return CONTRADICTED, "nli", f"contradicted on a passage naming its entities: {contra[0]['cite']['text'][:80]}"
        return INSUFFICIENT, "no-support", "no passage supports it" + (" (NLI: contradiction)" if contra else "")
    if contrast.get("result") == "pass" and contrast.get("near"):
        return AMBIGUOUS, "contrast", contrast["reason"]
    best = max(sup, key=lambda e: e["score"])
    return SUPPORTED, "support", f"{best['method']} on {best['cite']['doc']} sentence {best['cite']['sentence']}"


def decide(led: Ledger, policy: str, margin: float, stage: str = "decide") -> dict:
    """Set every claim's status from its record. Returns the removal set and whether proposals are added."""
    rules = POLICIES[policy]
    for c in led:
        v, rule, reason = verdict(c, margin, rules["evidence"])
        led.decide(c, stage, rule, v, reason)
    return rules


def removed(led: Ledger, policy: str) -> list[Claim]:
    return [c for c in led.stated() if c.status in POLICIES[policy]["remove"]]


def added(led: Ledger, policy: str) -> list[Claim]:
    if not POLICIES[policy]["add"]:
        return []
    return [c for c in led.by_origin(PROPOSED) if c.status == SUPPORTED]


def kept(led: Ledger, policy: str) -> set[tuple]:
    gone = {c.id for c in removed(led, policy)}
    return {c.key for c in led.stated() if c.id not in gone}
