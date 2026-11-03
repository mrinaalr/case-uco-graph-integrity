"""Ontology selector: the ontology lists what the graph could say about the entities the source names, and the source
picks. Where the hook keeps or removes the edges a method wrote, the selector decides every reading the task's
ontology allows for those entities: a wrong edge is replaced by the reading the source supports (repair), and a
supported reading no edge states is added (recovery). Reads results/RUN/<arm>/<case>/graph.jsonld and writes
results/RUN/<arm>+sel/<case>/: graph.jsonld, run.json, and sel.jsonl with one row per reading decided and per edge
removed or added. Deterministic apart from the hook's two models ([hook] in config.toml); no LLM.

1. Identity. Entities of one class with the same key (score.KEYS: a person's name, an address, an account number; an
   event's type and time) are one entity and are merged. An email account is keyed by the address it links to.
2. Anchoring. Each entity is placed in the source passages that contain its key (score.entity_mentions: exact
   normalized text; an event type also by two consecutive words). Times are not used: a time places whatever else
   happened then. Passages are sentences, with each mail-header run as one passage.
3. Readings. For every pair of entities that share a passage, and every pair an edge already links, the readings
   are the relation kinds and object properties whose domain and range fit, in either direction (hook.readings).
4. Selection. Each reading's plain sentence (say: an account's issuer reads "X issued account N") is scored by NLI on
   the pair's shared prose passages and the prose passages the pair's edges retrieve, with the CASE/UCO definitions
   of the properties in play after the passage. A reading is selected when, on some passage, NLI labels it entailment
   and no reading that cannot hold with it (hook.competitors: not the same fact, not one it entails) outranks it by
   more than [hook] contrast_margin in log-odds. Mail headers are read by rule, not NLI: a message's sender and
   recipients by hook.header_check, and Communicated_With between two people when a message goes from one's address
   to the other's (corresponded). A reading no edge states is added only when NLI selects it on a passage both
   entities share with entailment at least [selector] add_threshold, or the header rule passes it. A reading another
   selected reading entails is dropped (Initiated implies Participated_In), and a single-valued property selected
   more than once keeps the value whose reading leads the next by more than the margin, else none (an abstention,
   recorded). Last, any property CASE/UCO allows once that still holds several values is decided the same way
   (single_valued); spellings of one value keep the one the source uses.
5. Literals. A value must occur in a passage that names its subject (score.ground_literal) or, failing that, be
   entailed by a retrieved passage (the left hook). A date-time in a form xsd:dateTime rejects is rewritten in ISO
   form when it parses. A receivedTime the header rule fails because it is the Date: line becomes the sentTime; a
   literal whose property loses contrast to another of its class's properties on every passage moves to that
   property. A message whose one header block the rule can read gains the sentTime, sender and recipients it lacks.
6. Other edges. An object edge outside the task's readings (an email account's address, an unknown kind) is kept when
   the schema checks do not fail and both entities occur in the source, else when the left hook keeps it.

The selector adds no entity: a fact about an entity the method did not write, or wrote as the wrong thing (a person
named by an email address), stays missing or lands on that entity.

    python harness/selector.py --run-id RUN --arm c_edc [--data data_dev] [--cases ...] [--batch 16]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
import tomllib
import uuid
from collections import defaultdict
from pathlib import Path

import numpy as np
import rdflib
from case_uco.graph import DEFAULT_CONTEXT

from graphkit import HARNESS, SCHEMA, case_validate, expand, graph_triples, iso_time, load_graph
from hook import (BATCH, ENTAILS, HAS_FACET, HEADER, HEADER_PROPS, KIND_CLASSES, PROP_CLASSES, Verifier, competitors, context, header_blocks,
                  header_check, headers, holder_classes, kind_of, label, local, logit, mention, prop_spec, readings, remove,
                  render, schema_checks)
from llm import CONFIG, case_dirs, passages
from score import CANON_GROUPS, KEYS, TIME_PROPS, canon, norm, entity_mentions, ground_literal, key_of, linked_keys, times_in

logging.getLogger("rdflib").setLevel(logging.CRITICAL)
MAX_PASSAGES = 6  # shared passages scored per pair
RDF_TYPE = rdflib.RDF.type
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def source_index(source: list[dict]) -> dict:
    """The passages in score.load_source's form, for score.entity_mentions and score.ground_literal."""
    sents = [p["text"] for p in source]
    return {"sents": sents, "doc_of": [p["doc"] for p in source], "times": [times_in(x) for x in sents],
            "canon": {g: [canon(g, x) for x in sents] for g in CANON_GROUPS}}


