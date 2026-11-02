"""Local job-title words shipped with the program.

The lists in synonyms/roles.yaml are a starter set, written by hand.
They are not a complete dictionary.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from matching import normalise


# Languages stored for every role. English plus the starter translations.
LANGUAGES = ("en", "it", "de", "fr", "es", "pt", "nl", "pl")

# The language to suggest for a country code. Missing means English only.
COUNTRY_LANGUAGES = {
    "italy": ("it",),
    "germany": ("de",),
    "austria": ("de",),
    "switzerland": ("de", "fr", "it"),
    "france": ("fr",),
    "belgium": ("nl", "fr"),
    "spain": ("es",),
    "mexico": ("es",),
    "argentina": ("es",),
    "chile": ("es",),
    "colombia": ("es",),
    "peru": ("es",),
    "venezuela": ("es",),
    "ecuador": ("es",),
    "costa rica": ("es",),
    "panama": ("es",),
    "uruguay": ("es",),
    "portugal": ("pt",),
    "brazil": ("pt",),
    "netherlands": ("nl",),
    "poland": ("pl",),
    "luxembourg": ("fr", "de"),
}


def catalog_path() -> Path:
    """The synonyms file that ships in this folder."""
    return Path(__file__).resolve().parent / "synonyms" / "roles.yaml"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    """The role lists from synonyms/roles.yaml."""
    loaded = yaml.safe_load(catalog_path().read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("synonyms/roles.yaml should be a group of roles.")
    return loaded


def _same_words(left: object, right: object) -> bool:
    return normalise(left) == normalise(right) and bool(normalise(left))


def lookup_role(role: str, catalog: dict | None = None) -> str | None:
    """The catalog key for a job title, or None when we have no list for it."""
    table = load_catalog() if catalog is None else catalog
    for key, entry in table.items():
        names = [key]
        if isinstance(entry, dict):
            names.extend(entry.get("en") or [])
        if any(_same_words(role, name) for name in names):
            return str(key)
    return None


def _dedupe(phrases: list[str]) -> list[str]:
    kept: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        text = " ".join(str(phrase).split())
        if not text:
            continue
        key = " ".join(normalise(text))
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(text)
    return kept


def suggestions_for(roles: list[str], country: str, catalog: dict | None = None) -> dict[str, list[str]]:
    """Local titles to offer for these roles in this country.

    English extras are included when they are not the role the person typed.
    Roles with no list are left out.
    """
    table = load_catalog() if catalog is None else catalog
    languages = COUNTRY_LANGUAGES.get(country, ())
    found: dict[str, list[str]] = {}
    for role in roles:
        key = lookup_role(role, table)
        if key is None:
            continue
        entry = table.get(key) or {}
        phrases: list[str] = []
        for language in languages:
            phrases.extend(entry.get(language) or [])
        for phrase in entry.get("en") or []:
            if not _same_words(phrase, role):
                phrases.append(phrase)
        cleaned = _dedupe(phrases)
        if cleaned:
            found[role] = cleaned
    return found
