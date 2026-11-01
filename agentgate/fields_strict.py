"""Strict mode (optional, off by default): only identity fields vouch for a recipient.

Added after the out-of-distribution suites result (eval/SUITES_V0.md): in the default configuration any
structured leaf of a tool result vouches for a recipient, and two suites put attacker text in leaves that only
look structured: travel review texts are dict values keyed by a hotel name, and slack channel names are items
of a plain list. In strict mode a structured leaf vouches for a recipient only if its field name is in
IDENTITY_FIELDS; every other leaf (values under arbitrary keys, bare list items, ids, dates, sizes) counts as
free text for recipients. Ids, amounts and every other kind are trusted exactly as in the default mode, and a
tool the policy trusts for recipients (e.g. a contact search) still vouches for them.

The frozen files (gate.py, session.py, fields.py, policy.py) are unchanged: StrictSession subclasses Session
and overrides only trusted_for. Enable it with GatedToolsExecutor(..., strict=True) or
`python agentgate/mcp_server.py --strict`.
"""

from .labels import Origin
from .session import Session

# identity fields: the slot in the tool's data model holds a person or address, not prose
#   workspace: sender, recipients, cc, bcc, participants, owner, organizer, shared_with, email (contacts)
#   banking: sender, recipient (transactions); slack: sender, recipient (messages), user_email
IDENTITY_FIELDS = frozenset({
    "email", "emails", "email_address", "sender", "from", "to", "cc", "bcc", "recipient", "recipients",
    "participants", "attendees", "owner", "organizer", "shared_with", "user_email",
})


def is_identity_field(name: str) -> bool:
    return (name or "").lower().rstrip("_") in IDENTITY_FIELDS


class StrictSession(Session):
    """Session whose structured leaves vouch for a recipient only under an identity field name."""

    strict = True

    def trusted_for(self, record, kind, value=None) -> bool:
        if (kind == "recipient" and record.origin != Origin.USER and record.part == "structured"
                and not is_identity_field(record.field)):
            return self.policy.is_trusted_source(record.source, kind)
        return super().trusted_for(record, kind, value)


def make_session(user_request, policy, scorer=None, strict=False) -> Session:
    return (StrictSession if strict else Session)(user_request, policy, scorer=scorer)
