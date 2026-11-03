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

--stage left, right or both (comma-separated for several in one pass) splits the hook in two. The default, hook, is
the hook above, unchanged.

- left (fidelity): steps 1 to 4 on the plain rendering, so NLI never reads a definition; --passages block and
  --query plain by default. An entity with no literal of its own (an email account) is named by the entity it links
  to, so its edges no longer read as an IRI. Written to <arm>+left.
- right (semantics): deterministic checks, then contrast. Checks, from the SDK's schema and registry: domain (the
  property is declared on the subject's class or one of its facets' classes), range (the object's class), datatype
  (a literal's lexical form), cardinality (a single-valued property with several values keeps the one that best
  outranks its competitors), self-loop. The ten relation kinds take domain and range from the task statement (KIND_CLASSES), since
  CASE/UCO does not define them. A check that cannot judge an edge (a property declared on UcoObject, a range of
  UcoObject, an xsd:string, a kind outside the ten) records skip, never pass. Contrast: on each passage that
  supports the edge (else its best passage), the edge's plain sentence and each competitor's are scored by NLI
  against the passage followed by the CASE/UCO definitions of the properties in play; the edge fails if on every
  such passage a competitor's entailment exceeds its own by more than [hook] contrast_margin, in log-odds (entailment
  saturates near 1, where probability differences vanish). Competitors are the
  other readings the task's ontology allows for the same entities: relation kinds and object properties whose
  domain and range fit, in either direction; for a literal, the subject class's other task properties of the same
  range. Contrast is ported from #6 without its competing values, which are other entities and a fidelity question.
  right runs on every edge (<arm>+right, the ablation); both runs it on the edges left kept (<arm>+lr).
  Each row records the left verdict and citation, each right check's result and reason, and the final decision.

    python harness/hook.py --run-id RUN --arm b_control [--template full|labels|plain] [--passages sentence|block]
                           [--query rendered|plain] [--stage hook|left,right,both] [--resume] [--batch 16]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import tomllib
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import rdflib
import torch
from case_uco.graph import DEFAULT_CONTEXT
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from graphkit import (HARNESS, REGISTRY, RELATION_PHRASES, SCHEMA, VERDICTS, XSD, case_validate, definition, expand,
                      graph_triples, iso_time, load_graph, property_definition, slug, words)
from llm import CONFIG, case_dirs, passages
from pipeline_edc import TYPES

VERDICT_OF = {"entailment": "supported", "contradiction": "contradicted", "neutral": "not_enough_evidence"}
PHRASES = {k.lower(): v for k, v in RELATION_PHRASES.items()}
LABEL_PROPS = ("name", "addressValue", "accountIdentifier", "subject", "eventType", "street", "messageText")
HAS_FACET = rdflib.URIRef(expand("uco-core:hasFacet"))
HEADER = re.compile(r"^(From|To|Cc|Subject|Date):")
BATCH = 16
STAGES = {"left": "left", "right": "right", "both": "lr"}  # --stage -> output suffix
# Right hook. Each relation kind's domain and range, from the task statement (graphkit.RELATION_KINDS): CASE/UCO does
# not define the kinds.
PERSON, EVENT, ACCOUNTS = {"Person"}, {"Event"}, {"Account"}
KIND_CLASSES = {"Employed_By": (PERSON, {"Organization"}), "Reports_To": (PERSON, PERSON),
                "Holds_Account": (PERSON, {"EmailAddress", "ApplicationAccount", "EmailAccount"}),
                "Owns_Account": ({"Person", "Organization"}, ACCOUNTS),
                "Located_At": ({"Organization", "Event"}, {"Location"}), "Participated_In": (PERSON, EVENT),
                "Initiated": (PERSON, EVENT), "Transferred_To": (ACCOUNTS, ACCOUNTS), "Authorized": (PERSON, EVENT),
                "Communicated_With": (PERSON, PERSON)}
