"""Text normalisation and whole-token matching.

Provenance here is normalised string matching. Known limits (also in the README):
a value the model paraphrases, translates, splits across several fields, or encodes
in a way not handled below will not be traced.
"""

import html
import re
import unicodedata
import urllib.parse

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)


def normalize(value) -> str:
    s = str(value)
    s = unicodedata.normalize("NFKC", s).translate(_ZERO_WIDTH)
    s = urllib.parse.unquote(html.unescape(s)).lower()
    s = re.sub(r"\s*[\[\(]\s*at\s*[\]\)]\s*", "@", s)      # "bob [at] x.com"
    s = re.sub(r"\s*[\[\(]\s*dot\s*[\]\)]\s*", ".", s)      # "x (dot) com"
    s = re.sub(r"\s*@\s*", "@", s)                          # "bob @ x.com"
    s = re.sub(r"\s+", " ", s).strip()
    return s


def contains_token(haystack_norm: str, needle_norm: str) -> bool:
    """True if needle appears in haystack as a whole token (not inside a longer one)."""
    if not needle_norm:
        return False
    pattern = r"(?<![\w@.\-])" + re.escape(needle_norm) + r"(?![\w@\-]|\.\w)"
    return re.search(pattern, haystack_norm) is not None
