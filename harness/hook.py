"""Backward verification hook: every edge of a graph is checked against the source and kept only if a
source passage entails it. Applied identically to every arm's graph; deterministic apart from the two models.

1. Render: each edge becomes one sentence from a template filled with the CASE/UCO definitions (the SDK's
   registry, as get_class_details serves them) of its classes and its property. Relation kinds have no
   CASE/UCO definition and are said with graphkit.RELATION_PHRASES. No LLM.
2. Retrieve: the sentence is embedded and the top_k most similar source passages are taken. Passages are the
   sentences of the PDFs the arms read.
3. Verify: a local NLI model labels each (passage, sentence) pair supported (entailment), contradicted
   (contradiction) or not_enough_evidence (neutral).
4. Policy: the edge is kept if any passage supports it, citing the one with the highest entailment
   probability; otherwise it is removed: its Relationship node, or its value on the node and the node's facets.

Edges are the scored triples of graphkit.graph_triples. Reads results/RUN/<arm>/<case>/ and writes
results/RUN/<arm>+hook/<case>/: graph.jsonld, run.json, and hook.jsonl with one row per edge (triple, sentence,
the retrieved passages with location and pair verdict, verdict, kept, cited passage). Models are pinned in [hook].

--template labels or plain runs the ablation, written to <arm>+hook_labels or <arm>+hook_plain: labels keeps the
class and property names and drops their definitions; plain drops every ontology term, so an edge reads as its
entity labels and relation phrase alone.

--passages block (#2) makes each run of consecutive mail-header lines (From:, To:, Cc:, Subject:, Date:) one
passage, located from its first line to its last, so a Date: or To: line is read with the Subject: line that names
the message. Every other sentence stays its own passage. Written to <arm>+hook..._block. The default, sentence,
is the hook as published in hook-v1.

--query plain (#3) retrieves passages with each edge's plain rendering, the same query under every template, and
still verifies the template's sentence; definition text no longer steers retrieval, and templates differ only in
what NLI reads. Written to <arm>+hook..._qplain. The default, rendered, retrieves with the sentence it verifies.

--contrast adds a fifth step. 5. Contrast: a supported edge must also outrank, on the passage that supports it, the
other readings the ontology allows. An edge between two entities competes with every other edge the ontology allows
between them in either direction (relation kinds whose domain and range fit; object properties whose range fits); a
literal, with the subject class's other task properties of the same range. A single-valued property whose range is
an entity or a time also competes with the other values it could take: for an entity, the graph's entities of that
class named in the cited passage's document (and the addresses the document names, for an email address); for a
time, the graph's values of that property and the times the document names. The edge is kept if on some supporting
passage no competitor's entailment exceeds its own by more than [hook] contrast_margin, citing the best such passage;
otherwise it is removed as outranked. Written to <arm>+hook..._contrast; each row records its competitors and their
entailment on each supporting passage. Closest prior work: Sainz et al. (2021) choose a relation by comparing
entailment across relation templates; here the ontology chooses the competitors, and a finished edge is verified.

    python harness/hook.py --run-id RUN --arm b_control [--template full|labels|plain] [--passages sentence|block]
                           [--query rendered|plain] [--contrast]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import tomllib
from datetime import datetime
from pathlib import Path

import numpy as np
import rdflib
import torch
from case_uco.graph import DEFAULT_CONTEXT
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from graphkit import (HARNESS, REGISTRY, RELATION_PHRASES, SCHEMA, VERDICTS, case_validate, definition, expand,
                      graph_triples, iso_time, load_graph, property_definition, slug, words)
from llm import CONFIG, case_dirs, passages
from pipeline_edc import TYPES
from score import times_in

VERDICT_OF = {"entailment": "supported", "contradiction": "contradicted", "neutral": "not_enough_evidence"}
PHRASES = {k.lower(): v for k, v in RELATION_PHRASES.items()}
LABEL_PROPS = ("name", "addressValue", "accountIdentifier", "subject", "eventType", "street", "messageText")
HAS_FACET = rdflib.URIRef(expand("uco-core:hasFacet"))
HEADER = re.compile(r"^(From|To|Cc|Subject|Date):")
BATCH = 16
# Contrast. Each relation kind's domain and range, from the task statement (graphkit.RELATION_KINDS): CASE/UCO does
# not define the kinds. Properties take range and cardinality from the SDK's schema, over the task's properties
# (TYPES, as in arm C's target schema).
PERSON, EVENT, ACCOUNTS = {"Person"}, {"Event"}, {"Account"}
KIND_CLASSES = {"Employed_By": (PERSON, {"Organization"}), "Reports_To": (PERSON, PERSON),
                "Holds_Account": (PERSON, {"EmailAddress", "ApplicationAccount", "EmailAccount"}),
                "Owns_Account": ({"Person", "Organization"}, ACCOUNTS),
                "Located_At": ({"Organization", "Event"}, {"Location"}), "Participated_In": (PERSON, EVENT),
                "Initiated": (PERSON, EVENT), "Transferred_To": (ACCOUNTS, ACCOUNTS), "Authorized": (PERSON, EVENT),
                "Communicated_With": (PERSON, PERSON)}
SYMMETRIC = {"Communicated_With"}
# The task's object properties and the classes they point to (CASE/UCO's ranges are wider: UcoObject, ObservableObject).
PROP_CLASSES = {("Account", "accountIssuer"): {"Organization"}, ("EmailMessage", "from"): {"EmailAddress"},
                ("EmailMessage", "to"): {"EmailAddress"}, ("Message", "from"): {"ApplicationAccount"},
                ("Message", "to"): {"ApplicationAccount"}}
KIND_OF = {k.lower(): k for k in KIND_CLASSES}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def header_blocks(source: list[dict]) -> list[dict]:
    """Each run of consecutive mail-header lines in a document as one passage, from its first line to its last."""
    out, prev = [], None  # prev: (doc, sentence) of the header line that ended the last passage
    for p in source:
        if HEADER.match(p["text"]) and prev == (p["doc"], p["sentence"] - 1):
            out[-1] = {**out[-1], "end": p["end"], "text": f"{out[-1]['text']} {p['text']}"}
        else:
            out.append(p)
        prev = (p["doc"], p["sentence"]) if HEADER.match(p["text"]) else None
    return out


def class_phrase(cls: str, template: str = "full") -> str:
    """'a person (a grouping of identifying characteristics unique to a human being regarded as an individual)';
    'a person' under the labels template."""
    label = words(cls)
    genus = re.sub(r"^(?:an?|the)\s+.+?\s+is\s+", "", definition(REGISTRY.get(cls, {}).get("description")), count=1, flags=re.I)
    article = "an" if label[:1] in ("a", "e", "i", "o", "u") else "a"
    return f"{article} {label} ({genus})" if genus and template == "full" else f"{article} {label}"


def property_phrase(cls: str | None, prop: str, template: str = "full") -> str:
    """'address value (the value of an address)'; 'address value' under the labels and plain templates."""
    d = property_definition(cls, prop) if template == "full" else ""
    return f"{words(prop)} ({d[:1].lower()}{d[1:]})" if d else words(prop)


def label(iri: str, entities: dict) -> tuple[str, str] | None:
    """The entity's identifying (property, literal)."""
    props = entities.get(iri, {}).get("props", {})
    for p in (*LABEL_PROPS, *sorted(props)):
        for v in props.get(p, []):
            if not v.startswith(("http://", "https://")):
                return p, v
    return None


