"""Muse Spark Open client (Baseten, OpenAI-compatible) with budgets, a disk cache and a cost log.

* Key: BASETEN_API_KEY from the environment or .env (python-dotenv). Never printed or logged.
* Stages: every call declares one of STAGE_BUDGETS. A call whose worst-case cost would push
  that stage past its budget is refused with StageBudgetExceeded (nothing is sent).
* Total-spend confirmation: once total spend would pass CONFIRM_TOTAL_USD, calls are refused
  with ConfirmationRequired until AGENTGATE_CONFIRM_OVER_18=1 is set in the environment.
* Output cap: max_tokens <= MAX_TOKENS_CAP, reasoning included (Muse Spark Open always reasons).
* Surprise guard: SurpriseOutput if the visible answer (output minus reasoning) exceeds the
  caller's `expect_out` by more than SURPRISE_TOKENS.
* Screenshots: converted to JPEG, at most SCREENSHOT_WIDTH px wide, before sending.
* Cache: eval/cache/llm/<sha256>.json keyed by (model, prompt text, image hashes, params, salt);
  `salt` keeps repeated trials independent. Cost log: eval/cost_log.csv (uncached calls only).
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import math
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://inference.baseten.co/v1"
MODEL = "meta-models/muse-spark-open-1026"
PRICE_PER_M = {"input": 1.25, "cached_input": 0.15, "output": 4.25}  # baseten.co/pricing, Oct 2026
# Other Baseten models, USD per 1M tokens, from GET /v1/models "pricing" (prompt, input_cache_read,
# completion), read Oct 31, 2026. A model not listed here is priced at UNKNOWN_PRICE (see price_for).
MODEL_PRICES = {
    MODEL: PRICE_PER_M,
    "meta-models/muse-spark-open": PRICE_PER_M,
    "zai-org/GLM-5.3-Flash": {"input": 0.15, "cached_input": 0.015, "output": 0.50},
    "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B": {"input": 0.20, "cached_input": 0.02, "output": 0.50},
    "deepseek-ai/DeepSeek-V4.1-Flash-1017": {"input": 0.30, "cached_input": 0.03, "output": 1.20},
    "deepseek-ai/DeepSeek-V4.1-Flash": {"input": 0.30, "cached_input": 0.03, "output": 1.20},
    "zai-org/GLM-5.3": {"input": 1.40, "cached_input": 0.14, "output": 4.40},
    "moonshotai/Kimi-K3": {"input": 3.00, "cached_input": 0.30, "output": 15.00},
}
# Unknown model: the most expensive known price, field by field.
UNKNOWN_PRICE = {k: max(p[k] for p in MODEL_PRICES.values()) for k in PRICE_PER_M}


def price_for(model: str) -> Tuple[dict, bool]:
    """(USD per 1M tokens, known). An unknown model gets UNKNOWN_PRICE and known=False."""
    if model in MODEL_PRICES:
        return MODEL_PRICES[model], True
    return UNKNOWN_PRICE, False
STAGE_BUDGETS = {"dev": 5.0, "baseline": 15.0, "defense": 20.0, "benchmark": 30.0,
                 "arena": 20.0, "reserve": 10.0}
CONFIRM_TOTAL_USD = 18.0
CONFIRM_ENV = "AGENTGATE_CONFIRM_OVER_18"
MAX_TOKENS_CAP = 2000
SURPRISE_TOKENS = 100
SCREENSHOT_WIDTH = 768
JPEG_QUALITY = 85
CACHE_DIR = ROOT / "eval" / "cache" / "llm"
COST_LOG = ROOT / "eval" / "cost_log.csv"
COST_FIELDS = ["time", "stage", "tag", "model", "prompt_tokens", "cached_tokens", "completion_tokens",
               "reasoning_tokens", "finish_reason", "latency_s", "cost_usd"]


class BudgetError(RuntimeError):
    """Base class: the call was refused before anything was sent."""


class StageBudgetExceeded(BudgetError):
    pass


class ConfirmationRequired(BudgetError):
    pass


class SurpriseOutput(RuntimeError):
    pass


@dataclass
class Reply:
    text: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    finish_reason: str
    latency_s: float
    cost_usd: float
    cached: bool


def load_key() -> str:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    key = (os.environ.get("BASETEN_API_KEY") or "").strip().strip('"').strip("'")
    if not key:
        raise RuntimeError("BASETEN_API_KEY not set: add `BASETEN_API_KEY=...` to .env in the repo root")
    return key


# ---------- images ----------

def prepare_screenshot(image_bytes: bytes, width: int = SCREENSHOT_WIDTH) -> Tuple[bytes, float]:
    """Return (JPEG bytes at most `width` px wide, scale). Model coords / scale = original coords."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    scale = min(1.0, width / img.width)
    if scale < 1.0:
        img = img.resize((width, round(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue(), scale


def image_part(image_bytes: bytes, detail: str = "auto") -> dict:
    jpeg, _ = prepare_screenshot(image_bytes)
    url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    return {"type": "image_url", "image_url": {"url": url, "detail": detail}}


def text_msg(role: str, text: str, images: Sequence[bytes] = ()) -> dict:
    return {"role": role, "content": [{"type": "text", "text": text}, *[image_part(b) for b in images]]}


# ---------- spend accounting ----------

def read_log() -> List[dict]:
    if not COST_LOG.exists():
        return []
    with open(COST_LOG, newline="") as f:
        return list(csv.DictReader(f))


def spend_by_stage() -> Dict[str, float]:
    out: Dict[str, float] = defaultdict(float)
    for r in read_log():
        out[r.get("stage") or "unknown"] += float(r["cost_usd"])
    return dict(out)


def total_spent() -> float:
    return sum(spend_by_stage().values())


def cost_of(prompt_tokens: int, cached_tokens: int, completion_tokens: int, model: str = MODEL) -> float:
    p = price_for(model)[0]
    return ((prompt_tokens - cached_tokens) * p["input"] + cached_tokens * p["cached_input"]
            + completion_tokens * p["output"]) / 1e6


def worst_case_cost(messages: Sequence[dict], max_tokens: int, model: str = MODEL) -> float:
    """Upper-bound estimate: text at 1 token / 3 chars, each image as 28x28-px tiles, x2 margin,
    plus a full max_tokens of output."""
    from PIL import Image

    tokens = 0.0
    for m in messages:
        parts = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        for p in parts:
            if p.get("type") == "text":
                tokens += len(p["text"]) / 3
            elif p.get("type") == "image_url":
                b64 = p["image_url"]["url"].split(",", 1)[1]
                w, h = Image.open(io.BytesIO(base64.b64decode(b64))).size
                tokens += math.ceil(w / 28) * math.ceil(h / 28)
    return cost_of(int(2 * tokens) + 50, 0, max_tokens, model)


def check_budget(stage: str, est: float) -> None:
    if stage not in STAGE_BUDGETS:
        raise ValueError(f"unknown stage {stage!r}; use one of {list(STAGE_BUDGETS)}")
    by = spend_by_stage()
    spent = by.get(stage, 0.0)
    if spent + est > STAGE_BUDGETS[stage]:
        raise StageBudgetExceeded(
            f"stage '{stage}': spent ${spent:.4f} of ${STAGE_BUDGETS[stage]:.2f}; this call could cost up to "
            f"${est:.4f}. Refused; raise the stage budget or move work to another stage.")
    total = sum(by.values())
    if total + est > CONFIRM_TOTAL_USD and os.environ.get(CONFIRM_ENV) != "1":
        raise ConfirmationRequired(
            f"total spend ${total:.4f} + up to ${est:.4f} would pass ${CONFIRM_TOTAL_USD:.0f}. "
            f"Refused until you confirm: set {CONFIRM_ENV}=1.")


# ---------- client ----------

def _cache_key(model: str, messages: Sequence[dict], params: dict, salt: str) -> str:
    def strip(part):
        if isinstance(part, dict) and part.get("type") == "image_url":
            return {"image_sha256": hashlib.sha256(part["image_url"]["url"].encode()).hexdigest()}
        return part

    norm = [{"role": m["role"], "content": [strip(p) for p in m["content"]]
             if isinstance(m["content"], list) else m["content"]} for m in messages]
    blob = json.dumps({"model": model, "messages": norm, "params": params, "salt": salt}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


class SparkClient:
    def __init__(self, model: str = MODEL, reasoning_effort: Optional[str] = "low", use_cache: bool = True):
        from openai import OpenAI

        self.client = OpenAI(base_url=BASE_URL, api_key=load_key(), max_retries=5)
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.use_cache = use_cache

    def chat(self, messages: Sequence[dict], *, stage: str, expect_out: int, tag: str = "",
             salt: str = "", max_tokens: int = MAX_TOKENS_CAP) -> Reply:
        """One chat completion, charged to `stage`. `expect_out` = expected visible answer tokens."""
        max_tokens = min(max_tokens, MAX_TOKENS_CAP)
        params = {"max_tokens": max_tokens, "reasoning_effort": self.reasoning_effort}
        path = CACHE_DIR / f"{_cache_key(self.model, messages, params, salt)}.json"
        if self.use_cache and path.exists():
            return Reply(**{**json.loads(path.read_text()), "cached": True})

        check_budget(stage, worst_case_cost(messages, max_tokens, self.model))

        kwargs = {"model": self.model, "messages": list(messages), "max_tokens": max_tokens}
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        t0 = time.perf_counter()
        r = self.client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - t0

        u = r.usage
        cached_tok = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        reasoning = getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
        cost = cost_of(u.prompt_tokens, cached_tok, u.completion_tokens, self.model)
        reply = Reply(text=r.choices[0].message.content or "", prompt_tokens=u.prompt_tokens,
                      completion_tokens=u.completion_tokens, reasoning_tokens=reasoning,
                      finish_reason=r.choices[0].finish_reason or "", latency_s=round(latency, 3),
                      cost_usd=cost, cached=False)
        self._log(stage, tag, reply, cached_tok)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({k: v for k, v in reply.__dict__.items() if k != "cached"}))

        visible = u.completion_tokens - reasoning
        if visible > expect_out + SURPRISE_TOKENS:
            raise SurpriseOutput(f"{tag}: {visible} visible output tokens vs {expect_out} expected "
                                 f"(+{reasoning} reasoning)")
        return reply

    def _log(self, stage: str, tag: str, r: Reply, cached_tok: int) -> None:
        log_call(stage, tag, self.model, r.prompt_tokens, cached_tok, r.completion_tokens,
                 r.reasoning_tokens, r.finish_reason, r.latency_s, r.cost_usd)


def usage_numbers(usage) -> Tuple[int, int, int, int]:
    """(prompt, cached, completion, reasoning) tokens from an OpenAI-style usage object."""
    cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
    return usage.prompt_tokens, cached, usage.completion_tokens, reasoning


def log_call(stage: str, tag: str, model: str, prompt_tokens: int, cached_tokens: int,
             completion_tokens: int, reasoning_tokens: int, finish_reason: str, latency_s: float,
             cost_usd: float) -> None:
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not COST_LOG.exists()
    with open(COST_LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COST_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": stage,
                    "tag": tag, "model": model, "prompt_tokens": prompt_tokens, "cached_tokens": cached_tokens,
                    "completion_tokens": completion_tokens, "reasoning_tokens": reasoning_tokens,
                    "finish_reason": finish_reason, "latency_s": f"{latency_s:.3f}", "cost_usd": f"{cost_usd:.6f}"})
