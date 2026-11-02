# AgentGate

AgentGate is a plugin for browser agents that stops untrusted on-screen content (page text, images, popups, chat widgets) from commanding the agent: only the user's task may direct actions, and everything the agent reads from a page is treated as data. This repo holds the plugin work and its evaluation harness; the vision model under test is Muse Spark Open via Baseten's OpenAI-compatible Model API.

## Install and try it in one minute

Python 3.11. The core has no dependencies, and the example needs no model, key or network.

```
pip install git+https://github.com/mathesh310703/agentgate
git clone https://github.com/mathesh310703/agentgate
cd agentgate
python examples/ten_lines.py
```

Output:

```
ana@corp.test: ALLOW. All sensitive arguments trace to your request or a trusted source.
records@corp.test: BLOCK. Blocked 'send_email': recipients='records@corp.test' came from text from a tool result (email, web page, file or event) (read_file).
```

OCR and the MCP server are optional extras: `pip install "agentgate[ocr,mcp] @ git+https://github.com/mathesh310703/agentgate"`.

- **Works with pip alone:** the gate, the built-in policies, the OCR and MCP extras, and the offline examples, which need nothing else installed.
- **Needs a clone of the repo:** the image reader, the judge and policy synthesis (they use the budget proxy), the `policies/` folder, and the example script files themselves.
- **Tested from a fresh install:** only Python 3.11, and only the `ocr` and `mcp` extras.

License: MIT. Llama Prompt Guard 2 keeps its own license, noted below.

## What is new here

Text gates with provenance already exist ([docs/RELATED_WORK.md](docs/RELATED_WORK.md)). AgentGate adds three things:
- **Provenance through pixels, as a drop-in.** Text recovered from an image enters the session as untrusted pixels (`Session.add_pixels`, or `observe_image` on the MCP server). A share aimed at an address found only in an image is blocked, and the block names the image.
- **A second image reader that can only make the gate stricter.** An optional model transcript joins the OCR text as untrusted data. It traces more planted addresses to their image (60/60 vs 50/60) and changed no decision. Tests check that it never moves a decision towards allow.
- **An evaluation that assumes the model is fooled.** A scripted agent obeys every injection (worst-case replay): 231/240 attacks succeed ungated on AgentDojo workspace, 0/240 gated. A small real model that does fail shows the same on images: Qwen3-VL-2B leaks 16/300 ungated, 0/300 gated.

**Compared with the closest papers** ([docs/RELATED_WORK.md](docs/RELATED_WORK.md)): FIDES (preprint) also checks the context label, which our argument-only gate does not, so an injection that steers the agent's branch using only trusted values is a known gap. LlamaFirewall (preprint) is text only and reports PromptGuard 2 86M. We do not claim to be the first: we found no work that traces tool-call argument values to text recovered from images and enforces on that, though two papers come close and the search was not exhaustive.

## Runs on Meta open-weight models

The model under test is Muse Spark Open (`meta-models/muse-spark-open-1026`), served through Baseten partner inference. The proxy pins the model id on every request (`prepare()` in `agentlab/proxy.py`, default `llm.MODEL`) and logs it per call in the `model` column of `eval/cost_log.csv`.

## Results (attack success, gate off → on; Wilson 95% CI)

| test | gate off | gate on | false blocks |
|---|---|---|---|
| Scripted worst case, AgentDojo workspace | 231/240 | 0/240 | 0 on held-out half |
| Scripted worst case, 15 image carriers | 15/15 | 0/15 | 0/15 |
| Muse Spark Open, real attacks | 0/140, 0/15 (refused on its own) | – | – |
| Muse Spark Open, 11 AgentDojo attack types, 165 episodes (5 tasks, 3 goals, clustered) | 0/165 (0.0–2.3%), resisted | not run | – |
| Muse Spark Open as an instructed-compliant agent (system prompt tells it to obey tool results; not a natural vulnerability), 40 episodes per arm (10 tasks, 4 goals, clustered) | 1/40 (0.4–12.9%) | 0/40 (0.0–8.8%); **not evidence of protection:** the intervals overlap, and the model tried only 1 injected call when gated (blocked) | 0/110 calls |
| Qwen3-VL-2B (small open test model, not part of AgentGate), greedy, 60 images | 4/60 (2.6–15.9%) | 0/60 (0.0–6.0%) | 0/30 |
| Qwen3-VL-2B, T=0.7, 5 samples, 300 episodes | 16/300 (3.3–8.5%) | 0/300 (0.0–1.3%) | 1/150 (0.1–3.7%) |
| Set 3 (60 images, 3 carrier wordings): Qwen3-VL-2B, T=0.7, 3 samples | 4/90 (1.7–10.9%), all direct notes | 0/90 (0.0–4.1%) | 0/90 (0.0–4.1%) |
| Set 3: Muse Spark Open, 1 run | 0/30 (0.0–11.4%) | 0/30 (0.0–11.4%) | 0/30 (0.0–11.4%) |