def mention(iri: str, entities: dict, asserted: str | None = None, template: str = "full") -> str:
    """'Luca Petrov, a person (...),'; by its class alone when its label holds the value the sentence asserts,
    so that 'the name of X is X' (or 'the street of 1 Main St, Omaha is 1 Main St') is never a sentence.
    The plain template names no class: 'Luca Petrov', or 'an entity' in place of the class."""
    cls, name = entities.get(iri, {}).get("class"), label(iri, entities)
    if name and asserted and asserted in name[1] and cls:
        return "an entity" if template == "plain" else class_phrase(cls, template)
    if not cls or template == "plain":
        return name[1] if name else slug(iri)
    return f"{name[1]}, {class_phrase(cls, template)}," if name else class_phrase(cls, template)


def spoken(value: str) -> str:
    """A literal as the sentence says it; ISO date-times in words ('May 2, 2025 at 09:50 UTC')."""
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value) and (iso := iso_time(value)):
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
        return f"{dt:%B} {dt.day}, {dt.year} at {dt:%H:%M} UTC"
    return value


def render(t: dict, entities: dict, template: str = "full") -> str:
    """One sentence per edge. Relation: 'S, <class S>, <phrase> O, <class O>.'
    Property: 'The <property (definition)> of S, <class S>, is <value or O, <class O>>.'"""
    subject = mention(t["s"], entities, t["o"] if t["lit"] else None, template)
    if t["origin"].startswith("rel|"):
        phrase = PHRASES.get(re.sub(r"[\s-]+", "_", t["p"].strip()).lower(), words(t["p"]))
        text = f"{subject} {phrase} {mention(t['o'], entities, None, template)}"
    else:
        value = spoken(t["o"]) if t["lit"] else mention(t["o"], entities, None, template)
        text = f"The {property_phrase(entities[t['s']]['class'], t['p'], template)} of {subject} is {value}"
    return text.rstrip(",") + "."