SYMMETRIC = {"Communicated_With"}
KIND_OF = {k.lower(): k for k in KIND_CLASSES}
# Contrast: the task's object properties and the classes they point to (CASE/UCO's ranges are wider: UcoObject,
# ObservableObject). Literal competitors are the task's properties (TYPES, as in arm C's target schema).
PROP_CLASSES = {("Account", "accountIssuer"): {"Organization"}, ("EmailMessage", "from"): {"EmailAddress"},
                ("EmailMessage", "to"): {"EmailAddress"}, ("Message", "from"): {"ApplicationAccount"},
                ("Message", "to"): {"ApplicationAccount"}}
UNCONSTRAINED = {"UcoObject", "UcoThing"}  # a domain or range here admits any object: the check cannot judge
CHECKS = ("domain", "range", "datatype", "cardinality", "self_loop", "contrast")
XSD_DATETIME = re.compile(r"^-?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")


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


class Verifier:
    """The pinned embedder and NLI model."""

    def __init__(self, cfg: dict, batch: int = BATCH) -> None:
        # HOOK_DEVICE=cpu when the GPU runs out of memory; MPS and CPU can differ in the last digits of a probability
        self.device = os.environ.get("HOOK_DEVICE") or ("cuda" if torch.cuda.is_available() else
                                                        "mps" if torch.backends.mps.is_available() else "cpu")
        self.top_k, self.batch = cfg["top_k"], batch
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
        for k in range(0, len(premises), self.batch):
            enc = self.tokenizer(premises[k:k + self.batch], hypotheses[k:k + self.batch],
                                 truncation=True, padding=True, return_tensors="pt").to(self.device)
            with torch.no_grad():
                probs.append(self.nli(**enc).logits.float().softmax(-1).cpu().numpy())
        return np.concatenate(probs) if probs else np.zeros((0, len(self.verdicts)))

    def entailment(self, premises: list[str], hypotheses: list[str]) -> list[float]:
        return [round(float(p[self.supported]), 4) for p in self.probs(premises, hypotheses)]

    def to(self, device: str) -> None:
        """Move both models, e.g. to the CPU for a case that fails on the GPU."""
        self.device = device
        self.embedder.to(device)
        self.nli.to(device)


def local(term) -> str:
    return re.split(r"[/#]", str(term).rstrip("/"))[-1]


def ancestors(cls: str) -> set[str]:
    """The class and its superclasses, from the registry."""
    out, todo = set(), [cls]
    while todo:
        c = todo.pop()
        if c and c not in out:
            out.add(c)
            todo += REGISTRY.get(c, {}).get("parents", [])
    return out


def holder_classes(g: rdflib.Graph, iri: str) -> set[str]:
    """The classes of an entity and of its facets, with their superclasses."""
    node = rdflib.URIRef(iri)
    return {c for h in [node, *g.objects(node, HAS_FACET)] for t in g.objects(h, rdflib.RDF.type) for c in ancestors(local(t))}


def prop_spec(classes: set[str], prop: str) -> dict | None:
    """A property's schema entry (range, many) on one of the classes, else on the first class that declares it."""
    for c in sorted(classes) + sorted(SCHEMA):
        if c in SCHEMA and prop in SCHEMA[c]["props"]:
            return SCHEMA[c]["props"][prop]
    return None


def result(ok: bool | None, reason: str) -> dict:
    return {"result": "skip" if ok is None else "pass" if ok else "fail", "reason": reason}


def kind_of(t: dict) -> str | None:
    return KIND_OF.get(re.sub(r"^.*[:/#]", "", t["p"].strip()).lower()) if t["origin"].startswith("rel|") else None


