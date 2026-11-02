"""Generate and compare zero-config policies (agentgate/policy_synth.py). The rule is in eval/SYNTH_V0.md.

  .venv\\Scripts\\python -m agentlab.proxy --stage defense
  .venv\\Scripts\\python scripts/synth_policies.py generate --suite banking    # once: refuses to overwrite
  .venv\\Scripts\\python scripts/synth_policies.py sha                         # SHA-256 of each policy file
  .venv\\Scripts\\python scripts/synth_policies.py diff                        # workspace vs the hand-written policy
  .venv\\Scripts\\python scripts/synth_policies.py report                      # tables, from runs/synth_v0/ (free)

Hard stop: $1 of API spend over all generations.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from agentgate.policy import default_workspace_policy  # noqa: E402
from agentgate.policy_synth import ask_proxy, dumps, load_policy, synthesize  # noqa: E402

POLICIES = ROOT / "policies"
OUT = ROOT / "runs" / "synth_v0"
STAGE = "defense"
CAP = 1.0
SUITES = ("banking", "slack", "travel", "workspace")
TRACE_SCORED = {("slack", "injection_task_5")}   # as in scripts/suites_report.py


def suite_tools(name: str) -> list:
    """Only the tool names, descriptions and argument schemas."""
    from agentdojo.task_suite.load_suites import get_suite

    return [{"name": t.name, "description": t.description, "parameters": t.parameters.model_json_schema()}
            for t in get_suite("v1.2.2", name).tools]


def spent_since_start() -> float:
    from agentlab import llm

    OUT.mkdir(parents=True, exist_ok=True)
    start = OUT / "budget_start.json"
    now = llm.spend_by_stage().get(STAGE, 0.0)
    if not start.exists():
        start.write_text(json.dumps({"defense": now, "total": llm.total_spent()}), encoding="utf-8")
    return now - json.loads(start.read_text(encoding="utf-8"))["defense"]


def generate(suite: str, port: str, directory: Path, cap: float = CAP) -> Path:
    import httpx
    from agentlab import llm

    path = directory / f"{suite}.json"
    if path.exists():
        raise SystemExit(f"{path} exists. Generation runs once per suite; it is not overwritten.")
    httpx.get(f"http://127.0.0.1:{port}/v1/models", timeout=10).raise_for_status()   # a proxy that is down must not freeze an all-unknown file
    ask, raw = ask_proxy(port), directory.parent / "runs" / "synth_v0" / f"{suite}_raw.jsonl"
    raw.parent.mkdir(parents=True, exist_ok=True)
    spent_since_start()

    def capped(p):
        spent = spent_since_start()
        if spent >= cap:
            raise RuntimeError(f"stopped at the ${cap} cap, ${spent:.4f} spent")
        return ask(p)

    def log(name, text, error):
        with open(raw, "a", encoding="utf-8") as f:
            f.write(json.dumps({"tool": name, "raw": text, "error": error}) + "\n")
        print(name, "ERROR " + error if error else "replied", flush=True)

    doc = synthesize(suite_tools(suite), capped, suite, llm.MODEL, log)
    directory.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps(doc))
    print(path, {k: len(v) for k, v in doc["by_status"].items()}, f"${spent_since_start():.4f} spent so far", flush=True)
    return path


def sha() -> dict:
    return {s: hashlib.sha256((POLICIES / f"{s}.json").read_bytes()).hexdigest() for s in SUITES
            if (POLICIES / f"{s}.json").exists()}


def diff() -> list:
    """Workspace: synthesized vs hand-written, per tool of the suite. One row per tool that differs."""
    hand, synth = default_workspace_policy(), load_policy(POLICIES / "workspace.json")
    rows = []
    for t in suite_tools("workspace"):
        n = t["name"]
        h, s = hand.rules.get(n), synth.rules.get(n)
        hs = dict(h.sensitive) if h else None
        ss = dict(s.sensitive) if s else None
        hd, sd = bool(h and h.confirm_untraced_ids), bool(s and s.confirm_untraced_ids)
        if n in synth.unknown or hs != ss or hd != sd:
            state = "unknown (blocked)" if n in synth.unknown else (ss if ss is not None else "not risky")
            rows.append({"tool": n, "hand": hs if hs is not None else "no rule", "synth": state,
                         "destructive_hand": hd, "destructive_synth": sd})
    return rows


def load_run(name):
    d = OUT / name
    return json.loads((d / "summary.json").read_text(encoding="utf-8")), json.loads((d / "results.json").read_text(encoding="utf-8"))


def ran(suite, r) -> bool:
    if not r["attack_success"]:
        return False
    if (suite, r["injection_task"]) in TRACE_SCORED and r["arm"] == "gate":
        return all(c["action"] == "allow" for c in r["calls"] if c["phase"] == "injection")
    return True


def report() -> list:
    from run_llama31 import rate as cell

    labels = {"synth": "synthesized", "default": "frozen default", "suites": "hand rules (A)", "suites_trust": "hand rules + trust (B)"}
    rows = []
    for s in SUITES:
        for p, label in labels.items():
            if not (OUT / f"{s}_{p}_attack").exists():
                continue
            a, res = load_run(f"{s}_{p}_attack")
            c, _ = load_run(f"{s}_{p}_clean")
            gated = [r for r in res if r["arm"] == "gate" and r["replayable"]]
            k = sum(ran(s, r) for r in gated)
            rows.append({"suite": s, "policy": label, "none": cell(a["none"]["attack_success_replayable"], a["none"]["replayable_pairs"]),
                         "gate_agentdojo": cell(a["gate"]["attack_success_replayable"], a["gate"]["replayable_pairs"]),
                         "gate_ran": cell(k, len(gated)), "goals": len(a["replayable_goals"]),
                         "utility_clean_none": f"{c['none']['utility']}/{c['none']['pairs']}",
                         "utility_clean_gate": cell(c["gate"]["utility"], c["gate"]["pairs"]),
                         "clean_blocked": c["gate"]["user_calls_blocked"], "clean_asked": c["gate"]["user_calls_asked"],
                         "clean_calls": c["gate"]["user_calls"], "attacked_blocked": a["gate"]["user_calls_blocked"],
                         "attacked_asked": a["gate"]["user_calls_asked"], "attacked_calls": a["gate"]["user_calls"],
                         "utility_attacked": f"{a['none']['utility']}/{a['none']['pairs']} -> {a['gate']['utility']}/{a['gate']['pairs']}"})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=["generate", "sha", "diff", "report"])
    ap.add_argument("--suite", choices=SUITES)
    ap.add_argument("--port", default="8000")
    a = ap.parse_args(argv)
    if a.phase == "generate":
        generate(a.suite, a.port, POLICIES)
    else:
        print(json.dumps({"sha": sha, "diff": diff, "report": report}[a.phase](), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
