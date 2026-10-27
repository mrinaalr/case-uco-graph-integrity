"""What each critic revision fixed and broke, for the A1+QA arm.

Reads the per-pass scores score.py wrote for results/RUN/a1_critic/<case>/ and the pass log in
run.json, and compares consecutive passes: a gold triple that was missed before a revision and
supported after it is "fixed"; the reverse is "regressed". Unsupported emitted triples are
compared by error class. Each revision is attributed to the finding rules the model was asked to
address. Writes results/RUN/qa_delta.md and qa_delta.csv.

    python harness/qa_delta.py --run-id RUN
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from graphkit import HARNESS
from score import CLASSES, SCORERS, load_gold, mean, table

ARM = "a1_critic"


def pass_scores(run_dir: Path, scorer: str) -> list[tuple[int, dict]]:
    suffix = ".json" if scorer == "strict" else "_value.json"
    found = []
    for p in run_dir.glob(f"score_pass*{suffix}"):
        stem = p.name[len("score_pass"):-len(suffix)]
        if stem.isdigit():
            found.append((int(stem), json.loads(p.read_text())))
    return sorted(found)


def transitions(run_id: str) -> tuple[list[dict], dict[str, list[dict]]]:
    root = HARNESS / "results" / run_id / ARM
    rows, cases = [], {}
    for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        meta = json.loads((run_dir / "run.json").read_text())
        gold = load_gold(HARNESS / "data" / run_dir.name)
        all_tids = {t["tid"] for t in gold["triples"].values()}
        passes = {p["pass"]: p for p in meta.get("passes", [])}
        for scorer in SCORERS:
            scores = pass_scores(run_dir, scorer)
            cases.setdefault(scorer, []).append({"case_id": run_dir.name, "status": meta["status"],
                                                 "passes": len(scores), "final_outcome": meta.get("final_outcome"),
                                                 "trajectory": [(n, s.get("precision"), s.get("recall")) for n, s in scores]})
            for (n, before), (m, after) in zip(scores, scores[1:]):
                sup_b = all_tids - set(before.get("missed", [])) if before.get("emitted_triples") else set()
                sup_a = all_tids - set(after.get("missed", [])) if after.get("emitted_triples") else set()
                cls_b = Counter(before.get("unsupported_by_class", {}))
                cls_a = Counter(after.get("unsupported_by_class", {}))
                info = passes.get(n, {})
                rows.append({"scorer": scorer, "case_id": run_dir.name, "revision": f"{n}->{m}",
                             "addressed_rules": " ".join(info.get("addressed_rules", [])),
                             "fix_attempts": len(info.get("fix_attempts", [])),
                             "fixed": len(sup_a - sup_b), "regressed": len(sup_b - sup_a),
                             "recall_before": before.get("recall"), "recall_after": after.get("recall"),
                             "precision_before": before.get("precision"), "precision_after": after.get("precision"),
                             "conforms_before": info.get("conforms"), "conforms_after": passes.get(m, {}).get("conforms"),
                             **{f"d_{c}": cls_a.get(c, 0) - cls_b.get(c, 0) for c in CLASSES}})
        # a revision that never produced a graph is a QA outcome too: record it against the last pass
        for n, info in passes.items():
            rev = info.get("revision")
            if rev and rev != "ok":
                for scorer in SCORERS:
                    rows.append({"scorer": scorer, "case_id": run_dir.name, "revision": f"{n}->failed",
                                 "addressed_rules": " ".join(info.get("addressed_rules", [])),
                                 "fix_attempts": len(info.get("fix_attempts", [])), "fixed": 0, "regressed": 0,
                                 "recall_before": None, "recall_after": None, "precision_before": None,
                                 "precision_after": None, "conforms_before": info.get("conforms"), "conforms_after": None,
                                 **{f"d_{c}": 0 for c in CLASSES}, "failure": rev[:120]})
    return rows, cases


def markdown(run_id: str, rows: list[dict], cases: dict[str, list[dict]]) -> str:
    lines = [f"# QA adjustments: {run_id}\n",
             "Each row compares the graph before and after one serializer revision made in answer to the "
             "critic's findings. `fixed` and `regressed` count gold triples; `d_<class>` is the change in "
             "unsupported emitted triples of that class.\n"]
    for scorer in SCORERS:
        sub = [r for r in rows if r["scorer"] == scorer]
        ran = [r for r in sub if not r["revision"].endswith("failed")]
        failed = [r for r in sub if r["revision"].endswith("failed")]
        lines.append(f"\n## {scorer} scorer\n")
        lines.append(f"- revisions that produced a graph: {len(ran)}; revisions whose serializer crashed even after "
                     f"fix attempts: {len(failed)}")
        if ran:
            lines.append(f"- gold triples fixed: {sum(r['fixed'] for r in ran)}, regressed: {sum(r['regressed'] for r in ran)}; "
                         f"mean recall {mean([r['recall_before'] for r in ran]):.3f} -> {mean([r['recall_after'] for r in ran]):.3f}, "
                         f"mean precision {mean([r['precision_before'] for r in ran if r['precision_before'] is not None]):.3f} -> "
                         f"{mean([r['precision_after'] for r in ran if r['precision_after'] is not None]):.3f}")
            lines.append(f"- validity (SHACL conforms) before -> after: "
                         f"{sum(1 for r in ran if r['conforms_before'])}/{len(ran)} -> {sum(1 for r in ran if r['conforms_after'])}/{len(ran)}")
            deltas = Counter()
            for r in ran:
                for c in CLASSES:
                    deltas[c] += r[f"d_{c}"]
            lines.append("- unsupported triples by class, net change: " + ", ".join(f"{c} {deltas[c]:+d}" for c in CLASSES))
            lines.append("\n### Per rule addressed (a revision counts toward every rule it answered)\n")
            per_rule: dict[str, Counter] = defaultdict(Counter)
            for r in ran:
                for rule in r["addressed_rules"].split():
                    per_rule[rule].update(revisions=1, fixed=r["fixed"], regressed=r["regressed"],
                                          invented=r["d_invented"], wrong_relation=r["d_wrong_relation"],
                                          wrong_value=r["d_wrong_value"])
            lines += table(["rule", "revisions", "fixed", "regressed", "d_invented", "d_wrong_relation", "d_wrong_value"],
                           [[k, v["revisions"], v["fixed"], v["regressed"], v["invented"], v["wrong_relation"], v["wrong_value"]]
                            for k, v in sorted(per_rule.items())])
        lines.append("\n### Trajectory per case (pass: precision / recall)\n")
        lines += table(["case", "status", "final outcome", "passes"],
                       [[c["case_id"], c["status"], c["final_outcome"],
                         "; ".join(f"p{n}: {p if p is None else round(p, 2)} / {round(r, 2)}" for n, p, r in c["trajectory"])]
                        for c in cases.get(scorer, [])])
        if failed:
            lines.append("\n### Failed revisions\n")
            lines += [f"- {r['case_id']} {r['revision']} after {r['fix_attempts']} fix attempt(s): {r.get('failure')}" for r in failed]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    rows, cases = transitions(args.run_id)
    root = HARNESS / "results" / args.run_id
    if rows:
        with open(root / "qa_delta.csv", "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r}))
            writer.writeheader()
            writer.writerows(rows)
    (root / "qa_delta.md").write_text(markdown(args.run_id, rows, cases))
    print((root / "qa_delta.md").read_text())


if __name__ == "__main__":
    main()
