"""Muse Spark Open client (Baseten, OpenAI-compatible) with a disk cache, cost log and guards.

* Key: BASETEN_API_KEY from the environment or from .env in the repo root. Never printed.
* Cache: data/cache/llm/<sha256>.json, keyed by (model, prompt text, image hashes, params, salt).
  `salt` separates repeated trials of the same prompt, so trials are independent samples.
* Cost log: eval/cost_log.csv, one row per real (uncached) call.
* Guards: BudgetExceeded before a call that could push total spend past BUDGET_STOP_USD;
  SurpriseOutput after a call whose output tokens exceed the caller's expectation by more than
  SURPRISE_TOKENS. Both are meant to stop the run, not to be caught and ignored.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://inference.baseten.co/v1"
MODEL = "meta-models/muse-spark-open-1026"
PRICE_PER_M = {"input": 1.25, "cached_input": 0.15, "output": 4.25}  # baseten.co/pricing, Oct 2026
BUDGET_STOP_USD = 18.0  # stop before the $20 budget is reached
SURPRISE_TOKENS = 100
CACHE_DIR = ROOT / "data" / "cache" / "llm"
COST_LOG = ROOT / "eval" / "cost_log.csv"
COST_FIELDS = ["time", "tag", "model", "prompt_tokens", "cached_tokens", "completion_tokens",
               "reasoning_tokens", "latency_s", "cost_usd", "total_usd"]


class BudgetExceeded(RuntimeError):
    pass


class SurpriseOutput(RuntimeError):
    pass


@dataclass
class Reply:
    text: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    latency_s: float
    cost_usd: float
    cached: bool


def load_key() -> str:
    key = os.environ.get("BASETEN_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("BASETEN_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise RuntimeError("BASETEN_API_KEY not set: add `BASETEN_API_KEY=...` to .env in the repo root")
    return key


def image_part(png_bytes: bytes, detail: str = "auto") -> dict:
    url = "data:image/png;base64," + base64.b64encode(png_bytes).decode()
    return {"type": "image_url", "image_url": {"url": url, "detail": detail}}


def total_spent() -> float:
    if not COST_LOG.exists():
        return 0.0
    with open(COST_LOG, newline="") as f:
        return sum(float(r["cost_usd"]) for r in csv.DictReader(f))


def cost_of(prompt_tokens: int, cached_tokens: int, completion_tokens: int) -> float:
    p = PRICE_PER_M
    return ((prompt_tokens - cached_tokens) * p["input"] + cached_tokens * p["cached_input"]
            + completion_tokens * p["output"]) / 1e6


def _cache_key(model: str, messages: list, params: dict, salt: str) -> str:
    def strip(part):
        if isinstance(part, dict) and part.get("type") == "image_url":
            data = part["image_url"]["url"].encode()
            return {"image_sha256": hashlib.sha256(data).hexdigest()}
        return part

    norm = [{"role": m["role"], "content": [strip(p) for p in m["content"]]
             if isinstance(m["content"], list) else m["content"]} for m in messages]
    blob = json.dumps({"model": model, "messages": norm, "params": params, "salt": salt}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


class SparkClient:
    def __init__(self, model: str = MODEL, reasoning_effort: Optional[str] = "low",
                 budget_stop: float = BUDGET_STOP_USD, use_cache: bool = True):
        from openai import OpenAI

        self.client = OpenAI(base_url=BASE_URL, api_key=load_key())
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.budget_stop = budget_stop
        self.use_cache = use_cache

    def chat(self, messages: Sequence[dict], expect_out: int, tag: str = "", salt: str = "",
             max_tokens: Optional[int] = None, est_cost: float = 0.05) -> Reply:
        """One chat completion. `expect_out` is how many output tokens the caller expects."""
        params = {"max_tokens": max_tokens, "reasoning_effort": self.reasoning_effort}
        key = _cache_key(self.model, list(messages), params, salt)
        path = CACHE_DIR / f"{key}.json"
        if self.use_cache and path.exists():
            d = json.loads(path.read_text())
            return Reply(**{**d, "cached": True})

        spent = total_spent()
        if spent + est_cost > self.budget_stop:
            raise BudgetExceeded(f"spent ${spent:.2f}; next call could pass the ${self.budget_stop:.0f} stop")

        kwargs = {"model": self.model, "messages": list(messages)}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        t0 = time.perf_counter()
        r = self.client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - t0

        u = r.usage
        cached_tok = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        reasoning = getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
        cost = cost_of(u.prompt_tokens, cached_tok, u.completion_tokens)
        reply = Reply(text=r.choices[0].message.content or "", prompt_tokens=u.prompt_tokens,
                      completion_tokens=u.completion_tokens, reasoning_tokens=reasoning,
                      latency_s=round(latency, 3), cost_usd=cost, cached=False)
        self._log(tag, u.prompt_tokens, cached_tok, u.completion_tokens, reasoning, latency, cost, spent + cost)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({k: v for k, v in reply.__dict__.items() if k != "cached"}))

        if u.completion_tokens > expect_out + SURPRISE_TOKENS:
            raise SurpriseOutput(f"{tag}: {u.completion_tokens} output tokens ({reasoning} reasoning) "
                                 f"vs {expect_out} expected")
        return reply

    def _log(self, tag, prompt, cached, completion, reasoning, latency, cost, total):
        COST_LOG.parent.mkdir(parents=True, exist_ok=True)
        new = not COST_LOG.exists()
        with open(COST_LOG, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COST_FIELDS)
            if new:
                w.writeheader()
            w.writerow({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tag": tag,
                        "model": self.model, "prompt_tokens": prompt, "cached_tokens": cached,
                        "completion_tokens": completion, "reasoning_tokens": reasoning,
                        "latency_s": f"{latency:.3f}", "cost_usd": f"{cost:.6f}", "total_usd": f"{total:.4f}"})


def text_msg(role: str, text: str, images: List[bytes] = ()) -> dict:
    return {"role": role, "content": [{"type": "text", "text": text}, *[image_part(b) for b in images]]}
