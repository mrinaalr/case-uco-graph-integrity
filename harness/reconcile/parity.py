"""Does the reconciler, decided from the ledger, keep the edges the hook kept? Compares results/RUN/<arm>+<suffix>/
(the reconciler's output) with results/RUN/<ref>/ (a hook run: hook.jsonl, one row per edge with `kept`), edge by
edge, and reports agreement per case and in total. Run the reconciler first:

    python harness/reconcile/run.py --run-id hook-v1 --arm b_control --suffix rec-hookv1 --policy hook-v1 \
        --passes verify --template full --passages sentence --query rendered --cases case_01,...
    python harness/reconcile/parity.py --run-id hook-v1 --arm b_control --suffix rec-hookv1 --ref b_control+hook

Differences are listed with both sides' best passage and entailment, so a disagreement from a device's last-digit
difference in a probability can be told from a change in logic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphkit import HARNESS
from reconcile.ledger import Ledger
from reconcile.policy import POLICIES


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--suffix", required=True)
    ap.add_argument("--ref", required=True, help="the hook's arm folder, e.g. b_control+hook or gold+lr")
    ap.add_argument("--policy", default=None, help="which policy's removal set to apply (default: the run's)")
    args = ap.parse_args()
    root = HARNESS / "results" / args.run_id
    total = {"edges": 0, "agree": 0, "rec_only": 0, "hook_only": 0, "cases": 0}
    diffs = []
    for case in sorted((root / f"{args.arm}+{args.suffix}").glob("case_*")):
        ref = root / args.ref / case.name / "hook.jsonl"
        if not ref.exists() or not (case / "ledger").exists():
            continue
        led = Ledger.read(case / "ledger")
        policy = args.policy or json.loads((case / "run.json").read_text()).get("policy", "hook-v1")
        gone = POLICIES[policy]["remove"]
        mine = {c.key: c for c in led.stated()}
        kept_mine = {k for k, c in mine.items() if c.status not in gone}
        theirs, kept_theirs = {}, set()
        for line in ref.read_text().splitlines():
            r = json.loads(line)
            k = (r["s"], r["p"], r["o"], r["lit"])
            theirs[k] = r
            if r["kept"]:
                kept_theirs.add(k)
        keys = set(mine) | set(theirs)
        agree = sum((k in kept_mine) == (k in kept_theirs) for k in keys)
        total["edges"] += len(keys)
        total["agree"] += agree
        total["rec_only"] += len(kept_mine - kept_theirs)
        total["hook_only"] += len(kept_theirs - kept_mine)
        total["cases"] += 1
        for k in sorted(kept_mine ^ kept_theirs):
            c, r = mine.get(k), theirs.get(k)
            mb = max((e["score"] for e in c.evidence if e["method"] == "nli"), default=None) if c else None
            tb = max((p["entailment"] for p in r["passages"]), default=None) if r else None
            diffs.append(f"{case.name} {'rec' if k in kept_mine else 'hook'} kept only: {k[1]} {k[2][:40]!r} "
                         f"rec best={mb} hook best={tb} rec={c.status if c else None}")
    print(json.dumps(total))
    print(f"agreement {total['agree']}/{total['edges']} = {total['agree'] / max(total['edges'], 1):.4f} over {total['cases']} cases")
    for d in diffs[:60]:
        print(" ", d)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