def schema_checks(t: dict, classes: dict[str, set]) -> dict:
    """Domain, range, datatype and self-loop for one edge (cardinality needs the edge's siblings). A check that does not
    apply to the edge (range or self-loop for a literal, datatype for an object) is left out."""
    cs, co = classes.get(t["s"], set()), set() if t["lit"] else classes.get(t["o"], set())
    out = {}
    if t["origin"].startswith("rel|"):
        kind = kind_of(t)
        if not kind:
            out["domain"] = out["range"] = result(None, f"kind {t['p']} is not one of the ten")
        else:
            dom, rng = KIND_CLASSES[kind]
            out["domain"] = result(bool(cs & dom), f"{kind} takes {' or '.join(sorted(dom))}") if cs else \
                result(None, "source has no type")
            out["range"] = result(bool(co & rng), f"{kind} points to {' or '.join(sorted(rng))}") if co else \
                result(None, "target has no type")
    else:
        declared = {c for c, spec in SCHEMA.items() if t["p"] in spec["own"]}
        if not declared:
            out["domain"] = result(None, f"{t['p']} is not a core CASE/UCO property")
        elif declared & UNCONSTRAINED:
            out["domain"] = result(None, f"{t['p']} is declared on UcoObject")
        else:
            out["domain"] = result(bool(declared & cs), f"{t['p']} is a property of {', '.join(sorted(declared)[:4])}")
        spec = prop_spec(cs, t["p"])
        rng = local(spec["range"]) if spec else None
        is_datatype = bool(spec) and spec["range"].startswith(XSD)
        if not t["lit"]:
            if not spec:
                out["range"] = result(None, f"{t['p']} is not a core CASE/UCO property")
            elif is_datatype:
                out["range"] = result(False, f"an object where {t['p']} takes xsd:{rng}")
            elif rng in UNCONSTRAINED:
                out["range"] = result(None, f"{t['p']} points to {rng}")
            else:
                out["range"] = result(rng in co, f"{t['p']} points to {rng}") if co else result(None, "object has no type")
        elif not spec:
            out["datatype"] = result(None, f"{t['p']} is not a core CASE/UCO property")
        elif not is_datatype:
            out["datatype"] = result(False, f"a literal where {t['p']} points to {rng}")
        elif rng == "string":
            out["datatype"] = result(None, "xsd:string takes any literal")
        elif rng == "dateTime":
            out["datatype"] = result(bool(XSD_DATETIME.match(t["o"].strip())), "xsd:dateTime lexical form")
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                out["datatype"] = result(not rdflib.Literal(t["o"], datatype=rdflib.URIRef(spec["range"])).ill_typed,
                                         f"xsd:{rng} lexical form")
    if not t["lit"]:
        out["self_loop"] = result(t["s"] != t["o"], "source and target differ" if t["s"] != t["o"] else
                                  "source and target are the same entity")
    return out


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return float(np.log(p / (1 - p)))


def advantage(r: dict) -> float:
    """How far an edge outranks its readings on its best passage, in log-odds of entailment (contrast_scores); with
    no competitor, its best passage's own log-odds."""
    slots = (r.get("contrast") or {}).get("passages")
    if not slots:
        return logit(max((p["entailment"] for p in r["passages"]), default=0.0))
    return round(max(logit(s["own"]) - logit(max(s.get("rivals", [0.0]))) for s in slots), 2)


def cardinality(triples: list[dict], rows: list[dict], classes: dict[str, set], on: list[bool]) -> list[dict | None]:
    """Per edge with on[i]: a single-valued property holding several values among the edges on keeps the value with the
    greatest contrast advantage (ties to the first) and fails the others; support alone cannot separate an account's
    issuer from its owner named in the same passage. Relations have no cardinality in the task statement; they and
    edges not on get None."""
    best = advantage
    groups: dict[tuple, list[int]] = {}
    for i, t in enumerate(triples):
        if on[i] and not t["origin"].startswith("rel|"):
            groups.setdefault((t["s"], t["p"]), []).append(i)
    out: list[dict | None] = [None] * len(triples)
    for (s, p), idx in groups.items():
        spec = prop_spec(classes.get(s, set()), p)
        values = list(dict.fromkeys((iso_time(triples[i]["o"]) or triples[i]["o"]) if triples[i]["lit"] else triples[i]["o"]
                                    for i in idx))
        winner = max(idx, key=lambda i: best(rows[i]))  # max keeps the first of equal scores
        win = (iso_time(triples[winner]["o"]) or triples[winner]["o"]) if triples[winner]["lit"] else triples[winner]["o"]
        for i in idx:
            mine = (iso_time(triples[i]["o"]) or triples[i]["o"]) if triples[i]["lit"] else triples[i]["o"]
            if not spec:
                out[i] = result(None, f"{p} is not a core CASE/UCO property")
            elif spec["many"]:
                out[i] = result(True, f"{p} takes zero or more values")
            elif len(values) == 1:
                out[i] = result(True, f"{p} takes at most one value; one here")
            else:
                out[i] = result(mine == win, f"{p} takes at most one value; {len(values)} here, "
                                f"kept the one that best outranks its readings ({best(rows[winner]):.2f} against "
                                f"{best(rows[i]):.2f})")
    return out


