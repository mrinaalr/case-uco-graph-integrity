"""List every unsupported edge under the value scorer, grouped by arm and label.

Reads the score_value.json files that score.py wrote (final graphs only; A2's
first-validation snapshot is not listed) and writes
results/<run_id>/unsupported_edges_value.md with, for each edge: case, emitted
triple, the closest gold triple, its source sentence, and the model's citation.

    python harness/edges.py --run-id RUN
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict

from graphkit import HARNESS
from score import CLASSES, norm, norm_kind, value_matches

ARMS = ("b_control", "a1_script", "a2_tools")
UUID_TAIL = re.compile(r"-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def local(x) -> str:
    x = str(x)
    return UUID_TAIL.sub("", x.split("/kb/")[-1] if "/kb/" in x else x)


def kind(p: str) -> str:
    return norm_kind(p) if p[0].isupper() else p


def closest(u: dict, gold: list[dict]) -> dict | None:
    lit = not str(u["o"]).startswith("http")
    p, s, o, label = kind(u["p"]), u["aligned_s"], u["aligned_o"], u["class"]
    g = [(t, kind(t["p"]), norm(t["p"], t["o"]) if t["lit"] else t["o"]) for t in gold]
    if label == "misplaced_property":
        c = [t for t, gp, go in g if t["s"] == s and t["lit"] and gp != p and value_matches(gp, go, u["o"])]
    elif label == "wrong_value":
        c = [t for t, gp, _ in g if t["s"] == s and gp == p]
    elif label == "wrong_relation":
        c = [t for t, _, go in g if {t["s"], go} == {s, o}]
    elif label in ("wrong_entity", "cross_document_conflation"):
        ov = norm(u["p"], u["o"]) if lit else o
        c = [t for t, gp, go in g if gp == p and (go == ov or (t["s"] == s and not lit))]
    elif lit:
        c = [t for t, _, go in g if t["lit"] and value_matches(t["p"], go, u["o"])]
    else:
        c = [t for t, _, go in g if s and o and {t["s"], go} == {s, o}]
    return c[0] if c else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    root = HARNESS / "results" / ap.parse_args().run_id
    lines = [f"# Unsupported edges under the value scorer: {root.name}", "",
             "Final graphs for b_control, a1_script and a2_tools; a2_tools@first_validate is not listed.", "",
             "Format: case | emitted (s, p, o) | closest gold triple [tid] | source sentence [span] | model citation", ""]
    for arm in ARMS:
        by = defaultdict(list)
        for f in sorted((root / arm).glob("case_*/score_value.json")):
            r, case = json.loads(f.read_text()), f.parent.name
            if r["status"] in ("error", "empty"):
                by["run failed"].append(f"- {case} | run {r['status']}: {str(r.get('error', ''))[:110]}")
                continue
            gold = json.loads((HARNESS / "data" / case / "gold.json").read_text())["triples"]
            spans = json.loads((HARNESS / "data" / case / "spans.json").read_text())
            for u in r["unsupported"]:
                t = closest(u, gold)
                gt = f"({t['s']}, {t['p']}, {t['o']}) [{t['tid']}]" if t else "-"
                src = f"\"{spans[t['span_id']]['text']}\" [{t['span_id']}]" if t else "-"
                cite = ", ".join(u.get("cited_spans") or []) or "-"
                by[u["class"]].append(f"- {case} | ({local(u['s'])}, {u['p']}, {local(u['o'])[:70]}) | {gt} | {src} | {cite}")
        n = sum(len(v) for k, v in by.items() if k != "run failed")
        lines += [f"## {arm} ({n} edges)", ""]
        for label in CLASSES + ["run failed"]:
            if by.get(label):
                lines += [f"### {label} ({len(by[label])})" if label != "run failed" else "### run failed", ""]
                lines += by[label] + [""]
    out = root / "unsupported_edges_value.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
