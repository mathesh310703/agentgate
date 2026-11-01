"""Set 3 images: 60 images, 30 carriers, six layouts, three carrier styles (10 each), neutral data only.
Run with the venv: `.venv\\Scripts\\python tests/test_set3.py` (offline; renders into a temp copy, no model calls)."""

import collections
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval" / "vision_demo"))

import make_images  # noqa: E402

ADDR = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def _render():
    with tempfile.TemporaryDirectory() as tmp:
        old = make_images.HERE
        make_images.HERE = Path(tmp)
        try:
            manifest = make_images.main_set3()
            shipped = json.loads((old / "set3" / "manifest.json").read_text(encoding="utf-8"))
        finally:
            make_images.HERE = old
    return manifest, shipped


def test_set3_shape_and_determinism():
    manifest, shipped = _render()
    assert manifest == shipped   # same seed -> same manifest as the one in the repo
    assert len(manifest) == 60 and sum(m["carrier"] for m in manifest) == 30
    kinds = collections.Counter(m["kind"] for m in manifest)
    assert len(kinds) == 6 and set(kinds.values()) == {10}
    styles = collections.Counter(m["carrier_style"] for m in manifest if m["carrier"])
    assert styles == {"direct_note": 10, "procedural_footnote": 10, "table_cell": 10}
    assert all(collections.Counter(m["kind"] for m in manifest if m["carrier"])[k] == 5 for k in kinds)


def test_set3_neutral_data():
    manifest, _ = _render()
    for m in manifest:
        text = json.dumps(m)
        assert all(a.group(0).endswith(".test") for a in ADDR.finditer(text)), m["image"]
        if m["carrier"]:
            assert "budget_canary.txt" in m["carrier_text"] and m["carrier_address"].endswith(".test")
        assert not re.search(r"password|card number|iban|cvv|login", text, re.I)
    for kind_text in (make_images.PEOPLE_3, make_images.CARRIER_ADDRESSES_3):
        assert all(a.endswith(".test") for a in kind_text)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
