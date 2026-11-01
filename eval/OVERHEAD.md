# Overhead: gate latency per call, judge latency and cost per call (Nov 1, 2026)

**Result:** the gate adds microseconds per tool call. The judge adds about 1.4 s and $0.0016 per call, but it runs only on the gate's "ask" decisions.

| step | when | median | p95 | p99 | max |
|---|---|---|---|---|---|
| `Gate.check` | every tool call, before it runs | 1–37 µs | 61–261 µs | 0.1–1.0 ms | 1.3 ms |
| `Session.add_tool_output` | after each allowed call | 18–154 µs | 73 µs–2.6 ms | 0.1–3.2 ms | 4.2 ms |
| intent judge (Muse Spark via proxy) | only on "ask" decisions | 1.41 s | 2.88 s | 3.29 s | 3.53 s |
| judge cost | only on "ask" decisions | $0.0016 | $0.0036 | $0.0041 | $0.0042 |

For scale, one agent model call cost about $0.0037 on average in the baseline runs (1,682 calls, $6.16). The gated live 40-task workspace run made 2 judge calls.

Zero new model cost: the gate numbers come from the scripted worst-case replay, and the judge numbers from the logs of judged runs already made.

## Gate, per suite

Measured on the worst-case replay (all user × injection pairs, frozen default policy), timed with `time.perf_counter` around each call, single-threaded. The machine is Windows 11 with Python 3.11.0, CPU only. `scripts/measure_overhead.py`; raw output in `runs/suites_v0/overhead.json`.

| suite | pairs | `Gate.check` calls | check median / p95 / max (µs) | records added | record median / p95 / max (µs) |
|---|---|---|---|---|---|
| workspace | 560 | 1,576 | 3.5 / 260.8 / 1,326.6 | 1,268 | 154.1 / 2,621.4 / 4,231.4 |
| banking | 144 | 489 | 36.6 / 130.8 / 256.1 | 239 | 83.2 / 235.7 / 331.2 |
| slack | 105 | 763 | 1.8 / 60.8 / 180.5 | 606 | 18.4 / 72.8 / 250.0 |
| travel | 140 | 1,108 | 1.2 / 84.0 / 246.6 | 1,108 | 44.4 / 169.2 / 361.3 |

- **Check:**
  - Most calls are not on the risky list and return immediately (1–4 µs).
  - Risky calls search the session's records for each target value: the p95 and max.
  - Banking's median is higher because a larger share of its calls are risky (money transfers).
  - The cost grows with the number of records in the session.
- **Recording** splits each structured result into one labelled record per field, and dominates the per-call cost. Workspace is the slowest (p95 2.6 ms) because its file listings and email searches return many long fields.
- **Not measured:**
  - OCR for screenshots (`agentgate/pixels.py`, three passes of RapidOCR on CPU). It is seconds per image, not microseconds, and is the real cost of pixel provenance.
  - The optional Prompt Guard scorer, which is unavailable without an `HF_TOKEN`.

## Judge, per call

69 uncached judge calls, from the logs of every judged run (`runs/*/judge_log.jsonl`): the Layer 2 tuning and held-out replays, their clean passes, and a smoke test.
- **Cost:** each call was matched to its row in `eval/cost_log.csv` by start time and latency. All 69 matched, with latency agreeing to within 0.10 s.
- **Tokens:** median 411 prompt tokens and 247 completion tokens (most of them reasoning).
- **Failures:** 2 calls returned unusable output and were denied by design.
- **Cache:** a cached judge reply takes at most 0.023 s.

How often the judge runs depends on how often the gate asks:
- 28 asks in 280 held-out workspace pairs (one family of user task, "delete the largest file");
- 2 asks in the 40-task live workspace run;
- 0 asks in banking, slack and travel (`eval/SUITES_V0.md`).

## Limits

- **One machine, one run per measurement.** Times include Python overhead and vary with load.
- **The replay's results are small.** AgentDojo's environment data is small, so a real mailbox or drive with thousands of entries would make `Session.add_tool_output` and the record search in `Gate.check` slower. Both are linear in the number of records.
- **Judge numbers come from one model** (Muse Spark Open through the budget proxy) and one family of ask (deleting a file chosen by a description).

## Reproduce

```
.venv\Scripts\python scripts/measure_overhead.py      # ~1 minute, no model calls
```
