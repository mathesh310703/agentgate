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


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