def top_passages(embedder: SentenceTransformer, queries: list[str], source: list[dict], k: int) -> tuple:
    """For each query, the indices of its k most similar passages (cosine), and the similarity matrix."""
    p_emb = embedder.encode([p["text"] for p in source], normalize_embeddings=True)
    q_emb = embedder.encode(queries, normalize_embeddings=True)
    sims = q_emb @ p_emb.T
    return np.argsort(-sims, axis=1, kind="stable")[:, :k], sims


def prop_spec(cls: str | None, prop: str) -> dict | None:
    """A property's schema entry on the class or the facet that carries it."""
    for c in (cls, f"{cls}Facet", "SimpleAddressFacet" if cls == "Location" else None, "AccountFacet"):
        if c in SCHEMA and prop in SCHEMA[c]["props"]:
            return SCHEMA[c]["props"][prop]
    return None


def readings(x: str, y: str, entities: dict) -> list[dict]:
    """Every edge the task's ontology allows between entities x and y, in either direction: a relation kind whose
    domain and range fit, or an object property of one entity's class whose range fits the other's."""
    out = []
    for a, b in ((x, y), (y, x)):
        ca, cb = entities.get(a, {}).get("class"), entities.get(b, {}).get("class")
        out += [{"s": a, "p": k, "o": b, "lit": False, "origin": "rel|"} for k, (dom, rng) in KIND_CLASSES.items()
                if ca in dom and cb in rng and not (k in SYMMETRIC and a == y)]  # a symmetric kind reads one way
        out += [{"s": a, "p": p, "o": b, "lit": False, "origin": f"prop|{a}|{p}"} for (c, p), rng in PROP_CLASSES.items()
                if c == ca and cb in rng]
    return out


