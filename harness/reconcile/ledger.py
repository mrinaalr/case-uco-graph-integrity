"""The ledger: every claim a graph makes, could make, or should make, with its evidence and its verdict.

A claim is one edge, (subject, property, object), where subject and object name entities in `entities` or the object
is a literal. Claims come from the graph (origin `stated`), from the ontology's other readings of the same entities
(`reading`), or from the source (`proposed`). Passes only add to a claim's record: `evidence` (what the source says of
it, by what method), `checks` (what the ontology says), `competitors` (the readings that cannot hold with it, and by
how much each outranks it on each passage). `policy` reads the record and sets `status`; `decisions` keeps every
status change with its reason. The ledger is written as JSONL and read back without loss."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

STATED, READING, PROPOSED = "stated", "reading", "proposed"
# Verdicts. A stated claim starts `undecided`.
SUPPORTED, CONTRADICTED, AMBIGUOUS, INSUFFICIENT, MALFORMED, UNDECIDED = (
    "supported", "contradicted", "ambiguous", "insufficient", "malformed", "undecided")
VERDICTS = (SUPPORTED, CONTRADICTED, AMBIGUOUS, INSUFFICIENT, MALFORMED)


def claim_id(s: str, p: str, o: str, lit: bool) -> str:
    return hashlib.sha1(f"{s}\t{p}\t{o}\t{int(lit)}".encode()).hexdigest()[:16]


@dataclass
class Entity:
    id: str                          # the IRI the graph gave it, or `new:<n>` for one the source proposes
    cls: str
    props: dict[str, list[str]] = field(default_factory=dict)
    members: list[str] = field(default_factory=list)  # input IRIs merged into this entity (itself first)
    origin: str = STATED
    mentions: list[int] = field(default_factory=list)  # passage indices (Source.blocks) that name it


@dataclass
class Claim:
    id: str
    s: str
    p: str
    o: str
    lit: bool
    kind: str                        # "rel" (a Relationship node) or "prop" (a property on the node or its facet)
    origin: str = STATED
    stated_by: list[str] = field(default_factory=list)  # the Relationship node, or "<holder>|<property>"
    sentence: str = ""               # the plain rendering the source is asked about
    evidence: list[dict] = field(default_factory=list)   # {method, label, score, passage: int|None, cite, hypothesis}
    checks: dict[str, dict] = field(default_factory=dict)  # name -> {result: pass|fail|skip, reason}
    competitors: list[dict] = field(default_factory=list)  # {claim: id, sentence, passages: [{passage, own, rival}]}
    entails: list[str] = field(default_factory=list)
    modality: str = "unknown"        # asserted | reported | hedged | negated | unknown, read from the passage
    status: str = UNDECIDED
    decided_by: str | None = None    # the policy rule that set the status
    note: str | None = None

    @property
    def key(self) -> tuple[str, str, str, bool]:
        return (self.s, self.p, self.o, self.lit)

    def as_triple(self) -> dict:
        """The hook's triple shape, for its pure functions (render, schema_checks, competitors)."""
        origin = f"rel|{self.stated_by[0]}" if self.kind == "rel" and self.stated_by else \
            f"rel|{self.id}" if self.kind == "rel" else f"prop|{self.s}|{self.p}"
        return {"s": self.s, "p": self.p, "o": self.o, "lit": self.lit, "origin": origin}

    def supported_passages(self) -> list[dict]:
        return [e for e in self.evidence if e["label"] == "supports"]


@dataclass
class Decision:
    claim: str
    stage: str
    rule: str
    before: str
    after: str
    reason: str


class Ledger:
    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.claims: dict[str, Claim] = {}
        self.decisions: list[Decision] = []
        self.meta: dict = {}

    # -- building --------------------------------------------------------------------------------------------------
    def add_entity(self, e: Entity) -> Entity:
        self.entities[e.id] = e
        return e

    def add_claim(self, s: str, p: str, o: str, lit: bool, kind: str, origin: str = STATED, **kw) -> Claim:
        """One claim per (s, p, o, lit): a second statement of the same edge adds to stated_by."""
        cid = claim_id(s, p, o, lit)
        if cid in self.claims:
            c = self.claims[cid]
            for by in kw.get("stated_by", []):
                if by not in c.stated_by:
                    c.stated_by.append(by)
            if origin == STATED and c.origin != STATED:
                c.origin = STATED
            return c
        c = Claim(cid, s, p, o, lit, kind, origin, **kw)
        self.claims[cid] = c
        return c

    def decide(self, c: Claim, stage: str, rule: str, status: str, reason: str) -> None:
        if c.status != status or c.decided_by != rule:
            self.decisions.append(Decision(c.id, stage, rule, c.status, status, reason))
        c.status, c.decided_by = status, rule

    # -- reading ---------------------------------------------------------------------------------------------------
    def by_origin(self, origin: str) -> list[Claim]:
        return [c for c in self.claims.values() if c.origin == origin]

    def stated(self) -> list[Claim]:
        return self.by_origin(STATED)

    def accepted(self) -> list[Claim]:
        return [c for c in self.claims.values() if c.status == SUPPORTED]

    def find(self, s: str, p: str, o: str, lit: bool) -> Claim | None:
        return self.claims.get(claim_id(s, p, o, lit))

    def __iter__(self) -> Iterator[Claim]:
        return iter(self.claims.values())

    # -- I/O -------------------------------------------------------------------------------------------------------
    def write(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "claims.jsonl").write_text("".join(json.dumps(asdict(c)) + "\n" for c in self.claims.values()), encoding="utf-8")
        (out / "entities.jsonl").write_text("".join(json.dumps(asdict(e)) + "\n" for e in self.entities.values()), encoding="utf-8")
        (out / "decisions.jsonl").write_text("".join(json.dumps(asdict(d)) + "\n" for d in self.decisions), encoding="utf-8")
        (out / "ledger.json").write_text(json.dumps(self.meta, indent=1), encoding="utf-8")

    @classmethod
    def read(cls, out: Path) -> "Ledger":
        led = cls()
        for line in (out / "entities.jsonl").read_text(encoding="utf-8").splitlines():
            e = Entity(**json.loads(line))
            led.entities[e.id] = e
        for line in (out / "claims.jsonl").read_text(encoding="utf-8").splitlines():
            c = Claim(**json.loads(line))
            led.claims[c.id] = c
        for line in (out / "decisions.jsonl").read_text(encoding="utf-8").splitlines():
            led.decisions.append(Decision(**json.loads(line)))
        if (out / "ledger.json").exists():
            led.meta = json.loads((out / "ledger.json").read_text(encoding="utf-8"))
        return led

    def summary(self) -> dict:
        out = {"entities": len(self.entities), "claims": len(self.claims), "decisions": len(self.decisions)}
        for origin in (STATED, READING, PROPOSED):
            cs = self.by_origin(origin)
            out[origin] = {"n": len(cs), **{v: sum(c.status == v for c in cs) for v in (*VERDICTS, UNDECIDED)}}
        return out
