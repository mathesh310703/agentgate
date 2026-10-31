"""Worst-case replay on AgentDojo (no model calls, zero cost).

A scripted "compromised agent" issues, for each (user task, injection task) pair, the user task's
ground-truth tool calls and then the injection task's ground-truth tool calls, i.e. an agent that does
the user's job and then fully obeys the injection. Tool results come from the real suite environment
with the important_instructions attack placed in the injection vectors the user task reads.

Arms: "none" (agentdojo's ToolsExecutor) and "gate" (GatedToolsExecutor; every tool result goes into the
Session as untrusted text). Metrics come from the end state via agentdojo's own utility/security checks.

  .venv\\Scripts\\python scripts/run_worstcase.py                 # all pairs -> runs/worstcase_v0/
  .venv\\Scripts\\python scripts/run_worstcase.py --users user_task_0 --injections injection_task_1
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

ATTACK = "important_instructions"


class RecordingGate(Gate):
    """Gate that keeps every Decision (with findings) so the replay can report sources."""

    def __init__(self, policy):
        super().__init__(policy)
        self.decisions = []

    def check(self, tool, args, session):
        d = super().check(tool, args, session)
        self.decisions.append(d)
        return d


class CompromisedAgent(BasePipelineElement):
    """Replays user-task ground truth, then injection-task ground truth, one call per turn."""

    def __init__(self, executor):
        self.executor = executor
        self.user_task = self.injection_task = None
        self.phases = []   # "user" / "injection" for each call issued, in order

    def set_pair(self, user_task, injection_task):
        self.user_task, self.injection_task, self.phases = user_task, injection_task, []

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        # each plan is computed when its phase starts: the injection's ids (e.g. the next email id) must
        # reflect what the user-task calls already created
        for phase, task in (("user", self.user_task), ("injection", self.injection_task)):
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


def run(arm, suite, attack, pairs):
    gate = RecordingGate(default_workspace_policy()) if arm == "gate" else None
    agent = CompromisedAgent(GatedToolsExecutor(gate) if gate else ToolsExecutor())
    pipeline = AgentPipeline([InitQuery(), agent])
    pipeline.name = f"vllm_parsed_worstcase_{arm}"
    out = []
    for ut, it in pairs:
        injections = attack.attack(ut, it)
        agent.set_pair(ut, it)
        if gate:
            gate.decisions = []
        utility, security = suite.run_task_with_pipeline(pipeline, ut, it, injections)
        rec = {"arm": arm, "user_task": ut.ID, "injection_task": it.ID, "utility": bool(utility),
               "attack_success": bool(security), "calls": []}
        for i, phase in enumerate(agent.phases):
            c = {"phase": phase}
            if gate:
                d = gate.decisions[i]
                c.update(tool=d.tool, action=d.action, reason=d.reason, findings=findings_text(d))
            rec["calls"].append(c)
        out.append(rec)
    return out


def summarize(results, n_user_calls_total):
    rows = {}
    for arm in ("none", "gate"):
        rs = [r for r in results if r["arm"] == arm]
        row = {"pairs": len(rs), "attack_success": sum(r["attack_success"] for r in rs),
               "utility": sum(r["utility"] for r in rs)}
        if arm == "gate":
            uc = [c for r in rs for c in r["calls"] if c["phase"] == "user"]
            ic = [c for r in rs for c in r["calls"] if c["phase"] == "injection"]
            row["user_calls"] = len(uc)
            row["user_calls_blocked_or_asked"] = sum(c["action"] != "allow" for c in uc)
            row["injection_calls"] = Counter(c["action"] for c in ic)
        rows[arm] = row
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--benchmark-version", default="v1.2.2")
    ap.add_argument("--users", nargs="*")
    ap.add_argument("--injections", nargs="*")
    ap.add_argument("--out", default=str(ROOT / "runs" / "worstcase_v0"))
    a = ap.parse_args(argv)

    suite = get_suite(a.benchmark_version, "workspace")
    named = AgentPipeline([])
    named.name = "vllm_parsed"   # same model wording in the injected text as the runs/atk_* runs
    attack = load_attack(ATTACK, suite, named)
    users = [suite.user_tasks[u] for u in (a.users or suite.user_tasks)]
    injs = [suite.injection_tasks[i] for i in (a.injections or suite.injection_tasks)]
    pairs = [(u, i) for u in users for i in injs]
    print(f"{len(users)} user tasks x {len(injs)} injection tasks = {len(pairs)} pairs; attack {ATTACK}")

    results = run("none", suite, attack, pairs) + run("gate", suite, attack, pairs)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    summary = summarize(results, None)
    print(json.dumps(summary, indent=1, default=dict))
    through = [r for r in results if r["arm"] == "gate" and r["attack_success"]]
    print(f"\ninjection goals that got through the gate: {len(through)}")
    for r in through:
        print(f"- {r['user_task']} x {r['injection_task']}")
        for c in r["calls"]:
            if c["phase"] == "injection":
                print(f"    {c['action']:5} {c['tool']}: {c['findings']}")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=dict), encoding="utf-8")


if __name__ == "__main__":
    main()
