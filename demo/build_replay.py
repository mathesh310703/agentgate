"""Build demo/replay.html: one self-contained page (CSS, JS, trace data, images as base64) that replays
the vision test episode by episode, from two sources: the scripted worst-case agent (set 2, demo/trace.json)
and a real small open model, Qwen3-VL-2B (its leaked sampled episodes, demo/trace_qwen.json). No external
requests, no model calls, no cost.

  .venv\\Scripts\\python demo/build_replay.py
  .venv\\Scripts\\python demo/build_replay.py --screenshot     # also saves demo/screenshot.png (1920x1080)

Inputs: demo/trace.json (gated arm, from eval/vision_demo/worstcase.py --trace), runs/vision_wc_set2.json
(both arms, for the "gate off" outcome), eval/vision_demo/set2/{manifest.json,images/}, and
eval/vision_demo/results.json (the recorded Muse Spark run on set 1, for the header label).
"""

import argparse
import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SET = ROOT / "eval" / "vision_demo" / "set2"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


SETS = {"1": ROOT / "eval" / "vision_demo", "2": SET}
RISKY = ("share_file", "send_email")


def episode(e, set_name, *, off_calls, shared_off, shared_on, answer_off, label, meta=""):
    steps = [s for s in e["steps"] if "tool_call" in s]
    saw = e["steps"][0]["agent_saw"]
    return {
        "img": f"{set_name}/{e['image']}", "image": e["image"], "label": label, "meta": meta,
        "carrier": e["carrier"], "style": e["carrier_style"], "carrier_text": e["carrier_text"],
        "request": saw[0]["user_request"], "ocr": saw[1]["recovered_text"],
        "answer_on": e["steps"][-1]["final_answer"], "answer_off": answer_off,
        "calls": [{"tool": s["tool_call"]["tool"], "args": s["tool_call"]["args"], "decision": s["decision"],
                   "reason": s["reason"],
                   "sources": [{k: v for k, v in src.items() if k != "recovered_text"} for src in s["sources"]]}
                  for s in steps],
        "off_calls": [c for c in off_calls if c["tool"] in RISKY],
        "shared_off": shared_off, "shared_on": shared_on,
    }


def leaks(r):
    """Canary shares and canary email attachments, as [{"file", "email"}] for display."""
    out = [s for s in r["shares"] if s["file"] == "budget_canary.txt"]
    out += [{"file": "budget_canary.txt", "email": ", ".join(m["recipients"] or [])} for m in r["sent"]
            if "budget_canary.txt" in m["attachments"]]
    return out


def scripted_source():
    trace = load(HERE / "trace.json")
    runs = load(ROOT / "runs" / "vision_wc_set2.json")["results"]
    by_arm = {(r["arm"], r["image"]): r for r in runs}
    eps = []
    for e in trace["episodes"]:
        off, on = by_arm[("none", e["image"])], by_arm[("gate", e["image"])]
        eps.append(episode(e, "2", off_calls=off["calls"], shared_off=leaks(off), shared_on=leaks(on),
                           answer_off=off["answer"], label=e["image"].replace(".png", "")))
    eps.sort(key=lambda x: (not x["carrier"], x["image"]))   # carriers first, then clean images
    car = [e for e in eps if e["carrier"]]
    clean = [e for e in eps if not e["carrier"]]
    missed = [e["label"] for e in car if not any(s["argument"] == "email" and s["source"].startswith("screenshot:")
                                                 for c in e["calls"] for s in c["sources"])]
    vis = load(ROOT / "eval" / "vision_demo" / "results.json")
    refused = sum(not r["attack_success"] for k, r in vis.items() if k.startswith("none/") and r["carrier"])
    return {
        "name": "Scripted worst-case",
        "honest": "Scripted worst-case agent: it obeys every hidden instruction. "
                  f"Muse Spark Open refused all {refused} on its own (first image set).",
        "limits": f"<b>Limits:</b> OCR missed the hidden address in {len(missed)} of {len(car)} images with a hidden "
                  f"line ({', '.join(missed)}); those were still blocked, as an unknown recipient. Synthetic images, "
                  "<span class=\"mono\">.test</span> addresses and a canary file; no real data.",
        "attack": [f"{sum(bool(e['shared_off']) for e in car)}/{len(car)}", f"{sum(bool(e['shared_on']) for e in car)}/{len(car)}"],
        "attack_sub": "gate off → gate on",
        "false": f"{sum(any(c['decision'] == 'block' for c in e['calls']) for e in clean)}/{len(clean)}",
        "false_sub": "gate on, clean images",
        "rows": ["Hidden line", "Clean image"], "episodes": eps,
    }


