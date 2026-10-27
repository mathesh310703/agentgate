"""Offline tests for the budget manager (no API calls). Run: python tests/test_llm_budget.py"""

import csv
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from agentlab import llm  # noqa: E402


def _with_log(rows):
    d = tempfile.mkdtemp()
    llm.COST_LOG = Path(d) / "cost_log.csv"
    with open(llm.COST_LOG, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=llm.COST_FIELDS)
        w.writeheader()
        for stage, cost in rows:
            w.writerow({"stage": stage, "cost_usd": cost, "prompt_tokens": 0, "completion_tokens": 0})


def _raises(exc, fn, *a):
    try:
        fn(*a)
    except exc:
        return True
    return False


def test_stage_budget_refuses():
    _with_log([("dev", 4.99)])
    assert _raises(llm.StageBudgetExceeded, llm.check_budget, "dev", 0.02)
    llm.check_budget("baseline", 0.02)  # other stages unaffected


def test_unknown_stage():
    _with_log([])
    assert _raises(ValueError, llm.check_budget, "oops", 0.01)


def test_total_confirmation():
    _with_log([("baseline", 14.0), ("defense", 3.99)])
    os.environ.pop(llm.CONFIRM_ENV, None)
    assert _raises(llm.ConfirmationRequired, llm.check_budget, "defense", 0.02)
    os.environ[llm.CONFIRM_ENV] = "1"
    llm.check_budget("defense", 0.02)
    os.environ.pop(llm.CONFIRM_ENV)


def test_screenshot_downscale():
    buf = io.BytesIO()
    Image.new("RGB", (1280, 800), "white").save(buf, "PNG")
    jpeg, scale = llm.prepare_screenshot(buf.getvalue())
    img = Image.open(io.BytesIO(jpeg))
    assert img.format == "JPEG" and img.size == (768, 480) and abs(scale - 0.6) < 1e-9
    small = io.BytesIO()
    Image.new("RGB", (500, 300), "white").save(small, "PNG")
    assert Image.open(io.BytesIO(llm.prepare_screenshot(small.getvalue())[0])).size == (500, 300)


def test_worst_case_includes_full_output():
    msg = llm.text_msg("user", "hi")
    assert llm.worst_case_cost([msg], 2000) >= 2000 * llm.PRICE_PER_M["output"] / 1e6


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} passed")
