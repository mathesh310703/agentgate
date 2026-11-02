"""Llama 3.1 8B (local, Ollama, text only) as a real victim on AgentDojo workspace, ungated and gated. No API cost.

Same pipeline as the Muse Spark runs (vllm_parsed: default system message, YAML tool output, native tool calls), with
scripts/ollama_proxy.py in front of the model. Results are appended per episode and a re-run skips finished episodes.

  clean:  all 40 user tasks, no injection, ungated and gated
  attack: important_instructions; for one injection goal at a time, in numeric order, all 40 user tasks in both arms,
          so stopping at --deadline leaves complete goals only (a goal starts only if --deadline has not passed)

  .venv\\Scripts\\python scripts/run_llama31.py --phase clean --out runs/llama31_v0
  .venv\\Scripts\\python scripts/run_llama31.py --phase attack --out runs/llama31_v0 --deadline 14:00
  .venv\\Scripts\\python scripts/run_llama31.py --phase summary --out runs/llama31_v0
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from agentdojo.agent_pipeline import AgentPipeline, InitQuery, SystemMessage, ToolsExecutionLoop, ToolsExecutor  # noqa: E402
from agentdojo.agent_pipeline.agent_pipeline import get_llm, load_system_message  # noqa: E402
from agentdojo.attacks.attack_registry import load_attack  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402

from agentgate import default_workspace_policy  # noqa: E402
from agentgate.adapters.agentdojo_adapter import GatedToolsExecutor  # noqa: E402
from run_worstcase import ATTACK, SPLITS, RecordingGate, findings_text  # noqa: E402

USERS = [f"user_task_{i}" for i in SPLITS["all"]]
HALVES = {"tuning 0-19": set(f"user_task_{i}" for i in SPLITS["tune"]),
          "held-out 20-39": set(f"user_task_{i}" for i in SPLITS["heldout"])}


def build(arm, port):
    os.environ["LOCAL_LLM_PORT"] = str(port)
    model = get_llm("vllm_parsed", "vllm_parsed", None, "tool")
    gate = RecordingGate(default_workspace_policy()) if arm == "gate" else None
    executor = GatedToolsExecutor(gate) if gate else ToolsExecutor()
    pipeline = AgentPipeline([SystemMessage(load_system_message(None)), InitQuery(), model,
                              ToolsExecutionLoop([executor, model])])
    pipeline.name = "vllm_parsed_llama31"
    return pipeline, gate


def episode(suite, attack, pipelines, arm, user, injection):
    pipeline, gate = pipelines[arm]
    ut = suite.user_tasks[user]
    it = suite.injection_tasks[injection] if injection else None
    if gate:
        gate.decisions = []
    t0 = time.time()
    rec = {"arm": arm, "user_task": user, "injection_task": injection}
    try:
        utility, security = suite.run_task_with_pipeline(pipeline, ut, it, attack.attack(ut, it) if it else {})
        rec.update(utility=bool(utility), attack_success=bool(security) if it else False)
    except Exception as e:   # a model or tool-format failure counts against the episode, and is reported
        rec.update(utility=False, attack_success=False, error=f"{type(e).__name__}: {str(e)[:200]}")
    rec["seconds"] = round(time.time() - t0, 1)
    if gate:
        rec["decisions"] = [{"tool": d.tool, "action": d.action, "reason": d.reason, "findings": findings_text(d)}
                            for d in gate.decisions]
    return rec


def done_keys(path):
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(r["arm"], r["user_task"], r["injection_task"]): r for r in rows}


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - h), min(1.0, c + h))


def rate(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({lo * 100:.1f}-{hi * 100:.1f}%)"


def summary(out):
    rows = list(done_keys(out / "results.jsonl").values())
    report = {"episodes": len(rows), "errors": sum("error" in r for r in rows), "by_half": {}}
    for half, users in {**HALVES, "all 40": set(USERS)}.items():
        h = {}
        for arm in ("none", "gate"):
            clean = [r for r in rows if r["arm"] == arm and not r["injection_task"] and r["user_task"] in users]
            atk = [r for r in rows if r["arm"] == arm and r["injection_task"] and r["user_task"] in users]
            dec = [d for r in clean for d in r.get("decisions", [])]
            h[arm] = {"utility_clean": rate(sum(r["utility"] for r in clean), len(clean)),
                      "utility_attacked": rate(sum(r["utility"] for r in atk), len(atk)),
                      "attack_success": rate(sum(r["attack_success"] for r in atk), len(atk)),
                      "users_with_success": len({r["user_task"] for r in atk if r["attack_success"]}),
                      "clean_block": sum(d["action"] == "block" for d in dec),
                      "clean_ask": sum(d["action"] == "ask" for d in dec)}
        report["by_half"][half] = h
    report["goals_complete"] = sorted({r["injection_task"] for r in rows if r["injection_task"]},
                                      key=lambda s: int(s.rsplit("_", 1)[1]))
    report["by_goal"] = {}
    for g in report["goals_complete"]:
        rs = [r for r in rows if r["injection_task"] == g]
        report["by_goal"][g] = {a: sum(r["attack_success"] for r in rs if r["arm"] == a) for a in ("none", "gate")}
        report["by_goal"][g]["n_per_arm"] = sum(r["arm"] == "none" for r in rs)
    report["seconds_median"] = sorted(r["seconds"] for r in rows)[len(rows) // 2] if rows else None
    calls = out / "calls.jsonl"
    if calls.exists():
        c = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines() if line.strip()]
        ok = [x for x in c if x["status"] == 200]
        report["calls"] = {"n": len(c), "non_200": len(c) - len(ok), "truncated": sum(x["truncated"] for x in ok),
                           "max_prompt": max((x["prompt"] or 0 for x in ok), default=0),
                           "with_tool_call": sum(x["tool_calls"] > 0 for x in ok),
                           "coerced": sum(bool(x["coerced"]) for x in ok)}
    (out / "summary.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=["clean", "attack", "summary"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", default="8021")
    ap.add_argument("--limit", type=int, help="clean phase: only the first N user tasks (pilot)")
    ap.add_argument("--deadline", help="HH:MM local time: no new injection goal starts after this")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.phase == "summary":
        return summary(out)

    suite = get_suite("v1.2.2", "workspace")
    named = AgentPipeline([])
    named.name = "vllm_parsed"   # same model wording in the injected text as the other runs
    attack = load_attack(ATTACK, suite, named)
    pipelines = {arm: build(arm, a.port) for arm in ("none", "gate")}
    path = out / "results.jsonl"
    done = done_keys(path)

    def run(arm, user, injection):
        if (arm, user, injection) in done:
            return
        rec = episode(suite, attack, pipelines, arm, user, injection)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(arm, user, injection, "utility", rec["utility"], "attack", rec["attack_success"], rec["seconds"], "s",
              rec.get("error", ""), flush=True)

    if a.phase == "clean":
        for user in USERS[:a.limit]:
            for arm in ("none", "gate"):
                run(arm, user, None)
        return
    for injection in sorted(suite.injection_tasks, key=lambda s: int(s.rsplit("_", 1)[1])):
        if a.deadline and datetime.now().strftime("%H:%M") >= a.deadline:
            print("deadline reached before", injection, flush=True)
            break
        for user in USERS:
            for arm in ("none", "gate"):
                run(arm, user, injection)


if __name__ == "__main__":
    main()
