"""Pins the adaptive-case results of the frozen gate (eval/ADAPTIVE_V0.md): which cases get through, and that
every other case is blocked or asked. A change in either direction should be noticed and reported.
Run: `.venv\\Scripts\\python tests/test_adaptive.py` (offline)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adaptive_cases as ac  # noqa: E402


def test_known_gaps_are_exactly_the_allowed_cases():
    rows = [ac.run_case(c) for c in ac.cases()]
    allowed = {r["case"] for r in rows if r["action"] == "allow"}
    assert allowed == ac.KNOWN_ALLOWED, (allowed - ac.KNOWN_ALLOWED, ac.KNOWN_ALLOWED - allowed)
    assert all(r["action"] in ("block", "ask") for r in rows if r["case"] not in ac.KNOWN_ALLOWED)


def test_every_obfuscation_variant_is_blocked_in_both_channels():
    names = {v[0] for v in ac.VARIANTS}
    rows = [ac.run_case(c) for c in ac.cases() if c.name in names]
    assert len(rows) == 2 * len(names)
    assert {r["action"] for r in rows} == {"block"}


def test_branch_steering_gap_is_open():
    """Pinned: all arguments trace, so the gate allows a call that only untrusted text asked for."""
    from agentgate.policy_attach import AttachGate, attach_policy

    high = lambda text: 0.99  # noqa: E731
    assert {c.channel for c in ac.BRANCH_STEERING} == {"tool text", "image text"}
    for c in ac.BRANCH_STEERING:
        for r in (ac.run_case(c), ac.run_case(c, attach_policy(), AttachGate), ac.run_case(c, scorer=high)):
            assert r["action"] == "allow", r["reason"]
            assert r["verdicts"] == ["ok", "ok"], r["verdicts"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
