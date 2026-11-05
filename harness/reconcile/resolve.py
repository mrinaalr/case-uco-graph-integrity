"""Entity resolution on the ledger: which of the graph's entities are one thing, and which thing a name from the
source refers to.

- `merge_duplicates`: entities of one class with one key (keys.key_of: a person's name, an address, an account
  number; an event's type and time) are one entity. The first IRI in sorted order is kept, the others become its
  `members`, and every claim is rewritten onto it; two statements of one edge become one claim.
- `resolve`: a name from the source, "Class: key", to an entity. The key must be an exact span of a passage. It names
  the entity of a compatible class that carries the key under any property (an account number held as a name still
  finds its account), told apart from others of its key by its time where the class has one. A key that matches
  several entities names none; so does a person or organization whose name is part of an existing one's ("Elena"
  beside "Elena Kowalski"). Otherwise it is a provisional entity (origin `proposed`), which reaches the graph only
  with a claim that passes."""

from __future__ import annotations

import uuid
from collections import defaultdict

from case_uco.graph import DEFAULT_CONTEXT
from reconcile import keys
from reconcile.ledger import PROPOSED, Entity, Ledger, claim_id
from reconcile.source import Source

COMPATIBLE = {"Person": {"Identity"}, "Organization": {"Identity"}, "EmailAddress": {"EmailAccount", "ObservableObject"},
              "Account": {"DigitalAccount", "ApplicationAccount", "ObservableObject"},
              "ApplicationAccount": {"Account", "DigitalAccount", "ObservableObject"},
              "EmailMessage": {"Message", "ObservableObject"}, "Message": {"EmailMessage", "ObservableObject"},
              "Event": {"Action"}, "Location": set()}
TIMED = {"Event": "startTime", "EmailMessage": "sentTime", "Message": "sentTime"}  # the time that tells two apart
CONTAINS = {"eventType", "accountType"}


def linked_props(led: Ledger) -> dict[str, dict]:
    """Each entity's literals, an email account carrying the address it links to."""
    return keys.linked_keys({i: e.props for i, e in led.entities.items()},
                            {(c.s, c.p): c.o for c in led.stated() if not c.lit})


def merge_duplicates(led: Ledger) -> list[list[str]]:
    props = linked_props(led)
    groups = defaultdict(list)
    for iri in sorted(led.entities):
        e = led.entities[iri]
        key = keys.key_of(e.cls, props[iri]) if e.cls in keys.KEYS else None
        if key:
            groups[(e.cls, tuple(key))].append(iri)
    merged = [v for v in groups.values() if len(v) > 1]
    for keep, *dups in merged:
        k = led.entities[keep]
        for d in dups:
            e = led.entities.pop(d)
            k.members += [m for m in e.members if m not in k.members]
            for p, vs in e.props.items():
                k.props.setdefault(p, [])
                k.props[p] += [v for v in vs if v not in k.props[p]]
        rewrite = {d: keep for d in dups}
        for c in list(led.claims.values()):
            if c.s in rewrite or (not c.lit and c.o in rewrite):
                del led.claims[c.id]
                led.add_claim(rewrite.get(c.s, c.s), c.p, c.o if c.lit else rewrite.get(c.o, c.o), c.lit, c.kind, c.origin,
                              stated_by=c.stated_by)
    led.meta["merged"] = merged
    return merged


def flat(text: str) -> str:
    return " ".join(str(text).split())


def spans(value: str, src: Source) -> set[int]:
    """The passages that hold value verbatim (whitespace collapsed)."""
    v = flat(value)
    return {i for i, p in enumerate(src.blocks) if v and v in flat(p["text"])}


def compatible(cls: str, wanted: str) -> bool:
    return cls == wanted or cls in COMPATIBLE.get(wanted, set())


def holds(e: Entity, props: dict, wanted: str, key_prop: str, key_norm: str) -> bool:
    """Does entity e carry this key, under any property, as a query by value would find it?"""
    if not compatible(e.cls, wanted):
        return False
    literals = [v for vs in props.values() for v in vs if not v.startswith(("http://", "https://"))]
    if key_prop in CONTAINS:
        return any(key_norm in keys.split_words(v) for v in literals)
    return any(keys.norm(key_prop, v) == key_norm for v in literals)


