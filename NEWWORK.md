# New-work log

- **Oct 26, 2026:** hackathon kickoff.
- **Oct 27, 2026:** AgentGate started in this fresh repo. Written on Oct 27 for this project: `agentlab/llm.py` (Muse Spark Open client with disk cache, cost log, budget and surprise-output guards) and `scripts/spark_smoke.py`. No code or history copied from other projects.
- **Oct 31, 2026:** `agentgate/` package (deterministic action gate with provenance) added to this repo with 13 offline tests. Written today: `agentgate/adapters/agentdojo_adapter.py` (gate in front of every AgentDojo tool call, allow/block/ask log), `tests/test_agentdojo_adapter.py`, `scripts/run_agentdojo_gate.py`; first gated clean workspace run reported in `eval/GATE_V0.md`.
- **Oct 31, 2026:** screenshot test v0 written today: `eval/vision_demo/` (30 rendered documents, 15 with a low-contrast or small corner instruction line; fake-tool vision agent; no-gate and gated arms with OCR pixel provenance), `tests/test_vision_demo.py`, report `eval/VISION_V0.md`.
