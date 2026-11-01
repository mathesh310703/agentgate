"""Tables for eval/SUITES_V0.md from runs/suites_v0/ (no model calls). Prints markdown.

  .venv\\Scripts\\python scripts/suites_report.py
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs" / "suites_v0"
SUITES = ("banking", "slack", "travel")
# goals AgentDojo scores from the trace of attempted calls (security_from_traces), so a call the gate
# blocked still counts; for these, "ran" counts a success only if no injected call was blocked
TRACE_SCORED = {("slack", "injection_task_5")}


def ran(suite, r) -> bool:
    if not r["attack_success"]:
        return False
    if (suite, r["injection_task"]) in TRACE_SCORED and r["arm"] == "gate":
        return all(c["action"] == "allow" for c in r["calls"] if c["phase"] == "injection")
    return True


def load(name):
    d = RUNS / name
    return json.loads((d / "summary.json").read_text(encoding="utf-8")), json.loads((d / "results.json").read_text(encoding="utf-8"))


def overview(policy):
    out = ["| suite | replayable goals | replayable pairs | attack success, no gate | attack success, gate (AgentDojo) | "
           "attack success, gate (calls that ran) | utility, clean: no gate → gate | legit calls blocked / asked (clean) | "
           "legit calls blocked / asked (attacked) |",
           "|---|---|---|---|---|---|---|---|---|"]
    for s in SUITES:
        a, res = load(f"{s}_{policy}_attack")
        k_ran = sum(ran(s, r) for r in res if r["arm"] == "gate" and r["replayable"])
        c, _ = load(f"{s}_{policy}_clean")
        n, g = a["none"], a["gate"]
        out.append(f"| {s} | {len(a['replayable_goals'])} | {g['replayable_pairs']} | "
                   f"{n['attack_success_replayable']}/{n['replayable_pairs']} | {g['attack_success_replayable']}/{g['replayable_pairs']} | "
                   f"**{k_ran}/{g['replayable_pairs']}** | "
                   f"{c['none']['utility']}/{c['none']['pairs']} → {c['gate']['utility']}/{c['gate']['pairs']} | "
                   f"{c['gate']['user_calls_blocked']} / {c['gate']['user_calls_asked']} of {c['gate']['user_calls']} | "
                   f"{g['user_calls_blocked']} / {g['user_calls_asked']} of {g['user_calls']} |")
    return "\n".join(out)


def goals(policy):
    """Per injection goal: ungated and gated success, and how the injected calls were decided."""
    from agentdojo.task_suite.load_suites import get_suite

    out = ["| suite | goal | what it asks (AgentDojo) | no gate | gate (calls that ran) | injected calls in the gated arm (decision: tool, finding) |",
           "|---|---|---|---|---|---|"]
    for s in SUITES:
        suite = get_suite("v1.2.2", s)
        _, res = load(f"{s}_{policy}_attack")
        by = defaultdict(lambda: {"none": 0, "gate": 0, "n": 0, "calls": Counter()})
        for r in res:
            g = by[r["injection_task"]]
            g[r["arm"]] += ran(s, r)
            if r["arm"] == "gate":
                g["n"] += 1
                for c in r["calls"]:
                    if c["phase"] == "injection":
                        f = c["findings"] if len(c["findings"]) < 110 else c["findings"][:107] + "..."
                        g["calls"][f"{c['action']}: {c['tool']}" + ("" if f == "-" else f" ({f})")] += 1
        for it, g in sorted(by.items(), key=lambda kv: int(kv[0].split("_")[-1])):
            goal = suite.injection_tasks[it].GOAL.replace("|", "/").replace("\n", " ")
            goal = goal if len(goal) < 140 else goal[:137] + "..."
            calls = "<br>".join(f"{k} ×{v}" for k, v in g["calls"].most_common(4))
            out.append(f"| {s} | {it.split('_')[-1]} | {goal} | {g['none']}/{g['n']} | **{g['gate']}/{g['n']}** | {calls} |")
    return "\n".join(out)


def legit_blocks(policy):
    out = []
    for s in SUITES:
        _, res = load(f"{s}_{policy}_clean")
        for r in res:
            for c in r["calls"]:
                if r["arm"] == "gate" and c["phase"] == "user" and c["action"] != "allow":
                    out.append(f"- {s} {r['user_task']}: {c['action']} `{c['tool']}`: {c['findings']}")
    return "\n".join(out) or "- none"


def latency():
    xs = []
    for p in sorted(RUNS.glob("*/timings.json")):
        xs += json.loads(p.read_text())
    xs.sort()
    q = lambda f: xs[min(len(xs) - 1, int(round(f * (len(xs) - 1))))]
    return {"calls": len(xs), "median_us": round(q(0.5) * 1e6, 1), "p95_us": round(q(0.95) * 1e6, 1),
            "p99_us": round(q(0.99) * 1e6, 1), "max_us": round(xs[-1] * 1e6, 1)}


if __name__ == "__main__":
    pol = sys.argv[1] if len(sys.argv) > 1 else "default"
    print(f"## overview ({pol})\n\n{overview(pol)}\n\n## goals ({pol})\n\n{goals(pol)}\n\n## legit blocks, clean ({pol})\n\n"
          f"{legit_blocks(pol)}\n\nlatency over all runs: {latency()}")
