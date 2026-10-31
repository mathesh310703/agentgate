# Related work (cite in README and video)

Text-side gates with provenance already exist. Our contribution is extending provenance to pixels and measuring it.

- taintgate (PyPI, MIT, alpha): session tracks user input as trusted and tool output as untrusted; allow/deny/ask rules. No image handling stated. https://pypi.org/project/taintgate/
- agent-policy-gateway (PyPI, Apache-2.0, alpha): reference monitor between agent and tools, taint labels, MCP and AgentDojo adapters. No image handling stated. https://pypi.org/project/agent-policy-gateway/
- SnapGuard: detects injected text in screenshots with OCR, contrast reversal and cue patterns. A detector, not an enforcement layer. https://arxiv.org/html/2604.25562
- VPI-Bench (ICLR 2026): visual prompt injection attacks for computer-use agents. https://mlanthology.org/iclr/2026/cao2026iclr-vpibench/
- The Hacker News, July 2026: hidden screen text against open-source Android agents, no straightforward software fix for corner/cutout cases. https://thehackernews.com/2026/07/open-source-android-ai-agents-could-let.html
- AgentDojo (ETH, MIT): benchmark for tool-using agents under injection.
- Meta Agents Rule of Two (untrusted input / sensitive access / external action).

## Known limits of our approach (state them openly)
- Provenance is normalised string matching. Paraphrased, translated, split or encoded values are not traced; the gate fails closed (blocks), which can cause false blocks.
- A destructive action on an id that exists in a legitimate listing cannot be attributed by provenance alone; the gate returns "ask".
- Pixel provenance depends on OCR quality (two extra passes help with low-contrast text, not with all cases).
