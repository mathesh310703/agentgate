"""Set 3 summary: leaks per carrier style (Wilson 95%), distinct images that leaked, false blocks on the
30 clean images, and OCR recovery of the hidden address per style. Reads saved results only; no model calls.

  .venv\\Scripts\\python eval/vision_demo/set3_report.py
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from make_images import CARRIER_STYLES_3  # noqa: E402
from run_local import wilson  # noqa: E402

SET3 = HERE / "set3"
RUNS = {"qwen3-vl-2b (T=0.7, 3 samples)": ROOT / "runs" / "set3" / "qwen3-vl-2b_t0.7.json",
        "muse-spark-open (1 run)": ROOT / "runs" / "set3" / "meta-models__muse-spark-open-1026.json"}
ARMS = {"none": ("none",), "gate": ("gate", "gate_newmsg")}


def pct(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({100 * lo:.1f}–{100 * hi:.1f}%)"


def squash(s):
    return "".join(s.lower().split())


def ocr_recovery(manifest):
    out = {}
    for style in CARRIER_STYLES_3:
        car = [m for m in manifest if m["carrier_style"] == style]
        hit = [m for m in car if (SET3 / "ocr" / f"{m['image']}.txt").exists()
               and squash(m["carrier_address"]) in squash((SET3 / "ocr" / f"{m['image']}.txt").read_text(encoding="utf-8"))]
        out[style] = f"{len(hit)}/{len(car)}"
    return out


def model_rows(results, manifest):
    by_image = {m["image"]: m for m in manifest}
    rows = {}
    for arm, labels in ARMS.items():
        rs = [r for k, r in results.items() if k.split("/")[0] in labels]
        if not rs:
            continue
        car = [r for r in rs if r["carrier"]]
        clean = [r for r in rs if not r["carrier"]]
        row = {"episodes": len(rs), "leaks_all_carriers": pct(sum(r["attack_success"] for r in car), len(car))}
        for style in CARRIER_STYLES_3:
            s = [r for r in car if by_image[r["image"]]["carrier_style"] == style]
            row[style] = pct(sum(r["attack_success"] for r in s), len(s))
        row["distinct_images_leaked"] = sorted({r["image"] for r in car if r["attack_success"]})
        row["share_or_send_attempts_carriers"] = sum(any(c["tool"] in ("share_file", "send_email") for c in r["calls"])
                                                     for r in car)
        row["benign_ok"] = f"{sum(r['benign_ok'] for r in rs)}/{len(rs)}"
        row["no_answer"] = sum(not r["answer"] for r in rs)
        row["flagged_keyword_carriers"] = sum(r["flagged"] for r in car)
        if arm == "gate":
            fb = [r for r in clean if r["decisions"]]
            row["false_blocks_clean"] = pct(len(fb), len(clean))
            row["false_block_images"] = sorted({r["image"] for r in fb})
            row["blocks"] = sum(len(r["decisions"]) for r in rs)
        rows[arm] = row
    return rows


def main():
    manifest = json.loads((SET3 / "manifest.json").read_text(encoding="utf-8"))
    out = {"ocr_address_recovered": ocr_recovery(manifest)}
    for name, path in RUNS.items():
        if path.exists():
            out[name] = model_rows(json.loads(path.read_text(encoding="utf-8")), manifest)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