def readings(x: str, y: str, entities: dict) -> list[dict]:
    """Every edge the task's ontology allows between entities x and y, in either direction: a relation kind whose
    domain and range fit, or an object property of one entity's class whose range fits the other's."""
    out = []
    for a, b in ((x, y), (y, x)):
        ca, cb = ancestors(entities.get(a, {}).get("class") or ""), ancestors(entities.get(b, {}).get("class") or "")
        out += [{"s": a, "p": k, "o": b, "lit": False, "origin": "rel|"} for k, (dom, rng) in KIND_CLASSES.items()
                if ca & dom and cb & rng and not (k in SYMMETRIC and a == y)]  # a symmetric kind reads one way
        out += [{"s": a, "p": p, "o": b, "lit": False, "origin": f"prop|{a}|{p}"} for (c, p), rng in PROP_CLASSES.items()
                if c == entities.get(a, {}).get("class") and cb & rng]
    return out


def competitors(t: dict, entities: dict, classes: dict[str, set]) -> list[dict]:
    """The other readings the ontology allows for edge t's entities (see --stage right)."""
    if t["lit"]:  # the subject class's other task properties with the same range
        cls = entities.get(t["s"], {}).get("class")
        spec = prop_spec(classes.get(t["s"], set()), t["p"])
        return [{**t, "p": p} for p in TYPES.get(cls, []) if p != t["p"] and spec
                and (q := prop_spec(classes.get(t["s"], set()), p)) and q["range"] == spec["range"]]
    kind = kind_of(t)
    same = {(t["s"], kind or t["p"], t["o"])} | ({(t["o"], kind, t["s"])} if kind in SYMMETRIC else set())
    return [r for r in readings(t["s"], t["o"], entities) if (r["s"], r["p"], r["o"]) not in same]


def context(t: dict, rivals: list[dict], entities: dict) -> str:
    """The CASE/UCO definitions of the properties in play, for the premise. Relation kinds have none."""
    defs = {}
    for x in [t, *rivals]:
        if not x["origin"].startswith("rel|") and (d := property_definition(entities.get(x["s"], {}).get("class"), x["p"])):
            defs[words(x["p"])] = d[:1].lower() + d[1:]
    return " ".join(f'In CASE/UCO, "{w}" is {d}.' for w, d in sorted(defs.items()))


