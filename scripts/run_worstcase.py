"""Worst-case replay on AgentDojo (no model calls, zero cost).

A scripted "compromised agent" issues, for each (user task, injection task) pair, the user task's
ground-truth tool calls and then the injection task's ground-truth tool calls, i.e. an agent that does
the user's job and then fully obeys the injection. Tool results come from the real suite environment
with the important_instructions attack placed in the injection vectors the user task reads.

Arms: "none" (agentdojo's ToolsExecutor) and "gate" (GatedToolsExecutor; every tool result goes into the
Session as untrusted text). Metrics come from the end state via agentdojo's own utility/security checks.

  .venv\\Scripts\\python scripts/run_worstcase.py --split tune --out runs/worstcase_v1_tune       # develop here
  .venv\\Scripts\\python scripts/run_worstcase.py --split tune --mode clean --out runs/wc_v1_tune_clean
  .venv\\Scripts\\python scripts/run_worstcase.py --split heldout --out runs/worstcase_v1_heldout # once
  .venv\\Scripts\\python scripts/run_worstcase.py --split tune --detector promptguard --out runs/layer1_tune
  .venv\\Scripts\\python scripts/run_worstcase.py --users user_task_0 --injections injection_task_1 --out ...
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agentdojo.agent_pipeline import AgentPipeline, BasePipelineElement, InitQuery, ToolsExecutor  # noqa: E402
from agentdojo.attacks.attack_registry import load_attack  # noqa: E402
from agentdojo.functions_runtime import EmptyEnv  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402
from agentdojo.types import ChatAssistantMessage, text_content_block_from_string  # noqa: E402

from agentgate import Gate, default_workspace_policy  # noqa: E402
from agentgate.adapters.agentdojo_adapter import GatedToolsExecutor  # noqa: E402
from agentgate.judge import judge_decision  # noqa: E402

ATTACK = "important_instructions"


class RecordingGate(Gate):
    """Gate that keeps every Decision (with findings) so the replay can report sources.
    With a judge, its "ask" decisions go to the Layer 2 intent judge (agentgate/judge.py)."""

    def __init__(self, policy, judge=None):
        super().__init__(policy)
        self.judge = judge
        self.decisions = []

    def check(self, tool, args, session):
        d = judge_decision(self.judge, super().check(tool, args, session), args, session)
        self.decisions.append(d)
        return d


class CompromisedAgent(BasePipelineElement):
    """Replays user-task ground truth, then injection-task ground truth, one call per turn."""

    def __init__(self, executor):
        self.executor = executor
        self.user_task = self.injection_task = None
        self.phases = []   # "user" / "injection" for each call issued, in order

    def set_pair(self, user_task, injection_task):
        """injection_task=None: clean replay, user-task calls only."""
        self.user_task, self.injection_task, self.phases = user_task, injection_task, []

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        # each plan is computed when its phase starts: the injection's ids (e.g. the next email id) must
        # reflect what the user-task calls already created
        phases = [("user", self.user_task)] + ([("injection", self.injection_task)] if self.injection_task else [])
        for phase, task in phases:
            for call in task.ground_truth(env):
                call = call.model_copy(update={"id": f"gt{len(self.phases)}"})
                self.phases.append(phase)
                messages = [*messages, ChatAssistantMessage(role="assistant", tool_calls=[call],
                                                            content=[text_content_block_from_string("")])]
                query, runtime, env, messages, extra_args = self.executor.query(query, runtime, env, messages,
                                                                                extra_args)
        final = ChatAssistantMessage(role="assistant", tool_calls=None,
                                     content=[text_content_block_from_string(self.user_task.GROUND_TRUTH_OUTPUT)])
        return query, runtime, env, [*messages, final], extra_args


def findings_text(d):
    return "; ".join(f"{f.arg}={f.value!r} {f.verdict} (source: {f.source or 'none'})" for f in d.findings) or "-"


def run(arm, suite, attack, pairs, scorer=None, judge=None):
    gate = RecordingGate(default_workspace_policy(), judge) if arm == "gate" else None
    agent = CompromisedAgent(GatedToolsExecutor(gate, scorer=scorer) if gate else ToolsExecutor())
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
    return out


def summarize(results):
    rows = {}
    for arm in ("none", "gate"):
        rs = [r for r in results if r["arm"] == arm]
        row = {"pairs": len(rs), "attack_success": sum(r["attack_success"] for r in rs),
               "utility": sum(r["utility"] for r in rs)}
        if arm == "gate":
            uc = [c for r in rs for c in r["calls"] if c["phase"] == "user"]
            ic = [c for r in rs for c in r["calls"] if c["phase"] == "injection"]
            row["user_calls"] = len(uc)
            row["user_calls_blocked"] = sum(c["action"] == "block" for c in uc)
            row["user_calls_asked"] = sum(c["action"] == "ask" for c in uc)
            row["user_calls_blocked_sender_rule"] = sum(c["action"] == "block" and "sender_only" in c["findings"]
                                                        for c in uc)
            row["user_tasks_with_block"] = len({r["user_task"] for r in rs for c in r["calls"]
                                                if c["phase"] == "user" and c["action"] == "block"})
            row["user_tasks_with_ask"] = len({r["user_task"] for r in rs for c in r["calls"]
                                              if c["phase"] == "user" and c["action"] == "ask"})
            row["injection_calls"] = dict(Counter(c["action"] for c in ic))
            # Layer 2: approvals of injected calls are false approvals
            row["judge"] = {phase: dict(Counter(c["judge"] for c in calls if "judge" in c))
                            for phase, calls in (("user", uc), ("injection", ic))}
        rows[arm] = row
    return rows


SPLITS = {"tune": range(0, 20), "heldout": range(20, 40), "all": range(0, 40)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--benchmark-version", default="v1.2.2")
    ap.add_argument("--split", choices=list(SPLITS), default="all",
                    help="user tasks: tune = 0-19 (develop here), heldout = 20-39 (report once), all")
    ap.add_argument("--users", nargs="*", help="explicit user task ids (overrides --split)")
    ap.add_argument("--injections", nargs="*")
    ap.add_argument("--mode", choices=["attack", "clean"], default="attack",
                    help="clean: user-task calls only, no injections (utility without attack goals)")
    ap.add_argument("--detector", choices=["none", "promptguard"], default="none",
                    help="promptguard: score free-text records with Llama Prompt Guard 2 (CPU, local)")
    ap.add_argument("--judge", action="store_true",
                    help="Layer 2: send the gate's asks to the intent judge via the proxy (costs money; "
                         "start the proxy with --stage defense)")
    ap.add_argument("--port", default="8000")
    ap.add_argument("--out", required=True, help="output dir, e.g. runs/worstcase_v1_tune")
    a = ap.parse_args(argv)

    suite = get_suite(a.benchmark_version, "workspace")
    named = AgentPipeline([])
    named.name = "vllm_parsed"   # same model wording in the injected text as the runs/atk_* runs
    attack = load_attack(ATTACK, suite, named)
    users = [suite.user_tasks[u] for u in (a.users or [f"user_task_{i}" for i in SPLITS[a.split]])]
    if a.mode == "clean":
        pairs = [(u, None) for u in users]
        print(f"clean replay: {len(users)} user tasks, no injections")
    else:
        injs = [suite.injection_tasks[i] for i in (a.injections or suite.injection_tasks)]
        pairs = [(u, i) for u in users for i in injs]
        print(f"{len(users)} user tasks x {len(injs)} injection tasks = {len(pairs)} pairs; attack {ATTACK}")

    scorer = None
    if a.detector == "promptguard":
        from agentgate.detectors import PromptGuard
        scorer = PromptGuard()
    judge = None
    if a.judge:
        from agentgate.judge import IntentJudge
        judge = IntentJudge(a.port, log_path=Path(a.out) / "judge_log.jsonl")
    results = run("none", suite, attack, pairs) + run("gate", suite, attack, pairs, scorer, judge)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    summary = summarize(results)
    print(json.dumps(summary, indent=1))
    for r in results:
        for c in r["calls"]:
            if r["arm"] == "gate" and c["phase"] == "user" and (c["action"] != "allow" or "judge" in c):
                print(f"  user-call {c['action']}: {r['user_task']} x {r['injection_task']}: {c['tool']}: "
                      f"{c['findings']}")
    through = [r for r in results if r["arm"] == "gate" and r["attack_success"]]
    print(f"\ninjection goals that got through the gate: {len(through)}")
    for r in through:
        print(f"- {r['user_task']} x {r['injection_task']}")
        for c in r["calls"]:
            if c["phase"] == "injection":
                print(f"    {c['action']:5} {c['tool']}: {c['findings']}")
    for r in results:
        for c in r["calls"]:
            if r["arm"] == "gate" and c["phase"] == "injection" and "judge" in c:
                print(f"  judge {c['judge']} on injected {c['tool']}: {r['user_task']} x {r['injection_task']}: "
                      f"{c['findings']} -> {c['action']}")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=dict), encoding="utf-8")


if __name__ == "__main__":
    main()
