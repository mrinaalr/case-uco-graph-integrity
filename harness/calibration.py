"""Are the reconciler's verdicts right? For each `<arm>+<suffix>` folder of a scored run, every stated claim's verdict
(supported, contradicted, ambiguous, insufficient, malformed) is set against whether the strict scorer matched the
edge to gold in the graph the reconciler read (score.json of `<arm>`: `matched`), and every added claim's against
whether it is matched in the graph the reconciler wrote. Writes results/RUN/calibration.md: one confusion table per
arm, so "contradicted" can be read as a precision ("how often a claim we called contradicted was false") and
"insufficient" as what it is, unverified, not false. Evaluator side: reads score.py's output, never the ledger's
evidence, and nothing here feeds back into a decision.

    python harness/calibration.py --run-id RUN [--suffix rec]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from graphkit import HARNESS  # noqa: E402

VERDICTS = ("supported", "ambiguous", "insufficient", "contradicted", "malformed")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def table(counts: dict, title: str) -> list[str]:
    lines = [f"### {title}", "", "| verdict | true edges | false edges | share false |", "|---|---|---|---|"]
    for v in VERDICTS:
        t, f = counts[v]["true"], counts[v]["false"]
        lines.append(f"| {v} | {t} | {f} | {f / (t + f):.3f} |" if t + f else f"| {v} | 0 | 0 | - |")
    return lines + [""]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--suffix", default="rec")
    args = ap.parse_args()
    root = HARNESS / "results" / args.run_id
    out = [f"# Calibration: {args.run_id}", "",
           "Each stated claim's verdict against the strict scorer's match of that edge in the graph the reconciler read; "
           "each added claim's against its match in the graph it wrote. A verdict's `share false` is how often it was "
           "given to an edge gold does not support.", ""]
    for arm_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.endswith(f"+{args.suffix}")):
        base = arm_dir.name[: -len(args.suffix) - 1]
        stated = {v: Counter() for v in VERDICTS}
        added = {v: Counter() for v in VERDICTS}
        removed_true, removed_false, cases = 0, 0, 0
        for case in sorted(arm_dir.glob("case_*")):
            score_in, score_out = root / base / case.name / "score.json", case / "score.json"
            if not (case / "ledger" / "claims.jsonl").exists() or not score_in.exists():
                continue
            cases += 1
            true_in = {(m[0], m[1], m[2]) for m in json.loads(score_in.read_text()).get("matched", [])}
            true_out = {(m[0], m[1], m[2]) for m in json.loads(score_out.read_text()).get("matched", [])} if score_out.exists() else set()
            members, cls_of = {}, {}
            for e in read_jsonl(case / "ledger" / "entities.jsonl"):
                cls_of[e["id"]] = e["cls"]
                for m in e["members"]:
                    members[m] = e["id"]
            true_in = {(members.get(s, s), p, members.get(o, o)) for s, p, o in true_in}
            policy = json.loads((case / "run.json").read_text()).get("policy", "conservative")
            from reconcile.keys import KEYS
            from reconcile.policy import POLICIES
            rules = POLICIES[policy]
            for c in read_jsonl(case / "ledger" / "claims.jsonl"):
                key = (c["s"], c["p"], c["o"])
                if c["origin"] == "stated":
                    truth = "true" if key in true_in else "false"
                    stated[c["status"]][truth] += 1
                    kept_key = rules["keep_keys"] and c["status"] == "insufficient" and c["lit"] and \
                        c["p"] in KEYS.get(cls_of.get(c["s"], ""), [])
                    if c["status"] in rules["remove"] and not kept_key:
                        removed_true += truth == "true"
                        removed_false += truth == "false"
                elif c["origin"] == "proposed" and c["status"] == "supported" and not (c.get("note") or "").startswith("dropped"):
                    added[c["status"]]["true" if key in true_out else "false"] += 1
        if not cases:
            continue
        out.append(f"## {arm_dir.name} ({cases} cases)")
        out.append("")
        out += table(stated, "stated claims")
        out.append(f"Removed: {removed_true} true edges, {removed_false} false edges.")
        out.append("")
        a = added["supported"]
        out.append(f"Added claims gold supports: {a['true']} of {a['true'] + a['false']}.")
        out.append("")
    (root / "calibration.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
