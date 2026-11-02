# Related work (cite in README and video)

Text-side gates with provenance already exist. Our contribution is extending provenance to pixels and measuring it.

- taintgate (PyPI, MIT, alpha): session tracks user input as trusted and tool output as untrusted; allow/deny/ask rules. No image handling stated. https://pypi.org/project/taintgate/
- agent-policy-gateway (PyPI, Apache-2.0, alpha): reference monitor between agent and tools, taint labels, MCP and AgentDojo adapters. No image handling stated. https://pypi.org/project/agent-policy-gateway/
- SnapGuard: detects injected text in screenshots with OCR, contrast reversal and cue patterns. A detector, not an enforcement layer. https://arxiv.org/html/2604.25562
- VPI-Bench (ICLR 2026): visual prompt injection attacks for computer-use agents. https://mlanthology.org/iclr/2026/cao2026iclr-vpibench/
- The Hacker News, July 2026: hidden screen text against open-source Android agents, no straightforward software fix for corner/cutout cases. https://thehackernews.com/2026/07/open-source-android-ai-agents-could-let.html
- AgentDojo (ETH, MIT): benchmark for tool-using agents under injection.
- Meta Agents Rule of Two (untrusted input / sensitive access / external action).

## Closest papers (checked Nov 2, 2026 against each arXiv abstract page and full text)

All five are on arXiv with no journal reference on record, so treat them as preprints. NeurIPS 2026 also lists FIDES as a poster.

- **Adaptive Evaluation of Out-of-Band Defenses Against Prompt Injection in LLM Agents** (arXiv 2606.26479, preprint). Organizes deterministic defenses (CaMeL, FIDES, Progent, RTBAS, FORGE) as classical integrity protection, warns that all are validated only on static benchmarks, and reproduces Progent's adaptive analysis with Qwen2.5-7B: mean attack success 25.8% → 4.2%, and 2.6% under a hand-crafted adaptive attack, which the authors call one small data point.
  - **AgentGate differs:** it is a defense of that class, not an evaluation of one, and this warning applies to it. Our worst-case replay is a static benchmark, and our 37 adaptive cases are hand-built, not optimized. The paper does not cover images.
- **Securing AI Agents with Information-Flow Control, FIDES** (arXiv 2505.23643, preprint). A planner that tracks confidentiality and integrity labels, deterministically enforces policies, and hides untrusted data in variables; evaluated on AgentDojo.
  - **AgentGate differs:** FIDES also checks the context label: its integrity policy "checks the tool label to ensure that a call was generated in a trusted context". Our gate checks only the arguments. An injection that steers the agent onto a different branch, using only values that trace to trusted sources, is not caught (our known branch-steering gap; no test measures it directly). FIDES is a planner design; AgentGate wraps an existing tool loop. The paper does not mention image input.
- **LlamaFirewall** (arXiv 2505.03574, preprint). A guardrail framework with PromptGuard 2 (jailbreak detector), AlignmentCheck (experimental chain-of-thought auditor) and CodeShield (static analysis). It is text only: the authors list image and audio agents as future work. It reports PromptGuard 2 86M at AUC .98 and 97.5% recall at 1% false positives on its English dataset, and on AgentDojo attack success 17.6% → 7.5% with utility 47.7% → 47.0%, at a threshold tuned to a small utility cost.
  - **AgentGate differs:** the gate decides from provenance, not from a score, and also reads images. Our Prompt Guard numbers (`eval/LAYER1.md`) use a fixed 0.5 threshold on single texts, so they are not comparable with that attack-success figure.
- **Render Before Reading: Visual Rendering as a Prompt Injection Defense** (arXiv 2609.36121, preprint). Pictionary renders untrusted payloads as typographic images (or audio) because multimodal models obey instructions less in those channels; it reports lower attack success across ten models on DirectInject and AgentDojo, including adaptive attacks and human red teamers.
  - **AgentGate differs:** Pictionary lowers how likely the model is to obey; a benign fine-tune erodes that gap, per the paper. AgentGate assumes the model obeys and blocks the call. Pictionary sends text in as pixels; AgentGate treats text recovered from pixels as untrusted.
- **APPA: Recoverable Information-Flow Control for Real-World LLM Agents** (arXiv 2607.24625, preprint). A dual-phase reference monitor at tool dispatch and protocol gateways such as MCP, with gradual security typing, disposable child branches for recovery, and safety proofs; it reports 64.2–91% utility and no observed attacks across 1,320 guarded episodes.
  - **AgentGate differs:** APPA is much broader, with labels, workflow history, recovery and proofs. AgentGate is one narrow check with no proofs: string-level provenance of risky-call arguments, extended to images. The paper does not mention image input as a channel.

**Provenance through pixels.** We do not claim to be the first. We found no work that traces the values of tool-call arguments to text recovered from images and allows or blocks the call deterministically on that basis. That rests on the papers above and three web searches, so it is not exhaustive. Two come close, and a reader may weigh them differently:
- **Cross-Agent Multimodal Provenance-Aware Defense** (arXiv 2512.23557; accepted at ICCA 2025, per arXiv). It runs OCR on images and keeps a ledger of modality and trust by span or patch, then uses trust-aware masks and an attribution model that requests regeneration, not value tracing of arguments.
- **SAFEFLOW** (arXiv 2506.07564, preprint). It gives content integrity labels across multimodal agents, and gives as an example forbidding an agent "from using untrusted OCR text to compose a high-confidence database query". It does not describe tracing argument values to image text.

## Known limits of our approach (state them openly)
- Provenance is normalised string matching. Paraphrased, translated, split or encoded values are not traced; the gate fails closed (blocks), which can cause false blocks.
- A destructive action on an id that exists in a legitimate listing cannot be attributed by provenance alone; the gate returns "ask".
- Pixel provenance depends on OCR quality (two extra passes help with low-contrast text, not with all cases).
