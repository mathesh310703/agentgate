# AgentGate

AgentGate is a plugin for browser agents that stops untrusted on-screen content (page text, images, popups, chat widgets) from commanding the agent: only the user's task may direct actions, and everything the agent reads from a page is treated as data. This repo holds the plugin work and its evaluation harness; the vision model under test is Muse Spark Open via Baseten's OpenAI-compatible Model API.

## Results (attack success, gate off → on; Wilson 95% CI)

| test | gate off | gate on | false blocks |
|---|---|---|---|
| Scripted worst case, AgentDojo workspace | 231/240 | 0/240 | 0 on held-out half |
| Scripted worst case, 15 image carriers | 15/15 | 0/15 | 0/15 |
| Muse Spark Open, real attacks | 0/140, 0/15 (refused on its own) | – | – |
| Qwen3-VL-2B (small open test model, not part of AgentGate), greedy, 60 images | 4/60 (2.6–15.9%) | 0/60 (0.0–6.0%) | 0/30 |
| Qwen3-VL-2B, T=0.7, 5 samples, 300 episodes | 16/300 (3.3–8.5%) | 0/300 (0.0–1.3%) | 1/150 (0.1–3.7%) |

Details, limits and the block-message comparison are in [RESULTS.md](RESULTS.md) and `eval/LOCALVLM_V1.md`.

## Setup (Windows, NVIDIA GPU)

```bash
python -m venv .venv
.venv\Scripts\pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cu126
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
copy .env.example .env      # then put your key after BASETEN_API_KEY= (never commit .env)
```

## Quick start

```bash
.venv\Scripts\python scripts/spark_smoke.py   # one text call + one screenshot call; prints latency, tokens, cost
.venv\Scripts\python -m agentlab.spend        # spend per stage from eval/cost_log.csv
.venv\Scripts\python tests/test_llm_budget.py # offline budget tests (no API calls)
```

Every real model call is logged to `eval/cost_log.csv`; responses are cached on disk so reruns cost nothing.

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

License note: Llama Prompt Guard 2 is licensed under the Llama 4 Community License,
Copyright © Meta Platforms, Inc. All Rights Reserved. Use is subject to that license and Meta's
Acceptable Use Policy. This repo does not include or redistribute the model weights; they are downloaded from
Hugging Face after accepting the license there. Put your Hugging Face token in `.env` as `HF_TOKEN=` (never commit it).
Offline tests use a stub scorer and need neither the model nor the token.
