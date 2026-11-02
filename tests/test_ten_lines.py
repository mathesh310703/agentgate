"""examples/ten_lines.py runs with no model, key or network, the README shows its real output, and the core package needs no
dependency. Run: `.venv\\Scripts\\python tests/test_ten_lines.py`."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "ten_lines.py"
NO_NETWORK = ("import socket, runpy\n"
              "def refuse(*a, **k): raise OSError('network used')\n"
              "socket.socket = refuse; socket.create_connection = refuse\n"
              f"runpy.run_path({str(EXAMPLE)!r}, run_name='__main__')\n")


def run_example():
    env = {k: v for k, v in os.environ.items() if "KEY" not in k and "TOKEN" not in k}
    env["PYTHONPATH"] = str(ROOT)
    r = subprocess.run([sys.executable, "-c", NO_NETWORK], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_runs_offline_with_one_allow_and_one_block_with_a_reason():
    lines = run_example().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("ana@corp.test: ALLOW.")
    assert lines[1].startswith("records@corp.test: BLOCK.") and "read_file" in lines[1]


def test_at_most_twelve_lines_and_only_agentgate():
    source = EXAMPLE.read_text(encoding="utf-8").splitlines()
    assert len(source) <= 12
    assert [s for s in source if s.startswith(("import ", "from "))] == ["from agentgate import Gate, Session, default_workspace_policy"]


def test_readme_shows_the_commands_and_the_real_output():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "pip install git+https://github.com/mathesh310703/agentgate" in readme
    assert "python examples/ten_lines.py" in readme
    assert run_example() in readme.replace("\r\n", "\n")
    assert "License: MIT" in readme and "**Built with Llama.**" in readme


def test_core_has_no_required_dependency_and_extras_are_declared():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == []
    assert project["license"] == "MIT" and project["license-files"] == ["LICENSE"]
    assert "2026 Matheshwaran Prakash" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    extras = project["optional-dependencies"]
    assert {"ocr", "mcp"} <= set(extras)
    assert any(d.startswith("agentdojo") for d in extras["mcp"])   # agentgate/mcp_server.py imports the adapter


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(len(tests), "passed")
