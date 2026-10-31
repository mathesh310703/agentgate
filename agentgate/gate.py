"""The gate: a deterministic check on every tool call, before it runs. No model involved."""

import re
from dataclasses import dataclass, field

from .labels import Origin
from .session import Session


@dataclass
class Finding:
    arg: str
    value: str
    kind: str
    verdict: str          # "ok" | "untrusted" | "unknown" | "unnamed" | "sender_only"
    origin: Origin = None  # most specific untrusted origin seen, if any
    source: str = ""
    score: float = None    # injection score of the source record (or, for sender_only, of the worst text)
    flagged: str = ""      # sender_only: the free-text record whose score triggered the rule
    entry: str = ""        # ok findings from a structured record: its listing entry (Record.entry)


@dataclass
class Decision:
    action: str            # "allow" | "block" | "ask"
    tool: str
    reason: str
    findings: list = field(default_factory=list)
    judge: dict = None     # set by judge.judge_decision when the intent judge reviewed an "ask"

    @property
    def allowed(self) -> bool:
        return self.action == "allow"

    def explain(self) -> str:
        return self.reason


def _atoms(value):
    """Flatten an argument value into strings to check."""
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, (list, tuple, set)):
        out = []
        for v in value:
            out += _atoms(v)
        return out
    if isinstance(value, dict):
        out = []
        for v in value.values():
            out += _atoms(v)
        return out
    s = str(value).strip()
    if not s:
        return []
    if isinstance(value, str) and re.search(r"[;,]", s):
        return [p.strip() for p in re.split(r"[;,]", s) if p.strip()]
    return [s]


class Gate:
    def __init__(self, policy):
        self.policy = policy

    def check(self, tool: str, args: dict, session: Session) -> Decision:
        rule = self.policy.rules.get(tool)
        if rule is None:
            return Decision("allow", tool, "Tool is not on the risky list.")

        findings, bad, untraced_ids = [], [], []
        for arg, kind in rule.sensitive.items():
            for atom in _atoms((args or {}).get(arg)):
                recs = session.find(atom)
                trusted = [r for r in recs if session.trusted_for(r, kind, atom)]
                if trusted:
                    suspect = self._sender_only(kind, trusted, session)
                    if suspect is not None:
                        f = Finding(arg, atom, kind, "sender_only", trusted[0].origin, trusted[0].where,
                                    suspect.score, suspect.where)
                        findings.append(f)
                        bad.append(f)
                        continue
                    findings.append(Finding(arg, atom, kind, "ok", source=trusted[0].where,
                                            entry=trusted[0].entry))
                    continue
                untrusted = [r for r in recs if r.origin != Origin.USER]
                if untrusted:
                    # name the most specific origin: pixels first, then text
                    worst = min(untrusted, key=lambda r: r.origin)
                    f = Finding(arg, atom, kind, "untrusted", worst.origin, worst.where, worst.score)
                    findings.append(f)
                    bad.append(f)
                elif self.policy.block_unknown:
                    # "unnamed": the number is in the request, but not as an id (a date, an amount)
                    f = Finding(arg, atom, kind, "unnamed" if recs else "unknown")
                    findings.append(f)
                    bad.append(f)

        if bad:
            return Decision("block", tool, self._reason(tool, bad), findings)

        if rule.confirm_untraced_ids:
            for f in findings:
                if f.kind == "id" and f.source != "user":
                    untraced_ids.append(f)
            if untraced_ids:
                f = untraced_ids[0]
                return Decision(
                    "ask", tool,
                    f"'{tool}' is destructive and the target ({f.arg}={f.value}) was not named in "
                    f"your request; it was taken from '{f.source}'. Please confirm.",
                    findings,
                )
        return Decision("allow", tool, "All sensitive arguments trace to your request or a trusted source.",
                        findings)

    def _sender_only(self, kind, trusted, session):
        """A recipient whose only trusted sources are attacker-chosen structured fields (sender, owner) is
        not trusted when the session holds untrusted free text that scores as a likely injection.
        Returns that free-text record, or None."""
        if kind != "recipient":
            return None
        if not all(r.origin != Origin.USER and r.part == "structured" and r.field in self.policy.attacker_fields
                   for r in trusted):
            return None
        worst = session.most_suspicious()
        if worst is not None and worst.score >= self.policy.injection_threshold:
            return worst
        return None

    @staticmethod
    def _reason(tool: str, bad: list) -> str:
        parts = []
        for f in bad:
            score = f" (injection score {f.score:.2f})" if f.score is not None else ""
            if f.verdict == "untrusted":
                parts.append(f"{f.arg}='{f.value}' came from {f.origin.plain} ({f.source}){score}")
            elif f.verdict == "sender_only":
                parts.append(f"{f.arg}='{f.value}' comes only from the '{f.source}' field, which whoever sent or "
                             f"shared the item chooses, and text in this session looks like an injected "
                             f"instruction ({f.flagged}, injection score {f.score:.2f})")
            elif f.verdict == "unnamed":
                parts.append(f"{f.arg}='{f.value}' appears in your request only as a number (a date or amount), "
                             f"not as an id")
            else:
                parts.append(f"{f.arg}='{f.value}' does not appear in your request or any trusted source")
        return f"Blocked '{tool}': " + "; ".join(parts) + "."
