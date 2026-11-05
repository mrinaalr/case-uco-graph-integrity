"""Pass 1, backward verification: what the source says of each claim, attached as evidence. Nothing is decided here.

For every claim with no evidence yet (stated claims first; proposed claims when the forward pass sends them back):

1. Render the claim as one plain sentence (hook.render: "Luca Petrov is employed by Redfern Components Group.").
   An entity with no literal of its own (an email account) is named by the entity it links to.
2. Retrieve the top_k passages most similar to the sentence (the hook's embedder) and label each pair with the NLI
   model: `supports`, `contradicts` or `neutral`, with the entailment probability. One evidence row per passage.
3. Span evidence, which needs no model: a literal that occurs verbatim in a passage naming its subject (`span`,
   `supports`); an object claim whose two entities are both named in one passage (`span`, `anchors`: the passage is
   about them, which is not yet support for the edge).
4. Modality, read from the best supporting passage with a word list: `reported` ("alleged", "according to"),
   `hedged` ("may", "appears"), `negated` ("not", "denied"), else `asserted`. Recorded, never used to remove.

The hook's templates stay available for parity with its published runs: `template="full"` puts the CASE/UCO
definitions in the sentence and `passage_unit="sentence"` reads mail headers one line at a time, as hook-v1 did."""

from __future__ import annotations

import re

from hook import label, render
from reconcile import keys
from reconcile.ingest import entities_view
from reconcile.ledger import Claim, Ledger
from reconcile.source import Source, cite

LABEL = {"supported": "supports", "contradicted": "contradicts", "not_enough_evidence": "neutral"}
REPORTED = re.compile(r"\b(alleged(?:ly)?|reportedly|according to|claim(?:s|ed)?|said to|suspected|believed|purported(?:ly)?)\b", re.I)
HEDGED = re.compile(r"\b(may|might|possibly|perhaps|appears?|seem(?:s|ed)?|likely|unclear)\b", re.I)
NEGATED = re.compile(r"\b(not|never|no|denied|denies|without)\b", re.I)


def modality(text: str) -> str:
    if NEGATED.search(text):
        return "negated"
    if REPORTED.search(text):
        return "reported"
    if HEDGED.search(text):
        return "hedged"
    return "asserted"


def named_entities(led: Ledger) -> dict[str, dict]:
    """The hook's entities view, with an entity that has no literal named by the one it links to."""
    ents = entities_view(led)
    for iri, e in list(ents.items()):
        if label(iri, ents):
            continue
        linked = next((n for vs in e["props"].values() for o in vs if o in ents and (n := label(o, ents))), None)
        if linked:
            ents[iri] = {**e, "props": {**e["props"], "linked": [linked[1]]}}
    return ents


def sentence_of(c: Claim, ents: dict, template: str = "plain") -> str:
    return render(c.as_triple(), ents, template)


def verify(led: Ledger, src: Source, verifier, claims: list[Claim] | None = None, *, template: str = "plain",
           passage_unit: str = "block", query: str = "plain", linked: bool = True) -> None:
    todo = [c for c in (claims if claims is not None else led.stated()) if not c.evidence]
    if not todo:
        return
    ents = named_entities(led) if linked else entities_view(led)
    passages = src.blocks if passage_unit == "block" else src.passages
    sentences = [sentence_of(c, ents, template) for c in todo]
    queries = [sentence_of(c, ents, "plain") for c in todo] if query == "plain" and template != "plain" else sentences
    unique = list(dict.fromkeys(zip(sentences, queries)))
    checked = dict(zip(unique, verifier.check([s for s, _ in unique], passages, [q for _, q in unique])))
    mentions = {e.id: keys.entity_mentions(keys.naming(e.props, e.cls), src.index, e.cls)["sents"] for e in led.entities.values()}
    for e in led.entities.values():
        e.mentions = sorted(mentions[e.id])
    for c, s, q in zip(todo, sentences, queries):
        c.sentence = s
        for p in checked[(s, q)]:
            c.evidence.append({"method": "nli", "label": LABEL[p["verdict"]], "score": p["entailment"],
                               "similarity": p["similarity"], "unit": passage_unit, "passage": src.at.get((p["doc"], p["sentence"])),
                               "cite": cite(p), "hypothesis": s})
        if c.lit:
            for i in sorted(keys.ground_literal(c.p, c.o, src.index) & mentions.get(c.s, set())):
                c.evidence.append({"method": "span", "label": "supports", "score": 1.0, "unit": "block", "passage": i,
                                   "cite": cite(src.blocks[i]), "hypothesis": c.o})
        elif c.o in led.entities:
            for i in sorted(mentions.get(c.s, set()) & mentions.get(c.o, set())):
                c.evidence.append({"method": "span", "label": "anchors", "score": 1.0, "unit": "block", "passage": i,
                                   "cite": cite(src.blocks[i]), "hypothesis": s})
        best = max((e for e in c.evidence if e["label"] == "supports" and e["method"] == "nli"),
                   key=lambda e: e["score"], default=None)
        c.modality = modality(best["cite"]["text"]) if best else "unknown"
