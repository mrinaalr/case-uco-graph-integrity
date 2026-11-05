"""Shared graph plumbing for the faithfulness harness.

- SCHEMA: core CASE/UCO classes and properties, introspected from the SDK's
  generated dataclasses (no extensions, so CAC classes are never writable).
- GraphWriter: CASEGraph-backed writes with per-triple provenance, used by
  the gold generator and by arm A2's write tools.
- graph_triples: parse any CASE JSON-LD file into normalized triples.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import subprocess
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path

import rdflib
from rdflib.compare import to_canonical_graph
from case_uco.graph import DEFAULT_CONTEXT, CASEGraph
from case_uco.uco.core import Facet

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / "harness"
KB = DEFAULT_CONTEXT["kb"]
XSD = "http://www.w3.org/2001/XMLSchema#"

# The task profile (profile.toml): the relation kinds with their domain, range and phrase, the properties the task
# fills, and each class's key. CASE/UCO leaves these open; every arm, the hook and the reconciler read them here.
with open(HARNESS / "profile.toml", "rb") as _fh:
    PROFILE = tomllib.load(_fh)
# Relationship kinds (source -> target) both pipelines are told to use.
RELATION_KINDS = {k: v["description"] for k, v in PROFILE["kinds"].items()}
# Each kind as the verb phrase in "source <phrase> target". CASE/UCO does not define these kinds; the hook's
# sentence template and arm C's target schema use the phrase in place of a definition.
RELATION_PHRASES = {k: v["phrase"] for k, v in PROFILE["kinds"].items()}

# The verification hook's verdict on each edge (hook.py).
VERDICTS = ("supported", "contradicted", "not_enough_evidence")

# Annotation properties that carry no checkable fact; never scored.
SKIP_PROPS = {"isDirectional", "description", "tag", "specVersion", "objectMarking",
              "body", "displayName", "objectCreatedTime", "modifiedTime", "cites"}

_MODULES = [f"case_uco.uco.{m}" for m in (
    "action", "analysis", "configuration", "core", "identity", "location", "marking",
    "observable", "pattern", "role", "tool", "types", "victim")] + ["case_uco.case.investigation"]


def _load_schema() -> dict[str, dict]:
    schema: dict[str, dict] = {}
    for mod_name in _MODULES:
        mod = importlib.import_module(mod_name)
        for obj in vars(mod).values():
            if not (isinstance(obj, type) and dataclasses.is_dataclass(obj) and hasattr(obj, "CLASS_IRI")):
                continue
            local = obj.CLASS_IRI.rstrip("/").split("/")[-1]
            if local in schema:
                continue
            props, own = {}, set()
            parent_keys = set()
            for base in obj.__mro__[1:]:
                if dataclasses.is_dataclass(base):
                    parent_keys |= {f.metadata.get("jsonld_key") for f in dataclasses.fields(base)}
            for f in dataclasses.fields(obj):
                key = f.metadata.get("jsonld_key")
                if not key:
                    continue
                name = key.split(":", 1)[1]
                props.setdefault(name, {
                    "key": key,
                    "range": f.metadata.get("range_iri", ""),
                    "many": f.metadata.get("cardinality", "").endswith("more"),
                })
                if key not in parent_keys:
                    own.add(name)
            schema[local] = {
                "type": f"{obj.NAMESPACE_PREFIX}:{local}",
                "is_facet": issubclass(obj, Facet),
                "props": props,
                "own": sorted(own),
            }
    return schema


SCHEMA = _load_schema()

# Class and property definitions as the SDK's registry carries them (what get_class_details serves).
REGISTRY = json.loads((Path(importlib.import_module("case_uco").__file__).parent / "_registry.json").read_text())["classes"]


def definition(text: str | None) -> str:
    """A registry description without its source note and final period."""
    return re.sub(r"\s*\[based on [^\]]*\]", "", text or "").strip().rstrip(".")


PROPERTY_DEFS: dict[str, dict[str, str]] = {}  # property -> class -> definition
for _cls in sorted(REGISTRY):
    for _p in REGISTRY[_cls].get("properties", []):
        if _p.get("description"):
            PROPERTY_DEFS.setdefault(_p["name"], {})[_cls] = definition(_p["description"])


def property_definition(cls: str | None, prop: str) -> str:
    """The definition of prop on cls, on cls's facet, or on the first class that has it."""
    defs = PROPERTY_DEFS.get(prop, {})
    return defs.get(cls) or defs.get(f"{cls}Facet") or next(iter(defs.values()), "")


