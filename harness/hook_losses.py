"""Why the hook removed true edges, for every arm and template of a run.

A true edge is one the strict scorer matches to a gold triple in the graph the hook read (score.json "matched").
Each removed true edge lands in one bucket, checked in this order:

- multiline: its gold sentence is a mail header line (From:, To:, Cc:, Subject:, Date:) or a chat message line
  ("[time] @a to @b: ..."), so the fact's subject is named on another line;
- not_retrieved: its gold sentence is not among the passages the hook retrieved;
- nli_rejected: its gold sentence was retrieved and the NLI model did not say supported.

A passage is the gold sentence when it is in the same document and one text contains the other (the scorer's
citation rule). Also reports how often two templates retrieved the same top passages for an edge.

    python harness/hook_losses.py --run-id hook-v1 [--results harness/results]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from graphkit import HARNESS
from score import norm_text

MULTILINE = re.compile(r"^(From|To|Cc|Subject|Date):|^\[")
BUCKETS = ("not_retrieved", "nli_rejected", "multiline")


def is_gold(passage: dict, span: dict) -> bool:
    a, b = norm_text(passage["text"]), norm_text(span["text"])
    return passage["doc"] == span["doc_id"] and (a in b or b in a)


def edge_key(row: dict) -> tuple:
    return row["s"], row["p"], row["o"], row["origin"]  # row order differs between hook processes


def report(run_dir: Path, data: str) -> None:
    arms = sorted({p.name.split("+hook")[0] for p in run_dir.iterdir() if p.is_dir() and "+hook" in p.name})
    for arm in arms:
        templates = sorted(p.name[len(arm):] for p in run_dir.iterdir() if p.is_dir() and p.name.startswith(arm + "+hook"))
        buckets = {t: Counter() for t in templates}
        props = {t: defaultdict(Counter) for t in templates}
        overlap = defaultdict(Counter)
        for case_dir in sorted(p for p in (run_dir / arm).iterdir() if p.is_dir()):
            score = case_dir / "score.json"
            if not score.exists():
                continue
            tid_of = {(s, p, o): tid for s, p, o, tid in json.loads(score.read_text()).get("matched", [])}
            gold_dir = HARNESS / data / case_dir.name
            spans = json.loads((gold_dir / "spans.json").read_text())
            span_of = {t["tid"]: spans[t["span_id"]] for t in json.loads((gold_dir / "gold.json").read_text())["triples"]}
            rows = {}
            for t in templates:
                path = run_dir / f"{arm}{t}" / case_dir.name / "hook.jsonl"
                rows[t] = {edge_key(r): r for r in map(json.loads, path.read_text().splitlines())} if path.exists() else {}
            for i, x in enumerate(templates):
                for y in templates[i + 1:]:
                    for k in rows[x].keys() & rows[y].keys():
                        tops = [{(p["doc"], p["sentence"]) for p in rows[t][k]["passages"]} for t in (x, y)]
                        overlap[(x, y)]["edges"] += 1
                        overlap[(x, y)]["identical"] += tops[0] == tops[1]
                        overlap[(x, y)]["shared"] += len(tops[0] & tops[1])
            for t in templates:
                for r in rows[t].values():
                    tid = tid_of.get((r["s"], r["p"], r["o"]))
                    if tid is None or r["kept"]:
                        continue
                    span = span_of[tid]
                    bucket = "multiline" if MULTILINE.match(span["text"]) else \
                        "nli_rejected" if any(is_gold(p, span) for p in r["passages"]) else "not_retrieved"
                    buckets[t][bucket] += 1
                    props[t][bucket][r["p"]] += 1
        print(f"\n{arm}")
        for t in templates:
            n = sum(buckets[t].values())
            print(f"  {arm}{t}: true edges removed {n}")
            for b in BUCKETS:
                top = ", ".join(f"{p} {v}" for p, v in props[t][b].most_common(4))
                print(f"    {b}: {buckets[t][b]} ({buckets[t][b] / n:.0%}) | {top}" if n else f"    {b}: 0")
        for (x, y), c in overlap.items():
            print(f"  top passages {arm}{x} vs {arm}{y}: identical {c['identical'] / c['edges']:.1%}, "
                  f"mean shared {c['shared'] / c['edges']:.2f}, over {c['edges']} edges")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--results", default=str(HARNESS / "results"), help="folder holding the run (default: harness/results)")
    ap.add_argument("--data", default="data", help="gold folder the run's cases come from")
    args = ap.parse_args()
    report(Path(args.results) / args.run_id, args.data)


if __name__ == "__main__":
    main()