def competitors(t: dict, entities: dict, triples: list[dict], document: str) -> list[dict]:
    """The other readings the ontology allows for edge t, as edges in graph_triples' form (see --contrast)."""
    if t["origin"].startswith("rel|"):
        kind = KIND_OF.get(re.sub(r"^.*[:/#]", "", t["p"].strip()).lower())
        if not kind:
            return []
        same = {(t["s"], kind, t["o"])} | ({(t["o"], kind, t["s"])} if kind in SYMMETRIC else set())
        return [r for r in readings(t["s"], t["o"], entities) if (r["s"], r["p"], r["o"]) not in same]
    cls_s = entities.get(t["s"], {}).get("class")
    spec = prop_spec(cls_s, t["p"])
    if not spec:
        return []
    if t["lit"]:  # the other task properties of the class with the same range
        out = [{**t, "p": p} for p in TYPES.get(cls_s, []) if p != t["p"] and (q := prop_spec(cls_s, p))
               and q["range"] == spec["range"]]
    else:
        out = [r for r in readings(t["s"], t["o"], entities) if (r["s"], r["p"], r["o"]) != (t["s"], t["p"], t["o"])]
    is_time = spec["range"].endswith("dateTime")
    if spec["many"] or not (is_time or not t["lit"]):  # value competitors: single-valued, an entity or a time
        return out
    if is_time:
        values = {x["o"]: True for x in triples if x["p"] == t["p"]} | {v: True for v in times_in(document)}
    else:  # entities of the object's class named in the document, and for an address, the addresses it names
        cls_o = entities.get(t["o"], {}).get("class")
        named = {iri: e for iri, e in entities.items() if e["class"] == cls_o and (lab := label(iri, entities))
                 and lab[1] in document}
        values = {iri: False for iri in named}
        if cls_o == "EmailAddress":
            labels = {v for e in named.values() for vs in e["props"].values() for v in vs}
            values.update({a: True for a in EMAIL.findall(document) if a not in labels})
    same = iso_time(t["o"]) if is_time else t["o"]
    return out + [{**t, "o": v, "lit": lit} for v, lit in values.items() if (iso_time(v) if is_time else v) != same]


class Verifier:
    """The pinned embedder and NLI model."""

    def __init__(self, cfg: dict) -> None:
        # HOOK_DEVICE=cpu when the GPU runs out of memory; MPS and CPU can differ in the last digits of a probability
        self.device = os.environ.get("HOOK_DEVICE") or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.top_k = cfg["top_k"]
        self.embedder = SentenceTransformer(cfg["embed_model"], revision=cfg["embed_revision"], device=self.device)
        self.tokenizer = AutoTokenizer.from_pretrained(cfg["nli_model"], revision=cfg["nli_revision"])
        self.nli = AutoModelForSequenceClassification.from_pretrained(cfg["nli_model"], revision=cfg["nli_revision"])
        self.nli.to(self.device).eval()
        self.verdicts = [VERDICT_OF[self.nli.config.id2label[i].lower()] for i in range(self.nli.config.num_labels)]
        self.supported = self.verdicts.index("supported")

    def check(self, sentences: list[str], source: list[dict], queries: list[str] | None = None) -> list[list[dict]]:
        """For each sentence, its top_k passages with similarity, pair verdict and entailment probability.
        Passages are retrieved with queries[i] when given, else with the sentence itself."""
        if not sentences:
            return []
        top, sims = top_passages(self.embedder, queries or sentences, source, self.top_k)
        pairs = [(i, int(j)) for i in range(len(sentences)) for j in top[i]]
        probs = self.probs([source[j]["text"] for _, j in pairs], [sentences[i] for i, _ in pairs])
        out = [[] for _ in sentences]
        for (i, j), pr in zip(pairs, probs):
            out[i].append({**source[j], "similarity": round(float(sims[i, j]), 4),
                           "verdict": self.verdicts[int(pr.argmax())], "entailment": round(float(pr[self.supported]), 4)})
        return out

    def probs(self, premises: list[str], hypotheses: list[str]) -> np.ndarray:
        """NLI label probabilities for each (premise, hypothesis) pair."""
        probs = []
        for k in range(0, len(premises), BATCH):
            enc = self.tokenizer(premises[k:k + BATCH], hypotheses[k:k + BATCH],
                                 truncation=True, padding=True, return_tensors="pt").to(self.device)
            with torch.no_grad():
                probs.append(self.nli(**enc).logits.float().softmax(-1).cpu().numpy())
        return np.concatenate(probs) if probs else np.zeros((0, len(self.verdicts)))

    def entailment(self, premises: list[str], hypotheses: list[str]) -> list[float]:
        return [round(float(p[self.supported]), 4) for p in self.probs(premises, hypotheses)]


