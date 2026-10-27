"""Muse Spark Open smoke test: one text call, one call with a screenshot image.

Prints latency and token usage. Needs BASETEN_API_KEY in .env (see .env.example).
Uses the disk cache and cost log in agentlab/llm.py; stops on the budget or surprise-output guard.

  python scripts/spark_smoke.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentlab.llm import SparkClient, text_msg, total_spent  # noqa: E402


def screenshot_png() -> bytes:
    """A small synthetic 'screenshot' with a known code word, so the answer can be checked."""
    img = Image.new("RGB", (800, 450), (245, 247, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 800, 56], fill=(40, 60, 90))
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    d.text((20, 12), "Demo Dashboard", fill="white", font=font)
    d.text((40, 200), "Today's code word: BLUE-42", fill=(20, 20, 20), font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def show(name, r, expected=None):
    ok = "" if expected is None else f"  answer ok: {expected.lower() in r.text.lower()}"
    print(f"{name}: latency {r.latency_s:.2f}s  prompt {r.prompt_tokens}  output {r.completion_tokens} "
          f"(reasoning {r.reasoning_tokens})  cost ${r.cost_usd:.5f}  cached {r.cached}{ok}")
    print(f"  reply: {r.text.strip()[:120]!r}")


def main() -> int:
    c = SparkClient()
    r = c.chat([text_msg("user", "Reply with exactly one word: OK")], expect_out=10, tag="smoke_text")
    show("text", r, "OK")
    r = c.chat([text_msg("user", "What is the code word in this screenshot? Reply with the code word only.",
                         [screenshot_png()])], expect_out=10, tag="smoke_vision")
    show("vision", r, "BLUE-42")
    print(f"total spent so far: ${total_spent():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
