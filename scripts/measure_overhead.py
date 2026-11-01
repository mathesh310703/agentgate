"""Gate overhead per tool call, measured on the worst-case replay (no model calls), plus the intent judge's
latency and cost per call from the logs of the judged runs already made (no new calls). Prints JSON.

  .venv\\Scripts\\python scripts/measure_overhead.py

Two costs per tool call in the adapter (agentgate/adapters/agentdojo_adapter.py):
  check:  Gate.check on the call, before it runs (every call)
  record: Session.add_tool_output on the result, after an allowed call runs (splits it into labelled records)
Judge: runs/*/judge_log.jsonl (uncached calls), matched to eval/cost_log.csv rows by time and latency.
"""

import csv
import glob
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def stats(xs, scale=1e6, nd=1):
    xs = sorted(xs)
    q = lambda f: xs[min(len(xs) - 1, int(round(f * (len(xs) - 1))))]
    return {"n": len(xs), "median": round(statistics.median(xs) * scale, nd), "p95": round(q(0.95) * scale, nd),
            "p99": round(q(0.99) * scale, nd), "max": round(xs[-1] * scale, nd)}


def replay_overhead(suite_name):
    from agentdojo.agent_pipeline import AgentPipeline
    from agentdojo.attacks.attack_registry import load_attack
    from agentdojo.task_suite.load_suites import get_suite

    import run_suites
    from agentgate.session import Session

    record = []
    orig = Session.add_tool_output

    def timed(self, *a, **k):
        t0 = time.perf_counter()
        orig(self, *a, **k)
        record.append(time.perf_counter() - t0)

    Session.add_tool_output = timed
    try:
        suite = get_suite("v1.2.2", suite_name)
        named = AgentPipeline([])
        named.name = "vllm_parsed"
        attack = load_attack(run_suites.ATTACK, suite, named)
        pairs = [(u, i) for u in suite.user_tasks.values() for i in suite.injection_tasks.values()]
        policy = run_suites.policy_for("default", suite_name)
        t0 = time.perf_counter()
        _, checks = run_suites.run("gate", suite, attack, pairs, policy)
        wall = time.perf_counter() - t0
    finally:
        Session.add_tool_output = orig
    return {"pairs": len(pairs), "check_us": stats(checks), "record_us": stats(record),
            "replay_wall_s": round(wall, 1)}


def judge_overhead():
    log = [r for r in csv.DictReader(open(ROOT / "eval" / "cost_log.csv", encoding="utf-8")) if r["stage"] == "defense"]
    t = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    entries = []
    for p in glob.glob(str(ROOT / "runs" / "*" / "judge_log.jsonl")):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e.get("cached") is False:
                entries.append(e)
    used, matched = set(), []
    for e in sorted(entries, key=lambda e: e["time"]):
        t0 = t(e["time"])
        cands = [(abs((t(r["time"]) - t0).total_seconds()) + 5 * abs(float(r["latency_s"]) - e["latency_s"]), i)
                 for i, r in enumerate(log) if i not in used and -2 <= (t(r["time"]) - t0).total_seconds() <= e["latency_s"] + 5]
        if cands:
            i = min(cands)[1]
            used.add(i)
            matched.append((e, log[i]))
    return {"uncached_calls": len(entries), "matched_to_cost_log": len(matched),
            "max_latency_mismatch_s": round(max(abs(float(c["latency_s"]) - e["latency_s"]) for e, c in matched), 3),
            "latency_s": stats([e["latency_s"] for e in entries], 1, 2),
            "cost_usd": stats([float(c["cost_usd"]) for _, c in matched], 1, 6),
            "prompt_tokens_median": statistics.median(int(c["prompt_tokens"]) for _, c in matched),
            "completion_tokens_median": statistics.median(int(c["completion_tokens"]) for _, c in matched),
            "errors_denied": sum(bool(e["error"]) for e in entries),
            "cached_calls_latency_s_max": max((json.loads(l)["latency_s"] for p in glob.glob(str(ROOT / "runs" / "*" / "judge_log.jsonl"))
                                              for l in open(p, encoding="utf-8") if json.loads(l).get("cached")), default=None)}


if __name__ == "__main__":
    out = {s: replay_overhead(s) for s in ("workspace", "banking", "slack", "travel")}
    out["judge"] = judge_overhead()
    print(json.dumps(out, indent=1))