def contrast(rows: list[dict], triples: list[dict], entities: dict, source: list[dict], verifier: Verifier,
             template: str, margin: float) -> None:
    """Step 5 on the supported rows, in place: competitors scored on each supporting passage, then kept and cited
    as in the module docstring; a row no supporting passage survives is marked outranked and not kept."""
    jobs = []  # (row, passage index in row, competitor sentence)
    for r, t in zip(rows, triples):
        support = [i for i, p in enumerate(r["passages"]) if p["verdict"] == "supported"]
        if not support:
            continue
        doc = " ".join(p["text"] for p in source if p["doc"] == r["cited"]["doc"])
        rendered = dict.fromkeys(render(x, entities, template) for x in competitors(t, entities, triples, doc))
        r["competitors"] = [c for c in rendered if c != r["sentence"]]
        jobs += [(r, i, c) for i in support for c in r["competitors"]]
    scores = verifier.entailment([j[0]["passages"][j[1]]["text"] for j in jobs], [j[2] for j in jobs])
    best: dict = {}
    for (r, i, c), e in zip(jobs, scores):
        r.setdefault("contrast", []).append({"passage": i, "competitor": c, "entailment": e})
        best[id(r), i] = max(best.get((id(r), i), 0.0), e)
    for r in rows:
        if "competitors" not in r:
            continue
        alive = [p for i, p in enumerate(r["passages"]) if p["verdict"] == "supported"
                 and best.get((id(r), i), 0.0) - p["entailment"] <= margin]
        r["outranked"] = not alive
        cited = max(alive, key=lambda p: p["entailment"], default=None)
        r["kept"] = cited is not None
        r["cited"] = {k: cited[k] for k in ("doc", "sentence", "start", "end", "text")} if cited else None


def remove(g: rdflib.Graph, t: dict, nodes: dict) -> None:
    """Take one edge out: its Relationship node, or its value on the node and the node's facets."""
    kind, _, rest = t["origin"].partition("|")
    if kind == "rel":
        g.remove((nodes[rest], None, None))
        g.remove((None, None, nodes[rest]))
        return
    s = nodes[t["s"]]
    folded = rest.endswith("|givenName")  # graph_triples joins givenName and familyName into name
    for holder in [s, *g.objects(s, HAS_FACET)]:
        for p, o in list(g.predicate_objects(holder)):
            local = re.split(r"[/#]", str(p).rstrip("/"))[-1]
            if (folded and local in ("givenName", "familyName")) or (not folded and local == t["p"] and str(o) == t["o"]):
                g.remove((holder, p, o))