class Resolver:
    def __init__(self, led: Ledger, src: Source) -> None:
        self.led, self.src = led, src
        self.props = linked_props(led)
        self.named: dict[tuple, tuple | str] = {}
        self.new: dict[str, tuple[str, str]] = {}  # provisional entity -> (key property, key)

    def key_prop(self, cls: str) -> str:
        ks = keys.KEYS.get(cls)
        return ks[0] if ks else "addressValue"

    def times(self, cls: str, props: dict) -> set:
        from graphkit import iso_time
        return {iso_time(v) for v in props.get(TIMED.get(cls, ""), [])} - {None}

    def resolve(self, doc: str | None, name: str, stated_times: set | None = None) -> tuple | str:
        """(entity id, class, key) or the reason the name names nothing. `doc` scopes a timed class's name."""
        tok = (doc if name.partition(":")[0].strip() in TIMED else None, name)
        if tok in self.named:
            return self.named[tok]
        cls, _, key = (x.strip() for x in name.partition(":"))
        if cls not in keys.KEYS or not key:
            self.named[tok] = f"{name!r} is not a class and key of the profile"
            return self.named[tok]
        if not spans(key, self.src):
            self.named[tok] = "key is not a span of the source"
            return self.named[tok]
        kp, at = self.key_prop(cls), stated_times or set()
        hits = [i for i, e in self.led.entities.items() if i not in self.new
                and holds(e, self.props.get(i, e.props), cls, kp, keys.norm(kp, key))]
        hits = [i for i in hits if not at or not self.times(cls, self.props.get(i, {})) or at & self.times(cls, self.props.get(i, {}))]
        if len(hits) > 1:
            hits = [i for i in hits if self.led.entities[i].cls == cls] or hits
        part = cls in ("Person", "Organization") and next((
            v for i, e in self.led.entities.items() if e.cls == cls for v in self.props.get(i, {}).get("name", [])
            if set(keys.norm("name", key).split()) < set(keys.norm("name", v).split())), None)
        if len(hits) > 1:
            self.named[tok] = f"key matches {len(hits)} entities"
        elif not hits and part:
            self.named[tok] = f"key names {part!r} in part"
        elif hits:
            self.named[tok] = (hits[0], cls, flat(key))
        elif same := next((v for t, v in self.named.items() if isinstance(v, tuple) and v[0] in self.new and v[1] == cls
                           and keys.norm(kp, v[2]) == keys.norm(kp, key)), None):
            self.named[tok] = same
        else:
            iri = f"{DEFAULT_CONTEXT['kb']}rec-{cls.lower()}-{uuid.uuid5(uuid.NAMESPACE_URL, f'{cls}|{keys.norm(kp, key)}|{doc or ''}')}"
            props = {kp: [flat(key)]} if keys.KEYS.get(cls) else {}
            self.led.add_entity(Entity(iri, cls, props, [iri], PROPOSED, sorted(spans(key, self.src))))
            self.props[iri] = dict(props)
            self.new[iri] = (kp, flat(key))
            self.named[tok] = (iri, cls, flat(key))
        return self.named[tok]


def drop_unlinked(led: Ledger, accepted_ids: set[str]) -> list[str]:
    """Provisional entities with no accepted object claim leave the ledger with their claims."""
    linked = {x for c in led.claims.values() if c.id in accepted_ids and not c.lit for x in (c.s, c.o)}
    gone = [i for i, e in led.entities.items() if e.origin == PROPOSED and i not in linked]
    for i in gone:
        del led.entities[i]
        for c in list(led.claims.values()):
            if c.s == i or (not c.lit and c.o == i):
                led.decide(c, "resolve", "entity-without-a-link", c.status, f"{i} enters with no link")
                c.note = "dropped: entity without a link"
    return gone
