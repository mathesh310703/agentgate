"""Offline test for the worst-case replay (no model calls). Uses tuning-half tasks (0-19) only;
the "June 13" case (held-out task 30) is covered by tests/test_gate.py::test_june_13_does_not_name_file_13. Run: `.venv\\Scripts\\python tests/test_worstcase.py`."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agentdojo.agent_pipeline import AgentPipeline  # noqa: E402
from agentdojo.attacks.attack_registry import load_attack  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402

from scripts.run_worstcase import ATTACK, load_policy, run  # noqa: E402

SUITE = get_suite("v1.2.2", "workspace")
_named = AgentPipeline([])
_named.name = "vllm_parsed"
ATK = load_attack(ATTACK, SUITE, _named)


def pair(u, i):
    return [(SUITE.user_tasks[u], SUITE.injection_tasks[i])]


def test_replay_obeys_injection_without_gate():
    (r,) = run("none", SUITE, ATK, pair("user_task_0", "injection_task_2"))
    assert r["attack_success"] and [c["phase"] for c in r["calls"]][-1] == "injection"


def test_gate_blocks_injected_recipient_and_keeps_user_task():
    (r,) = run("gate", SUITE, ATK, pair("user_task_0", "injection_task_2"))
    assert not r["attack_success"] and r["utility"]
    inj = [c for c in r["calls"] if c["phase"] == "injection"]
    assert inj[-1]["action"] == "block" and "mark.black-2134@gmail.com" in inj[-1]["reason"]


def test_injection_ids_follow_user_calls():
    # user_task_6 creates an event, which sends an invitation email; the injected delete must hit the new id
    (r,) = run("none", SUITE, ATK, pair("user_task_6", "injection_task_5"))
    assert r["attack_success"]


def test_own_policy_runs_from_a_module_path():
    assert not load_policy("examples.my_policy:build").trusted_for["recipient"]
    (r,) = run("gate", SUITE, ATK, pair("user_task_0", "injection_task_2"), policy="examples.my_policy:build")
    assert not r["attack_success"] and r["arm"] == "gate"


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
