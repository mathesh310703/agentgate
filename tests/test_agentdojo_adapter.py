"""Offline tests for the AgentDojo adapter on the real workspace environment (no model calls).
Run with the venv: `.venv\\Scripts\\python tests/test_agentdojo_adapter.py`."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402

from agentgate import Gate, default_workspace_policy  # noqa: E402
from agentgate.adapters.agentdojo_adapter import SESSION_KEY, GatedToolsExecutor, GateLog  # noqa: E402

SUITE = get_suite("v1.2.2", "workspace")


def setup(tmp):
    env = SUITE.load_and_inject_default_environment({})
    runtime = FunctionsRuntime(SUITE.tools)
    log = GateLog(Path(tmp) / "gate_log.json", run="test")
    log.start_task("t")
    return env, runtime, log, GatedToolsExecutor(Gate(default_workspace_policy()), log)


def turn(*calls):
    return [{"role": "user", "content": []},
            {"role": "assistant", "content": None,
             "tool_calls": [FunctionCall(function=f, args=a, id=f"c{i}") for i, (f, a) in enumerate(calls)]}]


def test_untraced_recipient_is_blocked_and_not_sent():
    with tempfile.TemporaryDirectory() as tmp:
        env, runtime, log, ex = setup(tmp)
        n_sent = len(env.inbox.sent)
        _, _, env, msgs, extra = ex.query("Summarise my inbox", runtime, env,
                                          turn(("send_email", {"recipients": ["x@y.test"], "subject": "s",
                                                               "body": "b"})), {})
        assert len(env.inbox.sent) == n_sent
        assert "AgentGate did not run this call" in msgs[-1]["content"][0]["content"]
        assert msgs[-1]["tool_call_id"] == "c0"
        data = json.loads(Path(tmp, "gate_log.json").read_text())
        assert data["counts"]["all_calls"]["block"] == 1


def test_allowed_call_runs_and_feeds_session():
    with tempfile.TemporaryDirectory() as tmp:
        env, runtime, log, ex = setup(tmp)
        _, _, env, msgs, extra = ex.query("Who is in my contacts?", runtime, env,
                                          turn(("search_contacts_by_name", {"query": "Lily"})), {})
        session = extra[SESSION_KEY]
        added = [r for r in session.records if r.source == "search_contacts_by_name"]
        assert added and all(r.part == "structured" for r in added)   # raw pydantic result, split into fields
        assert any(r.field == "email" and r.text in msgs[-1]["content"][0]["content"] for r in added)
        assert log.counts()["all_calls"]["allow"] == 1


def test_error_text_is_free_text():
    with tempfile.TemporaryDirectory() as tmp:
        env, runtime, log, ex = setup(tmp)
        _, _, env, msgs, extra = ex.query("Who is in my contacts?", runtime, env,
                                          turn(("search_contacts_by_email", {"query": "nobody@corp.test"})), {})
        errs = [r for r in extra[SESSION_KEY].records if r.field == "error"]
        assert errs and errs[0].part == "free_text" and "nobody@corp.test" in errs[0].text


def test_user_named_recipient_is_sent_and_string_list_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        env, runtime, log, ex = setup(tmp)
        n_sent = len(env.inbox.sent)
        ex.query("Email david.smith@bluesparrowtech.com hello", runtime, env,
                 turn(("send_email", {"recipients": "['david.smith@bluesparrowtech.com']", "subject": "s", "body": "hello"})), {})
        assert len(env.inbox.sent) == n_sent + 1
        assert log.counts()["risky_calls"]["allow"] == 1


def test_session_does_not_leak_between_tasks():
    with tempfile.TemporaryDirectory() as tmp:
        env, runtime, log, ex = setup(tmp)
        shared = {}
        ex.query("first", runtime, env, turn(("get_current_day", {})), shared)
        assert SESSION_KEY not in shared


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
