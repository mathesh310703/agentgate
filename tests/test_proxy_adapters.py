"""Offline tests for the proxy's harness adapters, against a fake local upstream (no API calls).
Run: python tests/test_proxy_adapters.py"""

import io
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from agentlab import llm, proxy  # noqa: E402

TOOLS = [{"type": "function", "function": {
    "name": "get_file", "parameters": {"type": "object", "properties": {
        "file_id": {"type": "string"}, "limit": {"type": "integer"}}}}}]


class FakeUpstream(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, reply: dict, delay: float = 0.0):
        super().__init__(("127.0.0.1", 0), FakeHandler)
        self.reply, self.delay, self.hits = reply, delay, 0


class FakeHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.server.last = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        self.server.hits += 1
        time.sleep(self.server.delay)
        body = json.dumps(self.server.reply).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:  # the proxy gave up waiting
            pass


def _serve(srv):
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _run(reply: dict, delay: float = 0.0, timeout: float = proxy.UPSTREAM_TIMEOUT, model: str = llm.MODEL,
         upstream_seen: list = None):
    llm.COST_LOG = Path(tempfile.mkdtemp()) / "cost_log.csv"
    up = _serve(FakeUpstream(reply, delay))
    log = io.StringIO()
    px = _serve(proxy.ProxyServer(("127.0.0.1", 0), key="test-key-not-real", dry_run=False,
                                  upstream=f"http://127.0.0.1:{up.server_port}/v1/chat/completions",
                                  upstream_timeout=timeout, log=log, model=model))
    try:
        r = httpx.post(f"http://127.0.0.1:{px.server_port}/v1/chat/completions", timeout=30, json={
            "model": "x", "messages": [{"role": "user", "content": "open file 13"}], "tools": TOOLS})
        if upstream_seen is not None:
            upstream_seen.append(getattr(up, "last", None))
        return r, up.hits, log.getvalue()
    finally:
        px.shutdown(); px.server_close(); up.shutdown(); up.server_close()


def _reply(arguments: str) -> dict:
    return {"id": "fake", "object": "chat.completion", "model": llm.MODEL, "choices": [{
        "index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "get_file", "arguments": arguments}}]}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10}}


def test_string_param_coerced():
    r, hits, log = _run(_reply(json.dumps({"file_id": 13, "limit": 5})))
    assert r.status_code == 200 and hits == 1
    args = json.loads(r.json()["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
    assert args == {"file_id": "13", "limit": 5}  # integer-typed limit untouched
    assert "coerced file_id int->str" in log and "13" not in log.split("coerced", 1)[1].splitlines()[0]


def test_correct_args_unchanged():
    raw = json.dumps({"file_id": "13", "limit": 5})
    r, _, log = _run(_reply(raw))
    assert r.json()["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] == raw
    assert "coerced" not in log


def test_timeout_retried_once():
    r, hits, log = _run(_reply("{}"), delay=1.0, timeout=0.3)
    assert r.status_code == 504 and hits == 2 and "retrying once" in log


def _usage_reply(model):
    return {"id": "fake", "object": "chat.completion", "model": model, "choices": [{
        "index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}}


def _last_cost_row():
    import csv
    with open(llm.COST_LOG, newline="") as f:
        return list(csv.DictReader(f))[-1]


def test_model_option_forwards_and_prices_per_model():
    seen = []
    r, _, log = _run(_usage_reply("zai-org/GLM-5.3-Flash"), model="zai-org/GLM-5.3-Flash", upstream_seen=seen)
    assert r.status_code == 200 and seen[0]["model"] == "zai-org/GLM-5.3-Flash"   # caller's "x" is replaced
    row = _last_cost_row()
    assert row["model"] == "zai-org/GLM-5.3-Flash" and abs(float(row["cost_usd"]) - (0.15 + 0.50)) < 1e-6, row


def test_unknown_model_priced_at_most_expensive_known():
    price, known = llm.price_for("some/unlisted-model")
    assert not known and price == llm.UNKNOWN_PRICE
    assert all(price[k] >= p[k] for p in llm.MODEL_PRICES.values() for k in price)
    _run(_usage_reply("some/unlisted-model"), model="some/unlisted-model")
    assert abs(float(_last_cost_row()["cost_usd"]) - (price["input"] + price["output"])) < 1e-6
    assert llm.cost_of(1000, 0, 1000) == llm.cost_of(1000, 0, 1000, llm.MODEL)   # default stays Muse Spark


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} passed")
