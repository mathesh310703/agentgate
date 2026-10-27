"""Local budget-enforcing proxy for Baseten's OpenAI-compatible chat API.

  python -m agentlab.proxy               # serve on 127.0.0.1:8000, forward to Baseten
  python -m agentlab.proxy --dry-run     # fake responses, no network, no key needed

Point any OpenAI-compatible client at http://127.0.0.1:8000/v1 (any api_key string works).

* POST /v1/chat/completions, non-streaming ("stream": true -> 400). GET /v1/models is answered
  locally (no upstream call, no cost). Other paths -> 404.
* The Baseten key is read from .env only (not the environment) and is never logged; the caller's
  Authorization header is ignored. Log lines are additionally scrubbed of the key.
* The model is forced to MODEL; max_tokens (and max_completion_tokens) are capped at 2000.
* If Baseten rejects a request parameter (400/422 naming e.g. reasoning_effort or temperature),
  that parameter is dropped and the request retried once.
* Budget: before forwarding, the worst-case cost is checked against the stage budget and the $18
  total-spend confirmation; after each response the usage is logged with log_call(). Refusals
  return HTTP 402 with an explanation (the OpenAI SDK does not auto-retry 402).
* The upstream JSON body and status are returned unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from agentlab import llm

UPSTREAM = llm.BASE_URL + "/chat/completions"
PATH = "/v1/chat/completions"
MODELS_PATH = "/v1/models"
MODELS_LIST = {"object": "list", "data": [{"id": llm.MODEL, "object": "model"}]}
DROPPABLE = ["reasoning_effort", "temperature", "top_p", "parallel_tool_calls", "seed",
             "presence_penalty", "frequency_penalty", "logprobs", "top_logprobs", "stop"]
DRY_RUN_LOG = llm.ROOT / "eval" / "cache" / "cost_log_dryrun.csv"


def read_env_key(env_path: Path) -> str:
    """BASETEN_API_KEY from the .env file only (does not read or modify os.environ)."""
    from dotenv import dotenv_values

    key = (dotenv_values(env_path).get("BASETEN_API_KEY") or "").strip().strip('"').strip("'")
    if not key:
        raise SystemExit(f"BASETEN_API_KEY missing in {env_path}")
    return key


def estimate_cost(payload: dict) -> float:
    """Worst case: request JSON at 1 token / 3 chars x2 (images as 28x28 tiles via llm), full output."""
    msgs = payload.get("messages") or []
    try:
        msg_cost = llm.worst_case_cost(msgs, 0)
    except Exception:  # unusual message shapes: fall back to raw size
        msg_cost = llm.cost_of(int(2 * len(json.dumps(msgs)) / 3), 0, 0)
    tools_cost = llm.cost_of(int(2 * len(json.dumps(payload.get("tools") or [])) / 3), 0, 0)
    return msg_cost + tools_cost + llm.cost_of(0, 0, payload.get("max_tokens") or llm.MAX_TOKENS_CAP)


def prepare(payload: dict) -> dict:
    p = dict(payload)
    p["model"] = llm.MODEL
    for k in ("max_tokens", "max_completion_tokens"):
        if p.get(k) is not None:
            p[k] = min(int(p[k]), llm.MAX_TOKENS_CAP)
    if p.get("max_tokens") is None and p.get("max_completion_tokens") is None:
        p["max_tokens"] = llm.MAX_TOKENS_CAP
    return p


def rejected_params(status: int, body: bytes, payload: dict) -> list:
    if status not in (400, 422):
        return []
    text = body.decode("utf-8", "replace").lower()
    return [k for k in DROPPABLE if k in payload and k in text]


def fake_response(payload: dict) -> dict:
    prompt = max(1, int(len(json.dumps(payload.get("messages") or [])) / 4))
    return {"id": "dry-run", "object": "chat.completion", "created": int(time.time()), "model": payload["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "dry-run reply"}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": 12, "total_tokens": prompt + 12,
                      "completion_tokens_details": {"reasoning_tokens": 8}}}


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, *, key: Optional[str], dry_run: bool, stage: str = "baseline",
                 upstream: str = UPSTREAM, log=sys.stderr):
        super().__init__(addr, Handler)
        self.key, self.dry_run, self.stage, self.upstream, self.logf = key, dry_run, stage, upstream, log
        self.lock = threading.Lock()  # budget check + log as one step
        self.last_forwarded: Optional[dict] = None

    def log(self, msg: str) -> None:
        if self.key:
            msg = msg.replace(self.key, "***")
        print(f"[proxy] {msg}", file=self.logf, flush=True)


class Handler(BaseHTTPRequestHandler):
    server: ProxyServer

    def log_message(self, fmt, *args):  # silence default access log (it would include nothing secret,
        pass                            # but keep all output in one scrubbed place)

    def _send(self, status: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str, etype: str) -> None:
        self.server.log(f"{status} {etype}: {message}")
        self._send(status, json.dumps({"error": {"message": message, "type": etype, "code": status}}).encode())

    def do_GET(self):
        if self.path.rstrip("/") == MODELS_PATH:  # answered locally: no upstream call, no cost
            self.server.log("200 GET /v1/models (local)")
            return self._send(200, json.dumps(MODELS_LIST).encode())
        self._error(404, "only POST /v1/chat/completions and GET /v1/models are served", "not_found")

    def do_POST(self):
        s = self.server
        if self.path.rstrip("/") != PATH:
            return self._error(404, "only POST /v1/chat/completions is served", "not_found")
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except json.JSONDecodeError:
            return self._error(400, "request body is not JSON", "invalid_request")
        if payload.get("stream"):
            return self._error(400, "streaming is not supported by this proxy", "invalid_request")

        p = prepare(payload)
        est = estimate_cost(p)
        try:
            with s.lock:
                llm.check_budget(s.stage, est)
        except llm.BudgetError as e:
            return self._error(402, f"budget refused: {e}", "budget_exceeded")

        s.last_forwarded = p
        t0 = time.perf_counter()
        if s.dry_run:
            status, body = 200, json.dumps(fake_response(p)).encode()
        else:
            status, body = self._forward(p)
            drop = rejected_params(status, body, p)
            if drop:
                s.log(f"upstream rejected {drop}; dropping and retrying once")
                p = {k: v for k, v in p.items() if k not in drop}
                s.last_forwarded = p
                status, body = self._forward(p)
        latency = time.perf_counter() - t0
        self._record(status, body, latency)
        self._send(status, body)

    def _forward(self, p: dict):
        import httpx

        s = self.server
        try:
            r = httpx.post(s.upstream, json=p, timeout=300,
                           headers={"Authorization": f"Bearer {s.key}", "Content-Type": "application/json"})
            return r.status_code, r.content
        except httpx.HTTPError as e:
            msg = json.dumps({"error": {"message": f"upstream unreachable: {type(e).__name__}",
                                        "type": "upstream_error", "code": 502}})
            return 502, msg.encode()

    def _record(self, status: int, body: bytes, latency: float) -> None:
        s = self.server
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {}
        u = data.get("usage") if status == 200 else None
        if not u:
            s.log(f"{status} (no usage) {latency:.2f}s")
            return
        prompt = int(u.get("prompt_tokens") or 0)
        completion = int(u.get("completion_tokens") or 0)
        cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        reasoning = int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        finish = ((data.get("choices") or [{}])[0].get("finish_reason")) or ""
        cost = llm.cost_of(prompt, cached, completion)
        with s.lock:
            llm.log_call(s.stage, "proxy-dry-run" if s.dry_run else "proxy", llm.MODEL, prompt, cached,
                         completion, reasoning, finish, latency, cost)
            spent = llm.spend_by_stage().get(s.stage, 0.0)
        s.log(f"200 in={prompt} out={completion} (reasoning {reasoning}) ${cost:.5f} {latency:.2f}s; "
              f"{s.stage} ${spent:.4f}/${llm.STAGE_BUDGETS[s.stage]:.2f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--stage", default="baseline", choices=list(llm.STAGE_BUDGETS))
    ap.add_argument("--env", default=str(llm.ROOT / ".env"))
    ap.add_argument("--dry-run", action="store_true", help="fake responses; no network; separate cost log")
    a = ap.parse_args(argv)

    if a.dry_run:
        llm.COST_LOG = DRY_RUN_LOG
        key = None
    else:
        key = read_env_key(Path(a.env))
    srv = ProxyServer((a.host, a.port), key=key, dry_run=a.dry_run, stage=a.stage)
    srv.log(f"listening on http://{a.host}:{a.port}/v1 ({'DRY RUN' if a.dry_run else 'forwarding to Baseten'}); "
            f"stage {a.stage}; cost log {llm.COST_LOG}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
