"""The verdict on each claim, from its record alone, and what each policy does with it.

Verdicts (ledger.VERDICTS), in the order they are tested:

- `malformed`: a deterministic check failed (domain, range, datatype, self-loop, cardinality). This is about the
  graph, not the source. Outside the hook policies, a literal written on a node whose class declares it on its own
  facet (an EmailMessage's subject, declared on EmailMessageFacet) is not malformed: where the schema puts a value is
  SHACL's question, not the source's.
- `contradicted`: the header rule says otherwise, or on every passage that supports the claim a reading that cannot
  hold with it outranks it by more than the contrast margin (log-odds of entailment). An NLI contradiction label
  alone contradicts nothing: it is recorded, and the claim is `insufficient`.
- `supported`: some passage supports it (NLI entailment, or a literal found beside its subject), and nothing above.
  `ambiguous` instead when, on its best passage, a reading that cannot hold with it is also entailed and within the
  margin: the source does not separate the two, and the ledger keeps both.
- `insufficient`: no passage supports it. Not false: unverified.

Policies name the verdicts a stated claim is removed for, and whether verified proposals are added:

- `hook-v1`: removes all but `supported` and `ambiguous`; adds nothing. With `template="full"` and sentence
  passages this is the published hook (hook-v1) decided from the ledger.
- `lr`: the same, after the ontology checks and contrast; the left and right hooks (fix-dev).
- `conservative`: removes `contradicted` and `malformed` only; `insufficient` stays and is flagged; adds verified
  proposals. The default.
- `strict`: removes `insufficient` too, except an entity's key (profile `[keys]`): a key is what the entity is, and
  one that is unverified rather than contradicted leaves with nothing to put in its place. Adds verified proposals."""

from __future__ import annotations

from reconcile import keys
from reconcile.ledger import (AMBIGUOUS, CONTRADICTED, INSUFFICIENT, MALFORMED, PROPOSED, STATED, SUPPORTED, UNDECIDED,
                              Claim, Ledger)
from reconcile.ontology import declares

SCHEMA_CHECKS = ("domain", "range", "datatype", "self_loop", "cardinality")
# `evidence`: the methods whose `supports` count. The hook policies read NLI alone, as the hook did; the others also
# take a literal found verbatim beside its subject. `facets`: a literal the class declares on its own facet passes
# the domain check. `keep_keys`: an entity's key is not removed as `insufficient`.
POLICIES = {
    "hook-v1": {"remove": {CONTRADICTED, INSUFFICIENT, MALFORMED}, "add": False, "evidence": {"nli"}, "facets": False,
                "keep_keys": False},
    "lr": {"remove": {CONTRADICTED, INSUFFICIENT, MALFORMED}, "add": False, "evidence": {"nli"}, "facets": False,
           "keep_keys": False},
    "conservative": {"remove": {CONTRADICTED, MALFORMED}, "add": True, "evidence": {"nli", "span"}, "facets": True,
                     "keep_keys": True},
    "strict": {"remove": {CONTRADICTED, INSUFFICIENT, MALFORMED}, "add": True, "evidence": {"nli", "span"}, "facets": True,
               "keep_keys": True},
}


def supports(c: Claim, methods: set[str] = frozenset({"nli", "span"})) -> list[dict]:
    return [e for e in c.evidence if e["label"] == "supports" and e["method"] in methods]


def on_facet(c: Claim, classes: set[str]) -> bool:
    """A literal that one of the subject's classes declares, on itself or its facet (ontology.declares)."""
    return c.lit and any(declares(k, c.p) for k in classes)


def verdict(c: Claim, margin: float, methods: set[str] = frozenset({"nli", "span"}), add_at: float = 0.9,
            classes: set[str] = frozenset(), facets: bool = False) -> tuple[str, str, str]:
    """(verdict, rule, reason) for one claim from its record. A proposal must clear add_at (at_the_bar)."""
    failed = [k for k in SCHEMA_CHECKS if c.checks.get(k, {}).get("result") == "fail"]
    if facets and "domain" in failed and on_facet(c, classes):
        failed.remove("domain")
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
        contra = [e for e in c.evidence if e["label"] == "contradicts"]
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
    classes = {iri: set(cs) for iri, cs in led.meta.get("classes", {}).items()}
    for c in led:
        v, rule, reason = verdict(c, margin, rules["evidence"], add_at, classes.get(c.s, set()), rules["facets"])
        led.decide(c, stage, rule, v, reason)
    for c in led.by_origin(PROPOSED):
        if c.status == SUPPORTED and (d := implied(led, c)):
            led.decide(c, stage, "implied", INSUFFICIENT, f"implied by {d.p} ({d.id}); not added")
    return rules


def is_key(led: Ledger, c: Claim) -> bool:
    e = led.entities.get(c.s)
    return bool(e) and c.lit and c.p in keys.KEYS.get(e.cls, [])


def removed(led: Ledger, policy: str) -> list[Claim]:
    rules = POLICIES[policy]
    return [c for c in led.stated() if c.status in rules["remove"]
            and not (rules["keep_keys"] and c.status == INSUFFICIENT and is_key(led, c))]


def added(led: Ledger, policy: str) -> list[Claim]:
    """The proposals the policy writes: supported, not dropped with their entity, and, for a repair
    (`repair-of:<id>[,<id>] ...`), only when one of the stated claims it repairs is removed under this policy."""
    if not POLICIES[policy]["add"]:
        return []
    gone = {c.id for c in removed(led, policy)}
    out = []
    for c in led.by_origin(PROPOSED):
        note = c.note or ""
        if c.status != SUPPORTED or note.startswith("dropped"):
            continue
        if note.startswith("repair-of:") and not set(note.split()[0].partition(":")[2].split(",")) & gone:
            continue
        out.append(c)
    return out


def kept(led: Ledger, policy: str) -> set[tuple]:
    gone = {c.id for c in removed(led, policy)}
    return {c.key for c in led.stated() if c.id not in gone}