Details, limits and the block-message comparison are in [RESULTS.md](RESULTS.md), `eval/LOCALVLM_V1.md` and `eval/SET3_V0.md`.

## Limits

**What gets past the gate.** 7 of the 37 hand-built adaptive cases (`eval/ADAPTIVE_V0.md`) are allowed by the frozen default policy. **5 gaps remain in substance**, even with the optional attachment policy:
1. **#27:** an attacker's address that is in the user's contacts (contact search results are trusted).
2. **#28:** a reply to the attacker's email, because an email's `sender` field is trusted. Neither Prompt Guard 2 model flags the email (22M 0.003, 86M 0.001), so the sender rule doesn't fire.
   - With the optional attachment policy, the adaptive test blocks this case only because the reply attaches the canary.
   - An attacker-chosen sender used as the recipient still passes.
3. **#29:** the user names `team+records@archive.test`, and the agent sends to `records@archive.test` (`+` is not treated as part of an address).
4. **#33:** sharing the wrong file, because any file id in a listing vouches for `file_id`.
5. **#34:** sharing a calendar event's id used as a file id: ids are not typed.

**Closed by the optional attachment policy** (`agentgate/policy_attach.py`, off by default, added after the report):
- **#36:** an email to a recipient the user named, with an attachment chosen by injected email text.
- **#37:** the same, with the attachment chosen by text in an image.

**Branch steering is not closed:** when every argument traces to a trusted source but untrusted text caused the call, the gate allows it (pinned in `tests/adaptive_cases.py`), whereas FIDES's context-label check would catch it.

