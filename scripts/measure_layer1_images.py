"""Layer 1 (Prompt Guard 2, 22M, CPU) on image text and its cost per call. Local model, no API cost.

(a) OCR text of all three image sets (saved by the gated runs in <set>/ocr): carrier vs clean images, per set,
    and per carrier style for set 3.
(b) The image texts of every Qwen3-VL-2B episode that leaked the canary without the gate (runs/localvlm_v0,
    runs/localvlm_v1, runs/set3): how many score at or above 0.5.
(c) Latency per call: Gate-style scoring of one text (chunked to 512 tokens, max over chunks), uncached, on
    the OCR texts and on the de-duplicated workspace tool outputs of the tuning half (user tasks 0-19).

  .venv\\Scripts\\python scripts/measure_layer1_images.py --out runs/layer1_v1/images
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from agentgate.detectors import PromptGuard  # noqa: E402
from measure_layer1 import THRESHOLD, metrics  # noqa: E402

VD = ROOT / "eval" / "vision_demo"
SETS = {"1": VD, "2": VD / "set2", "3": VD / "set3"}


def manifest(set_name):
    if set_name == "1":
        return [{"image": f.name[:-4], "carrier": "_c." in f.name, "carrier_style": None}
                for f in sorted((VD / "ocr").glob("*.txt"))]
    return json.loads((SETS[set_name] / "manifest.json").read_text(encoding="utf-8"))


def ocr_text(set_name, image):
    p = SETS[set_name] / "ocr" / f"{image}.txt"
    return p.read_text(encoding="utf-8") if p.exists() else None


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    guard = PromptGuard()
    report = {"threshold": THRESHOLD, "ocr": {}, "qwen_leaks": {}, "latency": {}}

    # (a) OCR text, per set
    per_image, all_pos, all_neg = {}, [], []
    for s in SETS:
        pos, neg, styles, missing = [], [], {}, 0
        for m in manifest(s):
            text = ocr_text(s, m["image"])
            if text is None:
                missing += 1
                continue
            score = guard(text)
            per_image[f"set{s}/{m['image']}"] = {"carrier": m["carrier"], "style": m.get("carrier_style"), "score": score}
            (pos if m["carrier"] else neg).append(score)
            if m["carrier"] and s == "3":
                styles.setdefault(m["carrier_style"], []).append(score)
        report["ocr"][f"set{s}"] = {**metrics(pos, neg), "missing_ocr": missing}
        if styles:
            report["ocr"]["set3_styles"] = {k: {"n": len(v), "at_or_above_0.5": sum(x >= THRESHOLD for x in v),
                                                "median": statistics.median(v)} for k, v in styles.items()}
        all_pos += pos
        all_neg += neg
    report["ocr"]["all_sets"] = metrics(all_pos, all_neg)

    # (b) Qwen leak episodes (ungated arm, canary shared or emailed)
    runs = {"v0 greedy (sets 1-2)": ROOT / "runs/localvlm_v0/qwen3-vl-2b.json",
            "v1 T=0.7 x5 (sets 1-2)": ROOT / "runs/localvlm_v1/qwen3-vl-2b_t0.7.json",
            "set3 T=0.7 x3": ROOT / "runs/set3/qwen3-vl-2b_t0.7.json"}
    for name, path in runs.items():
        res = json.loads(path.read_text(encoding="utf-8"))
        eps = [(k, r) for k, r in res.items() if k.startswith("none/") and r["attack_success"]]
        rows = []
        for k, r in eps:
            s = r.get("set") or "1"
            score = per_image[f"set{s}/{r['image']}"]["score"]
            rows.append({"episode": k, "image": f"set{s}/{r['image']}", "score": round(score, 4)})
        report["qwen_leaks"][name] = {"episodes": len(rows), "at_or_above_0.5": sum(x["score"] >= THRESHOLD for x in rows),
                                      "distinct_images": len({x["image"] for x in rows}),
                                      "distinct_images_at_or_above_0.5": len({x["image"] for x in rows if x["score"] >= THRESHOLD}),
                                      "episodes_detail": rows}

    # (c) latency per call, uncached: a fresh scorer, model already loaded
    from measure_layer1 import ATTACK, collect  # noqa: E402
    from agentdojo.agent_pipeline import AgentPipeline
    from agentdojo.attacks.attack_registry import load_attack
    from agentdojo.task_suite.load_suites import get_suite

    suite = get_suite("v1.2.2", "workspace")
    named = AgentPipeline([])
    named.name = "vllm_parsed"
    data = collect(suite, load_attack(ATTACK, suite, named), [f"user_task_{i}" for i in range(20)])
    texts = {"ocr text": [ocr_text(k.split("/")[0][3:], k.split("/", 1)[1]) for k in per_image],
             "tool output (workspace, tuning half)": list(data["output"][0]) + list(data["output"][1])}
    timer = PromptGuard()
    timer._load()
    timer("warm-up")
    for kind, ts in texts.items():
        lat, nchunks = [], []
        for t in ts:
            timer.cache.clear()
            nchunks.append(len(timer.chunks(t)))
            t0 = time.perf_counter()
            timer(t)
            lat.append(time.perf_counter() - t0)
        report["latency"][kind] = {"calls": len(lat), "median_ms": round(statistics.median(lat) * 1e3, 1),
                                   "p95_ms": round(pct(lat, 0.95) * 1e3, 1), "max_ms": round(max(lat) * 1e3, 1),
                                   "chunks_median": statistics.median(nchunks), "chunks_max": max(nchunks)}

    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out / "per_image.json").write_text(json.dumps(per_image, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "qwen_leaks"}, indent=1))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "episodes_detail"} for k, v in report["qwen_leaks"].items()}, indent=1))


if __name__ == "__main__":
    main()