def hook_case(case_dir: Path, graph_path: Path, out: Path, verifier: Verifier, template: str = "full",
              passage_unit: str = "sentence", query: str = "rendered", margin: float | None = None) -> dict:
    g = load_graph(graph_path)
    entities, triples = graph_triples(g)
    sentences = [render(t, entities, template) for t in triples]
    queries = [render(t, entities, "plain") for t in triples] if query == "plain" else sentences
    unique = list(dict.fromkeys(zip(sentences, queries)))
    source = header_blocks(passages(case_dir)) if passage_unit == "block" else passages(case_dir)
    checked = dict(zip(unique, verifier.check([s for s, _ in unique], source, [q for _, q in unique])))
    nodes = {str(x): x for x in g.all_nodes() if not isinstance(x, rdflib.Literal)}
    rows = []
    for t, sentence, q in zip(triples, sentences, queries):
        retrieved = checked[(sentence, q)]
        verdict = next((v for v in VERDICTS if v in {p["verdict"] for p in retrieved}), "not_enough_evidence")
        cited = max((p for p in retrieved if p["verdict"] == "supported"), key=lambda p: p["entailment"], default=None)
        rows.append({"s": t["s"], "p": t["p"], "o": t["o"], "lit": t["lit"], "origin": t["origin"], "sentence": sentence,
                     **({"query": q} if q != sentence else {}), "passages": retrieved, "verdict": verdict, "kept": cited is not None,
                     "cited": {k: cited[k] for k in ("doc", "sentence", "start", "end", "text")} if cited else None})
    if margin is not None:
        contrast(rows, triples, entities, source, verifier, template, margin)
    for t, r in zip(triples, rows):
        if not r["kept"]:
            remove(g, t, nodes)
    g.serialize(destination=out / "graph.jsonld", format="json-ld", context=DEFAULT_CONTEXT, indent=2)
    (out / "hook.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return {"edges": len(rows), "kept": sum(r["kept"] for r in rows), **{v: sum(r["verdict"] == v for r in rows) for v in VERDICTS},
            **({"outranked": sum(r.get("outranked", False) for r in rows)} if margin is not None else {})}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--arm", required=True, help="the arm folder under results/RUN/ whose graphs the hook reads")
    ap.add_argument("--cases", help="comma-separated case ids (default: all)")
    ap.add_argument("--data", default="data")
    ap.add_argument("--template", default="full", choices=("full", "labels", "plain"),
                    help="full: classes and properties with their CASE/UCO definitions; labels, plain: the ablation")
    ap.add_argument("--passages", default="sentence", choices=("sentence", "block"),
                    help="sentence: each source sentence is a passage (hook-v1); block: mail-header runs are one passage")
    ap.add_argument("--query", default="rendered", choices=("rendered", "plain"),
                    help="rendered: retrieve with the sentence verified (hook-v1); plain: retrieve with the plain rendering")
    ap.add_argument("--contrast", action="store_true", help="step 5: a supported edge must outrank its competitors")
    args = ap.parse_args()
    with open(CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)["hook"]
    verifier = Verifier(cfg)
    root = HARNESS / "results" / args.run_id
    name = f"{args.arm}+hook" + ("" if args.template == "full" else f"_{args.template}") + \
        ("_block" if args.passages == "block" else "") + ("_qplain" if args.query == "plain" else "") + \
        ("_contrast" if args.contrast else "")
    for case_dir in case_dirs(args.cases, args.data):
        base, out = root / args.arm / case_dir.name, root / name / case_dir.name
        if not (base / "run.json").exists():
            continue
        meta = json.loads((base / "run.json").read_text())
        out.mkdir(parents=True, exist_ok=True)
        for stale in ("graph.jsonld", "hook.jsonl"):
            (out / stale).unlink(missing_ok=True)
        start = time.monotonic()
        info = {"final_validation": None}
        if meta["status"] not in ("error", "empty") and (base / "graph.jsonld").exists():
            try:
                info["hook"] = hook_case(case_dir, base / "graph.jsonld", out, verifier, args.template, args.passages,
                                         args.query, cfg["contrast_margin"] if args.contrast else None)
                info["final_validation"] = case_validate(out / "graph.jsonld")["conforms"]
            except Exception as exc:  # an unreadable graph is a recorded outcome, as in the arms
                info = {"status": "error", "error": f"hook: {type(exc).__name__}: {exc}"[:2000], "final_validation": None}
        hook_s = round(time.monotonic() - start, 1)
        run = {**meta, "arm": name, **info, "hook_s": hook_s, "wall_s": round(meta.get("wall_s", 0) + hook_s, 1),
               "hook_template": args.template, "hook_passages": args.passages, "hook_query": args.query,
               **({"hook_contrast_margin": cfg["contrast_margin"]} if args.contrast else {}),
               "hook_models": {k: cfg[k] for k in ("embed_model", "embed_revision", "nli_model", "nli_revision")}}
        (out / "run.json").write_text(json.dumps(run, indent=1))
        print(f"{name} {case_dir.name}: {run['status']} {info.get('hook')} valid={run['final_validation']} {hook_s}s", flush=True)


if __name__ == "__main__":
    main()
