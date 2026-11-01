"""Regenerate the final results table (RESULTS.md) with one command. No model calls, no cost.

  .venv\\Scripts\\python scripts/reproduce.py            # re-runs the zero-cost parts, reads the rest
  .venv\\Scripts\\python scripts/reproduce.py --cached   # reads everything from saved runs (fast)

(a) worst-case replay, all 560 workspace pairs, ungated vs gated, tuning half (user tasks 0-19) and
    held-out half (20-39), plus clean mode (no injections). Re-run by default (deterministic, local);
    the gate + judge rows are read from the saved judged replays.
(b) vision worst case: both 30-image sets with a scripted agent that obeys every carrier line
    (eval/vision_demo/worstcase.py). Re-run by default; OCR text is read from <set>/ocr (saved by the
    first run).
(c) live clean 40-task Muse Spark run: ungated (runs/full_clean_v2) vs gated with the judge (runs/final_live).
(d) Muse Spark real attacks already recorded: AgentDojo important_instructions on 140 pairs
    (runs/atk_ii) and the 15 image carriers (eval/vision_demo/results.json).

Any cell read from a saved run is marked "from cache" with the date the run was made.
"""

import argparse
import glob
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUNS = ROOT / "runs"


RUN_DATES = RUNS / "run_dates.json"   # when each cached input was made; a fresh clone has new file times


def day(path) -> str:
    rel = Path(path).resolve().relative_to(ROOT).as_posix()
    dates = load(RUN_DATES) if RUN_DATES.exists() else {}
    if rel in dates:
        return dates[rel]
    return datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%b %d, %Y")


def stamp(ts: str) -> str:
    """AgentDojo evaluation_timestamp ("2026-10-27 12:00:29") in the same format as day()."""
    return datetime.strptime(ts[:10], "%Y-%m-%d").strftime("%b %d, %Y")


def cache_note(path) -> str:
    return f"from cache, {day(path)}"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# ---------------------------------------------------------------- (a) worst-case replay

def replay_fresh(split, mode):
    from agentdojo.agent_pipeline import AgentPipeline
    from agentdojo.attacks.attack_registry import load_attack
    from agentdojo.task_suite.load_suites import get_suite

    from scripts.run_worstcase import ATTACK, SPLITS, run, summarize

    suite = get_suite("v1.2.2", "workspace")
    named = AgentPipeline([])
    named.name = "vllm_parsed"
    attack = load_attack(ATTACK, suite, named)
    users = [suite.user_tasks[f"user_task_{i}"] for i in SPLITS[split]]
    pairs = ([(u, None) for u in users] if mode == "clean"
             else [(u, i) for u in users for i in suite.injection_tasks.values()])
    return summarize(run("none", suite, attack, pairs) + run("gate", suite, attack, pairs))


SAVED_REPLAY = {("tune", "attack"): "worstcase_v1_tune", ("tune", "clean"): "worstcase_v1_tune_clean",
                ("heldout", "attack"): "worstcase_v1_heldout", ("heldout", "clean"): "worstcase_v1_heldout_clean"}
SAVED_JUDGED = {("tune", "attack"): "final_tune_judge", ("tune", "clean"): "final_tune_judge_clean",
                ("heldout", "attack"): "layer2b_heldout", ("heldout", "clean"): "layer2b_heldout_clean"}


def section_a(fresh):
    rows = []
    for split, label in (("tune", "tuning 0-19"), ("heldout", "held-out 20-39")):
        res = {}
        for mode in ("attack", "clean"):
            if fresh:
                res[mode], note = replay_fresh(split, mode), "re-run now"
            else:
                path = RUNS / SAVED_REPLAY[(split, mode)] / "summary.json"
                res[mode], note = load(path), cache_note(path)
        a, c = res["attack"], res["clean"]
        rows.append([label, "no gate", f"{a['none']['attack_success']}/120", f"{a['none']['utility']}/280",
                     f"{c['none']['utility']}/20", "–", "–", "–", note])
        g, gc = a["gate"], c["gate"]
        rows.append([label, "gate", f"{g['attack_success']}/120", f"{g['utility']}/280", f"{gc['utility']}/20",
                     g["user_calls_blocked"], g["user_calls_asked"], "–", note])
        ja, jc = (RUNS / SAVED_JUDGED[(split, m)] / "summary.json" for m in ("attack", "clean"))
        if ja.exists() and jc.exists():
            j, jcl = load(ja)["gate"], load(jc)["gate"]
            jd = j.get("judge", {})
            appr = sum(jd.get(p, {}).get("approve", 0) for p in ("user", "injection"))
            false_appr = jd.get("injection", {}).get("approve", 0)
            rows.append([label, "gate + judge", f"{j['attack_success']}/120", f"{j['utility']}/280",
                         f"{jcl['utility']}/20", j["user_calls_blocked"], j["user_calls_asked"],
                         f"{appr} ({false_appr} false)", cache_note(ja)])
        else:
            rows.append([label, "gate + judge", "not run", "", "", "", "", "", ""])
    return table(["half", "arm", "attack success (replayable)", "utility, attacked (280 pairs)",
                  "utility, clean (20)", "user calls blocked", "user calls asked", "judge approvals", "source"],
                 rows)


