"""Local-only proxy between AgentDojo and Ollama's OpenAI-compatible endpoint. No key, no cost, no other upstream.

The same harness adapters as agentlab/proxy.py apply (forced model id, max_tokens cap, schema-driven argument
coercion, reused from there), so runs stay comparable. It is separate because the budget proxy would price an
unknown model at the most expensive rate in the real cost log, and it forwards to Baseten.

Each call is logged to --log with tokens and latency. "truncated" flags a prompt Ollama cut to fit its context:
its /v1 endpoint does so silently and ignores num_ctx, so a model tag with a larger num_ctx is used.

  .venv\\Scripts\\python scripts/ollama_proxy.py --model llama31-8b-ctx16k --port 8021 --log runs/llama31_v0/calls.jsonl
  .venv\\Scripts\\python scripts/ollama_proxy.py --model qwen3-8b-ctx16k --reasoning-effort none --port 8021 --log runs/qwen3_text_v0/calls.jsonl
"""

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from agentlab.proxy import coerce_tool_args, prepare  # noqa: E402

UPSTREAM = "http://localhost:11434/v1/chat/completions"
TIMEOUT = 600.0


def looks_truncated(payload: dict, prompt_tokens: int) -> bool:
    """English text runs about 4 chars per token; a prompt counted at under a quarter of that was cut.
    Only the messages count: the stock Llama 3.1 template drops the tool list after the first tool result."""
    return prompt_tokens < len(json.dumps(payload.get("messages") or [])) / 16


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            return self._send(200, json.dumps({"object": "list", "data": [
                {"id": self.server.model, "object": "model"}]}).encode())
        self._send(404, b"{}")

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self._send(404, b"{}")
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        p = prepare(payload, self.server.model)
        if self.server.reasoning_effort:
            p["reasoning_effort"] = self.server.reasoning_effort
        t0 = time.perf_counter()
        try:
            r = httpx.post(UPSTREAM, json=p, timeout=TIMEOUT)
            status, body = r.status_code, r.content
        except httpx.HTTPError as e:
            status, body = 502, json.dumps({"error": {"message": type(e).__name__}}).encode()
        rec = {"status": status, "latency_s": round(time.perf_counter() - t0, 2)}
        if status == 200:
            data = json.loads(body)
            u = data.get("usage") or {}
            notes = coerce_tool_args(p, data)
            body = json.dumps(data).encode()
            msg = data["choices"][0]["message"]
            rec.update(prompt=u.get("prompt_tokens"), completion=u.get("completion_tokens"), coerced=notes,
                       tool_calls=len(msg.get("tool_calls") or []), finish=data["choices"][0].get("finish_reason"),
                       truncated=looks_truncated(p, int(u.get("prompt_tokens") or 0)))
        with self.server.lock:
            with open(self.server.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        self._send(status, body)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=8021)
    ap.add_argument("--log", required=True)
    ap.add_argument("--reasoning-effort", help="sent on every request; none turns thinking off for Qwen3 "
                                                "(think: false is ignored on /v1)")
    a = ap.parse_args(argv)
    Path(a.log).parent.mkdir(parents=True, exist_ok=True)
    import threading

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    srv.model, srv.log_path, srv.lock, srv.reasoning_effort = a.model, a.log, threading.Lock(), a.reasoning_effort
    print(f"ollama proxy on 127.0.0.1:{a.port}, model {a.model}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