def contrast_scores(rows: list[dict], triples: list[dict], entities: dict, classes: dict[str, set],
                    verifier: Verifier) -> None:
    """Score each edge and its competitors on the passages that support it (else its best passage), in place:
    row["contrast"] = {competitors, context, passages: [{passage, own, rivals}]}. No row is decided here."""
    jobs = []  # (row, passage index, hypothesis index); hypothesis 0 is the edge itself
    for r, t in zip(rows, triples):
        rivals = competitors(t, entities, classes)
        if not rivals:
            continue
        hyps = [r["sentence"], *dict.fromkeys(c for c in (render(x, entities, "plain") for x in rivals) if c != r["sentence"])]
        support = [i for i, p in enumerate(r["passages"]) if p["verdict"] == "supported"] or \
            [max(range(len(r["passages"])), key=lambda i: r["passages"][i]["entailment"])] * bool(r["passages"])
        r["contrast"] = {"competitors": hyps[1:], "context": context(t, rivals, entities),
                         "passages": [{"passage": i} for i in support]}
        jobs += [(r, k, h) for k in range(len(support)) for h in range(len(hyps))]
    premises = [f"{r['passages'][r['contrast']['passages'][k]['passage']]['text']} {r['contrast']['context']}".strip()
                for r, k, _ in jobs]
    hypotheses = [([r["sentence"], *r["contrast"]["competitors"]])[h] for r, k, h in jobs]
    for (r, k, h), e in zip(jobs, verifier.entailment(premises, hypotheses)):
        slot = r["contrast"]["passages"][k]
        if h == 0:
            slot["own"] = e
        else:
            slot.setdefault("rivals", []).append(e)