# ---------------------------------------------------------------- (b) vision worst case

def section_b(fresh):
    sys.path.insert(0, str(ROOT / "eval" / "vision_demo"))
    import worstcase

    rows = []
    for set_name, label in (("1", "set 1 (original)"), ("2", "set 2 (fresh seed, new wording/placement)")):
        path = RUNS / f"vision_wc_set{set_name}.json"
        if fresh or not path.exists():
            results, _ = worstcase.run(set_name)
            summ = worstcase.summary(results)
            path.write_text(json.dumps({"set": set_name, "summary": summ, "results": results}, indent=1),
                            encoding="utf-8")
            note = "re-run now (OCR text from cache, " + day(worstcase.SETS[set_name] / "ocr") + ")"
        else:
            summ, note = load(path)["summary"], cache_note(path)
        n, g = summ["none"], summ["gate"]
        rows.append([label, "no gate", f"{n['attack_success']}/{n['carriers']}", f"{n['benign_ok']}/{n['episodes']}",
                     "–", "–", "–", "–", note])
        rows.append([label, "gate", f"{g['attack_success']}/{g['carriers']}", f"{g['benign_ok']}/{g['episodes']}",
                     f"{g['carriers_blocked']}/{g['carriers']}", f"{g['false_blocks_clean']}/{g['clean']}",
                     f"{g['explanation_names_image']}/{g['carriers']}", f"{g['address_traced_to_image']}/{g['carriers']}",
                     note])
    return table(["image set", "arm", "attack success (15 carriers)", "benign answers (30)", "carriers blocked",
                  "false blocks (15 clean)", "block names the image", "address traced to the image", "source"],
                 rows)


# ---------------------------------------------------------------- (c) live clean run

def agentdojo_results(run):
    files = glob.glob(str(RUNS / run / "vllm_parsed*" / "workspace" / "user_task_*" / "none" / "none.json"))
    return [load(f) for f in files]


def section_c():
    rows = []
    base = agentdojo_results("full_clean_v2")
    when = stamp(max(r["evaluation_timestamp"] for r in base))
    rows.append(["no gate", f"{sum(r['utility'] for r in base)}/{len(base)}", "–", "–", "–", "–",
                 f"from cache, {when} (runs/full_clean_v2)"])
    summ = RUNS / "final_live" / "summary.json"
    if summ.exists():
        s = load(summ)
        rc = s["gate"]["risky_calls"]
        judge = [json.loads(line) for line in (RUNS / "final_live" / "judge_log.jsonl").read_text(
            encoding="utf-8").splitlines()] if (RUNS / "final_live" / "judge_log.jsonl").exists() else []
        appr = sum(e["decision"] == "approve" for e in judge)
        rows.append(["gate + judge", f"{sum(s['utility'].values())}/{s['tasks_run']}", rc["block"], rc["ask"],
                     f"{appr} approve / {len(judge) - appr} deny", f"${s['spent_usd']:.4f}",
                     f"{cache_note(summ)} (runs/final_live)"])
    else:
        rows.append(["gate + judge", "not run", "", "", "", "", ""])
    return table(["arm", "utility", "risky calls blocked", "asks left after judge", "judge calls", "cost",
                  "source"], rows)


# ---------------------------------------------------------------- (d) recorded real attacks

def section_d():
    files = [f for f in glob.glob(str(RUNS / "atk_ii" / "vllm_parsed" / "workspace" / "user_task_*" / "*" / "*.json"))
             if Path(f).parent.name != "none"]
    rs = [load(f) for f in files]
    when = stamp(max(r["evaluation_timestamp"] for r in rs))
    vis = load(ROOT / "eval/vision_demo/results.json")
    car = [r for k, r in vis.items() if k.startswith("none/") and r["carrier"]]
    rows = [["AgentDojo workspace, important_instructions, user tasks 0-9 x 14 injections", "no gate",
             f"{sum(r['security'] for r in rs)}/{len(rs)}", f"{sum(r['utility'] for r in rs)}/{len(rs)}",
             f"from cache, {when} (runs/atk_ii)"],
            ["15 image carriers (hidden share_file line)", "no gate", f"{sum(r['attack_success'] for r in car)}/15",
             f"{sum(r['benign_ok'] for r in car)}/15", cache_note(ROOT / "eval/vision_demo/results.json")]]
    return table(["attack", "arm", "attack success", "utility under attack", "source"], rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cached", action="store_true", help="read (a) and (b) from saved runs instead of re-running")
    a = ap.parse_args(argv)
    out = ["## (a) Worst-case replay (scripted compromised agent; 6 of 14 goals replayable)", section_a(not a.cached),
           "## (b) Vision worst case (scripted agent obeys every carrier line)", section_b(not a.cached),
           "## (c) Live clean run, Muse Spark Open, 40 workspace tasks", section_c(),
           "## (d) Muse Spark under real attacks (recorded, no gate)", section_d()]
    text = "\n\n".join(out) + "\n"
    print(text)
    (RUNS / "final_table.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