def words(name: str) -> str:
    """'EmailAddress' -> 'email address', 'Employed_By' -> 'employed by'."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ").lower()


_UUID_TAIL = re.compile(r"-?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def slug(value: str) -> str:
    text = value.strip()
    text = text[len(KB):] if text.startswith(KB) else text[3:] if text.startswith("kb:") else text
    return _UUID_TAIL.sub("", re.sub(r"[^A-Za-z0-9._-]+", "-", text))


def kb_id(value: str) -> str:
    """Stable kb: IRI for a short id; UCO suggests IRIs end in a UUID."""
    if value.startswith(("http://", "https://")) and not value.startswith(KB):
        return value
    s = slug(value)
    return f"kb:{s}-{uuid.uuid5(uuid.NAMESPACE_URL, KB + s)}"


def expand(compact: str) -> str:
    prefix, _, rest = compact.partition(":")
    return DEFAULT_CONTEXT[prefix] + rest if prefix in DEFAULT_CONTEXT and not rest.startswith("//") else compact


def iso_time(value: str) -> str | None:
    """Parse common date-time spellings into 'YYYY-MM-DDTHH:MM:SSZ' (UTC)."""
    text = str(value).strip().replace(" UTC", "+00:00").replace("Z", "+00:00")
    for parse in (datetime.fromisoformat,
                  lambda s: datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %z"),
                  lambda s: datetime.strptime(s, "%B %d, %Y at %H:%M%z"),
                  lambda s: datetime.strptime(s, "%d %B %Y, %H:%M%z")):
        try:
            dt = parse(text)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


class BuildError(ValueError):
    pass


class GraphWriter:
    """Graph writes backed by case_uco.graph.CASEGraph. Writes are upserts.

    Values are coerced to the property's range from SCHEMA (typed literals,
    @id references). prov maps each triple origin to the write call that
    first produced its current value, so a value changed during repair is
    attributed to repair.
    """

    def __init__(self) -> None:
        self.g = CASEGraph()
        self.classes: dict[str, str] = {}
        self.prov: dict[str, int] = {}

    def _note(self, key: str, call: int | None, changed: bool = False) -> None:
        if call is not None and (changed or key not in self.prov):
            self.prov[key] = call

    def _coerce(self, cls: str, name: str, value):
        spec = SCHEMA[cls]["props"].get(name)
        if spec is None:
            raise BuildError(f"{cls} has no property {name!r}; use get_class_details to see its properties")
        out = []
        for v in value if isinstance(value, list) else [value]:
            if isinstance(v, dict):  # accept the JSON-LD forms the prompt shows: {"@value": ...} / {"@id": ...}
                v = v.get("@value", v.get("@id", v))
            rng = spec["range"]
            if rng.startswith(XSD):
                dtype = rng[len(XSD):]
                if dtype == "string":
                    out.append(str(v))
                    continue
                if dtype == "dateTime":
                    v = iso_time(v) or str(v)
                elif dtype == "boolean":
                    v = str(v).lower()
                out.append({"@type": f"xsd:{dtype}", "@value": str(v)})
            elif "/vocabulary/" in rng:
                out.append(str(v))
            else:
                out.append({"@id": kb_id(str(v))})
        return out if spec["many"] or len(out) > 1 else out[0]

    def _set_props(self, target: str, cls: str, owner: str, properties: dict | None, call: int | None) -> None:
        for name, value in (properties or {}).items():
            name = name.split(":")[-1]  # "uco-core:name" and "name" both accepted
            new = self._coerce(cls, name, value)
            key = SCHEMA[cls]["props"][name]["key"]
            changed = (self.g.get(target) or {}).get(key) != new
            self.g.set_property(target, key, new)
            self._note(f"prop|{expand(owner)}|{name}", call, changed)

    def add_node(self, node_id: str, class_name: str, properties: dict | None = None, call: int | None = None) -> str:
        class_name = class_name.split(":")[-1]  # the class list shows prefixed names
        if class_name not in SCHEMA or SCHEMA[class_name]["is_facet"]:
            raise BuildError(f"{class_name!r} is not a core CASE/UCO object class")
        nid = kb_id(node_id)
        existing = self.classes.get(nid)
        if existing and existing != class_name:
            raise BuildError(f"node {node_id!r} already exists as {existing}; use a different id")
        if not existing:
            self.g.upsert_node(nid, types=SCHEMA[class_name]["type"])
            self.classes[nid] = class_name
        self._set_props(nid, class_name, nid, properties, call)
        return nid

    def add_facet(self, node_id: str, facet_class: str, properties: dict | None = None, call: int | None = None) -> str:
        facet_class = facet_class.split(":")[-1]
        nid = kb_id(node_id)
        if nid not in self.classes:
            raise BuildError(f"node {node_id!r} does not exist; add_node first")
        if facet_class not in SCHEMA or not SCHEMA[facet_class]["is_facet"]:
            raise BuildError(f"{facet_class!r} is not a core CASE/UCO facet class")
        fid = kb_id(f"{slug(nid)}-{facet_class}")
        if fid not in self.classes:
            self.g.upsert_node(fid, types=SCHEMA[facet_class]["type"])
            self.g.add_property(nid, "uco-core:hasFacet", {"@id": fid})
            self.classes[fid] = facet_class
        self._set_props(fid, facet_class, nid, properties, call)
        return fid

    def add_relationship(self, source: str, target: str, kind: str, call: int | None = None) -> str:
        src, tgt = kb_id(source), kb_id(target)
        for end in (src, tgt):
            if end not in self.classes:
                raise BuildError(f"node {end} does not exist; add_node first")
        rid = kb_id(f"rel-{slug(src)}-{kind}-{slug(tgt)}")
        self.g.create_relationship(src, tgt, kind, relationship_id=rid)
        self.classes[rid] = "Relationship"
        self._note(f"rel|{expand(rid)}", call)
        return rid

    def object_count(self) -> int:
        return sum(1 for c in self.classes.values() if c != "Relationship" and not SCHEMA[c]["is_facet"])

    def write(self, path: Path) -> None:
        self.g.write(str(path), indent=2)


def _local(term) -> str:
    text = str(term)
    return re.split(r"[/#]", text.rstrip("/"))[-1]


def load_graph(path: Path) -> rdflib.Graph:
    """Parse CASE JSON-LD. Blank nodes get canonical labels, so two parses of one file name them alike."""
    g = rdflib.Graph().parse(path, format="json-ld")
    if any(isinstance(x, rdflib.BNode) for t in g for x in t):
        canonical = rdflib.Graph()
        canonical += to_canonical_graph(g)
        return canonical
    return g


def graph_triples(source: Path | rdflib.Graph) -> tuple[dict[str, dict], list[dict]]:
    """Return (entities, triples) from a CASE JSON-LD file or a graph from load_graph.

    entities: iri -> {"class", "props": {prop: [values]}}
    triples: {"s", "p", "o", "lit", "origin"}; Relationship nodes become
    (source, kindOfRelationship, target); facet properties fold onto the owner.
    """
    g = source if isinstance(source, rdflib.Graph) else load_graph(source)
    rdf_type = rdflib.RDF.type
    has_facet = rdflib.URIRef(expand("uco-core:hasFacet"))
    types = {s: {_local(o) for o in g.objects(s, rdf_type)} for s in set(g.subjects(rdf_type, None))}
    facets = {s for s, t in types.items() if any(x.endswith("Facet") for x in t)}
    rels = {s for s, t in types.items() if "Relationship" in t}
    entities: dict[str, dict] = {}
    triples: list[dict] = []

    def emit(s, p, o, origin) -> None:
        lit = isinstance(o, rdflib.Literal)
        triples.append({"s": str(s), "p": p, "o": str(o), "lit": lit, "origin": origin})
        entities[str(s)]["props"].setdefault(p, []).append(str(o))

    for s, t in types.items():
        if s in facets or s in rels:
            continue
        specific = sorted(t - {"UcoObject", "ObservableObject", "Identity", "Item"}) or sorted(t)
        entities[str(s)] = {"class": specific[0], "props": {}}
    for s in entities:
        node = rdflib.URIRef(s)
        holders = [node] + [f for f in g.objects(node, has_facet) if f in facets]
        name_parts = {}
        for holder in holders:
            for p, o in g.predicate_objects(holder):
                p_local = _local(p)
                if p == rdf_type or p == has_facet or p_local in SKIP_PROPS:
                    continue
                if p_local in ("givenName", "familyName"):
                    name_parts[p_local] = str(o)
                    continue
                emit(s, p_local, o, f"prop|{s}|{p_local}")
        if name_parts and "name" not in entities[s]["props"]:
            full = " ".join(name_parts[k] for k in ("givenName", "familyName") if k in name_parts)
            emit(s, "name", rdflib.Literal(full), f"prop|{s}|givenName")
    for r in rels:
        kinds = [str(k) for k in g.objects(r, rdflib.URIRef(expand("uco-core:kindOfRelationship")))]
        for src in g.objects(r, rdflib.URIRef(expand("uco-core:source"))):
            for tgt in g.objects(r, rdflib.URIRef(expand("uco-core:target"))):
                for kind in kinds or ["(none)"]:
                    if str(src) in entities:
                        triples.append({"s": str(src), "p": kind, "o": str(tgt), "lit": False, "origin": f"rel|{r}"})
    return entities, triples


HEADER_LINE = re.compile(r"^(From|To|Cc|Subject|Date):|^[\[@#]")  # mail headers, chat lines: one sentence each


def sentences_of(text: str) -> list[str]:
    """Split a document into sentences. A blank line, a header or chat line, or a line ending in
    . ! ? ends a sentence; any other newline is a wrapped line (PDF-extracted text) and is joined.
    Within a line, . ! ? followed by a capital, quote or bracket ends a sentence."""
    blocks, cur = [], ""
    for line in (x.strip() for x in text.strip().split("\n")):
        if not line:
            blocks, cur = blocks + ([cur] if cur else []), ""
        elif cur and not re.search(r"[.!?]$", cur) and not HEADER_LINE.match(line) and not HEADER_LINE.match(cur):
            cur += " " + line
        elif cur and line[0].islower():
            cur += " " + line
        else:
            blocks, cur = blocks + ([cur] if cur else []), line
    blocks += [cur] if cur else []
    return [x.strip() for b in blocks for x in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[@#])", b) if x.strip()]


def pdf_text(path: Path) -> str:
    """Text of a PDF as pypdf extracts it, cached next to the file as <name>.pdf.txt."""
    cache = path.with_suffix(".pdf.txt")
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return cache.read_text(encoding="utf-8")
    from pypdf import PdfReader
    text = "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    cache.write_text(text, encoding="utf-8")
    return text


def case_validate(path: Path, timeout: int = 600) -> dict:
    """Run case_validate (sh:Info results allowed); returns {"conforms": bool|None, "report": str}."""
    exe = REPO / ".venv" / "bin" / "case_validate"
    try:
        proc = subprocess.run([str(exe), "--allow-info", str(path)], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"conforms": None, "report": "timeout"}
    out = proc.stdout + proc.stderr
    conforms = True if "Conforms: True" in out else False if "Conforms: False" in out else None
    return {"conforms": conforms, "report": out[-4000:]}


def git_describe() -> str:
    return subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=REPO,
                          capture_output=True, text=True).stdout.strip()


def class_list(names: list[str]) -> str:
    """Compact class/property listing given to Pipeline B."""
    lines = []
    for name in names:
        spec = SCHEMA[name]
        props = spec["own"]
        if not spec["is_facet"] and "name" in spec["props"] and "name" not in props:
            props = ["name"] + props
        lines.append(f"- {spec['type']} ({'facet' if spec['is_facet'] else 'object'}): " + ", ".join(
            f"{p}<{_local(spec['props'][p]['range'])}>" for p in props))
    return "\n".join(lines)
