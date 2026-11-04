"""Completion selector: an LLM proposes the facts the source documents state, and only what the source and the
ontology verify enters the graph. Reads results/RUN/<arm>/<case>/graph.jsonld and writes results/RUN/<arm>+llm/<case>/:
graph.jsonld, run.json and llm.jsonl with one row per fact proposed and per entity added. The proposals do not depend
on the graph and are kept once per case in results/RUN/proposals/<case>.json (each document's reply and facts).

1. Identity. Entities of one class with one key are merged (selector.merge_duplicates).
2. Proposal. The LLM ([llm] endpoint, --model) reads one document at a time and lists its facts as [subject,
   property, object] in the task's vocabulary (VOCAB, LINKS, the ten relation kinds), each entity named "Class: key",
   values as the text writes them. Each mail-header block adds its message's sentTime, from and to (Cc: included).
3. Entities. A name's key must be an exact span of a source passage. It is the graph entity of a compatible class that
   carries the key under any property (meaning.holds: the question scorer's match, so an account number held as a
   name finds its account); an event or message is named within its document and told apart from others of its key
   by its time. A name that matches several entities, or a new person or organization whose name is part of an
   existing one's, is no entity. Otherwise the name is a new entity, which enters only with a link that passes step 5.
   Each name states its key (unless a fact gives the key); an email account, the address it links to.
4. Literals. A value enters only as an exact span of a source passage (whitespace collapsed); a date-time is that span
   parsed to ISO form. A value the LLM gives under several properties of one entity enters under none. A property the
   graph already fills keeps its value, unless no fill is grounded in the source (score.ground_literal), in which case
   an accepted value replaces it.
5. Verification, by the hook's two stages on the proposed edges alone. Left: the edge's plain sentence (selector.say)
   is retrieved against the passages (mail-header runs as one passage) and kept when NLI labels a retrieved passage
   entailment with at least [selector] add_threshold; a literal must also occur in a passage that names its subject.
   Right: domain, range, datatype and self-loop; mail headers by rule (hook.header_check for a message's time, sender
   and recipients; selector.corresponded for Communicated_With), else contrast against the readings that cannot hold
   with the edge, at [hook] contrast_margin. An email account's emailAddress is checked by schema alone. A link
   written backwards is turned when only the reverse fits the kind's domain and range. A link the graph states, or
   one a stated or accepted link entails (Initiated implies Participated_In), is not added.
6. Cardinality. Several accepted values for one single-valued slot keep the one whose contrast advantage leads the
   next by more than the margin, else none (an abstention, recorded).

Nothing else the method wrote is removed: run it on <arm>+sel to complete the selector's graph.

    python harness/selector_llm.py --run-id RUN --arm b_control[,...] [--data data_dev] [--model tinker] [--cases ...]
                                   [--concurrency 8] [--resume] [--batch 16]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
import tomllib
import uuid
from collections import defaultdict
from pathlib import Path

import rdflib
from case_uco.graph import DEFAULT_CONTEXT

from graphkit import HARNESS, RELATION_KINDS, SCHEMA, case_validate, expand, graph_triples, iso_time, load_graph
from hook import (BATCH, ENTAILS, ancestors, HAS_FACET, HEADER_PROPS, KIND_CLASSES, SYMMETRIC, Verifier, advantage, contrast_result,
                  contrast_scores, header_blocks, header_check, headers, holder_classes, kind_of, label,
                  prop_spec, remove, schema_checks)
from llm import CONFIG, case_dirs, client, doc_ids, document_text, load_config, passages, tokens_of
from pipeline_monolith import extract_block
from meaning import holds
from score import entity_mentions, ground_literal, linked_keys, norm
from selector import EMAIL, corresponded, facet_for, merge_duplicates, naming, say, source_index

logging.getLogger("rdflib").setLevel(logging.CRITICAL)
RDF_TYPE = rdflib.RDF.type
# The task's vocabulary: each class's key, its other literals, and the facet that holds them.
VOCAB = {"Person": ("name", []), "Organization": ("name", []),
         "Location": ("street", ["locality", "region", "postalCode"]), "EmailAddress": ("addressValue", []),
         "EmailAccount": (None, []), "Account": ("accountIdentifier", ["accountType"]),
         "ApplicationAccount": ("accountIdentifier", []), "Event": ("eventType", ["startTime"]),
         "EmailMessage": ("subject", ["sentTime"]), "Message": ("messageText", ["sentTime"])}
FACET = {"Location": "SimpleAddressFacet", "EmailAddress": "EmailAddressFacet", "EmailAccount": "EmailAccountFacet",
         "Account": "AccountFacet", "ApplicationAccount": "AccountFacet", "EmailMessage": "EmailMessageFacet",
         "Message": "MessageFacet"}
# Object properties: (class, property) -> the classes it points to.
LINKS = {("Account", "accountIssuer"): {"Organization"}, ("EmailMessage", "from"): {"EmailAddress"},
         ("EmailMessage", "to"): {"EmailAddress"}, ("Message", "from"): {"ApplicationAccount"},
         ("Message", "to"): {"ApplicationAccount"}, ("EmailAccount", "emailAddress"): {"EmailAddress"}}
MANY = {"to"}  # the object property that takes several values
TIMED = {"Event": "startTime", "EmailMessage": "sentTime", "Message": "sentTime"}  # the time that tells two apart

PROMPT = """You extract a CASE/UCO knowledge graph from one investigation document, as a list of facts.

