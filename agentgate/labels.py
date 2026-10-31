"""Origin labels: where a piece of content came from."""

from enum import IntEnum


class Origin(IntEnum):
    """Higher value = more trusted. Only USER is trusted by default."""

    UNTRUSTED_PIXELS = 0  # text recovered from a screenshot or an image
    UNTRUSTED_TEXT = 1    # text returned by a tool (web page, email, file, event)
    USER = 3              # the person's own request

    @property
    def plain(self) -> str:
        return {
            Origin.UNTRUSTED_PIXELS: "text inside an image or screenshot",
            Origin.UNTRUSTED_TEXT: "text from a tool result (email, web page, file or event)",
            Origin.USER: "your own request",
        }[self]
