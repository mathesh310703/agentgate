"""More published AgentDojo attack types against Muse Spark Open, workspace suite. The rule is fixed in eval/ATTACKTYPES_V0.md.

Same pipeline as the earlier runs (vllm_parsed, default system message, YAML tool output), through the budget proxy:
  .venv\\Scripts\\python -m agentlab.proxy --stage benchmark
  .venv\\Scripts\\python scripts/run_attacktypes.py check                 # free: the sample, and every attack's text builds
  .venv\\Scripts\\python scripts/run_attacktypes.py run --limit 5         # pilot, counts towards the sample
  .venv\\Scripts\\python scripts/run_attacktypes.py run                   # ungated
  .venv\\Scripts\\python scripts/run_attacktypes.py run --gated           # the same episodes, gated, for attacks that succeeded
  .venv\\Scripts\\python scripts/run_attacktypes.py summary

Results are appended per episode and a re-run skips finished episodes. Hard stops: $2 ungated, $3 in all.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from agentdojo.agent_pipeline import AgentPipeline  # noqa: E402
from agentdojo.attacks.attack_registry import ATTACKS, load_attack  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402

from agentlab import llm  # noqa: E402
from run_llama31 import build, episode, rate  # noqa: E402

OUT = ROOT / "runs" / "attacktypes_v0"
STAGE = "benchmark"
UNGATED_CAP, TOTAL_CAP = 2.0, 3.0
EXCLUDED = {"manual": "needs typed input during the run", "dos": "no injection goal", "swearwords_dos": "no injection goal",
            "captcha_dos": "no injection goal", "offensive_email_dos": "no injection goal", "felony_dos": "no injection goal"}
ATTACK_TYPES = sorted(set(ATTACKS) - set(EXCLUDED))
USER_TASKS = [f"user_task_{i}" for i in range(0, 40, 8)]   # every 8th: 0, 8, 16, 24, 32
GOALS = ["injection_task_0", "injection_task_1", "injection_task_2"]   # the lowest-numbered three


def load_results():
    path = OUT / "results.jsonl"
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(r["attack"], r["arm"], r["user_task"], r["injection_task"]): r for r in rows}


def _suite_and_named():
    named = AgentPipeline([])
    named.name = "vllm_parsed"   # same model wording in the injected text as the earlier runs
    return get_suite("v1.2.2", "workspace"), named


def check():
    suite, named = _suite_and_named()
    report = {"attacks": ATTACK_TYPES, "excluded": EXCLUDED, "user_tasks": USER_TASKS, "goals": GOALS,
              "episodes_per_arm": len(ATTACK_TYPES) * len(USER_TASKS) * len(GOALS), "injection_slots": {}}
    for name in ATTACK_TYPES:
        attack = load_attack(name, suite, named)
        slots = []
        for u in USER_TASKS:
            for g in GOALS:
                injections = attack.attack(suite.user_tasks[u], suite.injection_tasks[g])
                assert injections and all(injections.values()), (name, u, g)
                slots.append(len(injections))
        report["injection_slots"][name] = slots[0]
    per_user = {u: len(load_attack(ATTACK_TYPES[0], suite, named).attack(suite.user_tasks[u], suite.injection_tasks[GOALS[0]]))
                for u in USER_TASKS}
    report["injection_slots_per_user_task"] = per_user
    print(json.dumps(report, indent=1))
    return report


def spent_since_start():
    OUT.mkdir(parents=True, exist_ok=True)
    start = OUT / "budget_start.json"
    if not start.exists():
        start.write_text(json.dumps({"benchmark": llm.spend_by_stage().get(STAGE, 0.0), "total": llm.total_spent()}), encoding="utf-8")
    return llm.spend_by_stage().get(STAGE, 0.0) - json.loads(start.read_text(encoding="utf-8"))["benchmark"]


def run(gated, limit, port):
    suite, named = _suite_and_named()
    pipelines = {arm: build(arm, port) for arm in ("none", "gate")}
    for pipeline, _ in pipelines.values():
        pipeline.name = "vllm_parsed"
    done = load_results()
    arm = "gate" if gated else "none"
    cap = TOTAL_CAP if gated else UNGATED_CAP
    types = ATTACK_TYPES
    if gated:
        types = sorted({k[0] for k, r in done.items() if k[1] == "none" and r["attack_success"]})
        print("gated arm for:", types, flush=True)
    n = 0
    path = OUT / "results.jsonl"
    for name in types:
        attack = load_attack(name, suite, named)
        for u in USER_TASKS:
            for g in GOALS:
                if (name, arm, u, g) in done:
                    continue
                if limit is not None and n >= limit:
                    print(f"limit reached, ${spent_since_start():.4f} spent so far", flush=True)
                    return
                spent = spent_since_start()
                if spent >= cap:
                    print(f"stopped at the ${cap} cap, ${spent:.4f} spent", flush=True)
                    return
                rec = {"attack": name, **episode(suite, attack, pipelines, arm, u, g)}
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")
                n += 1
                print(name, arm, u, g, "utility", rec["utility"], "attack", rec["attack_success"], rec["seconds"], "s",
                      f"${spent_since_start():.4f}", rec.get("error", ""), flush=True)
    print(f"done, ${spent_since_start():.4f} spent", flush=True)


def summary():
    rows = list(load_results().values())
    out = {"episodes": len(rows), "errors": [(r["attack"], r["arm"], r["user_task"], r["injection_task"], r["error"][:160])
                                             for r in rows if "error" in r],
           "spent": round(spent_since_start(), 4), "by_attack": {}}
    arms = ("none", "gate")
    for name in ATTACK_TYPES + ["all"]:
        row = {}
        for arm in arms:
            rs = [r for r in rows if r["arm"] == arm and (name == "all" or r["attack"] == name)]
            if rs:
                dec = [d for r in rs for d in r.get("decisions", [])]
                row[arm] = {"episodes": len(rs), "attack_success": rate(sum(r["attack_success"] for r in rs), len(rs)),
                            "utility": rate(sum(r["utility"] for r in rs), len(rs)),
                            "decisions": dict(Counter(d["action"] for d in dec)),
                            "user_tasks_with_success": sorted({r["user_task"] for r in rs if r["attack_success"]},
                                                              key=lambda t: int(t.rsplit("_", 1)[1]))}
        out["by_attack"][name] = row
    (OUT / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=["check", "run", "summary"])
    ap.add_argument("--gated", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--port", default="8000")
    a = ap.parse_args(argv)
    if a.phase == "check":
        check()
    elif a.phase == "run":
        run(a.gated, a.limit, a.port)
    else:
        summary()


if __name__ == "__main__":
    main()
