"""Whether a number in the user's request names an id.

A bare number only counts as an id the user named if an id-like cue comes within 3 tokens before it
("id", "file", "event", "email", "#") or it is quoted ('13', "13"). A number that is part of a date
("June 13", "13 June", "13/06", "10:13") or an amount ("$13", "13 EUR", "13%") never counts.
"""

import re

CUES = frozenset({"id", "ids", "file", "files", "event", "events", "email", "emails"})
MONTHS = frozenset("""january february march april may june july august september october november december
                   jan feb mar apr jun jul aug sep sept oct nov dec""".split())
CURRENCY_WORDS = frozenset({"eur", "euro", "euros", "usd", "dollar", "dollars", "gbp", "pound", "pounds",
                            "chf", "percent"})
_TOKEN = re.compile(r"#|[a-z0-9]+")


def is_number(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value or ""))


def _is_date_or_amount(before: str, after: str) -> bool:
    prev = _TOKEN.findall(before)[-1:]
    nxt = _TOKEN.findall(after)[:1]
    if any(t in MONTHS for t in prev + nxt) or (nxt and nxt[0] in CURRENCY_WORDS):
        return True
    b, a = before.rstrip(), after.lstrip()
    return (before[-1:] in {"/", ":", "$", "€", "£"} or b[-1:] in {"$", "€", "£"}
            or after[:1] in {"/", ":", "%"} or a[:1] in {"%", "€", "$", "£"})


def named_as_id(text_norm: str, number: str) -> bool:
    """True if `number` occurs in the (normalised) user text as a named id."""
    pattern = r"(?<![\w@.\-])" + re.escape(number) + r"(?![\w@\-]|\.\w)"
    for m in re.finditer(pattern, text_norm):
        before, after = text_norm[:m.start()], text_norm[m.end():]
        if _is_date_or_amount(before, after):
            continue
        if before[-1:] in {"'", '"', "`"} and after[:1] == before[-1:]:
            return True
        window = _TOKEN.findall(before)[-3:]
        if any(t == "#" or t in CUES for t in window):
            return True
    return False
