"""Pick a CV preset from the job location. The mapping lives in the preset files."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from regions import EU_EEA, contains_phrase, country_from_places, fold_text

from cv.presets import list_presets, load_preset


_REMOTE_ONLY = frozenset(
    {"remote", "worldwide", "anywhere", "global", "work from home", "working from home"}
)


def suggest_format(job: dict, directory: Path | None = None) -> str:
    """A named country wins. Remote or unknown places use the region, then the default."""
    presets = [load_preset(name, directory) for name in list_presets(directory)]
    default = next((item.id for item in presets if item.default_fallback), "us_resume")
    location = str(job.get("location") or "")
    place = str(job.get("place_searched") or "")
    for text in (location, place):
        if not text.strip():
            continue
        chosen = _from_text(text, presets, default)
        if chosen is not None:
            return chosen
    return default


def _from_text(text: str, presets, default: str) -> str | None:
    country = _country_from_location(text)
    if country:
        for item in presets:
            if country in item.countries:
                return item.id
        for item in presets:
            if item.fallback_eu_eea and country in EU_EEA:
                return item.id
        for item in presets:
            if country in item.fallback_countries:
                return item.id
        return default
    for item in presets:
        for word in item.fallback_words:
            if contains_phrase(word, text):
                return item.id
    if fold_text(text) in _REMOTE_ONLY:
        return None
    return default


def _country_from_location(text: str) -> str | None:
    place = SimpleNamespace(remote=False, name=text, indeed_location=text, linkedin_location="")
    return country_from_places([place])
