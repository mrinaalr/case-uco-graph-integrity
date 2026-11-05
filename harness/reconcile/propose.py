"""Pass 3, forward recovery: facts the source states and the graph may lack, as proposed claims. A proposal is a
claim like any other: it gets the same evidence (verify), the same checks and contrast (readings), and the policy
decides it from its record; it is added only when `supported` at the proposal bar (policy.add_at: entailment on a
passage both entities share, or the header rule, or a literal found beside its subject). Three generators:

- `from_readings`: for every pair of entities that share a passage or an edge, every reading the profile allows
  (hook.readings: relation kinds and object properties whose domain and range fit, either way round) that the graph
  does not state. This is the selector's enumeration; a wrong stated edge and its right reading are then two
  claims decided from the same passages, so a repair is a removal and an addition that happen to agree.
- `from_headers`: a message's sentTime, sender and recipients from the mail-header block whose Subject: line is its
  subject (From:, To:, Cc:, Date:), decided by the header rule, not NLI.
- `from_literals`: for a stated literal, the same value under each property of its class with the same range (a
  sentTime written as receivedTime), and an ISO form of a date-time xsd:dateTime rejects. The stated claim and its
  alternative are then decided side by side.
- `from_llm` (propose/llm): facts an LLM lists from each document, with their values as exact spans of the source
  and their names resolved to entities (resolve.Resolver). The proposals are cached per case; no model runs here."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from graphkit import iso_time
from hook import ENTAILS, SYMMETRIC, kind_of, prop_spec, readings
from reconcile import keys
from reconcile.ingest import classes_of
from reconcile.ledger import PROPOSED, STATED, Claim, Ledger
from reconcile.ontology import KIND_CLASSES, LITERAL_PROPS, PROP_CLASSES
from reconcile.resolve import Resolver, flat, merge_duplicates
from reconcile.source import Source
from reconcile.verify import named_entities, verify

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LINK_PROPS = {p for _, p in PROP_CLASSES} | {"emailAddress"}  # the object properties a proposal may state


def stated_keys(led: Ledger) -> set[tuple]:
    out = set()
    for c in led.stated():
        k = kind_of(c.as_triple()) or c.p
        out.add((c.s, k, c.o))
        if k in SYMMETRIC:
            out.add((c.o, k, c.s))
    return out


def propose_claim(led: Ledger, s: str, p: str, o: str, lit: bool, kind: str, how: str) -> Claim | None:
    if led.find(s, p, o, lit):
        return None
    c = led.add_claim(s, p, o, lit, kind, PROPOSED)
    c.note = how
    return c


def from_readings(led: Ledger) -> list[Claim]:
    ents = named_entities(led)
    have = stated_keys(led)
    pairs = set()
    for c in led.stated():
        if not c.lit and c.o in led.entities and c.s != c.o:
            pairs.add(frozenset((c.s, c.o)))
    by_passage = defaultdict(list)
    for e in led.entities.values():
        for i in e.mentions:
            by_passage[i].append(e.id)
    for ids in by_passage.values():
        for a in ids:
            for b in ids:
                if a < b:
                    pairs.add(frozenset((a, b)))
    out = []
    for pair in pairs:
        x, y = sorted(pair)
        for r in readings(x, y, ents):
            if (r["s"], r["p"], r["o"]) in have:
                continue
            if any((r["s"], k, r["o"]) in have for k, ents_k in ENTAILS.items() if r["p"] in ents_k):
                continue  # implied by a stated claim (Initiated states Participated_In)
            kind = "rel" if r["origin"].startswith("rel|") else "prop"
            c = propose_claim(led, r["s"], r["p"], r["o"], False, kind, "reading")
            if c:
                out.append(c)
    return out


def from_headers(led: Ledger, src: Source) -> list[Claim]:
    addresses = {(e.props.get("addressValue") or [""])[0].lower(): i for i, e in led.entities.items() if e.cls == "EmailAddress"}
    have = {(c.s, c.p, c.o) for c in led.stated()}
    out = []
    for m, e in list(led.entities.items()):
        if e.cls != "EmailMessage":
            continue
        blocks = [b for s in e.props.get("subject", []) for b in src.headers.get(" ".join(s.lower().split()), [])]
        if not blocks:
            continue
        if not e.props.get("sentTime") and len(blocks) == 1 and (iso := iso_time(blocks[0].get("Date", ""))):
            c = propose_claim(led, m, "sentTime", iso, True, "prop", "header")
            out += [c] if c else []
        for field, p in (("From", "from"), ("To", "to"), ("Cc", "to")):
            for addr, a in addresses.items():
                if addr and (m, p, a) not in have and all(addr in b.get(field, "").lower() for b in blocks):
                    c = propose_claim(led, m, p, a, False, "prop", "header")
                    out += [c] if c else []
    return out


def from_literals(led: Ledger) -> list[Claim]:
    classes = classes_of(led)
    out = []
    for c in list(led.stated()):
        if not c.lit:
            continue
        cls = led.entities.get(c.s, None)
        cls = cls.cls if cls else None
        spec = prop_spec(classes.get(c.s, set()), c.p)
        if not spec:
            continue
        value = c.o
        if spec["range"].endswith("dateTime") and (iso := iso_time(c.o)) and iso != c.o:
            alt = propose_claim(led, c.s, c.p, iso, True, "prop", "normalize")
            out += [alt] if alt else []
            value = iso
        for p in LITERAL_PROPS.get(cls, []):
            q = prop_spec(classes.get(c.s, set()), p)
            if p != c.p and q and q["range"] == spec["range"]:
                alt = propose_claim(led, c.s, p, value, True, "prop", "literal-alternative")
                out += [alt] if alt else []
    return out


def from_llm(led: Ledger, src: Source, proposal: dict) -> tuple[list[Claim], list[dict]]:
    """Facts [subject, property, object] per document, names as "Class: key". Returns the claims and the rejections."""
    res = Resolver(led, src)
    classes = classes_of(led)
    rejected, out = [], []
    facts = [(d["doc"], *f) for d in proposal.get("docs", []) for f in d.get("facts", []) if len(f) == 3]
    lits = defaultdict(lambda: defaultdict(list))
    for doc, s, p, o in facts:
        lits[(doc, s)][p].append(o)

    def reject(fact, why):
        rejected.append({"fact": list(fact), "why": why})

    def stated_times(doc, name):
        cls = name.partition(":")[0].strip()
        return {iso_time(v) for v in lits[(doc, name)].get({"Event": "startTime", "EmailMessage": "sentTime",
                                                             "Message": "sentTime"}.get(cls, ""), [])} - {None}

    for doc, name in list(dict.fromkeys((d, x) for d, s, _, o in facts for x in (s, o) if ":" in x)):
        cls, _, key = (x.strip() for x in name.partition(":"))
        kp = keys.KEYS.get(cls, [None])[0]
        if kp and not lits[(doc, name)].get(kp):
            facts.append((doc, name, kp, key))
        elif cls == "EmailAccount":
            facts.append((doc, name, "emailAddress", f"EmailAddress: {key}"))
    under = defaultdict(set)
    for doc, subj, p, o in facts:
        if p in LITERAL_PROPS.get(subj.partition(":")[0].strip(), []):
            under[(doc, subj, flat(o))].add(p)
    have = stated_keys(led)
    for fact in facts:
        doc, subj, p, o = fact[0], fact[1], fact[2].split(":")[-1].strip(), fact[3]
        if len(under.get((doc, subj, flat(o)), ())) > 1:
            reject(fact, f"one value under {sorted(under[(doc, subj, flat(o))])}")
            continue
        r = res.resolve(doc, subj, stated_times(doc, subj))
        if not isinstance(r, tuple):
            reject(fact, f"subject: {r}")
            continue
        s, cs = r[0], led.entities[r[0]].cls
        if p in LITERAL_PROPS.get(cs, []) or (p in keys.KEYS.get(cs, []) and ":" not in o):
            value = flat(o)
            if not any(value in flat(b["text"]) for b in src.blocks):
                reject(fact, "value is not a span of the source")
                continue
            spec = prop_spec(classes.get(s, set()) | {cs}, p)
            if spec and spec["range"].endswith("dateTime"):
                if not (value := iso_time(value)):
                    reject(fact, "span is not a date-time")
                    continue
            if s in res.new and res.new[s] == (p, value):
                c = propose_claim(led, s, p, value, True, "prop", "llm-key")
                out += [c] if c else []
                continue
            if any(keys.norm(p, c.o) == keys.norm(p, value) for c in led.stated() if c.s == s and c.p == p):
                reject(fact, "the graph states this value")
                continue
            c = propose_claim(led, s, p, value, True, "prop", "llm")
            out += [c] if c else []
            continue
        kind = next((k for k in KIND_CLASSES if k.lower() == p.lower()), None)
        r = res.resolve(doc, o, stated_times(doc, o)) if ":" in o else "not an entity"
        if not isinstance(r, tuple):
            reject(fact, f"object: {r}")
            continue
        t = r[0]
        if not kind and p not in LINK_PROPS:
            reject(fact, f"{p} is not a link of the profile")
            continue
        if (s, kind or p, t) in have:
            reject(fact, "the graph states this link")
            continue
        c = propose_claim(led, s, kind or p, t, False, "rel" if kind else "prop", "llm")
        out += [c] if c else []
    return out, rejected


def propose_pass(led: Ledger, src: Source, verifier, margin: float, add_at: float, proposals: Path | None = None,
                 case: str | None = None, **render) -> dict:
    """Generate every proposal, then give each the same evidence a stated claim gets."""
    merged = merge_duplicates(led)
    led.meta["add_at"] = add_at
    made = {"reading": from_readings(led), "header": from_headers(led, src), "literal": from_literals(led)}
    rejected = []
    if proposals is not None:
        path = proposals / f"{case}.json" if case else proposals
        if path.exists():
            import json
            made["llm"], rejected = from_llm(led, src, json.loads(path.read_text()))
    led.meta["proposed"] = {k: len(v) for k, v in made.items()}
    led.meta["llm_rejected"] = rejected
    verify(led, src, verifier, [c for cs in made.values() for c in cs], **render)
    return {"merged": sum(len(m) - 1 for m in merged), **led.meta["proposed"]}
