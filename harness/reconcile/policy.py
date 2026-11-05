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


def verdict(c: Claim, margin: float, methods: set[str] = frozenset({"nli", "span"}), add_at: float = 0.9) -> tuple[str, str, str]:
    """(verdict, rule, reason) for one claim from its record. A proposal must clear add_at (at_the_bar)."""
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
    if c.origin == PROPOSED and header.get("result") != "pass":
        sup = at_the_bar(c, sup, add_at)
    if not sup:
        anchored = {e["passage"] for e in c.evidence if e["label"] == "anchors"}
        contra = [e for e in c.evidence if e["label"] == "contradicts" and (not anchored or e["passage"] in anchored)]
        if contra and anchored and c.origin == STATED:
            return CONTRADICTED, "nli", f"contradicted on a passage naming its entities: {contra[0]['cite']['text'][:80]}"
        why = "no passage supports it" if c.origin == STATED else f"no passage supports it at the proposal bar ({add_at})"
        return INSUFFICIENT, "no-support", why + (" (NLI: contradiction)" if contra else "")
    if contrast.get("result") == "pass" and contrast.get("near"):
        return AMBIGUOUS, "contrast", contrast["reason"]
    best = max(sup, key=lambda e: e["score"])
    return SUPPORTED, "support", f"{best['method']} on {best['cite']['doc']} sentence {best['cite']['sentence']}"


def at_the_bar(c: Claim, sup: list[dict], add_at: float) -> list[dict]:
    """The support a proposal needs: a literal found verbatim beside its subject, or NLI entailment of at least add_at
    on a prose passage that names both entities (an object claim) or the subject (a literal)."""
    anchored = {e["passage"] for e in c.evidence if e["label"] == "anchors"} if not c.lit else None
    out = []
    for e in sup:
        if e["method"] == "span":
            out.append(e)
        elif e["score"] >= add_at and (anchored is None or e["passage"] in anchored) and not str(e["cite"]["text"]).startswith(
                ("From:", "To:", "Cc:", "Subject:", "Date:")):
            out.append(e)
    return out


def implied(led: Ledger, c: Claim) -> Claim | None:
    """A stated or accepted claim that entails proposal c (Initiated states Participated_In)."""
    from reconcile.ontology import ENTAILS
    for d in led:
        if d is c or d.lit or (d.s, d.o) != (c.s, c.o) or c.p not in ENTAILS.get(d.p, set()):
            continue
        if d.origin == STATED or d.status == SUPPORTED:
            return d
    return None


def decide(led: Ledger, policy: str, margin: float, stage: str = "decide") -> dict:
    """Set every claim's status from its record. Returns the removal set and whether proposals are added."""
    rules = POLICIES[policy]
    add_at = led.meta.get("add_at", 0.9)
    for c in led:
        v, rule, reason = verdict(c, margin, rules["evidence"], add_at)
        led.decide(c, stage, rule, v, reason)
    for c in led.by_origin(PROPOSED):
        if c.status == SUPPORTED and (d := implied(led, c)):
            led.decide(c, stage, "implied", INSUFFICIENT, f"implied by {d.p} ({d.id}); not added")
    return rules


def removed(led: Ledger, policy: str) -> list[Claim]:
    return [c for c in led.stated() if c.status in POLICIES[policy]["remove"]]


def added(led: Ledger, policy: str) -> list[Claim]:
    if not POLICIES[policy]["add"]:
        return []
    return [c for c in led.by_origin(PROPOSED) if c.status == SUPPORTED and not (c.note or "").startswith("dropped")]


def kept(led: Ledger, policy: str) -> set[tuple]:
    gone = {c.id for c in removed(led, policy)}
    return {c.key for c in led.stated() if c.id not in gone}