Classes, each with its key value and its other values:
{classes}

Links (source -> target):
{links}

Each fact is [subject, property, object]. Name every entity as "Class: key value", e.g. "Person: Dana Fischer",
"Event: vendor onboarding", "EmailMessage: Quarter-end vendor payments", "EmailAccount: dana.fischer@stonebridge.com".
The object of a link is an entity; the object of a value is the value.

Rules:
- Copy every key and value character for character from the document. Write dates and times exactly as the text
  writes them (e.g. "October 4, 2025 at 16:45 UTC", "Thu, 23 Oct 2025 16:00:00 +0000").
- Name an entity the same way in every fact.
- A person who uses an email address holds it (Holds_Account) and holds its EmailAccount, which links to the address
  by emailAddress.
- A message's From:, To: and Date: lines give its from, to and sentTime. Two people communicated when one wrote to
  the other.
- Only what the document states. Do not infer.

Reply with one ```json code block holding the list of facts and nothing else, e.g.
[["Event: vendor onboarding", "startTime", "October 15, 2025 at 09:15 UTC"],
 ["Person: Mei Holloway", "Initiated", "Event: vendor onboarding"]]

=== Document {doc} ({kind}) ===
{text}"""


def vocabulary() -> tuple[str, str]:
    classes = "\n".join(f"- {c}: " + (f"key {k}" if k else "key: the address of its emailAddress") +
                        (f"; {', '.join(rest)}" if rest else "") for c, (k, rest) in VOCAB.items())
    links = [f"- {k} ({RELATION_KINDS[k]}): {' or '.join(sorted(d))} -> {' or '.join(sorted(r))}"
             for k, (d, r) in KIND_CLASSES.items()]
    links += [f"- {p}: {c} -> {' or '.join(sorted(r))}" for (c, p), r in LINKS.items()]
    return classes, "\n".join(links)


def lit_props(cls: str) -> list[str]:
    key, rest = VOCAB.get(cls, (None, []))
    return [p for p in (key, *rest) if p]


def key_prop(cls: str) -> str:
    return VOCAB[cls][0] or "addressValue"  # an email account is named by its address


def prepare(graph_path: Path) -> tuple[rdflib.Graph, list, dict, list[dict]]:
    """The graph with duplicates merged, and its entities and triples, email accounts named by their address."""
    g = load_graph(graph_path)
    merged = merge_duplicates(g)
    entities, triples = graph_triples(g)
    for iri, e in list(entities.items()):
        linked = next((n for vs in e["props"].values() for o in vs if o in entities and (n := label(o, entities))), None)
        if not label(iri, entities) and linked:
            entities[iri] = {**e, "props": {**e["props"], "linked": [linked[1]]}}
    return g, merged, entities, triples


def parse_reply(text: str) -> tuple[list[list[str]], str | None]:
    block = extract_block(text, "json") or text[text.find("["): text.rfind("]") + 1]
    try:
        doc = json.loads(block)
    except json.JSONDecodeError:
        return [], "no parseable JSON"
    if isinstance(doc, dict):
        doc = next((v for v in doc.values() if isinstance(v, list)), [])
    facts = [[str(x) for x in f] for f in doc if isinstance(f, list) and len(f) == 3] if isinstance(doc, list) else []
    return facts, None


async def propose(case_dir: Path, cfg: dict, llm, gate: asyncio.Semaphore) -> dict:
    """One call per document; the facts do not depend on the graph, so every arm reads the same proposal."""
    classes, links = vocabulary()

    async def one(doc: str, kind: str) -> dict:
        prompt = PROMPT.format(classes=classes, links=links, doc=doc, kind=kind, text=document_text(case_dir, doc))
        async with gate:
            resp = await llm.chat.completions.create(
                model=cfg["llm"]["model"], temperature=cfg["llm"]["temperature"], max_tokens=cfg["llm"]["max_tokens"],
                extra_body=cfg["llm"].get("extra_body"), messages=[{"role": "user", "content": prompt}])
        text = resp.choices[0].message.content or ""
        facts, error = parse_reply(text)
        return {"doc": doc, "reply": text, "facts": facts, "error": error, "tokens": tokens_of(resp)}

    docs = await asyncio.gather(*(one(d, k) for d, k in doc_ids(case_dir).items()))
    return {"docs": list(docs), "facts": [f for d in docs for f in d["facts"]],
            "tokens": {k: sum(d["tokens"][k] for d in docs) for k in ("prompt", "completion")}}


def flat(text: str) -> str:
    return " ".join(str(text).split())


def spans(value: str, source: list[dict]) -> set[int]:
    """The passages that hold value verbatim (whitespace collapsed)."""
    v = flat(value)
    return {i for i, p in enumerate(source) if v and v in flat(p["text"])}


def put(g: rdflib.Graph, iri: str, cls: str, prop: str, value: str, lit: bool) -> None:
    """Write one value on the entity, or on its facet for the property (created if missing)."""
    node = rdflib.URIRef(iri)
    if prop in SCHEMA.get(cls, {}).get("props", {}):
        holder, spec = node, SCHEMA[cls]["props"][prop]
    elif found := facet_for(g, iri, prop):
        holder, spec = found
    else:
        fcls = FACET[cls]
        holder = rdflib.URIRef(f"{DEFAULT_CONTEXT['kb']}llm-{fcls}-{uuid.uuid4()}")
        g.add((holder, RDF_TYPE, rdflib.URIRef(expand(SCHEMA[fcls]["type"]))))
        g.add((node, HAS_FACET, holder))
        spec = SCHEMA[fcls]["props"][prop]
    rng = spec["range"]
    o = (rdflib.Literal(value) if rng.endswith("#string") else
         rdflib.Literal(value, datatype=rdflib.URIRef(rng), normalize=False)) if lit else rdflib.URIRef(value)
    g.add((holder, rdflib.URIRef(expand(spec["key"])), o))


def relate(g: rdflib.Graph, s: str, kind: str, o: str) -> None:
    r = rdflib.URIRef(f"{DEFAULT_CONTEXT['kb']}rel-llm-{uuid.uuid4()}")
    g.add((r, RDF_TYPE, rdflib.URIRef(expand("uco-core:Relationship"))))
    g.add((r, rdflib.URIRef(expand("uco-core:source")), rdflib.URIRef(s)))
    g.add((r, rdflib.URIRef(expand("uco-core:target")), rdflib.URIRef(o)))
    g.add((r, rdflib.URIRef(expand("uco-core:kindOfRelationship")), rdflib.Literal(kind)))
    g.add((r, rdflib.URIRef(expand("uco-core:isDirectional")), rdflib.Literal(True)))


def complete_case(case_dir: Path, graph_path: Path, out: Path, proposal: dict, verifier: Verifier, margin: float,
                  add_at: float) -> dict:
    g, merged, entities, triples = prepare(graph_path)
    raw = passages(case_dir)
    source = header_blocks(raw)
    src = source_index(source)
    heads = headers(raw)
    cls_of = {iri: e["class"] for iri, e in entities.items()}
    keyed = linked_keys({i: e["props"] for i, e in entities.items()},
                        {(t["s"], t["p"]): t["o"] for t in triples if not t["lit"]})
    rows = []

    def reject(fact: tuple, why: str) -> None:
        rows.append({"fact": fact, "action": "reject", "why": why})

    # Entities: "Class: key", the key a span of the source, matched to the graph entities that carry the key under
    # any property (meaning.holds); a new entity otherwise. An event or message is named within its document and
    # told apart from others of its key by its time.
    def token(doc: str, name: str) -> tuple:
        return (doc if name.partition(":")[0].strip() in TIMED else None, name)

    facts = [(d["doc"], *f) for d in proposal["docs"] for f in d["facts"]]
    for blocks in heads.values():  # each mail-header block states its message's time, sender and recipients
        for b in blocks:
            m = f"EmailMessage: {flat(b['Subject'])}"
            facts += [(b["at"]["doc"], m, "sentTime", b["Date"])] * bool(b.get("Date"))
            facts += [(b["at"]["doc"], m, p, f"EmailAddress: {a}") for f, p in (("From", "from"), ("To", "to"), ("Cc", "to"))
                      for a in EMAIL.findall(b.get(f, ""))]
    lits = defaultdict(lambda: defaultdict(list))  # token -> property -> values, for matching addresses and times
    for doc, s, p, o in facts:
        lits[token(doc, s)][p].append(o)
    named = {}  # token -> (iri, class, key) or the reason it names no entity
    new = {}  # iri -> (key property, key) of an entity the LLM added

    def times(cls: str, props: dict) -> set:
        return {iso_time(v) for v in props.get(TIMED.get(cls, ""), [])} - {None}

    def resolve(tok: tuple):
        if tok in named:
            return named[tok]
        cls, _, key = (x.strip() for x in tok[1].partition(":"))
        if cls not in VOCAB or not key:
            named[tok] = f"{tok[1]!r} is not a vocabulary class and key"
            return named[tok]
        if not spans(key, source):
            named[tok] = "key is not a span of the source"
            return named[tok]
        kp, at = key_prop(cls), times(cls, lits[tok])
        hits = [i for i, e in entities.items() if i not in new and holds(
            {"class": e["class"], "props": keyed[i]}, cls, lits[tok], (kp, norm(kp, key)))]
        hits = [i for i in hits if not at or not times(cls, keyed[i]) or at & times(cls, keyed[i])]
        if len(hits) > 1:
            hits = [i for i in hits if entities[i]["class"] == cls] or hits
        part = cls in ("Person", "Organization") and next((
            v for i, e in entities.items() if e["class"] == cls for v in keyed[i].get("name", [])
            if set(norm("name", key).split()) < set(norm("name", v).split())), None)
        if len(hits) > 1:
            named[tok] = f"key matches {len(hits)} entities"
        elif not hits and part:
            named[tok] = f"key names {part!r} in part"
        elif hits:
            named[tok] = (hits[0], cls, flat(key))
        elif same := next((v for t, v in named.items() if isinstance(v, tuple) and v[0] in new and v[1] == cls
                           and norm(kp, v[2]) == norm(kp, key)
                           and (not at or not times(cls, lits[t]) or at & times(cls, lits[t]))), None):
            named[tok] = same
        else:
            iri = f"{DEFAULT_CONTEXT['kb']}llm-{cls.lower()}-{uuid.uuid4()}"
            g.add((rdflib.URIRef(iri), RDF_TYPE, rdflib.URIRef(expand(SCHEMA[cls]["type"]))))
            if VOCAB[cls][0]:
                put(g, iri, cls, kp, flat(key), True)
            new[iri], cls_of[iri] = (kp, flat(key)), cls
            named[tok] = (iri, cls, flat(key))
        return named[tok]

    # Each entity named states its key, unless a fact gives it; an email account, the address it links to.
    for doc, name in list(dict.fromkeys((d, x) for d, s, _, o in facts for x in (s, o) if ":" in x)):
        cls, _, key = (x.strip() for x in name.partition(":"))
        if cls in VOCAB and VOCAB[cls][0] and not lits[token(doc, name)].get(VOCAB[cls][0]):
            facts.append((doc, name, VOCAB[cls][0], key))
        elif cls == "EmailAccount":
            facts.append((doc, name, "emailAddress", f"EmailAddress: {key}"))

    # Facts: resolved, in the vocabulary, not already stated; literals as spans.
    have = {(t["s"], kind_of(t) or t["p"], t["o"]) for t in triples}
    held = defaultdict(list)  # (s, p) -> the triples that fill it
    for t in triples:
        held[(t["s"], t["p"])].append(t)
    added, replaces = [], {}  # (s, p, o, lit); a value that replaces ungrounded ones -> those triples

    def fits(s: str, p: str, o: str) -> bool:
        cs, co = ancestors(cls_of.get(s) or ""), ancestors(cls_of.get(o) or "")
        if p in KIND_CLASSES:
            return bool(cs & KIND_CLASSES[p][0] and co & KIND_CLASSES[p][1])
        return bool(co & LINKS.get((cls_of.get(s), p), set()))

    under = defaultdict(set)  # (token, value) -> the literal properties the LLM gives it
    for doc, subj, p, o in facts:
        if p in lit_props(subj.partition(":")[0].strip()):
            under[(token(doc, subj), flat(o))].add(p)
    for fact in facts:
        doc, subj, p, o = fact[0], fact[1], fact[2].split(":")[-1].strip(), fact[3]
        if len(under.get((token(doc, subj), flat(o)), ())) > 1:
            reject(fact, f"one value under {sorted(under[(token(doc, subj), flat(o))])}")
            continue
        r = resolve(token(doc, subj))
        if not isinstance(r, tuple):
            reject(fact, f"subject: {r}")
            continue
        s, cs = r[0], cls_of[r[0]]
        if p in lit_props(r[1]) and p not in lit_props(cs):
            reject(fact, f"{p} is not a value of {cs}")
            continue
        if p in lit_props(cs):
            value = flat(o)
            if not spans(value, source):
                reject(fact, "value is not a span of the source")
                continue
            if (prop_spec({cs, FACET.get(cs, "")}, p) or {}).get("range", "").endswith("dateTime"):
                if not (value := iso_time(value)):
                    reject(fact, "span is not a date-time")
                    continue
            old = held.get((s, p), [])
            if s in new and new[s] == (p, value):
                continue  # written with the entity
            if any(norm(p, t["o"]) == norm(p, value) for t in old):
                reject(fact, "the graph states this value")
            elif any(ground_literal(p, t["o"], src) for t in old):
                reject(fact, "the graph fills this property with a value the source holds")
            else:
                added.append((s, p, value, True))
                replaces[(s, p, value)] = old
            continue
        kind = next((k for k in KIND_CLASSES if k.lower() == p.lower()), None)
        r = resolve(token(doc, o)) if ":" in o else "not an entity"
        if not isinstance(r, tuple):
            reject(fact, f"object: {r}")
            continue
        target = r[0]
        if not fits(s, kind or p, target) and fits(target, kind or p, s):
            s, target = target, s  # the link written backwards
        if not kind and (cls_of[s], p) not in LINKS:
            reject(fact, f"{p} is not a link of {cls_of[s]}")
        elif not fits(s, kind or p, target):
            reject(fact, f"{kind or p} does not take {cls_of[s]} to {cls_of[target]}")
        elif (s, kind or p, target) in have or (kind in SYMMETRIC and (target, kind, s) in have):
            reject(fact, "the graph states this link")
        elif not kind and p not in MANY and held.get((s, p)):
            reject(fact, "the graph fills this property")
        else:
            added.append((s, kind or p, target, False))
    added = list(dict.fromkeys(added))
    for s, p, o, lit in added:
        if p not in KIND_CLASSES:
            put(g, s, cls_of[s], p, o, lit)
        else:
            relate(g, s, p, o)

    # The hook's two stages on the proposed edges.
    entities, triples = graph_triples(g)
    for iri, e in list(entities.items()):
        linked = next((n for vs in e["props"].values() for o in vs if o in entities and (n := label(o, entities))), None)
        if not label(iri, entities) and linked:
            entities[iri] = {**e, "props": {**e["props"], "linked": [linked[1]]}}
    classes = {iri: holder_classes(g, iri) for iri in entities}
    want = {(s, p, o) for s, p, o, _ in added}
    cand = [t for t in triples if (t["s"], kind_of(t) or t["p"], t["o"]) in want]
    unseen = want - {(t["s"], kind_of(t) or t["p"], t["o"]) for t in cand}
    assert not unseen, f"written but not read back: {sorted(unseen)[:3]}"
    keyed = linked_keys({i: e["props"] for i, e in entities.items()},
                        {(t["s"], t["p"]): t["o"] for t in triples if not t["lit"]})
    where = {i: entity_mentions(naming(keyed[i], e["class"]), src, e["class"])["sents"] for i, e in entities.items()}
    addresses_of = defaultdict(set)
    for t in triples:
        if not t["lit"] and kind_of(t) == "Holds_Account":
            addresses_of[t["s"]] |= {v.lower() for v in keyed.get(t["o"], {}).get("addressValue", [])}
    for i, e in entities.items():
        addresses_of[i] |= {v.lower() for vs in e["props"].values() for v in vs if EMAIL.fullmatch(v)}
    sentences = [say(t, entities) for t in cand]
    checked = verifier.check(sentences, source) if cand else []
    vrows, rule = [], []
    for t, sentence, retrieved in zip(cand, sentences, checked):
        cited = max((p for p in retrieved if p["verdict"] == "supported"), key=lambda p: p["entailment"], default=None)
        head = header_check(t, entities, heads) if t["p"] in HEADER_PROPS else \
            corresponded(t, addresses_of, heads) if kind_of(t) == "Communicated_With" else None
        head = head if head and head["result"] != "skip" else None
        if t["p"] == "emailAddress":
            head = {"result": "pass", "reason": "an email account's address"}
        vrows.append({"s": t["s"], "p": t["p"], "o": t["o"], "lit": t["lit"], "origin": t["origin"],
                      "sentence": sentence, "passages": retrieved,
                      "left": {"kept": cited is not None and cited["entailment"] >= add_at, "cited": cited}})
        rule.append(head)
    contrast_scores([r for r, h in zip(vrows, rule) if not h], [t for t, h in zip(cand, rule) if not h],
                    entities, classes, verifier)
    accepted = []
    for t, r, head in zip(cand, vrows, rule):
        checks = schema_checks(t, classes)
        failed = [c for c, v in checks.items() if v["result"] == "fail"]
        if head:
            ok, by = head["result"] == "pass", "rule"
            r["right"] = {**checks, "header": head}
        else:
            contrast, _ = contrast_result(r, margin)
            r["right"] = {**checks, "contrast": contrast}
            failed += ["contrast"] * (contrast["result"] == "fail")
            ok, by = r["left"]["kept"], "nli"
        if t["lit"] and by != "rule" and not ground_literal(t["p"], t["o"], src) & where.get(t["s"], set()):
            failed.append("anchor")
        r.update(accepted=ok and not failed, by=by, failed=failed or None)
        if r["accepted"]:
            accepted.append((t, r))
    # Implied links, cardinality, and entities left without a link.
    stated = [(t["s"], kind_of(t), t["o"]) for t in triples if (t["s"], kind_of(t) or t["p"], t["o"]) not in want]
    stated += [(t["s"], kind_of(t), t["o"]) for t, _ in accepted]
    keep = [(t, r) for t, r in accepted if not any((s, o) == (t["s"], t["o"]) and kind_of(t) in ENTAILS.get(k, ())
                                                   for s, k, o in stated)]
    for t, r in accepted:
        if (t, r) not in keep:
            r.update(accepted=False, failed=["implied"])
    slots = defaultdict(list)
    for t, r in keep:
        if not t["origin"].startswith("rel|") and t["p"] not in MANY:
            slots[(t["s"], t["p"])].append((t, r))
    for (s, p), xs in slots.items():
        if len({t["o"] for t, _ in xs}) < 2:
            continue
        score = lambda r: 99.0 if r["by"] == "rule" else advantage(r)  # noqa: E731
        ranked = sorted(xs, key=lambda x: -score(x[1]))
        win = ranked[0] if score(ranked[0][1]) - score(ranked[1][1]) > margin else None
        for t, r in xs:
            if win is None or t["o"] != win[0]["o"]:
                r.update(accepted=False, failed=["cardinality"] if win else ["cardinality: abstain"])
    keep = [(t, r) for t, r in keep if r["accepted"]]
    linked = {x for t, _ in keep if not t["lit"] for x in (t["s"], t["o"])}
    for t, r in keep:
        if t["s"] in new and t["s"] not in linked:
            r.update(accepted=False, failed=["entity without a link"])
    nodes = {str(x): x for x in g.all_nodes() if not isinstance(x, rdflib.Literal)}
    for t, r in zip(cand, vrows):
        if not r["accepted"]:
            remove(g, t, nodes)
        elif old := replaces.get((t["s"], t["p"], t["o"])):
            r["replaced"] = [x["o"] for x in old]
            for x in old:
                remove(g, x, nodes)
    for iri in new:
        if iri not in linked:
            node = rdflib.URIRef(iri)
            for f in list(g.objects(node, HAS_FACET)):
                g.remove((f, None, None))
            g.remove((node, None, None))
            g.remove((None, None, node))
    for r in vrows:
        r["passages"] = [{k: p[k] for k in ("doc", "sentence", "text", "verdict", "entailment")} for p in r["passages"]]
        r["left"]["cited"] = r["left"]["cited"] and {k: r["left"]["cited"][k] for k in ("doc", "sentence", "text")}
        rows.append({**r, "action": "add" if r["accepted"] else "reject"})
    rows += [{"entity": iri, "key": list(kv), "action": "add" if iri in linked else "reject",
              "why": None if iri in linked else "no link passed"} for iri, kv in new.items()]
    g.serialize(destination=out / "graph.jsonld", format="json-ld", context=DEFAULT_CONTEXT, indent=2)
    (out / "llm.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    added_rows = [r for r in vrows if r["accepted"]]
    return {"merged": sum(len(m) - 1 for m in merged), "proposed": len(proposal["facts"]),
            "new_entities": len([i for i in new if i in linked]), "candidates": len(cand),
            "added": len(added_rows), "added_literals": sum(r["lit"] for r in added_rows),
            "added_by_rule": sum(r["by"] == "rule" for r in added_rows),
            "replaced": sum(bool(r.get("replaced")) for r in added_rows)}



async def propose_all(cfg: dict, todo: list[tuple[Path, Path]], concurrency: int) -> None:
    llm, gate = client(cfg), asyncio.Semaphore(concurrency)

    async def one(case_dir: Path, path: Path) -> None:
        try:
            p = await propose(case_dir, cfg, llm, gate)
        except Exception as exc:  # a failed call is a recorded outcome: the graph is left as it is
            p = {"docs": [], "facts": [], "error": f"{type(exc).__name__}: {exc}", "tokens": {"prompt": 0, "completion": 0}}
        path.write_text(json.dumps(p, indent=1))
        print(f"proposed {case_dir.name}: {len(p['facts'])} facts "
              f"{[d['error'] for d in p['docs'] if d['error']] or p.get('error', '')}", flush=True)

    await asyncio.gather(*(one(*x) for x in todo))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--arm", required=True, help="comma-separated arms")
    ap.add_argument("--cases")
    ap.add_argument("--data", default="data")
    ap.add_argument("--model", default="tinker")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--resume", action="store_true", help="reuse results/RUN/proposals/<case>.json where present")
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--add-at", type=float, help="override [selector] add_threshold")
    ap.add_argument("--suffix", default="llm")
    args = ap.parse_args()
    cfg = load_config(model=args.model)
    with open(CONFIG, "rb") as fh:
        add_at = args.add_at if args.add_at is not None else tomllib.load(fh)["selector"]["add_threshold"]
    root = HARNESS / "results" / args.run_id
    cache = root / "proposals"
    cache.mkdir(parents=True, exist_ok=True)
    cases = case_dirs(args.cases, args.data)
    asyncio.run(propose_all(cfg, [(c, cache / f"{c.name}.json") for c in cases
                                  if not (args.resume and (cache / f"{c.name}.json").exists())], args.concurrency))
    verifier = Verifier(cfg["hook"], args.batch)
    for arm in args.arm.split(","):
        for case_dir in cases:
            base, out = root / arm / case_dir.name, root / f"{arm}+{args.suffix}" / case_dir.name
            if not (base / "run.json").exists():
                continue
            meta = json.loads((base / "run.json").read_text())
            out.mkdir(parents=True, exist_ok=True)
            proposal = json.loads((cache / f"{case_dir.name}.json").read_text())
            start, info = time.monotonic(), {"final_validation": None}
            if meta["status"] not in ("error", "empty") and (base / "graph.jsonld").exists():
                try:
                    info["completion"] = complete_case(case_dir, base / "graph.jsonld", out, proposal, verifier,
                                                       cfg["hook"]["contrast_margin"], add_at)
                    info["final_validation"] = case_validate(out / "graph.jsonld")["conforms"]
                except Exception as exc:  # an unreadable graph is a recorded outcome, as in the hook
                    info = {"status": "error", "error": f"selector_llm: {type(exc).__name__}: {exc}"[:2000],
                            "final_validation": None}
            sel_s = round(time.monotonic() - start, 1)
            run = {**meta, "arm": f"{arm}+{args.suffix}", **info, "completion_s": sel_s,
                   "completion_model": cfg["llm"]["model"], "completion_tokens": proposal["tokens"],
                   "selector_add_threshold": add_at, "wall_s": round(meta.get("wall_s", 0) + sel_s, 1)}
            (out / "run.json").write_text(json.dumps(run, indent=1))
            print(f"{run['arm']} {case_dir.name}: {run['status']} {info.get('completion')} "
                  f"valid={run['final_validation']} {sel_s}s", flush=True)


if __name__ == "__main__":
    main()
