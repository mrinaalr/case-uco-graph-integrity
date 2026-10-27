"""How many unsupported triples a deterministic source-fidelity rule could have flagged.

For every arm of a scored run, each unsupported triple (value scorer) is tested against the
candidate rules proposed in findings/critic-source-fidelity-unassessed.md, using only what a
critic rule would have: the graph, the source documents, and (for the vocabulary rule) the task's
relation list. Writes results/RUN/rule_coverage.md.

    python harness/rule_coverage.py --run-id RUN
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from graphkit import HARNESS, RELATION_KINDS, graph_triples
from score import TIME_PROPS, norm, norm_kind, norm_text, table

RULES = ["F-LITERAL-NOT-IN-SOURCE", "F-TYPED-VALUE-UNDER-NAME", "F-CROSS-DOCUMENT-LINK", "F-DUPLICATE-KEY",
         "F-UNANCHORED-ENTITY", "F-KIND-OUTSIDE-TASK-VOCAB"]
# A value with the shape of a typed facet property (email address, account number, street address) stored
# under the generic uco-core:name instead of the facet property that carries it.
TYPED_VALUE = re.compile(r"^(?:[\w.+-]+@[\w-]+\.[\w.-]+|\d{6,}|\d+\s+\w.*\b(?:street|st|avenue|ave|road|rd|boulevard|"
                         r"blvd|lane|ln|drive|dr|way|court|ct|place|pl)\b.*)$", re.I)
VOCAB = {norm_kind(k) for k in RELATION_KINDS}


def source_text(case_dir: Path) -> tuple[str, str]:
    text = "\n".join(p.read_text() for p in sorted((case_dir / "docs").glob("D*.txt")))
    return norm_text(text), norm("name", text)


def rules_hit(u: dict, lit_keys: set, rel_keys: set, docs: tuple[str, str]) -> list[str]:
    hits = []
    is_lit = (u["s"], u["o"]) in lit_keys
    if is_lit and u["p"] not in TIME_PROPS:
        target = norm(u["p"], u["o"])
        if target and target not in docs[0] and target not in docs[1]:
            hits.append("F-LITERAL-NOT-IN-SOURCE")
    if is_lit and u["p"] == "name" and TYPED_VALUE.match(u["o"].strip()):
        hits.append("F-TYPED-VALUE-UNDER-NAME")
    if u["class"] == "cross_document_conflation":
        hits.append("F-CROSS-DOCUMENT-LINK")
    if u["class"] == "duplicate_entity":
        hits.append("F-DUPLICATE-KEY")
    if u.get("aligned_s") is None or (not is_lit and u.get("aligned_o") is None):
        hits.append("F-UNANCHORED-ENTITY")
    if (u["s"], u["o"]) in rel_keys and u["p"] not in VOCAB:
        hits.append("F-KIND-OUTSIDE-TASK-VOCAB")
    return hits


def coverage(run_id: str) -> tuple[list[dict], dict[str, Counter]]:
    root = HARNESS / "results" / run_id
    rows, by_class = [], {}
    for arm_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        totals, any_hit, first_hit, time_lits = Counter(), 0, Counter(), 0
        n_unsupported = 0
        cls_hit: dict[str, Counter] = {}
        for run_dir in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            score_path, graph_path = run_dir / "score_value.json", run_dir / "graph.jsonld"
            if not score_path.exists() or not graph_path.exists():
                continue
            score = json.loads(score_path.read_text())
            if not score.get("unsupported"):
                continue
            try:
                _, raw = graph_triples(graph_path)
            except Exception:  # noqa: BLE001  unparseable graphs were already scored as failures
                continue
            lit_keys = {(t["s"], t["o"]) for t in raw if t["lit"]}
            rel_keys = {(t["s"], t["o"]) for t in raw if t["origin"].startswith("rel|")}
            rel_keys |= {(o, s) for s, o in rel_keys}  # the value scorer may have flipped symmetric kinds
            docs = source_text(HARNESS / "data" / run_dir.name)
            for u in score["unsupported"]:
                n_unsupported += 1
                if (u["s"], u["o"]) in lit_keys and u["p"] in TIME_PROPS:
                    time_lits += 1
                hits = rules_hit(u, lit_keys, rel_keys, docs)
                totals.update(hits)
                cls_hit.setdefault(u["class"], Counter()).update({"total": 1, "caught": bool(hits)})
                if hits:
                    any_hit += 1
                    first_hit[hits[0]] += 1
        if n_unsupported:
            rows.append({"arm": arm_dir.name, "unsupported": n_unsupported, "caught_by_any": any_hit,
                         "caught_rate": round(any_hit / n_unsupported, 3), "time_literals_unchecked": time_lits,
                         **{r: totals[r] for r in RULES}})
            by_class[arm_dir.name] = cls_hit
    return rows, by_class


def markdown(run_id: str, rows: list[dict], by_class: dict) -> str:
    lines = [f"# Candidate source-fidelity rules against {run_id} (value scorer, final graphs)\n",
             "Each unsupported triple is tested against the rules proposed in "
             "findings/critic-source-fidelity-unassessed.md, using only the graph, the source documents and the "
             "task's relation list. A triple can hit several rules; `caught_by_any` counts it once. Date and time "
             "literals are not checked by the literal rule here (`time_literals_unchecked`).\n"]
    lines += table(["arm", "unsupported", "caught_by_any", "caught_rate", "time_literals_unchecked"] + RULES,
                   [[r["arm"], r["unsupported"], r["caught_by_any"], r["caught_rate"], r["time_literals_unchecked"]]
                    + [r[k] for k in RULES] for r in rows])
    lines.append("\n## By error class: unsupported triples caught by at least one rule\n")
    classes = sorted({c for d in by_class.values() for c in d})
    lines += table(["arm"] + classes, [[arm] + [f"{d.get(c, {}).get('caught', 0)}/{d.get(c, {}).get('total', 0)}"
                                                for c in classes] for arm, d in by_class.items()])
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    rows, by_class = coverage(args.run_id)
    out = HARNESS / "results" / args.run_id / "rule_coverage.md"
    out.write_text(markdown(args.run_id, rows, by_class))
    print(out.read_text())


if __name__ == "__main__":
    main()
