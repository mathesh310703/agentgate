"""Build demo/replay.html: one self-contained page (CSS, JS, trace data, images as base64) that replays
the set-2 vision worst case episode by episode. No external requests, no model calls, no cost.

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


def build_data():
    trace = load(HERE / "trace.json")
    runs = load(ROOT / "runs" / "vision_wc_set2.json")["results"]
    manifest = {m["image"]: m for m in load(SET / "manifest.json")}
    by_arm = {(r["arm"], r["image"]): r for r in runs}
    episodes = []
    for e in trace["episodes"]:
        m = manifest[e["image"]]
        steps = [s for s in e["steps"] if "tool_call" in s]
        saw = e["steps"][0]["agent_saw"]
        episodes.append({
            "image": e["image"], "carrier": e["carrier"], "style": e["carrier_style"],
            "carrier_text": e["carrier_text"], "address": m.get("carrier_address"),
            "request": saw[0]["user_request"], "ocr": saw[1]["recovered_text"],
            "answer": e["steps"][-1]["final_answer"],
            "calls": [{"tool": s["tool_call"]["tool"], "args": s["tool_call"]["args"], "decision": s["decision"],
                       "reason": s["reason"],
                       "sources": [{k: v for k, v in src.items() if k != "recovered_text"} for src in s["sources"]]}
                      for s in steps],
            "shared_off": by_arm[("none", e["image"])]["shares"],
            "shared_on": by_arm[("gate", e["image"])]["shares"],
        })
    # carriers first, then clean images, each in file order
    episodes.sort(key=lambda x: (not x["carrier"], x["image"]))
    images = {e["image"]: "data:image/png;base64," + base64.b64encode((SET / "images" / e["image"]).read_bytes())
              .decode() for e in episodes}
    vis = load(ROOT / "eval" / "vision_demo" / "results.json")
    model = [r for k, r in vis.items() if k.startswith("none/") and r["carrier"]]
    return {"episodes": episodes, "images": images,
            "model_refused": sum(not r["attack_success"] for r in model), "model_carriers": len(model)}


def build(out: Path):
    data = build_data()
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (HERE / "replay_template.html").read_text(encoding="utf-8").replace("/*__DATA__*/null", blob)
    out.write_text(html, encoding="utf-8")
    return data


def screenshot(page_path: Path, png: Path, theme="light", hash_="#ep=0&gate=on"):
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
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB, {len(data['episodes'])} episodes)")
    if a.screenshot:
        external, errors = screenshot(out, HERE / "screenshot.png")
        print("external requests:", external or "none", "| page errors:", errors or "none")


if __name__ == "__main__":
    main()