def merge_duplicates(g: rdflib.Graph) -> list[list[str]]:
    """Merge entities of one class with one key, in place; returns the merged groups (kept IRI first)."""
    ents, triples = graph_triples(g)
    props = linked_keys({i: e["props"] for i, e in ents.items()},
                        {(t["s"], t["p"]): t["o"] for t in triples if not t["lit"]})
    groups = defaultdict(list)
    for iri in sorted(ents):
        cls = ents[iri]["class"]
        key = key_of(cls, props[iri]) if cls in KEYS else None
        if key:
            groups[(cls, tuple(key))].append(iri)
    merged = [v for v in groups.values() if len(v) > 1]
    for keep, *dups in merged:
        k = rdflib.URIRef(keep)
        for d in map(rdflib.URIRef, dups):
            for p, o in list(g.predicate_objects(d)):
                g.remove((d, p, o))
                g.add((k, p, o))
            for s, p in list(g.subject_predicates(d)):
                g.remove((s, p, d))
                g.add((s, p, k))
    return merged


def facet_for(g: rdflib.Graph, s: str, prop: str) -> tuple[rdflib.URIRef, dict] | None:
    """The subject's facet whose class declares prop, and the property's schema entry."""
    for f in g.objects(rdflib.URIRef(s), HAS_FACET):
        for t in g.objects(f, RDF_TYPE):
            spec = SCHEMA.get(local(t))
            if spec and prop in spec["props"]:
                return f, spec["props"][prop]
    return None


def add_edge(g: rdflib.Graph, t: dict) -> bool:
    """Write one edge: a Relationship node for a relation kind, else the property on the subject's facet."""
    if t["origin"].startswith("rel|"):
        r = rdflib.URIRef(f"{DEFAULT_CONTEXT['kb']}rel-sel-{uuid.uuid4()}")
        g.add((r, RDF_TYPE, rdflib.URIRef(expand("uco-core:Relationship"))))
        g.add((r, rdflib.URIRef(expand("uco-core:source")), rdflib.URIRef(t["s"])))
        g.add((r, rdflib.URIRef(expand("uco-core:target")), rdflib.URIRef(t["o"])))
        g.add((r, rdflib.URIRef(expand("uco-core:kindOfRelationship")), rdflib.Literal(t["p"])))
        g.add((r, rdflib.URIRef(expand("uco-core:isDirectional")), rdflib.Literal(True)))
        return True
    found = facet_for(g, t["s"], t["p"])
    if not found:
        return False
    f, spec = found
    o = rdflib.Literal(t["o"], datatype=rdflib.URIRef(spec["range"])) if t["lit"] else rdflib.URIRef(t["o"])
    g.add((f, rdflib.URIRef(expand(spec["key"])), o))
    return True


def naming(props: dict, cls: str) -> dict:
    """The literals that place an entity in a passage: its key, less any time (a time also places whatever else
    happened then); every non-time literal for a class with no key."""
    keys = set(KEYS.get(cls, [])) - TIME_PROPS
    return {p: v for p, v in props.items() if (p in keys if keys else p not in TIME_PROPS)}


def corresponded(r: dict, addresses_of: dict, heads: dict) -> dict | None:
    """Header rule for Communicated_With: a message from one person's address to the other's (To: or Cc:) passes. Else
    None: prose decides, since a header that names both as recipients says nothing of their talking."""
    a, b = addresses_of.get(r["s"], set()), addresses_of.get(r["o"], set())
    for blocks in heads.values():
        for h in blocks:
            sender, rcpt = h.get("From", "").lower(), f"{h.get('To', '')} {h.get('Cc', '')}".lower()
            for x, y in ((a, b), (b, a)):
                if any(v in sender for v in x) and any(v in rcpt for v in y):
                    return {"result": "pass", "reason": f"From: {h.get('From')} To: {h.get('To')} ({h['at']['doc']})"}
    return None


