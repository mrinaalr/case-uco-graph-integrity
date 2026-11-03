"""Check hook.py --contrast: the hook without and with step 5, on the same graphs, at several margins.

Two samples, each reported separately:

- dev: data_dev gold graphs (every edge true) and hook_dev_check's corrupted copies (sender and first recipient
  swapped; sentTime, startTime and each relation kind's targets rotated). This sample is built from the errors
  contrast targets, so it favors it by design.
- real: the graphs an arm actually produced (results/SOURCE/ARM/), on the cases given. The edges the strict scorer
  labels wrong_relation or wrong_value are the test; the edges it matches to gold are the cost.

The hook runs once per arm, with --passages block --query plain --contrast. Steps 1 to 4 are the same with and
without --contrast, and each row records its passages' verdicts and its competitors' entailment on each supporting
passage, so the decision without step 5 and at every margin in --margins is recomputed here without rerunning the
model. Reported per margin: true edges kept, false edges removed
(by error class and property), and kept true edges citing their gold sentence.

    python harness/hook_contrast_check.py --run-id RUN --sample dev [--cases case_01,...] [--template full|labels|plain]
    python harness/hook_contrast_check.py --run-id RUN --sample real --source results/hook-v1 --arms a_sdk_agent,b_control
        --cases case_02,case_12 [--margins 0.1,0.2,0.3,0.5]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from graphkit import HARNESS, REPO
from hook_dev_check import stage
from score import norm_text, score_case

FLAGS = ["--passages", "block", "--query", "plain"]
def suffix(template: str) -> str:
    return f"+hook{'' if template == 'full' else '_' + template}_block_qplain_contrast"
TARGET = ("wrong_relation", "wrong_value")


def decide(row: dict, margin: float | None) -> dict | None:
    """The passage a row cites at this margin (None: removed). margin None is the hook without step 5."""
    support = [(i, p) for i, p in enumerate(row["passages"]) if p["verdict"] == "supported"]
    if margin is not None:
        best = Counter()
        for c in row.get("contrast", []):
            best[c["passage"]] = max(best[c["passage"]], c["entailment"])
        support = [(i, p) for i, p in support if best[i] - p["entailment"] <= margin]
    return max((p for _, p in support), key=lambda p: p["entailment"], default=None)


def evaluate(data: Path, graph: Path, rows: list[dict], margins: list[float | None]) -> dict[float | None, Counter]:
    scored = score_case(data, graph)
    true = {(s, p, o): tid for s, p, o, tid in scored["matched"]}
    false = {(u["s"], u["p"], u["o"]): u["class"] for u in scored["unsupported"]}
    spans = json.loads((data / "spans.json").read_text())
    span_of = {t["tid"]: spans[t["span_id"]] for t in json.loads((data / "gold.json").read_text())["triples"]}
    out = {m: Counter() for m in margins}
    for r in rows:
        key = (r["s"], r["p"], r["o"])
        for m in margins:
            cited, c = decide(r, m), out[m]
            if key in true:
                span = span_of[true[key]]
                c["true"] += 1
                c["true kept"] += cited is not None
                c["cited correct"] += bool(cited) and cited["doc"] == span["doc_id"] and \
                    norm_text(span["text"]) in norm_text(cited["text"])
            elif key in false:
                cls = false[key] if false[key] in TARGET else "other"
                c[f"{cls}"] += 1
                c[f"{cls} removed"] += cited is None
                if cls in TARGET:
                    c[f"{cls}|{r['p']}"] += 1
                    c[f"{cls}|{r['p']} removed"] += cited is None
    return out


def report(name: str, totals: dict[float | None, Counter]) -> None:
    print(f"\n{name}")
    print("  margin | true kept | cited correct | wrong_relation removed | wrong_value removed | other false removed")
    for m, c in totals.items():
        pct = lambda a, b: f"{c[a]}/{c[b]} = {c[a] / c[b]:.1%}" if c[b] else "0/0"
        print(f"  {'no contrast' if m is None else m:>11} | {pct('true kept', 'true')} | {pct('cited correct', 'true kept')} | "
              f"{pct('wrong_relation removed', 'wrong_relation')} | {pct('wrong_value removed', 'wrong_value')} | "
              f"{pct('other removed', 'other')}")
    for m, c in totals.items():
        props = sorted(k for k in c if "|" in k and not k.endswith(" removed"))
        print(f"  by property at {'no contrast' if m is None else m}: " +
              ", ".join(f"{k} {c[k + ' removed']}/{c[k]}" for k in props))


def run_hook(run_id: str, arm: str, data: str, cases: str, template: str) -> None:
    subprocess.run([str(REPO / ".venv" / "bin" / "python"), str(HARNESS / "hook.py"), "--run-id", run_id, "--arm", arm,
                    "--data", data, "--cases", cases, "--template", template, *FLAGS, "--contrast"],
                   check=True, capture_output=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--sample", choices=("dev", "real"), required=True)
    ap.add_argument("--cases", default=",".join(f"case_{i:02d}" for i in range(1, 6)))
    ap.add_argument("--source", type=Path, help="real: the run folder whose arm graphs are checked")
    ap.add_argument("--arms", default="a_sdk_agent,b_control")
    ap.add_argument("--margins", default="0.1,0.2,0.3,0.5")
    ap.add_argument("--template", default="full", choices=("full", "labels", "plain"))
    ap.add_argument("--no-run", action="store_true", help="report from the hook rows already written")
    args = ap.parse_args()
    cases, root = args.cases.split(","), HARNESS / "results" / args.run_id
    data = "data_dev" if args.sample == "dev" else "data"
    arms = ["gold", "corrupt"] if args.sample == "dev" else args.arms.split(",")
    if not args.no_run:
        if args.sample == "dev":
            stage(root, cases)
        else:
            shutil.rmtree(root, ignore_errors=True)
            for arm in arms:
                for case in cases:
                    src = args.source / arm / case
                    if (src / "graph.jsonld").exists():
                        (root / arm / case).mkdir(parents=True)
                        for f in ("graph.jsonld", "run.json"):
                            shutil.copy(src / f, root / arm / case / f)
        for arm in arms:
            run_hook(args.run_id, arm, data, args.cases, args.template)
    margins = [None, *map(float, args.margins.split(","))]
    for arm in arms:
        totals = {m: Counter() for m in margins}
        for case in cases:
            graph = root / arm / case / "graph.jsonld"
            hooked = root / f"{arm}{suffix(args.template)}" / case / "hook.jsonl"
            if not hooked.exists():
                continue
            rows = [json.loads(x) for x in hooked.read_text().splitlines()]
            for m, c in evaluate(HARNESS / data / case, graph, rows, margins).items():
                totals[m].update(c)
        report(f"{args.sample} {arm}, template {args.template}: {len(cases)} cases", totals)


if __name__ == "__main__":
    main()
