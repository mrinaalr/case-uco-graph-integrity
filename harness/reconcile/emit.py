"""The reconciled graph and its record, written next to the original.

The input graph is copied byte for byte to input/graph.jsonld. The reconciled graph.jsonld is the input with the
claims the policy removes taken out (hook.remove: the Relationship node, or the value on the node and its facets),
merged entities folded onto one IRI, and verified proposals written in (a Relationship node, or the property on the
subject's facet). Everything else the graph said, annotation properties and IRIs included, is left as it was. The
ledger (claims, entities, decisions) goes to ledger/, and provenance.jsonld says in CASE terms what was done."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path

import rdflib
from case_uco.graph import DEFAULT_CONTEXT

from graphkit import SCHEMA, expand, load_graph
from hook import remove
from reconcile.ingest import HAS_FACET, local
from reconcile.ledger import PROPOSED, Claim, Ledger
from reconcile.policy import POLICIES, added, removed

RDF_TYPE = rdflib.RDF.type
KB = DEFAULT_CONTEXT["kb"]


def facet_for(g: rdflib.Graph, s: str, prop: str) -> tuple[rdflib.URIRef, dict] | None:
    """The subject's facet whose class declares prop, and the property's schema entry."""
    for f in g.objects(rdflib.URIRef(s), HAS_FACET):
        for t in g.objects(f, RDF_TYPE):
            spec = SCHEMA.get(local(t))
            if spec and prop in spec["props"]:
                return f, spec["props"][prop]
    for t in g.objects(rdflib.URIRef(s), RDF_TYPE):
        spec = SCHEMA.get(local(t))
        if spec and prop in spec["props"]:
            return rdflib.URIRef(s), spec["props"][prop]
    return None


def add_edge(g: rdflib.Graph, c: Claim) -> str | None:
    """Write one claim. Returns why it could not be written, or None."""
    if c.kind == "rel":
        r = rdflib.URIRef(f"{KB}rel-rec-{uuid.uuid5(uuid.NAMESPACE_URL, c.id)}")
        g.add((r, RDF_TYPE, rdflib.URIRef(expand("uco-core:Relationship"))))
        g.add((r, rdflib.URIRef(expand("uco-core:source")), rdflib.URIRef(c.s)))
        g.add((r, rdflib.URIRef(expand("uco-core:target")), rdflib.URIRef(c.o)))
        g.add((r, rdflib.URIRef(expand("uco-core:kindOfRelationship")), rdflib.Literal(c.p)))
        g.add((r, rdflib.URIRef(expand("uco-core:isDirectional")), rdflib.Literal(True)))
        return None
    found = facet_for(g, c.s, c.p)
    if not found:
        return f"{c.s} has no facet that carries {c.p}"
    holder, spec = found
    o = rdflib.Literal(c.o, datatype=rdflib.URIRef(spec["range"])) if c.lit else rdflib.URIRef(c.o)
    g.add((holder, rdflib.URIRef(expand(spec["key"])), o))
    return None


def merge(g: rdflib.Graph, keep: str, dups: list[str]) -> None:
    k = rdflib.URIRef(keep)
    for d in map(rdflib.URIRef, dups):
        for p, o in list(g.predicate_objects(d)):
            g.remove((d, p, o))
            g.add((k, p, o))
        for s, p in list(g.subject_predicates(d)):
            g.remove((s, p, d))
            g.add((s, p, k))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def emit(led: Ledger, graph_path: Path, out: Path, policy: str, meta: dict) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    (out / "input").mkdir(exist_ok=True)
    shutil.copy(graph_path, out / "input" / "graph.jsonld")
    g = load_graph(graph_path)
    nodes = {str(x): x for x in g.all_nodes() if not isinstance(x, rdflib.Literal)}
    for e in led.entities.values():
        if len(e.members) > 1 and e.id in nodes:
            merge(g, e.id, [m for m in e.members if m != e.id and m in nodes])
    gone = removed(led, policy)
    for c in gone:
        remove(g, c.as_triple(), nodes)
    written, failed = [], []
    adds = added(led, policy)
    linked = {x for c in adds if not c.lit for x in (c.s, c.o)}
    for e in led.entities.values():  # a provisional entity enters with its class, its facet and its key
        if e.origin == PROPOSED and e.id in linked and e.id not in nodes:
            node = rdflib.URIRef(e.id)
            g.add((node, RDF_TYPE, rdflib.URIRef(expand(SCHEMA[e.cls]["type"]))))
            facet = next((f for f in (f"{e.cls}Facet", "SimpleAddressFacet" if e.cls == "Location" else "", "AccountFacet"
                                      if e.cls == "ApplicationAccount" else "") if f in SCHEMA), None)
            if facet:
                fid = rdflib.URIRef(f"{e.id}-facet")
                g.add((fid, RDF_TYPE, rdflib.URIRef(expand(SCHEMA[facet]["type"]))))
                g.add((node, HAS_FACET, fid))
            nodes[e.id] = node
            for p, vs in e.props.items():
                for v in vs:
                    add_edge(g, Claim(f"key-{e.id}-{p}", e.id, p, v, True, "prop"))
    for c in adds:
        if c.s not in nodes or (not c.lit and c.o not in nodes):
            failed.append((c, "an entity the graph does not hold"))
            continue
        why = add_edge(g, c)
        (failed if why else written).append((c, why) if why else c)
    for c, why in failed:
        led.decide(c, "emit", "not-written", c.status, why)
    g.serialize(destination=out / "graph.jsonld", format="json-ld", context=DEFAULT_CONTEXT, indent=2)
    led.write(out / "ledger")
    info = {"input_sha256": sha256(graph_path), "output_sha256": sha256(out / "graph.jsonld"), "policy": policy,
            "removed": len(gone), "added": len(written), "not_written": len(failed),
            "merged": sum(len(e.members) - 1 for e in led.entities.values()), **led.summary()}
    provenance(led, out, policy, {**meta, **info})
    return info


def provenance(led: Ledger, out: Path, policy: str, info: dict) -> None:
    """provenance.jsonld: the run as a case-investigation:InvestigativeAction, each removed claim as a
    uco-core:Assertion with its statement and the reason, each kept claim's citation, and the merges."""
    act = f"kb:reconcile-{uuid.uuid5(uuid.NAMESPACE_URL, info.get('output_sha256', ''))}"
    graph = [{"@id": act, "@type": "case-investigation:InvestigativeAction",
              "uco-core:name": "reconcile", "uco-core:description": json.dumps({k: v for k, v in info.items()
                                                                                 if k not in ("stated", "reading", "proposed")})}]
    for c in led.stated():
        if c.status in POLICIES[policy]["remove"]:
            graph.append({"@id": f"kb:assertion-{c.id}", "@type": "uco-core:Assertion",
                          "uco-core:statement": c.sentence or f"{c.s} {c.p} {c.o}",
                          "uco-core:description": f"removed: {c.status} ({c.decided_by}); {next((d.reason for d in reversed(led.decisions) if d.claim == c.id), '')}",
                          "uco-core:tag": [c.status, *c.stated_by]})
        else:
            cites = [e["cite"] for e in c.evidence if e["label"] == "supports"]
            if cites:
                best = max((e for e in c.evidence if e["label"] == "supports"), key=lambda e: e["score"])["cite"]
                graph.append({"@id": f"kb:support-{c.id}", "@type": "uco-core:Assertion",
                              "uco-core:statement": c.sentence,
                              "uco-core:description": f"{c.status}; {best['doc']} sentence {best['sentence']} "
                                                      f"[{best['start']}:{best['end']}]: {best['text']}",
                              "uco-core:tag": [c.status, c.modality, *c.stated_by]})
    for c in added(led, policy):
        best = max((e for e in c.evidence if e["label"] == "supports"), key=lambda e: e["score"], default=None)
        graph.append({"@id": f"kb:added-{c.id}", "@type": "uco-core:Assertion", "uco-core:statement": c.sentence,
                      "uco-core:description": f"added ({c.note or 'proposed'}); " +
                      (f"{best['cite']['doc']} sentence {best['cite']['sentence']}: {best['cite']['text']}" if best else ""),
                      "uco-core:tag": [c.status, c.modality]})
    for e in led.entities.values():
        if len(e.members) > 1:
            graph.append({"@id": f"kb:merge-{re.sub(r'[^A-Za-z0-9]+', '-', e.id)[-40:]}", "@type": "uco-core:Assertion",
                          "uco-core:statement": f"{e.cls} {e.id} also written as {', '.join(m for m in e.members if m != e.id)}",
                          "uco-core:tag": ["merged"]})
    ctx = {k: DEFAULT_CONTEXT[k] for k in ("kb", "uco-core", "case-investigation", "xsd") if k in DEFAULT_CONTEXT}
    (out / "provenance.jsonld").write_text(json.dumps({"@context": ctx, "@graph": graph}, indent=1), encoding="utf-8")