def single_valued(g: rdflib.Graph, score_value) -> list[dict]:
    """A property CASE/UCO allows once that holds several values (two names after a merge, a repair onto a filled
    property), in place. Values equal under the scorer's normalization are one value spelled two ways: the spelling
    found verbatim in more passages stays, else the longer, else none. Different values are scored by score_value
    (the best entailment log-odds of the value's sentence): one that leads the next by more than the margin stays,
    else none (an abstention). Returns a row per decision."""
    out = []
    for holder in sorted(set(g.subjects()), key=str):
        spec = {}
        for t in g.objects(holder, RDF_TYPE):
            spec |= SCHEMA.get(local(t), {}).get("props", {})
        for p in sorted(set(g.predicates(holder)), key=str):
            entry = spec.get(local(p))
            values = sorted(g.objects(holder, p), key=str)
            if not entry or entry["many"] or len(values) < 2:
                continue
            keep, scores = score_value(holder, local(p), values)
            for o in values:
                if o != keep:
                    g.remove((holder, p, o))
            out.append({"s": str(holder), "p": local(p), "values": [str(v) for v in values], "scores": scores,
                        "action": "keep" if keep is not None else "abstain", "why": "cardinality",
                        "kept": str(keep) if keep is not None else None})
    return out


def say(t: dict, entities: dict) -> str:
    """The plain rendering, with an account's issuer said as the event that makes it one ("Granite Federal Credit Union
    issued account 2622357143."): "The account issuer of N is X" reads as close to "X owns N" as NLI can tell
    (rendering_audit.py)."""
    if t["p"] == "accountIssuer" and not t["lit"]:
        return f"{mention(t['o'], entities, None, 'plain')} issued account {mention(t['s'], entities, None, 'plain')}."
    return render(t, entities, "plain")


def same(a: dict, b: dict) -> bool:
    ka, kb = kind_of(a) or a["p"], kind_of(b) or b["p"]
    return (a["s"], ka, a["o"]) == (b["s"], kb, b["o"]) or (
        ka == kb == "Communicated_With" and (a["s"], a["o"]) == (b["o"], b["s"]))


