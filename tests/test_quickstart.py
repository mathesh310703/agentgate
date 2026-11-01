"""examples/quickstart.py runs offline and gives the four documented decisions.
Run with the venv: `.venv\\Scripts\\python tests/test_quickstart.py`."""

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_quickstart_decisions():
    t = time.time()
    out = subprocess.run([sys.executable, str(ROOT / "examples" / "quickstart.py")], capture_output=True, text=True,
                         encoding="utf-8", timeout=60, check=True).stdout
    assert re.findall(r"-> (\w+):", out) == ["ALLOW", "BLOCK", "BLOCK", "ALLOW"], out
    assert "screenshot:invoice_00.png" in out
    assert time.time() - t < 60


if __name__ == "__main__":
    test_quickstart_decisions()
    print("ok test_quickstart_decisions\n1 passed")
