"""Which images leak in the live demo's harness, and how long a run takes. Real local Qwen3-VL-2B, greedy, every run a fresh
generation (no reply cache). No API cost. Picks the demo's scenarios; results in runs/live_demo_v0/.

  .venv\\Scripts\\python scripts/measure_live_demo.py --repeats 5 --out runs/live_demo_v0
"""

import argparse
import json
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "demo"), str(ROOT / "eval" / "vision_demo")]

import live  # noqa: E402
import run_local as rl  # noqa: E402

CANDIDATES = [("1", "invoice_01_c.png"), ("1", "invoice_05_c.png"), ("1", "invoice_09_c.png"), ("2", "notice_09.png"),
              ("1", "notice_01_c.png"), ("2", "notice_01.png"), ("1", "notice_02.png"), ("1", "notice_06.png")]


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(max(0.0, c - h) * 100, 1), round(min(1.0, c + h) * 100, 1)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*", help="set/image pairs such as 1/invoice_05_c.png; default: all candidates")
    ap.add_argument("--file", default="scenarios.json")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rl.load()
    report = {"decoding": "greedy", "repeats": a.repeats, "model": rl.MODEL_ID, "images": {}}
    for set_name, image in ([tuple(x.split("/")) for x in a.only] if a.only else CANDIDATES):
        m = live.manifest_entry(set_name, image)
        row = {"carrier": m["carrier"], "style": m["carrier_style"], "runs": {"off": [], "on": []}}
        for label, gate_on in (("off", False), ("on", True)):
            for _ in range(a.repeats):
                events = []
                with tempfile.TemporaryDirectory() as tmp:
                    rl.CACHE = Path(tmp)
                    live.run_episode(m, set_name, gate_on, rl.call_model, events.append)
                done = events[-1]
                row["runs"][label].append({
                    **{k: done[k] for k in ("seconds", "model_seconds", "leaked", "answered", "calls", "blocks", "hit_turn_cap")},
                    "shares": done["shares"],
                    "first_decisions": [(e["tool"], e["action"]) for e in events if e["type"] == "decision"][:4]})
            runs = row["runs"][label]
            leaks = sum(r["leaked"] for r in runs)
            row[label] = {"leaks": leaks, "n": len(runs), "wilson_95": wilson(leaks, len(runs)),
                          "answered": sum(r["answered"] for r in runs),
                          "seconds_median": statistics.median(r["seconds"] for r in runs),
                          "seconds_max": max(r["seconds"] for r in runs)}
            print(set_name, image, label, json.dumps(row[label]), json.dumps(runs[0]["first_decisions"]), runs[0]["shares"], flush=True)
        report["images"][f"set{set_name}/{image}"] = row
        (out / a.file).write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
