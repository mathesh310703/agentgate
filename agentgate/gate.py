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
    verdict: str          # "ok" | "untrusted" | "unknown"
    origin: Origin = None  # most specific untrusted origin seen, if any
    source: str = ""


@dataclass
class Decision:
    action: str            # "allow" | "block" | "ask"
    tool: str
    reason: str
    findings: list = field(default_factory=list)

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
                trusted = [r for r in recs if session.trusted_for(r, kind)]
                if trusted:
                    findings.append(Finding(arg, atom, kind, "ok", source=trusted[0].source))
                    continue
                untrusted = [r for r in recs if r.origin != Origin.USER]
                if untrusted:
                    # name the most specific origin: pixels first, then text
                    worst = min(untrusted, key=lambda r: r.origin)
                    f = Finding(arg, atom, kind, "untrusted", worst.origin, worst.source)
                    findings.append(f)
                    bad.append(f)
                elif self.policy.block_unknown:
                    f = Finding(arg, atom, kind, "unknown")
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

    @staticmethod
    def _reason(tool: str, bad: list) -> str:
        parts = []
        for f in bad:
            if f.verdict == "untrusted":
                parts.append(f"{f.arg}='{f.value}' came from {f.origin.plain} ({f.source})")
            else:
                parts.append(f"{f.arg}='{f.value}' does not appear in your request or any trusted source")
        return f"Blocked '{tool}': " + "; ".join(parts) + "."
