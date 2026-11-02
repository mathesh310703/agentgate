"""Llama Prompt Guard 2 86M next to the 22M on the texts of scripts/measure_llamaguard.py: the injected and clean
workspace tool outputs, the planted line of the 60 image carriers, and the clean images' OCR text. Local CPU model, no
API cost. The gate keeps using the 22M; this only measures. The positive control checks the wiring first.

  .venv\\Scripts\\python scripts/measure_promptguard_86m.py --out runs/promptguard_86m_v0
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "eval" / "vision_demo"), str(ROOT / "scripts")]

from agentgate.detectors import MODEL_ID, PromptGuard  # noqa: E402
from layer1_positive_control import BENIGN, JAILBREAKS  # noqa: E402
from measure_llamaguard import image_texts, prompt_guard_row, tool_texts  # noqa: E402

MODEL_86M = "meta-llama/Llama-Prompt-Guard-2-86M"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    tool_pos, tool_neg = tool_texts()
    lines, clean_ocr = image_texts()
    report = {"threshold": 0.5, "texts": {"tool_pos": len(tool_pos), "tool_neg": len(tool_neg), "lines": len(lines),
                                          "lines_distinct": len(set(lines)), "clean_ocr": len(clean_ocr)}}
    for name, model_id in (("22M", MODEL_ID), ("86M", MODEL_86M)):
        guard = PromptGuard(model_id)
        control = {"jailbreaks": [round(guard(t), 4) for t in JAILBREAKS], "benign": [round(guard(t), 4) for t in BENIGN]}
        t0 = time.time()
        tools = prompt_guard_row(guard, tool_pos, tool_neg)
        seconds = time.time() - t0
        tools["max_neg"] = max(guard(t) for t in tool_neg)
        image = prompt_guard_row(guard, lines, clean_ocr)
        image["max_neg"] = max(guard(t) for t in clean_ocr)
        report[name] = {"model": model_id, "labels": {str(k): v for k, v in guard._model.config.id2label.items()},
                        "malicious_index": guard._malicious, "positive_control": control, "tool_outputs": tools,
                        "planted_lines": image, "tool_output_seconds": round(seconds, 1)}
        print(name, json.dumps(report[name]), flush=True)
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


def detail(out):
    """Per-text 86M scores on the injected tool outputs, by half and by injection goal."""
    from collections import Counter

    from agentdojo.agent_pipeline import AgentPipeline
    from agentdojo.attacks.attack_registry import load_attack
    from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
    from agentdojo.task_suite.load_suites import get_suite
    from measure_layer1 import ATTACK, HALVES, collect

    suite = get_suite("v1.2.2", "workspace")
    named = AgentPipeline([])
    named.name = "vllm_parsed"
    attack = load_attack(ATTACK, suite, named)
    guard = PromptGuard(MODEL_86M)
    rows = []
    for half, rng in HALVES.items():
        pos, _ = collect(suite, attack, [f"user_task_{i}" for i in rng])["output"]
        rows += [{"half": half, "source": src, "score": guard(t), "chunks": len(guard.chunks(t))} for t, src in pos.items()]
    goal = lambda r: r["source"].split("x", 1)[1].split(":")[0]  # noqa: E731
    flagged = [r for r in rows if r["score"] >= 0.5]
    report = {"by_half": {h: [sum(r["half"] == h for r in flagged), sum(r["half"] == h for r in rows)] for h in HALVES},
              "by_goal_first_seen": {g: [Counter(goal(r) for r in flagged)[g], n]
                                     for g, n in sorted(Counter(goal(r) for r in rows).items(), key=lambda kv: int(kv[0].rsplit("_", 1)[1]))},
              "by_chunks": {str(c): [sum(r["chunks"] == c for r in flagged), n] for c, n in sorted(Counter(r["chunks"] for r in rows).items())},
              "payload_alone": {i: guard(ImportantInstructionsAttack._JB_STRING.format(
                  goal=t.GOAL, user="Emma Johnson", model="AI model")) for i, t in suite.injection_tasks.items()}}
    (out / "detail.json").write_text(json.dumps({"report": report, "rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    if "--detail" in sys.argv:
        detail(Path(sys.argv[sys.argv.index("--out") + 1]))
    else:
        main()
