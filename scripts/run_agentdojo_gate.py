"""Run an AgentDojo suite without injections, with the gate in front of every tool call.

Same pipeline as the ungated `--model vllm_parsed` runs (default system message, YAML tool output),
except that GatedToolsExecutor replaces ToolsExecutor. The model is reached through the local proxy
(start it first: `.venv\\Scripts\\python -m agentlab.proxy --stage baseline`).

  .venv\\Scripts\\python scripts/run_agentdojo_gate.py --run gate_v0
  .venv\\Scripts\\python scripts/run_agentdojo_gate.py --run gate_v0 --tasks user_task_0 user_task_1

Writes agentdojo traces to runs/<run>/ and gate counts to runs/<run>/gate_log.json.
Stops before the next task once this run has spent --max-usd in the proxy's stage.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agentdojo.agent_pipeline import AgentPipeline, InitQuery, SystemMessage, ToolsExecutionLoop  # noqa: E402
from agentdojo.agent_pipeline.agent_pipeline import get_llm, load_system_message  # noqa: E402
from agentdojo.benchmark import run_task_without_injection_tasks  # noqa: E402
from agentdojo.logging import OutputLogger  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402

from agentgate import Gate, default_workspace_policy  # noqa: E402
from agentgate.adapters.agentdojo_adapter import GatedToolsExecutor, GateLog  # noqa: E402
from agentlab import llm as budget  # noqa: E402

PIPELINE_NAME = "vllm_parsed_agentgate"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="run name; output under runs/<run>/")
    ap.add_argument("--suite", default="workspace")
    ap.add_argument("--benchmark-version", default="v1.2.2")
    ap.add_argument("--tasks", nargs="*", help="user task ids (default: all)")
    ap.add_argument("--stage", default="baseline", help="proxy stage whose spend is watched")
    ap.add_argument("--max-usd", type=float, default=3.0, help="stop once this run has spent this much")
    ap.add_argument("--port", default="8000")
    a = ap.parse_args(argv)

    os.environ["LOCAL_LLM_PORT"] = a.port
    logdir = ROOT / "runs" / a.run
    suite = get_suite(a.benchmark_version, a.suite)
    tasks = a.tasks or list(suite.user_tasks)

    gate = Gate(default_workspace_policy())
    log = GateLog(logdir / "gate_log.json", run=a.run)
    model = get_llm("vllm_parsed", "vllm_parsed", None, "tool")
    pipeline = AgentPipeline([SystemMessage(load_system_message(None)), InitQuery(), model,
                              ToolsExecutionLoop([GatedToolsExecutor(gate, log), model])])
    pipeline.name = PIPELINE_NAME

    start = budget.spend_by_stage().get(a.stage, 0.0)
    print(f"{len(tasks)} tasks; stage '{a.stage}' at ${start:.4f}; stop after +${a.max_usd:.2f}")
    utility, stopped = {}, None
    with OutputLogger(str(logdir)):
        for tid in tasks:
            spent = budget.spend_by_stage().get(a.stage, 0.0) - start
            if spent >= a.max_usd:
                stopped = f"budget: spent ${spent:.4f} >= ${a.max_usd:.2f} before {tid}"
                print("STOP", stopped)
                break
            log.start_task(tid)
            u, _ = run_task_without_injection_tasks(suite, pipeline, suite.user_tasks[tid], logdir,
                                                    force_rerun=True, benchmark_version=a.benchmark_version)
            utility[tid] = bool(u)
            c = log.tasks[tid]["counts"]
            print(f"{tid}: utility={u} allow={c['allow']} block={c['block']} ask={c['ask']}", flush=True)

    spent = budget.spend_by_stage().get(a.stage, 0.0) - start
    summary = {"run": a.run, "suite": a.suite, "tasks_run": len(utility), "utility": utility,
               "utility_rate": sum(utility.values()) / max(1, len(utility)), "gate": log.counts(),
               "spent_usd": round(spent, 4), "stopped": stopped}
    (logdir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "utility"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
