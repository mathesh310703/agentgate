"""AgentGate as an MCP server (stdio): an agent host asks the gate before it runs a tool call.

A thin wrapper. Decisions come from Gate.check unchanged (gate-final.1); this file only keeps one
Session per server process and turns tool arguments into Session records.

Tools:
  reset(user_request)                   start a new session; the request is the only trusted text
  observe_text(tool, output)            record a tool result (untrusted text; JSON is split into fields)
  observe_image(path, source)           OCR an image file, record its text as untrusted pixels
  check(tool, arguments)                allow / block / ask, with the reason and the text to return to the agent

  python agentgate/mcp_server.py        # stdio; launched by the MCP client (see scripts/mcp_demo.py)
  python agentgate/mcp_server.py --strict   # strict mode (agentgate/fields_strict.py), off by default

OCR needs rapidocr-onnxruntime (agentgate/pixels.py). Without it, set AGENTGATE_OCR_TEXT_DIR to a folder of
saved OCR text, <dir>/<image file name>.txt (e.g. eval/vision_demo/set2/ocr); the tests do this.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from agentgate import Gate, Session, default_workspace_policy  # noqa: E402
from agentgate.adapters.agentdojo_adapter import gate_message  # noqa: E402
from agentgate.fields_strict import make_session  # noqa: E402

ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

policy = default_workspace_policy()
gate = Gate(policy)
state = {"session": None, "strict": "--strict" in sys.argv[1:]}
server = MCPServer("agentgate", instructions="Ask check() before running any tool call; run it only on allow.")


def _session() -> Session:
    if state["session"] is None:
        raise ValueError("call reset(user_request) first")
    return state["session"]


def _ocr(path: Path) -> str:
    saved = os.environ.get("AGENTGATE_OCR_TEXT_DIR")
    if saved:
        return (Path(saved) / f"{path.name}.txt").read_text(encoding="utf-8")
    from agentgate.pixels import extract_text

    return extract_text(path.read_bytes())


@server.tool()
def reset(user_request: str) -> dict:
    """Start a new session. The user's request is the only trusted text."""
    state["session"] = make_session(user_request, policy, strict=state["strict"])
    return {"ok": True, "trusted": user_request, "strict": state["strict"]}


@server.tool()
def observe_text(tool: str, output: str) -> dict:
    """Record a tool result as untrusted text. A JSON object or list is split into structured and free-text fields."""
    try:
        value = json.loads(output)
    except (TypeError, ValueError):
        value = output
    _session().add_tool_output(tool, value)
    return {"ok": True, "label": "untrusted_text", "source": tool}


@server.tool()
def observe_image(path: str, source: str = "") -> dict:
    """OCR an image file and record its text as untrusted pixels under screenshot:<source>."""
    p = Path(path)
    text = _ocr(p)
    source = source or p.name
    _session().add_pixels(text, source)
    return {"ok": True, "label": "untrusted_pixels", "source": f"screenshot:{source}",
            "lines": len(text.splitlines()), "addresses": _addresses(text)}


def _addresses(text: str) -> list:
    """Email addresses in the OCR text, most frequent first, then shortest (OCR sometimes glues a word on)."""
    found = [a.lower().rstrip(".") for a in ADDRESS.findall(text)]
    return sorted(set(found), key=lambda a: (-found.count(a), len(a), a))


@server.tool()
def check(tool: str, arguments: dict) -> dict:
    """Decide on one tool call before it runs: allow, block or ask."""
    d = gate.check(tool, arguments, _session())
    return {"action": d.action, "reason": d.explain(),
            "message_to_agent": None if d.allowed else gate_message(d)}


if __name__ == "__main__":
    server.run("stdio")