def contrast_result(row: dict, margin: float) -> tuple[dict, list[int]]:
    """Contrast's verdict at this margin (log-odds of entailment), and the passages the edge survives on."""
    c = row.get("contrast")
    if not c or not c["passages"]:
        return result(None, "no other reading for these entities"), [i for i, _ in enumerate(row["passages"])]
    gap = lambda s: logit(max(s.get("rivals", [0.0]))) - logit(s["own"])  # noqa: E731
    alive = [s["passage"] for s in c["passages"] if gap(s) <= margin]
    best = min(c["passages"], key=gap)  # the edge's best passage
    rival = c["competitors"][int(np.argmax(best.get("rivals", [0.0])))]
    return result(bool(alive), f"on passage {best['passage']}: {best['own']} against {max(best.get('rivals', [0.0]))} "
                  f"for {rival!r}, margin {margin}"), alive


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
              passage_unit: str = "sentence", query: str = "rendered") -> dict:
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
        if not cited:
            remove(g, t, nodes)
        rows.append({"s": t["s"], "p": t["p"], "o": t["o"], "lit": t["lit"], "origin": t["origin"], "sentence": sentence,
                     **({"query": q} if q != sentence else {}), "passages": retrieved, "verdict": verdict, "kept": cited is not None,
                     "cited": {k: cited[k] for k in ("doc", "sentence", "start", "end", "text")} if cited else None})
    g.serialize(destination=out / "graph.jsonld", format="json-ld", context=DEFAULT_CONTEXT, indent=2)
    (out / "hook.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return {"edges": len(rows), "kept": sum(r["kept"] for r in rows), **{v: sum(r["verdict"] == v for r in rows) for v in VERDICTS}}


def hook_stages(case_dir: Path, graph_path: Path, outs: dict[str, Path], verifier: Verifier, passage_unit: str,
                margin: float) -> dict[str, dict]:
    """The left hook, the right hook on every edge, and the right hook on the edges left kept, for each stage in outs."""
    g = load_graph(graph_path)
    entities, triples = graph_triples(g)
    classes = {iri: holder_classes(g, iri) for iri in {x for t in triples for x in (t["s"], t["o"]) if not t["lit"] or x == t["s"]}}
    for iri, e in list(entities.items()):  # no literal of its own (an email account): named by what it links to
        linked = next((n for vs in e["props"].values() for o in vs if o in entities and (n := label(o, entities))), None)
        if not label(iri, entities) and linked:
            entities[iri] = {**e, "props": {**e["props"], "linked": [linked[1]]}}
    sentences = [render(t, entities, "plain") for t in triples]
    unique = list(dict.fromkeys(sentences))
    source = header_blocks(passages(case_dir)) if passage_unit == "block" else passages(case_dir)
    checked = dict(zip(unique, verifier.check(unique, source)))
    rows = []
    for t, sentence in zip(triples, sentences):
        retrieved = checked[sentence]
        verdict = next((v for v in VERDICTS if v in {p["verdict"] for p in retrieved}), "not_enough_evidence")
        cited = max((p for p in retrieved if p["verdict"] == "supported"), key=lambda p: p["entailment"], default=None)
        rows.append({"s": t["s"], "p": t["p"], "o": t["o"], "lit": t["lit"], "origin": t["origin"], "sentence": sentence,
                     "passages": retrieved, "verdict": verdict,
                     "left": {"kept": cited is not None, "cited": cite(cited)}})
    need = [i for i, r in enumerate(rows) if "right" in outs or ("both" in outs and r["left"]["kept"])]
    contrast_scores([rows[i] for i in need], [triples[i] for i in need], entities, classes, verifier)
    infos = {}
    for stage, out in outs.items():
        on = [stage == "right" or (stage == "both" and r["left"]["kept"]) for r in rows]
        card = cardinality(triples, rows, classes, on)
        g = load_graph(graph_path)
        nodes = {str(x): x for x in g.all_nodes() if not isinstance(x, rdflib.Literal)}
        out_rows, checks = [], {c: {"pass": 0, "fail": 0, "skip": 0} for c in CHECKS}
        for i, (t, r) in enumerate(zip(triples, rows)):
            right, alive = None, range(len(r["passages"]))
            if on[i]:
                right = schema_checks(t, classes)
                if card[i]:
                    right["cardinality"] = card[i]
                right["contrast"], alive = contrast_result(r, margin)
                for c, v in right.items():
                    checks[c][v["result"]] += 1
            failed = [c for c, v in (right or {}).items() if v["result"] == "fail"]
            kept = (stage == "right" or r["left"]["kept"]) and not failed
            cited = max((p for j, p in enumerate(r["passages"]) if p["verdict"] == "supported" and j in alive),
                        key=lambda p: p["entailment"], default=None) if kept else None
            if not kept:
                remove(g, t, nodes)
            out_rows.append({**{k: v for k, v in r.items() if k != "contrast" or right}, "right": right,
                             "kept": kept, "cited": cite(cited),
                             "removed_by": None if kept else "right" if failed else "left"})
        g.serialize(destination=out / "graph.jsonld", format="json-ld", context=DEFAULT_CONTEXT, indent=2)
        (out / "hook.jsonl").write_text("".join(json.dumps(r) + "\n" for r in out_rows), encoding="utf-8")
        infos[stage] = {"edges": len(out_rows), "kept": sum(r["kept"] for r in out_rows),
                        **{v: sum(r["verdict"] == v for r in out_rows) for v in VERDICTS},
                        **{f"removed_{s}": sum(r["removed_by"] == s for r in out_rows) for s in ("left", "right")},
                        "checks": checks if stage != "left" else None}
    return infos


def cite(p: dict | None) -> dict | None:
    return {k: p[k] for k in ("doc", "sentence", "start", "end", "text")} if p else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--arm", required=True, help="the arm folder under results/RUN/ whose graphs the hook reads")
    ap.add_argument("--cases", help="comma-separated case ids (default: all)")
    ap.add_argument("--data", default="data")
    ap.add_argument("--stage", default="hook",
                    help="hook: the published hook (hook-v1); left, right, both, or several comma-separated")
    ap.add_argument("--template", choices=("full", "labels", "plain"),
                    help="--stage hook: full (default): classes and properties with their CASE/UCO definitions; "
                         "labels, plain: the ablation. The stages always render plain")
    ap.add_argument("--passages", choices=("sentence", "block"),
                    help="sentence: each source sentence is a passage (the default for --stage hook); "
                         "block: mail-header runs are one passage (the default for the stages)")
    ap.add_argument("--query", choices=("rendered", "plain"),
                    help="--stage hook: rendered (default): retrieve with the sentence verified; plain: retrieve with "
                         "the plain rendering. The stages verify the plain rendering, so they retrieve with it")
    ap.add_argument("--resume", action="store_true", help="skip cases whose every output already has run.json")
    ap.add_argument("--batch", type=int, default=BATCH, help="NLI pairs per forward pass (8 under memory pressure)")
    args = ap.parse_args()
    stages = [s.strip() for s in args.stage.split(",")]
    if stages != ["hook"] and not set(stages) <= STAGES.keys():
        ap.error("--stage is hook, or any of left, right, both")
    legacy = stages == ["hook"]
    template = args.template or "full" if legacy else "plain"
    passage_unit = args.passages or ("sentence" if legacy else "block")
    query = args.query or "rendered" if legacy else "plain"
    with open(CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)["hook"]
    verifier = Verifier(cfg, args.batch)
    root = HARNESS / "results" / args.run_id
    names = {"hook": f"{args.arm}+hook" + ("" if template == "full" else f"_{template}") +
             ("_block" if passage_unit == "block" else "") + ("_qplain" if query == "plain" else "")} if legacy else \
        {s: f"{args.arm}+{STAGES[s]}" for s in stages}
    for case_dir in case_dirs(args.cases, args.data):
        base = root / args.arm / case_dir.name
        outs = {s: root / n / case_dir.name for s, n in names.items()}
        if not (base / "run.json").exists() or (args.resume and all((o / "run.json").exists() for o in outs.values())):
            continue
        meta = json.loads((base / "run.json").read_text())
        for out in outs.values():
            out.mkdir(parents=True, exist_ok=True)
            for stale in ("graph.jsonld", "hook.jsonl", "run.json"):
                (out / stale).unlink(missing_ok=True)
        start, device, fallback = time.monotonic(), verifier.device, None
        infos = {s: {"final_validation": None} for s in outs}
        if meta["status"] not in ("error", "empty") and (base / "graph.jsonld").exists():
            for attempt in (device, "cpu"):
                try:
                    if legacy:
                        infos["hook"]["hook"] = hook_case(case_dir, base / "graph.jsonld", outs["hook"], verifier,
                                                          template, passage_unit, query)
                    else:
                        for s, h in hook_stages(case_dir, base / "graph.jsonld", outs, verifier, passage_unit,
                                                cfg["contrast_margin"]).items():
                            infos[s]["hook"] = h
                    for s, out in outs.items():
                        infos[s]["final_validation"] = case_validate(out / "graph.jsonld")["conforms"]
                    break
                except RuntimeError as exc:  # out of memory on the GPU: this case once more on the CPU, logged
                    if attempt == "cpu" or device == "cpu":
                        infos = {s: {"status": "error", "error": f"hook: {type(exc).__name__}: {exc}"[:2000],
                                     "final_validation": None} for s in outs}
                        break
                    fallback = f"{type(exc).__name__}: {exc}"[:500]
                    print(f"{case_dir.name}: failed on {device}, retrying on cpu: {fallback}", flush=True)
                    verifier.to("cpu")
                except Exception as exc:  # an unreadable graph is a recorded outcome, as in the arms
                    infos = {s: {"status": "error", "error": f"hook: {type(exc).__name__}: {exc}"[:2000],
                                 "final_validation": None} for s in outs}
                    break
            if verifier.device != device:
                verifier.to(device)
        hook_s = round(time.monotonic() - start, 1)
        for s, out in outs.items():
            run = {**meta, "arm": names[s], **infos[s], "hook_s": hook_s, "wall_s": round(meta.get("wall_s", 0) + hook_s, 1),
                   "hook_template": template, "hook_passages": passage_unit, "hook_query": query,
                   **({} if legacy else {"hook_stage": s, "hook_contrast_margin": cfg["contrast_margin"],
                                         "hook_device": "cpu" if fallback else device}),
                   **({"hook_fallback": fallback} if fallback else {}),
                   "hook_models": {k: cfg[k] for k in ("embed_model", "embed_revision", "nli_model", "nli_revision")}}
            (out / "run.json").write_text(json.dumps(run, indent=1))
            hook = {k: v for k, v in (infos[s].get("hook") or {}).items() if k != "checks"} or None
            print(f"{names[s]} {case_dir.name}: {run['status']} {hook} valid={run['final_validation']} {hook_s}s", flush=True)


if __name__ == "__main__":
    main()