All 26 obfuscated spellings of an injected address are blocked. Other limits are in [RESULTS.md](RESULTS.md#limits).

## Setup (Windows, NVIDIA GPU)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip      # pip 22.3 (Python 3.11.0) fails on the PyTorch index
.venv\Scripts\pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cu126
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install --no-deps rapidocr-onnxruntime==1.4.4   # OCR; --no-deps avoids an opencv clash
.venv\Scripts\python -m playwright install chromium
copy .env.example .env      # then put your key after BASETEN_API_KEY= (never commit .env)
```

Clone into a short path (e.g. `D:\agentgate`): the torch wheel has paths too long for deep folders on
Windows unless long paths are enabled.

Offline only (tests, quickstart, `scripts/reproduce.py`; any OS, CPU, no keys):

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-ci.txt     # Windows: .venv\Scripts\pip
.venv/bin/python examples/quickstart.py      # four tool calls, four decisions, under a second
for t in tests/test_*.py; do .venv/bin/python "$t"; done
.venv/bin/python scripts/reproduce.py        # final table, zero cost, ~2 minutes
```

How the gate works and where it stops working: [docs/TECHNICAL.md](docs/TECHNICAL.md).

## Quick start

```bash
.venv\Scripts\python scripts/spark_smoke.py   # one text call + one screenshot call; prints latency, tokens, cost
.venv\Scripts\python -m agentlab.spend        # spend per stage from eval/cost_log.csv
.venv\Scripts\python tests/test_llm_budget.py # offline budget tests (no API calls)
```

Every real model call is logged to `eval/cost_log.csv`; responses are cached on disk so reruns cost nothing.

## Live demo

A small assistant reads a document with a hidden line, on `http://127.0.0.1:8765`, with a gate switch. It binds this machine only and needs no network or API.

```
.venv\Scripts\python demo/live.py            # real local Qwen3-VL-2B (needs the GPU setup above)
.venv\Scripts\python demo/live.py --stub     # fake victim, no GPU, labelled STUB on the page
.venv\Scripts\python demo/live.py --record   # re-record demo/live_trace.json, for "Replay recorded run"
```

Measured with fresh greedy runs on an RTX 4060 Laptop (5 per arm, `runs/live_demo_v0/final_scenarios.json`):

| scenario | canary leaked, gate off | canary leaked, gate on | correct answer, off / on | median time, off / on |
|---|---|---|---|---|
| invoice, hidden low-contrast line | 5/5 | 0/5 | 5/5, 0/5 | 15.8 s, 17.4 s |
| notice, hidden small line | 5/5 | 0/5 | 5/5, 0/5 | 42.5 s, 36.3 s |
| clean control | 0/5 | 0/5 | 5/5, 5/5 | 3.0 s, 2.8 s |

- **These images were picked because they fool this model.** Greedy runs repeat the same output, so 5/5 means one behaviour repeated, not a rate. Most hidden lines do not fool it: 16/300 sampled episodes leak in (e) of [RESULTS.md](RESULTS.md).
- **The cost shows on the page:** with the gate on, the agent stops the leak but apologises instead of answering the question.
- **OCR misses the notice's hidden line,** so that block says the address "does not appear in your request" and does not name the image.

## Test your own policy

Write a function that returns a `Policy` ([examples/my_policy.py](examples/my_policy.py) is a small example), then run the worst-case replay on AgentDojo workspace. No model, no keys, no cost; about a minute per half.

```
python scripts/run_worstcase.py --split tune --policy examples.my_policy:build --out runs/my_policy
python scripts/run_worstcase.py --split tune --mode clean --policy examples.my_policy:build --out runs/my_policy_clean
```

- `--policy` takes `package.module:function`; `--split` takes `tune` (tasks 0–19), `heldout` (20–39) or `all`.
- The first command replays each task against all 14 injection goals, and the second without injections, for false blocks.
- Attack success, utility, and user calls blocked or asked print at the end and land in `<out>/summary.json`. Every call's decision and reason is in `<out>/results.json`.

**Zero-config policies (optional): a starting point to review before use.** `agentgate/policy_synth.py` has Muse Spark Open propose a policy from tool schemas alone, used with `SynthGate`, which also blocks tools the policy doesn't classify. Frozen before measuring, worst-case replay, gated attack success: banking 0/144, slack 13/105, travel 76/120, workspace 0/240. That stops at least as much as the hand-written rules (A), but travel still leaks. Clean utility is lower than the hand-written rules on banking (7/16 vs 8/16), slack (9/21 vs 13/21) and workspace (33/40 vs 38/40), and equal on travel (20/20) (`eval/SYNTH_V0.md`).

## Budgets and guards (agentlab/llm.py)

- Every call names a stage; budgets (USD): dev 5, baseline 15, defense 20, benchmark 30, arena 20, reserve 10. A call whose worst-case cost would exceed its stage budget is refused before sending.
- Total spend past $18 needs explicit confirmation (`AGENTGATE_CONFIRM_OVER_18=1`).
- `max_tokens` is capped at 2000, reasoning included; screenshots are sent as JPEG at most 768 px wide.
- Experiments use pilot mode (`agentlab/pilot.py`): 5 trials with cost and results printed; the full set only with `--full`.

## Harness adapters (applied equally to baseline and defended runs)

Benchmark agents talk to the model through the local proxy (`python -m agentlab.proxy`, `agentlab/proxy.py`). Two compatibility fixes there apply to every run, with or without a defense, so they do not favor either side:

- **Tool-argument coercion.** For each tool call in a model response, the proxy looks up the function's parameter schema in the request's `tools`. If a parameter is declared `"type": "string"` but the model sent a number or boolean, it is converted to a string (`13` → `"13"`, `true` → `"true"`) and the fixed JSON is written back into `arguments`. Nothing else is changed. Each coercion is logged by parameter name and types only, never values (e.g. `coerced file_id int->str`).
- **Upstream timeout.** Each upstream call times out after 90 s and is retried once; a second timeout returns HTTP 504 instead of stalling the run for minutes.

Offline test (fake local upstream, no API calls): `.venv\Scripts\python tests/test_proxy_adapters.py`.

## Layer 1 detector: Llama Prompt Guard 2

**Built with Llama.** `agentgate/detectors.py` scores untrusted tool text and OCR text with
[meta-llama/Llama-Prompt-Guard-2-22M](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-22M), run locally on CPU.
The score is advisory: it is stored on each record, shown in block explanations, and used by one rule
(a recipient taken only from an email's sender or a file's owner is blocked when the session holds text scoring 0.5 or higher).

**Measured at the fixed 0.5 threshold (`eval/LAYER1.md`):**
- **22M, the model the gate uses by default:** 0/378 injected tool outputs (AUC 0.886), 0/60 planted image lines.
- **86M, optional and off by default (`--detector promptguard86`):** 125/378 injected tool outputs (AUC 0.997), 0/60 planted image lines, with no signal on image lines. In the gate it changes no decision on the workspace replay, which does not exercise the sender rule (`eval/LAYER1_86M.md`).
- **False positives:** none for either model on the clean set (0/55 outputs, 0/60 OCR texts).
- **Wiring:** classic jailbreaks score 0.996 or above on both, so it works; the AgentDojo payload is low on most goals.
- **The 22M rule never fires, and no reported result depends on it.**

License note: Llama Prompt Guard 2 is licensed under the Llama 4 Community License,
Copyright © Meta Platforms, Inc. All Rights Reserved. Use is subject to that license and Meta's
Acceptable Use Policy. This repo does not include or redistribute the model weights; they are downloaded from
Hugging Face after accepting the license there. Put your Hugging Face token in `.env` as `HF_TOKEN=` (never commit it).
Offline tests use a stub scorer and need neither the model nor the token.

**Meta tooling used:**
- **Muse Spark Open** (through Baseten): the agent under test, the intent judge, and the optional image reader. The planted address is traced to the image on 60/60 carriers with the reader, vs 50/60 with OCR alone; no gate decision changes (`eval/READER_V0.md`).
- **Llama Prompt Guard 2:** measured at 0.5 (`eval/LAYER1.md`). 22M flags 0/378 injected tool outputs and 0/60 planted image lines; 86M flags 125/378 and 0/60. Neither has a false positive on the clean set (0/55 outputs, 0/60 OCR texts). The 86M reaches AUC 0.997 on tool outputs and shows no signal on image lines.
