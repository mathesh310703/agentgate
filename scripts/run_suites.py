"""Worst-case replay on the other AgentDojo suites (banking, slack, travel): out-of-distribution check of the
frozen gate. No model calls, zero cost (unless --judge).

Same scripted compromised agent as scripts/run_worstcase.py (user-task ground truth, then the injection
task's ground truth, important_instructions attack). Adds: --suite, --policy (the frozen workspace policy,
agentgate/policy_suites.py, written after seeing the first run, or the synthesized policies/<suite>.json from
agentgate/policy_synth.py), clean mode, and the gate's own latency per call (Gate.check only, judge excluded).

  .venv\\Scripts\\python scripts/run_suites.py --suite banking --policy default --out runs/suites_v0/banking_default
  .venv\\Scripts\\python scripts/run_suites.py --suite banking --policy default --mode clean --out runs/suites_v0/banking_default_clean
  .venv\\Scripts\\python scripts/run_suites.py --suite banking --policy suites --out runs/suites_v0/banking_suites

Writes results.json, summary.json and timings.json (seconds per Gate.check) to --out.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from agentdojo.agent_pipeline import AgentPipeline, InitQuery, ToolsExecutor  # noqa: E402
from agentdojo.attacks.attack_registry import load_attack  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402

from agentgate import Gate, default_workspace_policy  # noqa: E402
from agentgate.adapters.agentdojo_adapter import GatedToolsExecutor  # noqa: E402
from agentgate.judge import judge_decision  # noqa: E402
from agentgate.policy_synth import SynthGate, SynthPolicy, load_policy  # noqa: E402
from run_worstcase import ATTACK, CompromisedAgent, findings_text, summarize  # noqa: E402

WRITE_VERBS = ("send_", "share_", "delete_", "update_", "schedule_", "reserve_", "add_", "remove_", "invite_",
               "post_", "cancel_", "create_", "append_", "reschedule_")


def policy_for(name, suite_name):
    if name == "default":
        return default_workspace_policy()
    if name == "synth":
        return load_policy(ROOT / "policies" / f"{suite_name}.json")
    from agentgate.policy_suites import suite_policy
    return suite_policy(suite_name, "rules" if name == "suites" else "rules_trust")


class TimedGate(Gate):
    """Keeps every Decision and the time Gate.check took; asks go to the judge when one is given."""

    def __init__(self, policy, judge=None):
        super().__init__(policy)
        self.judge, self.decisions, self.timings = judge, [], []

    def check(self, tool, args, session):
        t0 = time.perf_counter()
        d = super().check(tool, args, session)
        self.timings.append(time.perf_counter() - t0)
        d = judge_decision(self.judge, d, args, session)
        self.decisions.append(d)
        return d


class TimedSynthGate(TimedGate, SynthGate):
    """TimedGate around SynthGate: tools the synthesized policy does not classify are blocked, and recorded."""


def replayable(suite, injection_task) -> bool:
    env = suite.load_and_inject_default_environment({})
    return len(injection_task.ground_truth(env)) > 0


def run(arm, suite, attack, pairs, policy, judge=None, strict=False):
    gate_cls = TimedSynthGate if isinstance(policy, SynthPolicy) else TimedGate
    gate = gate_cls(policy, judge) if arm == "gate" else None
    agent = CompromisedAgent(GatedToolsExecutor(gate, strict=strict) if gate else ToolsExecutor())
    pipeline = AgentPipeline([InitQuery(), agent])
    pipeline.name = f"vllm_parsed_worstcase_{arm}"
    out = []
    for ut, it in pairs:
        injections = attack.attack(ut, it) if it else {}
        agent.set_pair(ut, it)
        if gate:
            gate.decisions = []
        utility, security = suite.run_task_with_pipeline(pipeline, ut, it, injections)
        rec = {"arm": arm, "user_task": ut.ID, "injection_task": it.ID if it else None, "utility": bool(utility),
               "attack_success": bool(security) if it else False, "calls": []}
        for i, phase in enumerate(agent.phases):
            c = {"phase": phase}
            if gate:
                d = gate.decisions[i]
                c.update(tool=d.tool, action=d.action, reason=d.reason, findings=findings_text(d))
                if d.judge is not None:
                    c["judge"] = d.judge["decision"]
            rec["calls"].append(c)
        out.append(rec)
    return out, (gate.timings if gate else [])


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", required=True, choices=["banking", "slack", "travel", "workspace"])
    ap.add_argument("--policy", choices=["default", "suites", "suites_trust", "synth"],
                    help="suites: agentgate/policy_suites.py level 'rules'; suites_trust: level 'rules_trust'; "
                         "synth: policies/<suite>.json from agentgate/policy_synth.py", default="default")
    ap.add_argument("--mode", choices=["attack", "clean"], default="attack")
    ap.add_argument("--benchmark-version", default="v1.2.2")
    ap.add_argument("--strict", action="store_true", help="strict mode (agentgate/fields_strict.py)")
    ap.add_argument("--split", choices=["all", "tune", "heldout"], default="all",
                    help="user tasks: tune = first half, heldout = second half (workspace: 0-19 / 20-39)")
    ap.add_argument("--judge", action="store_true", help="send asks to the intent judge via the proxy (costs money)")
    ap.add_argument("--port", default="8000")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    suite = get_suite(a.benchmark_version, a.suite)
    named = AgentPipeline([])
    named.name = "vllm_parsed"
    attack = load_attack(ATTACK, suite, named)
    users = list(suite.user_tasks.values())
    if a.split != "all":
        half = len(users) // 2
        users = sorted(users, key=lambda u: int(u.ID.split("_")[-1]))
        users = users[:half] if a.split == "tune" else users[half:]
    injs = list(suite.injection_tasks.values())
    rep = {i.ID: replayable(suite, i) for i in injs}
    pairs = [(u, None) for u in users] if a.mode == "clean" else [(u, i) for u in users for i in injs]
    print(f"{a.suite}: {len(users)} user tasks x {len(injs)} injection tasks; replayable goals "
          f"{sum(rep.values())}/{len(injs)}; mode {a.mode}; policy {a.policy}; strict {a.strict}; split {a.split}")

    judge = None
    if a.judge:
        from agentgate.judge import IntentJudge
        judge = IntentJudge(a.port, log_path=Path(a.out) / "judge_log.jsonl")
    policy = policy_for(a.policy, a.suite)
    none, _ = run("none", suite, attack, pairs, policy)
    gated, timings = run("gate", suite, attack, pairs, policy, judge, a.strict)
    results = none + gated
    for r in results:
        r["replayable"] = bool(rep.get(r["injection_task"], False)) if r["injection_task"] else None

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    summary = summarize(results)
    if a.mode == "attack":
        for arm in ("none", "gate"):
            rs = [r for r in results if r["arm"] == arm and r["replayable"]]
            summary[arm]["replayable_pairs"] = len(rs)
            summary[arm]["attack_success_replayable"] = sum(r["attack_success"] for r in rs)
    summary["replayable_goals"] = sorted(k for k, v in rep.items() if v)
    summary["write_tools_without_rule"] = sorted(t.name for t in suite.tools
                                                 if t.name.startswith(WRITE_VERBS) and t.name not in policy.rules)
    summary["gate_latency_s"] = {"calls": len(timings), "median": statistics.median(timings) if timings else None,
                                 "p95": pct(timings, 0.95), "max": max(timings) if timings else None}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=dict), encoding="utf-8")
    (out / "timings.json").write_text(json.dumps(timings), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=dict))
    for r in gated:
        if r["attack_success"]:
            inj = [f"{c['action']} {c['tool']}: {c['findings']}" for c in r["calls"] if c["phase"] == "injection"]
            print(f"THROUGH {r['user_task']} x {r['injection_task']}: " + " | ".join(inj))
    for r in gated:
        for c in r["calls"]:
            if c["phase"] == "user" and c["action"] != "allow":
                print(f"USER-{c['action'].upper()} {r['user_task']} x {r['injection_task']}: {c['tool']}: {c['findings']}")


if __name__ == "__main__":
    main()