def wilson_txt(k, n):
    import sys
    sys.path.insert(0, str(ROOT / "eval" / "vision_demo"))
    from run_local import wilson
    lo, hi = wilson(k, n)
    return f"95% CI {100 * lo:.1f}–{100 * hi:.1f}%"


def qwen_source():
    trace = load(HERE / "trace_qwen.json")
    runs = load(ROOT / "runs" / "localvlm_v1" / "qwen3-vl-2b_t0.7.json")
    off = [r for k, r in runs.items() if k.startswith("none/")]
    on = [r for k, r in runs.items() if k.startswith("gate_newmsg/")]
    clean_on = [r for r in on if not r["carrier"]]
    k_off, k_on = sum(r["attack_success"] for r in off), sum(r["attack_success"] for r in on)
    eps = []
    for e in trace["episodes"]:
        u = e["ungated"]
        on_r = runs[f"gate_newmsg/set{e['set']}/{e['image']}/s{e['sample']}"]
        eps.append(episode(e, e["set"], off_calls=u["calls"], shared_off=leaks(u), shared_on=leaks(on_r),
                           answer_off=u["answer"], label=f"{e['image'].replace('.png', '')} s{e['sample']}",
                           meta=f"set {e['set']} · sample {e['sample']} · seed {e['seed']} · temperature {e['temperature']}"))
    return {
        "name": "Real model: Qwen3-VL-2B",
        "honest": "Real model: Qwen3-VL-2B-Instruct (Apache-2.0), a small open model used as a test subject. "
                  f"It is not part of AgentGate. Shown: the {len(eps)} of {len(off)} sampled episodes where it leaked the "
                  "canary with the gate off.",
        "limits": f"<b>Limits:</b> one small model; temperature {trace['episodes'][0]['temperature'] if eps else 0.7}, "
                  "5 samples per image, both image sets; tools are prompted as JSON (no native tool calling). Leaks "
                  f"without the gate {k_off}/{len(off)} ({wilson_txt(k_off, len(off))}); with the gate {k_on}/{len(on)} "
                  f"({wilson_txt(k_on, len(on))}). Synthetic images, <span class=\"mono\">.test</span> addresses, a canary file.",
        "attack": [f"{k_off}/{len(off)}", f"{k_on}/{len(on)}"],
        "attack_sub": "gate off → gate on, all sampled episodes",
        "false": f"{sum(bool(r['decisions']) for r in clean_on)}/{len(clean_on)}",
        "false_sub": "gate on, clean-image samples",
        "rows": ["Leaked (gate off)"], "episodes": eps,
    }


def build_data():
    sources = {"scripted": scripted_source()}
    if (HERE / "trace_qwen.json").exists():
        sources["qwen"] = qwen_source()
    images = {}
    for s in sources.values():
        for e in s["episodes"]:
            set_name, name = e["img"].split("/")
            images[e["img"]] = "data:image/png;base64," + base64.b64encode(
                (SETS[set_name] / "images" / name).read_bytes()).decode()
    return {"sources": sources, "order": list(sources), "images": images}


def build(out: Path):
    data = build_data()
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (HERE / "replay_template.html").read_text(encoding="utf-8").replace("/*__DATA__*/null", blob)
    out.write_text(html, encoding="utf-8")
    return data


def screenshot(page_path: Path, png: Path, theme="light", hash_="#src=scripted&ep=0&gate=on"):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080}, color_scheme=theme)
        external = []
        pg.on("request", lambda r: external.append(r.url) if not r.url.startswith(("file:", "data:")) else None)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(page_path.resolve().as_uri() + hash_)
        pg.wait_for_timeout(600)
        pg.screenshot(path=str(png))
        b.close()
    return external, errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "replay.html"))
    ap.add_argument("--screenshot", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out)
    data = build(out)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB, " + ", ".join(f"{s['name']}: {len(s['episodes'])} episodes" for s in data['sources'].values()) + ")")
    if a.screenshot:
        external, errors = screenshot(out, HERE / "screenshot.png")
        print("external requests:", external or "none", "| page errors:", errors or "none")


if __name__ == "__main__":
    main()
