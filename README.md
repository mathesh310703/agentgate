# AgentGate

AgentGate is a plugin for browser agents that stops untrusted on-screen content (page text, images, popups, chat widgets) from commanding the agent: only the user's task may direct actions, and everything the agent reads from a page is treated as data. This repo holds the plugin work and its evaluation harness; the vision model under test is Muse Spark Open via Baseten's OpenAI-compatible Model API.

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
```

Every real model call is logged to `eval/cost_log.csv`; responses are cached on disk so reruns cost nothing.
