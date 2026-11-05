"""Pass 2, semantic correction: what the ontology says of each claim, and whether the source prefers another reading.

On every claim with support (or every claim, `on="all"`): the right hook's checks, from the SDK's schema and the task
profile (hook.schema_checks: domain, range, datatype, self-loop; hook.cardinality: a single-valued property with several
values keeps the one that best outranks its readings), the mail-header rule (hook.header_check: Date:, From:, To:
decide a message's time, sender and recipients), and contrast (hook.contrast_scores): on each passage that supports the
claim, its plain sentence and each competing reading's are scored against the passage followed by the CASE/UCO
definitions in play; the claim fails when a competitor outranks it by more than the margin in log-odds on every such
passage. Competitors are the other readings the profile allows for the same entities, less those the claim entails.

Results go on the claim as `checks` (each check's pass, fail or skip with its reason) and `competitors` (each rival's
sentence and, per passage, both entailments). The pass decides nothing; policy.verdict reads the record. `ambiguous`
is signalled here: contrast passed, but on the claim's best passage a rival is itself entailed and within the margin."""

from __future__ import annotations

from graphkit import iso_time
from hook import advantage, contrast_result, contrast_scores, header_check, logit, prop_spec, schema_checks
from reconcile.ingest import classes_of
from reconcile.ledger import STATED, Claim, Ledger
from reconcile.source import Source
from reconcile.verify import named_entities

VERDICT_OF = {"supports": "supported", "contradicts": "contradicted", "neutral": "not_enough_evidence"}


def row_of(c: Claim) -> dict:
    """The hook's per-edge row, from the claim's NLI evidence, for its contrast functions."""
    passages = [{**e["cite"], "verdict": VERDICT_OF[e["label"]], "entailment": e["score"]}
                for e in c.evidence if e["method"] == "nli"]
    return {"sentence": c.sentence, "passages": passages}


def near_miss(contrast: dict | None, margin: float) -> bool:
    """On the claim's best passage, is a rival entailed and within the margin?"""
    if not contrast or not contrast.get("passages"):
        return False
    best = max(contrast["passages"], key=lambda s: logit(s["own"]) - logit(max(s.get("rivals", [0.0]))))
    rival = max(best.get("rivals", [0.0]))
    return rival >= 0.5 and 0 <= logit(best["own"]) - logit(rival) <= margin


def cardinality(todo: list[Claim], rows: list[dict], classes: dict[str, set], active: list[bool], margin: float) -> list[dict | None]:
    """A single-valued property holding several values among the active claims. Among stated values, the one that
    best outranks its readings is kept (hook.cardinality, so the hook's runs reproduce). A proposed value displaces a
    stated one only when its advantage leads by more than the margin; proposed values alone keep a leader by more
    than the margin, else none (an abstention, every one fails). Relations and inactive claims get None."""
    groups: dict[tuple, list[int]] = {}
    for i, c in enumerate(todo):
        if active[i] and c.kind != "rel":
            groups.setdefault((c.s, c.p), []).append(i)
    out: list[dict | None] = [None] * len(todo)
    value = lambda c: (iso_time(c.o) or c.o) if c.lit else c.o  # noqa: E731
    for (s, p), idx in groups.items():
        spec = prop_spec(classes.get(s, set()), p)
        values = list(dict.fromkeys(value(todo[i]) for i in idx))
        if not spec:
            for i in idx:
                out[i] = {"result": "skip", "reason": f"{p} is not a core CASE/UCO property"}
            continue
        if spec["many"]:
            for i in idx:
                out[i] = {"result": "pass", "reason": f"{p} takes zero or more values"}
            continue
        if len(values) == 1:
            for i in idx:
                out[i] = {"result": "pass", "reason": f"{p} takes at most one value; one here"}
            continue
        score = {i: advantage(rows[i]) for i in idx}
        stated = [i for i in idx if todo[i].origin == STATED]
        if stated:
            best_stated = max(stated, key=lambda i: score[i])
            challengers = [i for i in idx if i not in stated and score[i] - score[best_stated] > margin]
            winner = max(challengers, key=lambda i: score[i]) if challengers else best_stated
            how = "a proposed value leads the stated one by more than the margin" if challengers else \
                "kept the stated value that best outranks its readings"
        else:
            ranked = sorted(idx, key=lambda i: -score[i])
            winner = ranked[0] if len(ranked) < 2 or score[ranked[0]] - score[ranked[1]] > margin else None
            how = "kept the proposed value that leads by more than the margin" if winner is not None else \
                "no value leads by more than the margin: none kept"
        for i in idx:
            mine = winner is not None and value(todo[i]) == value(todo[winner])
            out[i] = {"result": "pass" if mine else "fail",
                      "reason": f"{p} takes at most one value; {len(values)} here, {how} "
                                f"({score[i]:.2f}{' against ' + format(score[winner], '.2f') if winner is not None and not mine else ''})"}
    return out


def readings_pass(led: Ledger, src: Source, verifier, margin: float, claims: list[Claim] | None = None,
                  on: str = "supported") -> None:
    todo = list(claims if claims is not None else led.stated())
    ents = named_entities(led)
    classes = classes_of(led)
    triples = [c.as_triple() for c in todo]
    rows = [row_of(c) for c in todo]
    header = [header_check(t, ents, src.headers) for t in triples]
    active = [on == "all" or any(e["label"] == "supports" and e["method"] == "nli" for e in c.evidence) for c in todo]
    need = [i for i in range(len(todo)) if active[i] and header[i]["result"] == "skip"]
    contrast_scores([rows[i] for i in need], [triples[i] for i in need], ents, classes, verifier)
    card = cardinality(todo, rows, classes, active, margin)
    for i, (c, t, r) in enumerate(zip(todo, triples, rows)):
        if not active[i]:
            continue
        checks = schema_checks(t, classes)
        if card[i]:
            checks["cardinality"] = card[i]
        checks["header"] = header[i]
        if header[i]["result"] == "skip":
            result, alive = contrast_result(r, margin)
            checks["contrast"] = {**result, "near": near_miss(r.get("contrast"), margin), "alive": list(alive)}
        else:
            checks["contrast"] = {"result": "skip", "reason": "decided by the header rule", "near": False,
                                  "alive": list(range(len(r["passages"])))}
        c.checks = checks
        ctr = r.get("contrast")
        if ctr:
            c.competitors = [{"sentence": s, "passages": [{"passage": slot["passage"], "own": slot.get("own"),
                                                           "rival": (slot.get("rivals") or [None] * len(ctr["competitors"]))[k]}
                                                          for slot in ctr["passages"]]}
                             for k, s in enumerate(ctr["competitors"])]
