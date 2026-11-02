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

    python harness/hook.py --run-id RUN --arm b_control [--template full|labels|plain] [--cases case_01,case_02]
"""

from __future__ import annotations

import argparse
import json
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

from graphkit import (HARNESS, REGISTRY, RELATION_PHRASES, VERDICTS, case_validate, definition, expand, graph_triples,
                      iso_time, load_graph, property_definition, slug, words)
from llm import CONFIG, case_dirs, passages

VERDICT_OF = {"entailment": "supported", "contradiction": "contradicted", "neutral": "not_enough_evidence"}
PHRASES = {k.lower(): v for k, v in RELATION_PHRASES.items()}
LABEL_PROPS = ("name", "addressValue", "accountIdentifier", "subject", "eventType", "street", "messageText")
HAS_FACET = rdflib.URIRef(expand("uco-core:hasFacet"))
BATCH = 16


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


class Verifier:
    """The pinned embedder and NLI model."""

    def __init__(self, cfg: dict) -> None:
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.top_k = cfg["top_k"]
        self.embedder = SentenceTransformer(cfg["embed_model"], revision=cfg["embed_revision"], device=self.device)
        self.tokenizer = AutoTokenizer.from_pretrained(cfg["nli_model"], revision=cfg["nli_revision"])
        self.nli = AutoModelForSequenceClassification.from_pretrained(cfg["nli_model"], revision=cfg["nli_revision"])
        self.nli.to(self.device).eval()
        self.verdicts = [VERDICT_OF[self.nli.config.id2label[i].lower()] for i in range(self.nli.config.num_labels)]
        self.supported = self.verdicts.index("supported")

    def check(self, sentences: list[str], source: list[dict]) -> list[list[dict]]:
        """For each sentence, its top_k passages with similarity, pair verdict and entailment probability."""
        if not sentences:
            return []
        p_emb = self.embedder.encode([p["text"] for p in source], normalize_embeddings=True)
        s_emb = self.embedder.encode(sentences, normalize_embeddings=True)
        sims = s_emb @ p_emb.T
        top = np.argsort(-sims, axis=1, kind="stable")[:, :self.top_k]
        pairs = [(i, int(j)) for i in range(len(sentences)) for j in top[i]]
        probs = []
        for k in range(0, len(pairs), BATCH):
            batch = pairs[k:k + BATCH]
            enc = self.tokenizer([source[j]["text"] for _, j in batch], [sentences[i] for i, _ in batch],
                                 truncation=True, padding=True, return_tensors="pt").to(self.device)
            with torch.no_grad():
                probs.append(self.nli(**enc).logits.float().softmax(-1).cpu().numpy())
        probs = np.concatenate(probs)
        out = [[] for _ in sentences]
        for (i, j), pr in zip(pairs, probs):
            out[i].append({**source[j], "similarity": round(float(sims[i, j]), 4),
                           "verdict": self.verdicts[int(pr.argmax())], "entailment": round(float(pr[self.supported]), 4)})
        return out


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


def hook_case(case_dir: Path, graph_path: Path, out: Path, verifier: Verifier, template: str = "full") -> dict:
    g = load_graph(graph_path)
    entities, triples = graph_triples(g)
    sentences = [render(t, entities, template) for t in triples]
    unique = list(dict.fromkeys(sentences))
    checked = dict(zip(unique, verifier.check(unique, passages(case_dir))))
    nodes = {str(x): x for x in g.all_nodes() if not isinstance(x, rdflib.Literal)}
    rows = []
    for t, sentence in zip(triples, sentences):
        retrieved = checked[sentence]
        verdict = next((v for v in VERDICTS if v in {p["verdict"] for p in retrieved}), "not_enough_evidence")
        cited = max((p for p in retrieved if p["verdict"] == "supported"), key=lambda p: p["entailment"], default=None)
        if not cited:
            remove(g, t, nodes)
        rows.append({"s": t["s"], "p": t["p"], "o": t["o"], "lit": t["lit"], "origin": t["origin"], "sentence": sentence,
                     "passages": retrieved, "verdict": verdict, "kept": cited is not None,
                     "cited": {k: cited[k] for k in ("doc", "sentence", "start", "end", "text")} if cited else None})
    g.serialize(destination=out / "graph.jsonld", format="json-ld", context=DEFAULT_CONTEXT, indent=2)
    (out / "hook.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return {"edges": len(rows), "kept": sum(r["kept"] for r in rows), **{v: sum(r["verdict"] == v for r in rows) for v in VERDICTS}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--arm", required=True, help="the arm folder under results/RUN/ whose graphs the hook reads")
    ap.add_argument("--cases", help="comma-separated case ids (default: all)")
    ap.add_argument("--data", default="data")
    ap.add_argument("--template", default="full", choices=("full", "labels", "plain"),
                    help="full: classes and properties with their CASE/UCO definitions; labels, plain: the ablation")
    args = ap.parse_args()
    with open(CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)["hook"]
    verifier = Verifier(cfg)
    root = HARNESS / "results" / args.run_id
    name = f"{args.arm}+hook" + ("" if args.template == "full" else f"_{args.template}")
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
                info["hook"] = hook_case(case_dir, base / "graph.jsonld", out, verifier, args.template)
                info["final_validation"] = case_validate(out / "graph.jsonld")["conforms"]
            except Exception as exc:  # an unreadable graph is a recorded outcome, as in the arms
                info = {"status": "error", "error": f"hook: {type(exc).__name__}: {exc}"[:2000], "final_validation": None}
        hook_s = round(time.monotonic() - start, 1)
        run = {**meta, "arm": name, **info, "hook_s": hook_s, "wall_s": round(meta.get("wall_s", 0) + hook_s, 1),
               "hook_template": args.template,
               "hook_models": {k: cfg[k] for k in ("embed_model", "embed_revision", "nli_model", "nli_revision")}}
        (out / "run.json").write_text(json.dumps(run, indent=1))
        print(f"{name} {case_dir.name}: {run['status']} {info.get('hook')} valid={run['final_validation']} {hook_s}s", flush=True)


if __name__ == "__main__":
    main()
