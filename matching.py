"""Whole-word matching for job titles and place names.

A phrase matches when every one of its words appears as its own word.
Order does not matter. "hr" does not match inside "Three-shift", and
"software engineer" matches "Engineer, Software". A star on the end of
a word ("develop*") matches words that start with those letters.
"""

from __future__ import annotations

import re
import unicodedata


# Letters, plus a trailing * so "develop*" stays one token.
_WORD = re.compile(r"[^\W\d_]+(?:\*)?", re.UNICODE)


def normalise(text: object) -> list[str]:
    """Casefold, strip accents, and split on anything that is not a letter.

    Hyphens, commas, and slashes become gaps. "Software-Entwickler" is
    "software" and "entwickler". A trailing * is kept, for "develop*".
    """
    raw = "" if text is None else str(text)
    decomposed = unicodedata.normalize("NFKD", raw)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _WORD.findall(stripped.casefold())


def phrase_matches(text: object, phrase: object) -> bool:
    """True when every word of phrase appears as a whole word in text.

    The words may be in any order. A word that ends in * matches a word
    that starts with the letters before the star.
    """
    haystack = normalise(text)
    needles = normalise(phrase)
    if not needles:
        return False
    for needle in needles:
        if needle.endswith("*"):
            prefix = needle[:-1]
            if not prefix or not any(token.startswith(prefix) for token in haystack):
                return False
        elif needle not in haystack:
            return False
    return True


def _same_token(token: str, needle: str) -> bool:
    """One normalised word. A trailing * still means "starts with"."""
    if needle.endswith("*"):
        prefix = needle[:-1]
        return bool(prefix) and token.startswith(prefix)
    return token == needle


def sequence_matches(text: object, phrase: object) -> bool:
    """True when the words of phrase appear in text in the same order, together.

    The same normalise as phrase_matches is used, so capitals, accents, and
    punctuation do not matter. The words have to be consecutive. A trailing *
    keeps its prefix meaning.
    """
    haystack = normalise(text)
    needles = normalise(phrase)
    if not needles or len(needles) > len(haystack):
        return False
    width = len(needles)
    last = len(haystack) - width
    for start in range(last + 1):
        window = haystack[start : start + width]
        if all(_same_token(token, needle) for token, needle in zip(window, needles)):
            return True
    return False
