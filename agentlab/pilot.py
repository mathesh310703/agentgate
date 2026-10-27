"""Pilot mode for experiments: run 5 trials, print cost and results, and stop unless --full.

Usage inside an experiment script:

    ap = argparse.ArgumentParser(); add_pilot_args(ap); a = ap.parse_args()
    results = run_trials(trials, run_one, full=a.full, name="baseline")

`run_one(trial)` must return a dict of results (e.g. {"task_ok": True}); it is printed per trial.
"""

from __future__ import annotations

import argparse
from typing import Callable, List, Sequence

from agentlab.llm import spend_by_stage, total_spent

PILOT_TRIALS = 5


def add_pilot_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--full", action="store_true", help=f"run all trials (default: {PILOT_TRIALS}-trial pilot)")


def run_trials(trials: Sequence, run_one: Callable[[object], dict], full: bool = False,
               name: str = "experiment") -> List[dict]:
    todo = list(trials) if full else list(trials)[:PILOT_TRIALS]
    mode = "FULL" if full else f"PILOT ({len(todo)} of {len(trials)} trials)"
    print(f"== {name}: {mode}")
    start = total_spent()
    results = []
    for i, t in enumerate(todo):
        before = total_spent()
        res = run_one(t)
        results.append(res)
        print(f"[{i + 1}/{len(todo)}] {t}: {res}  cost ${total_spent() - before:.4f}")
    spent = total_spent() - start
    print(f"== {name}: {len(todo)} trials, cost ${spent:.4f}"
          + (f" (~${spent / max(len(todo), 1) * len(trials):.2f} projected for all {len(trials)})" if not full else ""))
    print(f"   spend by stage: { {k: round(v, 4) for k, v in spend_by_stage().items()} }")
    if not full and len(trials) > len(todo):
        print("   pilot only. Re-run with --full to run the full set.")
    return results