def select_case(case_dir: Path, graph_path: Path, out: Path, verifier: Verifier, margin: float, add_at: float) -> dict:
    g = load_graph(graph_path)
    merged = merge_duplicates(g)
    entities, triples = graph_triples(g)
    nodes = {str(x): x for x in g.all_nodes() if not isinstance(x, rdflib.Literal)}
    classes = {iri: holder_classes(g, iri) for iri in entities}
    for iri, e in list(entities.items()):  # no literal of its own (an email account): named by what it links to
        linked = next((n for vs in e["props"].values() for o in vs if o in entities and (n := label(o, entities))), None)
        if not label(iri, entities) and linked:
            entities[iri] = {**e, "props": {**e["props"], "linked": [linked[1]]}}
    raw = passages(case_dir)
    source = header_blocks(raw)
    src = source_index(source)
    at = {(p["doc"], p["sentence"]): i for i, p in enumerate(source)}  # a retrieved passage's index
    heads = headers(raw)
    keyed = linked_keys({i: e["props"] for i, e in entities.items()},
                        {(t["s"], t["p"]): t["o"] for t in triples if not t["lit"]})
    where = {i: entity_mentions(naming(keyed[i], e["class"]), src, e["class"])["sents"] for i, e in entities.items()}
    rows, removals, additions = [], [], []
    addresses_of = defaultdict(set)  # a person's email addresses: those it holds, or its own (an address as its name)
    for t in triples:
        if not t["lit"] and kind_of(t) == "Holds_Account":
            addresses_of[t["s"]] |= {v.lower() for v in keyed.get(t["o"], {}).get("addressValue", [])}
    for i, e in entities.items():
        addresses_of[i] |= {v.lower() for vs in e["props"].values() for v in vs if EMAIL.fullmatch(v)}

    # Object readings, by pair.
    pairs: dict[frozenset, dict] = defaultdict(lambda: {"edges": [], "passages": set()})
    for t in triples:
        if not t["lit"] and t["o"] in entities and t["s"] != t["o"]:
            pairs[frozenset((t["s"], t["o"]))]["edges"].append(t)
    by_passage = defaultdict(list)
    for i, ps in where.items():
        for p in ps:
            by_passage[p].append(i)
    for p, ids in by_passage.items():
        for a in ids:
            for b in ids:
                if a < b:
                    pairs[frozenset((a, b))]["passages"].add(p)
    jobs = []  # (pair key, reading index, passage index)
    plan = {}
    for key, pair in pairs.items():
        x, y = sorted(key)
        cands = readings(x, y, entities)
        if not cands:
            continue
        existing = [t for t in pair["edges"] if any(same(t, r) for r in cands)]
        if not existing and not pair["passages"]:
            continue
        prose = sorted(pi for pi in pair["passages"] if not HEADER.match(source[pi]["text"]))
        evidence = prose[:MAX_PASSAGES]
        if existing:
            retrieved = verifier.check([say(t, entities) for t in existing], source)
            evidence = sorted(set(evidence) | {at[(p["doc"], p["sentence"])] for ps in retrieved for p in ps
                                               if not HEADER.match(p["text"])})
        sentences = [say(r, entities) for r in cands]
        ctx = context(cands[0], cands[1:], entities)
        plan[key] = {"cands": cands, "existing": existing, "evidence": evidence, "sentences": sentences, "ctx": ctx,
                     "prose": set(prose)}
        jobs += [(key, ri, pi) for ri in range(len(cands)) for pi in evidence]
    probs = verifier.probs([f"{source[pi]['text']} {plan[k]['ctx']}".strip() for k, _, pi in jobs],
                           [plan[k]["sentences"][ri] for k, ri, _ in jobs]) if jobs else np.zeros((0, 3))
    score = defaultdict(dict)
    for (k, ri, pi), pr in zip(jobs, probs):
        score[k][(ri, pi)] = (float(pr[verifier.supported]), int(pr.argmax()) == verifier.supported)
    chosen = []  # (reading, best log-odds, how, passage)
    for k, pl in plan.items():
        cands = pl["cands"]
        for ri, r in enumerate(cands):
            rivals = {ci for ci, c in enumerate(cands) if any(same(c, x) for x in competitors(r, entities, classes))}
            alive = [pi for pi in pl["evidence"] if score[k][(ri, pi)][1] and all(
                logit(score[k][(ci, pi)][0]) - logit(score[k][(ri, pi)][0]) <= margin for ci in rivals)]
            best = max((score[k][(ri, pi)][0] for pi in alive), default=0.0)
            head = header_check(r, entities, heads) if r["p"] in HEADER_PROPS else \
                corresponded(r, addresses_of, heads) if kind_of(r) == "Communicated_With" else None
            if head and head["result"] != "skip":
                ok, how = head["result"] == "pass", "header"
            else:
                ok, how = bool(alive), "nli"
            stated = any(same(t, r) for t in pl["existing"])
            if ok and not stated and how == "nli" and (best < add_at or not any(pi in pl["prose"] for pi in alive)):
                ok = False
            pi = max(alive, key=lambda p: score[k][(ri, p)][0]) if alive else None
            if ok:
                chosen.append((r, logit(best) if how == "nli" else 99.0, how, pi))
            rows.append({"s": r["s"], "p": r["p"], "o": r["o"], "stated": stated, "selected": ok, "by": how,
                         "entailment": round(best, 4), "passage": source[pi]["text"] if pi is not None else None,
                         "header": head})
    # A reading another selected reading entails is implied, not stated (Initiated entails Participated_In).
    chosen = [c for c in chosen if not any(kind_of(c[0]) in ENTAILS.get(kind_of(d[0]), ()) and
                                           (d[0]["s"], d[0]["o"]) == (c[0]["s"], c[0]["o"]) for d in chosen)]
    # A single-valued object property selected with several values keeps the one whose score leads the next by more
    # than the margin; otherwise none, recorded as an abstention.
    groups = defaultdict(list)
    for c in chosen:
        spec = prop_spec(classes.get(c[0]["s"], set()), c[0]["p"]) if not c[0]["origin"].startswith("rel|") else None
        if spec and not spec["many"]:
            groups[(c[0]["s"], c[0]["p"])].append(c)
    for (subj, prop), cs in groups.items():
        if len({c[0]["o"] for c in cs}) < 2:
            continue
        ranked = sorted(cs, key=lambda c: -c[1])
        keep = ranked[0] if ranked[0][1] - ranked[1][1] > margin else None
        chosen = [c for c in chosen if c not in cs or c is keep]
        rows.append({"s": subj, "p": prop, "values": [c[0]["o"] for c in ranked], "scores": [round(c[1], 2) for c in ranked],
                     "action": "keep" if keep else "abstain", "why": "cardinality"})
    decided = set()
    for k, pl in plan.items():
        for t in pl["existing"]:
            decided.add(id(t))
            if not any(same(t, c[0]) for c in chosen):
                removals.append((t, "not selected"))
        for c in chosen:
            if c[0]["s"] in k and c[0]["o"] in k and not any(same(t, c[0]) for t in pl["existing"]) and \
                    not any(same(t, c[0]) for t in pairs[k]["edges"]):
                additions.append((c[0], "repair" if pl["existing"] else "recover"))

    # Literals, and object edges outside the readings.
    lit_jobs = [t for t in triples if id(t) not in decided]
    checked = verifier.check([render(t, entities, "plain") for t in lit_jobs], source) if lit_jobs else []
    for t, retrieved in zip(lit_jobs, checked):
        left = any(p["verdict"] == "supported" for p in retrieved)
        checks = schema_checks(t, classes)
        if not t["lit"]:
            failed = [c for c, v in checks.items() if v["result"] == "fail"]
            ok = not failed and ((where.get(t["s"]) and where.get(t["o"])) or left)
            if not ok:
                removals.append((t, f"other edge: {failed or 'not in the source'}"))
            continue
        value, prop, why = t["o"], t["p"], None
        if checks.get("datatype", {}).get("result") == "fail":
            spec = prop_spec(classes.get(t["s"], set()), t["p"])
            fixed = iso_time(value) if spec and spec["range"].endswith("dateTime") else None
            if not fixed:
                removals.append((t, "datatype"))
                continue
            value, why = fixed, "normalize"
        anchored = ground_literal(t["p"], value, src) & where.get(t["s"], set())  # the value beside its subject
        if not anchored and not left:
            removals.append((t, "value not in the source"))
            continue
        head = header_check({**t, "o": value}, entities, heads)
        rivals = competitors(t, entities, classes)
        if head["result"] == "fail":
            if t["p"] != "receivedTime" or "not received" not in head["reason"]:
                removals.append((t, f"header: {head['reason']}"))
                continue
            prop, why = "sentTime", "repair"
        elif rivals and head["result"] == "skip":
            ps = sorted(anchored)[:MAX_PASSAGES] or \
                [at[(p["doc"], p["sentence"])] for p in retrieved]
            hyps = [render({**t, "o": value}, entities, "plain"), *(render({**c, "o": value}, entities, "plain") for c in rivals)]
            ctx = context(t, rivals, entities)
            e = np.array(verifier.entailment([f"{source[p]['text']} {ctx}".strip() for p in ps for _ in hyps],
                                             [h for _ in ps for h in hyps])).reshape(len(ps), len(hyps))
            if ps and all(max(logit(v) for v in e[i, 1:]) - logit(e[i, 0]) > margin for i in range(len(ps))):
                prop, why = rivals[int(np.argmax(e[:, 1:].max(axis=0)))]["p"], "repair"
        if why:
            removals.append((t, why))
            additions.append(({**t, "p": prop, "o": value, "origin": f"prop|{t['s']}|{prop}"}, why))
    # Messages gain what their header block states.
    addresses = {(keyed[i].get("addressValue") or [""])[0].lower(): i for i, e in entities.items() if e["class"] == "EmailAddress"}
    have = {(t["s"], t["p"], t["o"]) for t in triples}
    for m, e in entities.items():
        if e["class"] != "EmailMessage":
            continue
        cands = []
        if not e["props"].get("sentTime"):
            blocks = [b for s in e["props"].get("subject", []) for b in heads.get(" ".join(s.lower().split()), [])]
            if len(blocks) == 1 and (iso := iso_time(blocks[0].get("Date", ""))):
                cands.append({"s": m, "p": "sentTime", "o": iso, "lit": True, "origin": f"prop|{m}|sentTime"})
        for field, p in (("From", "from"), ("To", "to")):
            blocks = [b for s in e["props"].get("subject", []) for b in heads.get(" ".join(s.lower().split()), [])]
            for addr, a in addresses.items():
                if addr and blocks and (m, p, a) not in have and all(addr in b.get(field, "").lower() for b in blocks):
                    cands.append({"s": m, "p": p, "o": a, "lit": False, "origin": f"prop|{m}|{p}"})
        for c in cands:
            if not any(same(c, x[0]) for x in additions):
                additions.append((c, "header"))

    for t, why in removals:
        remove(g, t, nodes)
    written = [(t, why) for t, why in additions if add_edge(g, t)]
    owner = {str(f): str(e) for e, f in g.subject_objects(HAS_FACET)}

    def score_value(holder, prop: str, values: list) -> tuple:
        subj = owner.get(str(holder), str(holder))
        lit = isinstance(values[0], rdflib.Literal)
        forms = defaultdict(list)
        for v in values:
            forms[norm(prop, str(v)) if lit else str(v)].append(v)
        if len(forms) == 1:  # one value, several spellings
            seen = {v: sum(str(v) in q["text"] for q in source) for v in values}
            ranked = sorted(values, key=lambda v: (-seen[v], -len(str(v))))
            tie = (seen[ranked[0]], len(str(ranked[0]))) == (seen[ranked[1]], len(str(ranked[1])))
            return (None if tie else ranked[0]), {str(v): seen[v] for v in values}
        reps = [vs[0] for vs in forms.values()]
        best = {}
        for v in reps:
            t = {"s": subj, "p": prop, "o": str(v), "lit": lit, "origin": f"prop|{subj}|{prop}"}
            sentence = say(t, entities)
            ps = sorted(ground_literal(prop, str(v), src) & where.get(subj, set())) if lit else []
            ps = (ps + [at[(q["doc"], q["sentence"])] for q in verifier.check([sentence], source)[0]])[:MAX_PASSAGES + 3]
            best[v] = max((logit(e) for e in verifier.entailment([source[i]["text"] for i in ps], [sentence] * len(ps))),
                          default=logit(0.0))
        ranked = sorted(reps, key=lambda v: -best[v])
        keep = ranked[0] if best[ranked[0]] - best[ranked[1]] > margin else None
        return keep, {str(v): round(best[v], 2) for v in reps}

    rows += single_valued(g, score_value)
    for t, why in removals:
        rows.append({"s": t["s"], "p": t["p"], "o": t["o"], "action": "remove", "why": why})
    for t, why in written:
        rows.append({"s": t["s"], "p": t["p"], "o": t["o"], "action": "add", "why": why})
    g.serialize(destination=out / "graph.jsonld", format="json-ld", context=DEFAULT_CONTEXT, indent=2)
    (out / "sel.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    count = lambda xs, w: sum(1 for _, y in xs if y == w)  # noqa: E731
    return {"edges": len(triples), "merged": sum(len(m) - 1 for m in merged), "removed": len(removals),
            **{f"added_{w}": count(written, w) for w in ("repair", "recover", "normalize", "header")}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--cases")
    ap.add_argument("--data", default="data")
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--add-at", type=float, help="override [selector] add_threshold")
    ap.add_argument("--suffix", default="sel")
    args = ap.parse_args()
    with open(CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)
    add_at = args.add_at if args.add_at is not None else cfg["selector"]["add_threshold"]
    verifier = Verifier(cfg["hook"], args.batch)
    root = HARNESS / "results" / args.run_id
    for case_dir in case_dirs(args.cases, args.data):
        base = root / args.arm / case_dir.name
        out = root / f"{args.arm}+{args.suffix}" / case_dir.name
        if not (base / "run.json").exists():
            continue
        meta = json.loads((base / "run.json").read_text())
        out.mkdir(parents=True, exist_ok=True)
        start, info = time.monotonic(), {"final_validation": None}
        if meta["status"] not in ("error", "empty") and (base / "graph.jsonld").exists():
            try:
                info["selector"] = select_case(case_dir, base / "graph.jsonld", out, verifier,
                                               cfg["hook"]["contrast_margin"], add_at)
                info["final_validation"] = case_validate(out / "graph.jsonld")["conforms"]
            except Exception as exc:  # an unreadable graph is a recorded outcome, as in the hook
                info = {"status": "error", "error": f"selector: {type(exc).__name__}: {exc}"[:2000], "final_validation": None}
        sel_s = round(time.monotonic() - start, 1)
        run = {**meta, "arm": f"{args.arm}+{args.suffix}", **info, "selector_s": sel_s, "selector_add_threshold": add_at,
               "wall_s": round(meta.get("wall_s", 0) + sel_s, 1)}
        (out / "run.json").write_text(json.dumps(run, indent=1))
        print(f"{args.arm}+{args.suffix} {case_dir.name}: {run['status']} {info.get('selector')} "
              f"valid={run['final_validation']} {sel_s}s", flush=True)


if __name__ == "__main__":
    main()
