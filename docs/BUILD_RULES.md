# AgentGate build rules (read first in every session)

Solo entry, Meta Global AI Developer Hackathon, Indie track. Submit **Nov 3** (hard deadline Nov 4, 9 PM ET).
Owner: Matheshwaran Prakash (Germany, UTC+1, Windows, RTX 4060 8 GB).

## What we build
A deterministic action gate with provenance, including provenance through pixels.
Everything the agent reads from a tool result is untrusted text; everything recovered from a
screenshot or image is untrusted pixels; only the user's request is trusted. A risky tool call
(send, share, delete, pay) is blocked unless each target argument traces to the user or a trusted source.
Block messages say why, in plain words.

## Rules
1. Secrets only in `.env` (git-ignored). Never print, log, commit or paste keys.
2. Every model call goes through the proxy / `agentlab/llm.py` budget manager. State the estimated cost first for any batch. Stop at $3 per experiment unless told otherwise.
3. Write the gate from scratch. Cite related work (docs/RELATED_WORK.md), do not copy code.
4. Report honestly, including negative results. Never tune on the test set.
5. No attack content beyond what a published benchmark already contains. Test cases use neutral data: `.test` addresses, a canary file, no credentials, no payment forms.
6. Small commits, tests for anything non-trivial (`python tests/test_gate.py` must pass).
7. Log new work in NEWWORK.md with date (the "built during the event" rule).
8. Keep answers short. Lead with the result.
9. If a safety filter stops a step, do not work around it. Report it and stop.

## Disclosure
Code was written with Claude (Anthropic) as a coding assistant; the author directed the design and ran the experiments.
