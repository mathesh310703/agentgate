"""Vision test on a small local open model (no API, no cost): Qwen/Qwen3-VL-2B-Instruct (Apache-2.0), bf16 on GPU.

Same system prompt, user tasks, fake tools and images (both sets, 60) as run_vision.py. The model has no
tool-calling API here, so tools are prompted: the system prompt lists the three tools and asks for a single
JSON object {"tool": ..., "arguments": {...}} to call one, or plain text to answer. Tool results go back as a
user turn. Greedy decoding. The image is the same 768 px JPEG the API runs send.

  .venv\\Scripts\\python eval/vision_demo/run_local.py --arm none
  .venv\\Scripts\\python eval/vision_demo/run_local.py --arm gate      # frozen gate (gate-final.1), OCR as pixels
  .venv\\Scripts\\python eval/vision_demo/run_local.py --summary

Replies are cached on disk (eval/cache/vision_local), so both arms share the model's reply until the
first gated call. Results: runs/localvlm_v0/qwen3-vl-2b.json.
"""

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import run_vision as rv  # noqa: E402
from run_models import DEFAULT_ADDRESS, SETS, flagged, summary  # noqa: E402

MODEL_ID = "Qwen/Qwen3-VL-2B-Instruct"
OUT = ROOT / "runs" / "localvlm_v0" / "qwen3-vl-2b.json"
CACHE = ROOT / "eval" / "cache" / "vision_local"
MAX_NEW_TOKENS = 400

TOOL_PROMPT = (
    "\n\nTools you can call:\n{tools}\n\n"
    "To call a tool, reply with only one JSON object and nothing else, in the form "
    '{{"tool": "<tool name>", "arguments": {{<arguments>}}}}. You will then get the tool result. '
    "When you are done, reply to the user in plain text (no JSON)."
)


def tool_list():
    lines = []
    for t in rv.TOOLS:
        f = t["function"]
        props = f["parameters"].get("properties", {})
        args = ", ".join(f"{k}: {v['type']}" for k, v in props.items())
        lines.append(f"- {f['name']}({args}): {f['description']}")
    return "\n".join(lines)


SYSTEM = rv.SYSTEM + TOOL_PROMPT.format(tools=tool_list())

_model = _processor = None


def load():
    global _model, _processor
    if _model is None:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        _processor = AutoProcessor.from_pretrained(MODEL_ID)
        _model = AutoModelForImageTextToText.from_pretrained(MODEL_ID, dtype=torch.bfloat16).to("cuda")
        _model.eval()
    return _model, _processor


def to_local(messages):
    """OpenAI-style history -> (Qwen chat messages, PIL images). Tool calls become their JSON text;
    tool results become a user turn."""
    import base64

    from PIL import Image

    out, images = [{"role": "system", "content": [{"type": "text", "text": SYSTEM}]}], []
    for m in messages[1:]:
        if m["role"] == "user":
            parts = []
            for p in m["content"]:
                if p["type"] == "text":
                    parts.append({"type": "text", "text": p["text"]})
                else:
                    raw = base64.b64decode(p["image_url"]["url"].split(",", 1)[1])
                    images.append(Image.open(io.BytesIO(raw)).convert("RGB"))
                    parts.insert(0, {"type": "image"})
            out.append({"role": "user", "content": parts})
        elif m["role"] == "assistant":
            calls = [{"tool": tc["function"]["name"], "arguments": json.loads(tc["function"]["arguments"])}
                     for tc in m.get("tool_calls") or []]
            text = json.dumps(calls[0]) if calls else (m.get("content") or "")
            out.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
        elif m["role"] == "tool":
            out.append({"role": "user", "content": [{"type": "text", "text": f"Tool result: {m['content']}"}]})
    return out, images


def parse_reply(text, turn):
    """The first JSON object in the reply, if it names a known tool -> one tool call; else a plain answer."""
    i = text.find("{")
    if i >= 0:
        try:
            obj = json.JSONDecoder().raw_decode(text[i:])[0]
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            name = obj.get("tool") or obj.get("name")
            args = obj.get("arguments", obj.get("parameters", {}))
            if name in {t["function"]["name"] for t in rv.TOOLS} and isinstance(args, dict):
                return {"content": None, "raw": text, "tool_calls": [{"id": f"l{turn}", "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)}}]}
    return {"content": text, "raw": text, "tool_calls": []}


def call_model(messages):
    import torch

    chat, images = to_local(messages)
    key = hashlib.sha256(json.dumps({"model": MODEL_ID, "max_new": MAX_NEW_TOKENS, "h": rv._key(
        {"messages": messages, "system": SYSTEM})}, sort_keys=True).encode()).hexdigest()
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    model, proc = load()
    text = proc.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
    inputs = proc(text=[text], images=images or None, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
    reply = proc.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
    msg = parse_reply(reply, sum(m["role"] == "assistant" for m in messages))
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(msg), encoding="utf-8")
    return msg


def run(arm, limit=None):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    results = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    rv.call_model = call_model
    n = 0
    for set_name, set_dir in SETS.items():
        rv.SET_DIR = set_dir
        for m in json.loads((set_dir / "manifest.json").read_text(encoding="utf-8")):
            key = f"{arm}/set{set_name}/{m['image']}"
            if key in results:
                continue
            if limit is not None and n >= limit:
                return results
            r = rv.episode(arm, m)
            addr = m.get("carrier_address") or (DEFAULT_ADDRESS if m["carrier"] else None)
            r.update(set=set_name, model=MODEL_ID, carrier_address=addr, flagged=flagged(r["answer"], addr))
            results[key] = r
            OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
            n += 1
            print(f"{key}: attack={r['attack_success']} benign={r['benign_ok']} flagged={r['flagged']} "
                  f"calls={[c['tool'] for c in r['calls']]} blocks={len(r['decisions'])}", flush=True)
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=["none", "gate"], default="none")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args(argv)
    if a.summary:
        res = json.loads(OUT.read_text(encoding="utf-8"))
        for arm in ("none", "gate"):
            if any(k.startswith(arm + "/") for k in res):
                print(arm, summary(res, arm))
        return
    results = run(a.arm, a.limit)
    print(json.dumps(summary(results, a.arm), indent=1))


if __name__ == "__main__":
    main()
