"""AgentDojo (v0.1.35) adapter: the gate checks every tool call before it runs.

GatedToolsExecutor takes the place of agentdojo's ToolsExecutor inside ToolsExecutionLoop:

    ToolsExecutionLoop([GatedToolsExecutor(gate, log), llm])

For each tool call in the last assistant message:
  * the gate decides allow / block / ask against the run's Session;
  * allow: the call is run by agentdojo's own ToolsExecutor (same argument parsing, errors and
    output format as an ungated run) and its raw result (pydantic objects, before formatting) is added
    to the Session as untrusted text under the tool's name, split into structured and free-text fields;
    the error message, if any, is added as free text; with a scorer, free-text records get an
    injection score (detectors.py);
  * block / ask: the call is not run; the model gets a tool result holding the gate's explanation.
    In a benchmark nobody can answer an "ask", so it is treated like a block.

The Session is created from the user's prompt on the first tool call of a task and travels in
extra_args (a fresh dict per task), so tasks never share state.
"""

import json
from ast import literal_eval
from collections import Counter
from pathlib import Path

from agentdojo.agent_pipeline import BasePipelineElement, ToolsExecutor
from agentdojo.agent_pipeline.tool_execution import is_string_list, tool_result_to_str
from agentdojo.functions_runtime import EmptyEnv
from agentdojo.types import ChatToolResultMessage, text_content_block_from_string

from ..fields_strict import make_session
from ..gate import Gate

SESSION_KEY = "agentgate_session"
ACTIONS = ("allow", "block", "ask")


BLOCK_PREFIX = "Action not performed. Do not retry it. Tell the user why:"


def gate_message(decision) -> str:
    """The tool result the agent gets instead of a blocked or asked call (since Oct 31, 2026).
    Only this text changed; the decision itself is the gate's, unchanged since gate-final.1."""
    return f"{BLOCK_PREFIX} {decision.explain()}"


def gate_message_v0(decision) -> str:
    """The text used up to gate-final.1, kept to compare how the agent reacts to each."""
    if decision.action == "ask":
        return f"AgentGate did not run this call; it needs the user's confirmation. {decision.explain()}"
    return f"AgentGate did not run this call. {decision.explain()}"


class GateLog:
    """Counts allow / block / ask per run and per task; rewritten to a JSON file after every decision."""

    def __init__(self, path, run: str = ""):
        self.path = Path(path)
        self.run = run
        self.task = None
        self.tasks = {}

    def start_task(self, task_id: str) -> None:
        self.task = task_id
        self.tasks.setdefault(task_id, {"counts": dict.fromkeys(ACTIONS, 0), "decisions": []})
        self.save()

    def record(self, query: str, tool: str, args: dict, decision, risky: bool) -> None:
        task = self.tasks.setdefault(self.task or query, {"counts": dict.fromkeys(ACTIONS, 0), "decisions": []})
        task["counts"][decision.action] += 1
        task["decisions"].append({"tool": tool, "args": args, "action": decision.action, "risky": risky,
                                  "reason": decision.reason})
        self.save()

    def counts(self) -> dict:
        total = Counter()
        for t in self.tasks.values():
            total.update(t["counts"])
        risky = Counter(d["action"] for t in self.tasks.values() for d in t["decisions"] if d["risky"])
        return {"all_calls": {a: total[a] for a in ACTIONS}, "risky_calls": {a: risky[a] for a in ACTIONS}}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"run": self.run, "counts": self.counts(), "tasks": self.tasks}
        self.path.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")


class GatedToolsExecutor(BasePipelineElement):
    def __init__(self, gate: Gate, log: GateLog = None, tool_output_formatter=tool_result_to_str,
                 scorer=None, strict: bool = False) -> None:
        self.gate = gate
        self.log = log
        self.scorer = scorer   # optional injection scorer (detectors.PromptGuard) for the Session
        self.strict = strict   # strict mode (agentgate/fields_strict.py): only identity fields vouch for recipients
        self._raw = None

        def capture(result):   # keep the structured result the tool returned, then format as usual
            self._raw = result
            return tool_output_formatter(result)

        self.executor = ToolsExecutor(capture)

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        if not messages or messages[-1]["role"] != "assistant" or not messages[-1]["tool_calls"]:
            return query, runtime, env, messages, extra_args

        session = extra_args.get(SESSION_KEY)
        if session is None:
            session = make_session(query, self.gate.policy, scorer=self.scorer, strict=self.strict)
            extra_args = {**extra_args, SESSION_KEY: session}

        last = messages[-1]
        results = []
        for call in last["tool_calls"]:
            # same list parsing ToolsExecutor does, so the gate sees the arguments the tool will get
            for k, v in call.args.items():
                if isinstance(v, str) and is_string_list(v):
                    call.args[k] = literal_eval(v)

            decision = self.gate.check(call.function, call.args, session)
            if self.log is not None:
                self.log.record(query, call.function, dict(call.args), decision,
                                risky=call.function in self.gate.policy.rules)

            if decision.allowed:
                self._raw = None
                _, _, env, out, _ = self.executor.query(query, runtime, env, [{**last, "tool_calls": [call]}],
                                                        extra_args)
                result = out[-1]
                session.add_tool_output(call.function, self._raw, error=result["error"])
            else:
                result = ChatToolResultMessage(role="tool", content=[text_content_block_from_string(gate_message(decision))],
                                               tool_call_id=call.id, tool_call=call, error=None)
            results.append(result)
        return query, runtime, env, [*messages, *results], extra_args
