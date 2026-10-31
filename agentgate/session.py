"""A session records what the user asked and what each source returned, with origin labels."""

from dataclasses import dataclass

from .labels import Origin
from .normalize import contains_token, normalize
from .policy import Policy


@dataclass
class Record:
    origin: Origin
    text: str
    source: str   # "user", a tool name, or "screenshot:<name>"
    norm: str


class Session:
    def __init__(self, user_request: str, policy: Policy):
        self.policy = policy
        self.records: list = []
        self.add_user(user_request)

    def add_user(self, text: str) -> None:
        self._add(Origin.USER, text, "user")

    def add_tool_output(self, tool: str, text: str) -> None:
        self._add(Origin.UNTRUSTED_TEXT, text, tool)

    def add_pixels(self, text: str, source: str = "screenshot") -> None:
        """Text recovered from an image or screenshot (OCR). Always untrusted."""
        self._add(Origin.UNTRUSTED_PIXELS, text, f"screenshot:{source}")

    def _add(self, origin: Origin, text: str, source: str) -> None:
        text = "" if text is None else str(text)
        self.records.append(Record(origin, text, source, normalize(text)))

    def find(self, value) -> list:
        needle = normalize(value)
        return [r for r in self.records if contains_token(r.norm, needle)]

    def trusted_for(self, record: Record, kind: str) -> bool:
        """A record is a trusted source of this kind of value if it is the user,
        or if it came from a tool the policy trusts for that kind."""
        if record.origin == Origin.USER:
            return True
        return self.policy.is_trusted_source(record.source, kind)
