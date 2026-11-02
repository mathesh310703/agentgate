"""The sample of scripts/run_attacktypes.py stays as fixed in eval/ATTACKTYPES_V0.md, and every attack's text builds from
AgentDojo alone. Offline, no model. Run: `.venv\\Scripts\\python tests/test_attacktypes.py`."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

import run_attacktypes as rat  # noqa: E402

from agentdojo.attacks.attack_registry import ATTACKS  # noqa: E402


def test_sample_is_the_written_rule():
    assert rat.USER_TASKS == ["user_task_0", "user_task_8", "user_task_16", "user_task_24", "user_task_32"]
    assert rat.GOALS == ["injection_task_0", "injection_task_1", "injection_task_2"]
    assert (rat.UNGATED_CAP, rat.TOTAL_CAP) == (2.0, 3.0)


def test_only_shipped_attacks_and_exclusions_are_explained():
    assert set(rat.ATTACK_TYPES) | set(rat.EXCLUDED) == set(ATTACKS)
    assert not set(rat.ATTACK_TYPES) & set(rat.EXCLUDED)
    assert len(rat.ATTACK_TYPES) == 11 and "important_instructions" in rat.ATTACK_TYPES


def test_every_attack_builds_for_every_pair():
    report = rat.check()
    assert report["episodes_per_arm"] == 165
    assert set(report["injection_slots"]) == set(rat.ATTACK_TYPES)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(len(tests), "passed")
