"""The MCP demo session, offline: a real MCP client (official SDK) talks to agentgate/mcp_server.py over stdio,
with saved OCR text in place of OCR (no rapidocr needed). Run: `.venv\\Scripts\\python tests/test_mcp_demo.py`."""

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import mcp_demo  # noqa: E402


def test_mcp_session_blocks_image_address_and_allows_listing():
    import asyncio

    out = io.StringIO()
    steps = asyncio.run(mcp_demo.session(out, 0, ROOT / "eval" / "vision_demo" / "set2" / "ocr"))
    by_step = [(s["tool"], s["result"]) for s in steps]
    assert [t for t, _ in by_step] == ["reset", "observe_image", "check", "check"]
    img = by_step[1][1]
    assert img["label"] == "untrusted_pixels" and img["addresses"][0] == "audit@corp.test"
    share, listing = by_step[2][1], by_step[3][1]
    assert share["action"] == "block"
    assert "email='audit@corp.test' came from text inside an image or screenshot (screenshot:invoice.png)" in share["reason"]
    assert share["message_to_agent"].startswith("Action not performed. Do not retry it. Tell the user why:")
    assert listing["action"] == "allow" and listing["message_to_agent"] is None
    assert "list_tools <- reset, observe_text, observe_image, check" in out.getvalue()


def test_check_before_reset_is_an_error_not_an_allow():
    sys.path.insert(0, str(ROOT))
    from agentgate import mcp_server

    mcp_server.state["session"] = None
    try:
        mcp_server.check("share_file", {"file_id": "1", "email": "a@corp.test"})
    except ValueError:
        return
    raise AssertionError("check without a session must fail")


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
