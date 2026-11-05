"""What the ontology says, for the reconciler: the SDK's schema and registry (graphkit.SCHEMA, REGISTRY) and the task
profile (profile.toml), checked against each other at load. Every class and property the profile names must exist
in the schema, and every property must be declared on its class or one of its facets; otherwise the profile is
wrong, and loading fails rather than skipping the check."""

from __future__ import annotations

from graphkit import PROFILE, REGISTRY, SCHEMA

KIND_CLASSES: dict[str, tuple[set[str], set[str]]] = {k: (set(v["domain"]), set(v["range"])) for k, v in PROFILE["kinds"].items()}
PHRASES: dict[str, str] = {k: v["phrase"] for k, v in PROFILE["kinds"].items()}
SYMMETRIC = set(PROFILE["relations"]["symmetric"])
ENTAILS: dict[str, set[str]] = {k: set(v) for k, v in PROFILE["entails"].items()}
PROP_CLASSES: dict[tuple[str, str], set[str]] = {(o["class"], o["property"]): set(o["range"]) for o in PROFILE["object_properties"]}
LITERAL_PROPS: dict[str, list[str]] = {c: list(ps) for c, ps in PROFILE["literal_properties"].items()}
KIND_OF = {k.lower(): k for k in KIND_CLASSES}
UNCONSTRAINED = {"UcoObject", "UcoThing"}


def ancestors(cls: str) -> set[str]:
    out, todo = set(), [cls]
    while todo:
        c = todo.pop()
        if c and c not in out:
            out.add(c)
            todo += REGISTRY.get(c, {}).get("parents", [])
    return out


def declares(cls: str, prop: str) -> bool:
    """Is prop a property of cls or a superclass, or of a facet of one of them (an ApplicationAccount's
    accountIdentifier is on AccountFacet)?"""
    lineage = ancestors(cls)
    for c in lineage:
        if c in SCHEMA and prop in SCHEMA[c]["props"]:
            return True
    facets = {f"{c}Facet" for c in lineage} | ({"SimpleAddressFacet"} if "Location" in lineage else set())
    return any(f in SCHEMA and prop in SCHEMA[f]["props"] for f in facets)


def validate() -> list[str]:
    """Every class and property the profile names, against the schema. Returns the problems; empty when none."""
    problems = []
    for kind, (dom, rng) in KIND_CLASSES.items():
        for c in dom | rng:
            if c not in SCHEMA:
                problems.append(f"kind {kind}: {c} is not a CASE/UCO class")
    for (cls, prop), rng in PROP_CLASSES.items():
        if cls not in SCHEMA:
            problems.append(f"object property {cls}.{prop}: {cls} is not a CASE/UCO class")
        elif not declares(cls, prop):
            problems.append(f"object property {cls}.{prop}: {prop} is not a property of {cls} or its facets")
        for c in rng:
            if c not in SCHEMA:
                problems.append(f"object property {cls}.{prop}: range {c} is not a CASE/UCO class")
    for cls, props in LITERAL_PROPS.items():
        if cls not in SCHEMA:
            problems.append(f"literal properties: {cls} is not a CASE/UCO class")
            continue
        problems += [f"literal properties: {prop} is not a property of {cls} or its facets" for prop in props
                     if not declares(cls, prop)]
    for cls, props in PROFILE["keys"].items():
        if cls not in SCHEMA:
            problems.append(f"keys: {cls} is not a CASE/UCO class")
            continue
        problems += [f"keys: {prop} is not a property of {cls} or its facets" for prop in props
                     if not declares(cls, prop) and not (cls == "EmailAccount" and prop == "addressValue")]
    for k in ENTAILS:
        problems += [f"entails: {k} is not a kind"] if k not in KIND_CLASSES else []
    return problems


_PROBLEMS = validate()
if _PROBLEMS:
    raise ImportError("profile.toml does not fit the SDK's schema:\n  " + "\n  ".join(_PROBLEMS))
