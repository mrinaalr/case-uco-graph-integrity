"""A CASE/UCO graph as a ledger of stated claims. Any JSON-LD graph graphkit.graph_triples can read: Relationship
nodes become (source, kind, target), facet properties fold onto their owner, type triples and annotation properties
are not claims. Each entity keeps the IRI the graph gave it; each claim records which node stated it."""

from __future__ import annotations

from pathlib import Path

import rdflib

from graphkit import expand, graph_triples, load_graph
from reconcile.ledger import STATED, Claim, Entity, Ledger
from reconcile.ontology import ancestors

HAS_FACET = rdflib.URIRef(expand("uco-core:hasFacet"))


def local(term) -> str:
    return str(term).rstrip("/").split("/")[-1].split("#")[-1]


def holder_classes(g: rdflib.Graph, iri: str) -> set[str]:
    """The classes of an entity and of its facets, with their superclasses."""
    node = rdflib.URIRef(iri)
    return {c for h in [node, *g.objects(node, HAS_FACET)] for t in g.objects(h, rdflib.RDF.type) for c in ancestors(local(t))}


def ingest(graph_path: Path) -> tuple[Ledger, rdflib.Graph]:
    g = load_graph(graph_path)
    entities, triples = graph_triples(g)
    led = Ledger()
    for iri, e in entities.items():
        led.add_entity(Entity(iri, e["class"], {p: list(vs) for p, vs in e["props"].items()}, [iri]))
    for t in triples:
        kind, _, rest = t["origin"].partition("|")
        by = rest if kind == "rel" else f"{t['s']}|{rest.split('|')[-1]}"
        led.add_claim(t["s"], t["p"], t["o"], t["lit"], kind, STATED, stated_by=[by])
    led.meta = {"graph": str(graph_path), "classes": {iri: sorted(holder_classes(g, iri)) for iri in entities}}
    return led, g


def classes_of(led: Ledger) -> dict[str, set[str]]:
    return {iri: set(cs) for iri, cs in led.meta.get("classes", {}).items()}


def entities_view(led: Ledger) -> dict[str, dict]:
    """The hook's `entities` shape, {iri: {class, props}}, for its pure functions."""
    return {e.id: {"class": e.cls, "props": e.props} for e in led.entities.values()}


def triples_view(led: Ledger, claims: list[Claim] | None = None) -> list[dict]:
    return [c.as_triple() for c in (claims if claims is not None else led.stated())]
