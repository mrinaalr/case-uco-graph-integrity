"""The reconciliation layer (harness/reconcile/) depends on no construction arm and reads no gold: it must work on a
graph nobody in this repo built. Checked on the import graph and on the source text, not at run time."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1]
RECONCILE = HARNESS / "reconcile"
ARMS = re.compile(r"^pipeline_\w+$")
GOLD = re.compile(r"gold\.jsonl?d?\b|spans\.json|\.marked\.txt")


def modules() -> list[Path]:
    if not RECONCILE.exists():
        pytest.skip("harness/reconcile/ is not there yet")
    return sorted(RECONCILE.rglob("*.py"))


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def closure(path: Path, seen: set[str] | None = None) -> set[str]:
    """Harness modules reachable from path, through harness modules only."""
    seen = seen if seen is not None else set()
    for name in imports_of(path):
        if name in seen:
            continue
        target = HARNESS / f"{name}.py"
        if target.exists():
            seen.add(name)
            closure(target, seen)
        elif (RECONCILE / f"{name.replace('reconcile', '').strip('.')}.py").exists():
            seen.add(name)
    return seen


def test_reconcile_imports_no_construction_arm():
    for m in modules():
        reached = {name for name in closure(m) if ARMS.match(name)}
        assert not reached, f"{m.relative_to(HARNESS)} reaches {sorted(reached)}"


def test_reconcile_names_no_gold_file():
    for m in modules():
        for i, line in enumerate(m.read_text().splitlines(), 1):
            assert not GOLD.search(line), f"{m.relative_to(HARNESS)}:{i}: {line.strip()}"
