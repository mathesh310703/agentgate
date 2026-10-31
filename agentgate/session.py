"""A session records what the user asked and what each source returned, with origin labels."""

from dataclasses import dataclass

from .fields import is_id_field, leaves
from .ids import is_number, named_as_id
from .labels import Origin
from .normalize import contains_token, normalize
from .policy import Policy


@dataclass
class Record:
    origin: Origin
    text: str
    source: str   # "user", a tool name, or "screenshot:<name>"
    norm: str
    field: str = ""     # structured tool results: the key the value sat under
    part: str = "text"  # "text" (unparsed string), "structured" or "free_text"

    @property
    def where(self) -> str:
        return f"{self.source}.{self.field}" if self.field else self.source


class Session:
    def __init__(self, user_request: str, policy: Policy):
        self.policy = policy
        self.records: list = []
        self.add_user(user_request)

    def add_user(self, text: str) -> None:
        self._add(Origin.USER, text, "user")

    def add_tool_output(self, tool: str, output, error: str = None) -> None:
        """Record a tool result. A structured result (dict, list, pydantic model) is split into one record
        per leaf, labelled structured or free text; a plain string is kept whole. Error text is free text."""
        parts = list(leaves(output, self.policy.free_text_fields))
        for field, value, part in parts:
            self._add(Origin.UNTRUSTED_TEXT, value, tool, field, part)
        if not parts and not isinstance(output, (dict, list, tuple, set)):
            self._add(Origin.UNTRUSTED_TEXT, output, tool)
        if error:
            self._add(Origin.UNTRUSTED_TEXT, error, tool, "error", "free_text")

    def add_pixels(self, text: str, source: str = "screenshot") -> None:
        """Text recovered from an image or screenshot (OCR). Always untrusted."""
        self._add(Origin.UNTRUSTED_PIXELS, text, f"screenshot:{source}")

    def _add(self, origin: Origin, text, source: str, field: str = "", part: str = "text") -> None:
        text = "" if text is None else str(text)
        self.records.append(Record(origin, text, source, normalize(text), field, part))

    def find(self, value) -> list:
        needle = normalize(value)
        return [r for r in self.records if contains_token(r.norm, needle)]

    def trusted_for(self, record: Record, kind: str, value=None) -> bool:
        """Whether this record is a trusted source for this kind of value:

        * the user's request, except that a bare number only counts as an id if it is named as one
          (ids.py: "June 13" does not name id 13);
        * a structured field of any tool result, for kinds in policy.structured_trust (ids: id fields only);
        * an unparsed string or structured field from a tool the policy trusts for this kind.
        Free text (description, body, content, subject, title, error messages) is never trusted.
        """
        if record.origin == Origin.USER:
            needle = normalize(value) if value is not None else ""
            if kind == "id" and is_number(needle):
                return named_as_id(record.norm, needle)
            return True
        trusted_tool = self.policy.is_trusted_source(record.source, kind)
        if record.part == "structured":
            if kind == "id" and not is_id_field(record.field):
                return False
            return kind in self.policy.structured_trust or trusted_tool
        if record.part == "text":
            return trusted_tool
        return False
