"""Print spend per stage from eval/cost_log.csv.

  python -m agentlab.spend
"""

from __future__ import annotations

from collections import defaultdict

from agentlab.llm import CONFIRM_TOTAL_USD, COST_LOG, STAGE_BUDGETS, read_log


def main() -> int:
    rows = read_log()
    calls, cost, tok_in, tok_out, tok_r = (defaultdict(int), defaultdict(float), defaultdict(int),
                                           defaultdict(int), defaultdict(int))
    for r in rows:
        s = r.get("stage") or "unknown"
        calls[s] += 1
        cost[s] += float(r["cost_usd"])
        tok_in[s] += int(r["prompt_tokens"])
        tok_out[s] += int(r["completion_tokens"])
        tok_r[s] += int(r.get("reasoning_tokens") or 0)
    print(f"cost log: {COST_LOG}")
    print(f"{'stage':<10}{'calls':>7}{'in tok':>10}{'out tok':>10}{'(reason)':>10}{'spent $':>10}"
          f"{'budget $':>10}{'left $':>10}")
    for s in [*STAGE_BUDGETS, *sorted(set(cost) - set(STAGE_BUDGETS))]:
        b = STAGE_BUDGETS.get(s)
        left = f"{b - cost[s]:.4f}" if b is not None else "-"
        print(f"{s:<10}{calls[s]:>7}{tok_in[s]:>10}{tok_out[s]:>10}{tok_r[s]:>10}{cost[s]:>10.4f}"
              f"{(b if b is not None else 0):>10.2f}{left:>10}")
    total = sum(cost.values())
    print(f"{'total':<10}{sum(calls.values()):>7}{sum(tok_in.values()):>10}{sum(tok_out.values()):>10}"
          f"{sum(tok_r.values()):>10}{total:>10.4f}{sum(STAGE_BUDGETS.values()):>10.2f}")
    print(f"total-spend confirmation at ${CONFIRM_TOTAL_USD:.0f}: "
          f"{'REACHED' if total >= CONFIRM_TOTAL_USD else f'${CONFIRM_TOTAL_USD - total:.4f} to go'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
