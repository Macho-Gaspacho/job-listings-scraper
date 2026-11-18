"""Turn a large scrape into a short, ranked list.

A normal search runs this on its own. The rules live in shortlist_defaults.yaml
and can be overridden under shortlist: in config.yaml. Nothing here calls a
paid service or an AI API.

Indeed rows are often a short preview. This module does not open Indeed job
pages. When the same role at the same company has a longer description from
another site, that text is used for the years and language checks, and the
reason says so. LinkedIn descriptions that are still missing are read from
the public job page, one at a time, with a pause, and stored in a cache.
"""

from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from listings import OUTPUT_FIELDS, city_key, clean_text, company_name_key
from matching import normalise, phrase_matches
from save_results import _http_link, safe_cell
from sources import retry_delay, transient_reason

try:
    from langdetect import DetectorFactory, LangDetectException, detect_langs

    DetectorFactory.seed = 0
except ImportError:  # pragma: no cover - the requirements file installs it
    detect_langs = None
    LangDetectException = Exception


DEFAULTS_PATH = Path(__file__).resolve().parent / "shortlist_defaults.yaml"

HEADER_TO_KEY = {label: key for key, label in OUTPUT_FIELDS}
HEADER_TO_KEY.update({key: key for key, _label in OUTPUT_FIELDS})

_LANG_NAMES = {
    "en": "English",
    "it": "Italian",
    "de": "German",
    "nl": "Dutch",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "pl": "Polish",
    "sv": "Swedish",
    "da": "Danish",
    "cs": "Czech",
    "fi": "Finnish",
    "no": "Norwegian",
    "hu": "Hungarian",
    "ro": "Romanian",
    "el": "Greek",
    "ru": "Russian",
    "uk": "Ukrainian",
    "tr": "Turkish",
    "ca": "Catalan",
}
_NAME_TO_CODE = {name.casefold(): code for code, name in _LANG_NAMES.items()}
_NAME_TO_CODE.update(
    {
        "english": "en",
        "italian": "it",
        "italiano": "it",
        "german": "de",
        "deutsch": "de",
        "dutch": "nl",
        "nederlands": "nl",
        "french": "fr",
        "francais": "fr",
        "spanish": "es",
        "espanol": "es",
        "portuguese": "pt",
        "polish": "pl",
        "swedish": "sv",
    }
)

_TITLE_JUNIOR = (
    "junior",
    "associate",
    "graduate",
    "entry level",
    "entry-level",
    "early career",
)
_BODY_JUNIOR = (
    "junior",
    "entry level",
    "entry-level",
    "early career",
    "new graduate",
    "recent graduate",
)

_RANGE = re.compile(
    r"(?P<a>\d+)\s*(?:\+|plus)?\s*(?:to|-|–|—|/)\s*(?P<b>\d+)\s*\+?\s*"
    r"(?:years?|yrs?|jahre(?:n)?|jaar|ans|anni|años|anos|lat)\b",
    re.I,
)
_PLUS = re.compile(
    r"(?P<a>\d+)\s*(?:\+|plus)\s*"
    r"(?:years?|yrs?|jahre(?:n)?|jaar|ans|anni|años|anos|lat)\b",
    re.I,
)
_N_YEARS_EXP = re.compile(
    r"(?P<a>\d+)\s*(?:\+|plus)?\s*"
    r"(?:years?|yrs?|jahre(?:n)?|jaar|ans|anni|años|anos|lat)\s+"
    r"(?:of\s+|de\s+|di\s+|d['’]\s*)?"
    r"(?:experience|experiencia|expérience|ervaring|erfahrung|berufserfahrung|esperienza)\b",
    re.I,
)
_EXP_N_YEARS = re.compile(
    r"(?:experience|experiencia|expérience|ervaring|erfahrung|berufserfahrung|esperienza)"
    r".{0,30}?(?P<a>\d+)\s*(?:\+|plus)?\s*"
    r"(?:years?|yrs?|jahre(?:n)?|jaar|ans|anni|años|anos|lat)\b",
    re.I,
)
_AT_LEAST = re.compile(
    r"(?:at least|minimum of|minimum|min\.?|more than|over|at a minimum|"
    r"mindestens|minimaal|ten minste|almeno|au moins|mínimo|minimo|"
    r"al menos|co najmniej)\s+(?P<a>\d+)\s*(?:\+|plus)?\s*"
    r"(?:years?|yrs?|jahre(?:n)?|jaar|ans|anni|años|anos|lat)\b",
    re.I,
)
_WORD_YEARS = re.compile(
    r"\b(?P<w>three|four|five|six|seven|eight|nine|ten|drei|vier|fünf|funf|"
    r"trois|quatre|cinq|tre|quattro|cinque|drie|vijf)\s+"
    r"(?:or more\s+)?"
    r"(?:years?|jahre(?:n)?|jaar|ans|anni|años)\b",
    re.I,
)
_N_OR_MORE = re.compile(
    r"\b(?P<a>\d+)\s+or more\s+(?:years?|yrs?|jahre(?:n)?|jaar|ans|anni|años|anos|lat)\b",
    re.I,
)
_YEAR_WORDS = {
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "drei": 3,
    "vier": 4,
    "funf": 5,
    "fünf": 5,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "tre": 3,
    "quattro": 4,
    "cinque": 5,
    "drie": 3,
    "vijf": 5,
}
_EXPERIENCE_CUES = (
    "experience",
    "experiencia",
    "expérience",
    "ervaring",
    "erfahrung",
    "berufserfahrung",
    "esperienza",
    "qualification",
    "required",
    "requirement",
    "must have",
    "you have",
    "you bring",
    "you've spent",
    "you have spent",
    "candidate",
    "applicants",
    "mindestens",
    "minimaal",
    "almeno",
    "au moins",
    "at least",
    "minimum",
    "ausgeprägt",
    "ausgepragt",
    "product management",
    "project management",
    "as a product manager",
    "as a project manager",
    "in a pmo",
)
_COMPANY_AGE_CUES = (
    "we've",
    "we have been",
    "we have built",
    "our company",
    "founded",
    "legacy",
    "depuis plus",
    "al bijna",
    "years, we",
    "years we've",
    "years we have",
    "innove depuis",
    "headquartered",
    "global reach",
    "bildungsträger",
    "years of data",
    "years of activity",
    "heritage",
    "ist ein etablierter",
    "grounded in over",
    "the company is offering",
    "años de experiencia en el sector",
)
_EXPERIENCE_WORDS = (
    "experience",
    "experiencia",
    "expérience",
    "ervaring",
    "erfahrung",
    "berufserfahrung",
    "esperienza",
)
_YEAR_PATTERNS = (_RANGE, _PLUS, _N_YEARS_EXP, _EXP_N_YEARS, _AT_LEAST, _N_OR_MORE)
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_CONSECUTIVE_FETCH_FAILURES = 10
_SHEET_COLUMNS = (
    "Rank",
    "Score",
    "Reason",
    "Title",
    "Company",
    "Location",
    "Place searched",
    "Date posted",
    "Source",
    "URL",
    "Role searched",
    "Level",
    "Languages",
    "Visa",
    "Description status",
    "Required years",
    "Detected language",
    "Description",
)


@dataclass
class LocationPriority:
    label: str
    points: int
    places: tuple[str, ...]


@dataclass
class RolePhrase:
    label: str
    points: int
    phrases: tuple[str, ...]


@dataclass
class Rules:
    """The shortlist rules after defaults and config.yaml are combined."""

    enabled: bool = True
    top_n: int = 40
    max_required_years: int | None = 3
    allowed_languages: tuple[str, ...] = ()
    language_min_probability: float = 0.70
    title_only_probability: float = 0.85
    title_exclude: tuple[str, ...] = ()
    title_include: tuple[str, ...] = ()
    exclude_companies: tuple[str, ...] = ()
    exclude_countries: tuple[str, ...] = ()
    description_exclude: tuple[str, ...] = ()
    location_priorities: tuple[LocationPriority, ...] = ()
    other_location_points: int = 0
    keywords: tuple[str, ...] = ()
    role_phrases: tuple[RolePhrase, ...] = ()
    snippet_characters: int = 280
    pause_seconds: float = 2.0
    weights: dict = field(default_factory=dict)


def load_rules(overlay: dict | None = None) -> Rules:
    """Defaults from shortlist_defaults.yaml, with config.yaml values on top."""
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(defaults, dict):
        raise ValueError("shortlist_defaults.yaml should be a group of settings.")
    merged = _merge_overlay(defaults, overlay or {})
    return _rules_from_dict(merged)


def _merge_overlay(defaults: dict, overlay: dict) -> dict:
    merged = dict(defaults)
    for key, value in overlay.items():
        if (
            key == "weights"
            and isinstance(value, dict)
            and isinstance(merged.get("weights"), dict)
        ):
            merged["weights"] = {**merged["weights"], **value}
        else:
            merged[key] = value
    return merged


def _rules_from_dict(raw: dict) -> Rules:
    if not isinstance(raw, dict):
        raise ValueError("shortlist in config.yaml should be a group of settings.")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("shortlist.enabled must be true or false.")
    top_n = _whole_number(raw.get("top_n", 40), "top_n", 1, 1000)
    years = raw.get("max_required_years", 3)
    if years in (None, ""):
        max_years = None
    else:
        max_years = _whole_number(years, "max_required_years", 1, 40)
    languages = tuple(
        _language_code(item)
        for item in _text_list(raw.get("allowed_languages"))
    )
    minimum = raw.get("language_min_probability", 0.70)
    title_only = raw.get("title_only_probability", 0.85)
    if isinstance(minimum, bool) or not isinstance(minimum, (int, float)):
        raise ValueError("language_min_probability should be a number between 0 and 1.")
    if isinstance(title_only, bool) or not isinstance(title_only, (int, float)):
        raise ValueError("title_only_probability should be a number between 0 and 1.")
    pause = raw.get("pause_seconds", 2)
    if isinstance(pause, bool) or not isinstance(pause, (int, float)) or pause < 1:
        raise ValueError("shortlist pause_seconds must be a number from 1 upward.")
    weights = raw.get("weights") or {}
    if not isinstance(weights, dict):
        raise ValueError("shortlist weights should be a group of numbers.")
    clean_weights = {}
    for name, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"shortlist weight {name} should be a number.")
        clean_weights[str(name)] = int(value)
    return Rules(
        enabled=enabled,
        top_n=top_n,
        max_required_years=max_years,
        allowed_languages=languages,
        language_min_probability=float(minimum),
        title_only_probability=float(title_only),
        title_exclude=tuple(_text_list(raw.get("title_exclude"))),
        title_include=tuple(_text_list(raw.get("title_include"))),
        exclude_companies=tuple(_text_list(raw.get("exclude_companies"))),
        exclude_countries=tuple(_text_list(raw.get("exclude_countries"))),
        description_exclude=tuple(_text_list(raw.get("description_exclude"))),
        location_priorities=tuple(_location_priorities(raw.get("location_priorities"))),
        other_location_points=_whole_number(
            raw.get("other_location_points", 0), "other_location_points", 0, 100
        ),
        keywords=tuple(_text_list(raw.get("keywords"))),
        role_phrases=tuple(_role_phrases(raw.get("role_phrases"))),
        snippet_characters=_whole_number(
            raw.get("snippet_characters", 280), "snippet_characters", 40, 5000
        ),
        pause_seconds=float(pause),
        weights=clean_weights,
    )


def _whole_number(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f"{name} in shortlist should be a whole number from {low} to {high}.")
    number = int(value)
    if number < low or number > high:
        raise ValueError(f"{name} in shortlist should be a whole number from {low} to {high}.")
    return number


def _text_list(values: object) -> list[str]:
    if not values:
        return []
    if not isinstance(values, list):
        raise ValueError("A shortlist list in config.yaml should be a list.")
    return [str(item).strip() for item in values if str(item).strip()]


def _language_code(value: str) -> str:
    text = value.strip().casefold()
    if text in _LANG_NAMES:
        return text
    code = _NAME_TO_CODE.get(text)
    if code:
        return code
    if re.fullmatch(r"[a-z]{2}", text):
        return text
    raise ValueError(
        f"Unknown language '{value}' in shortlist. Use a code such as en, it, de, or nl."
    )


def _location_priorities(value: object) -> list[LocationPriority]:
    if not value:
        return []
    if not isinstance(value, list):
        raise ValueError("location_priorities in shortlist should be a list.")
    found = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("Each location priority needs a label, points, and places.")
        label = str(entry.get("label") or "").strip()
        if not label:
            raise ValueError("Each location priority needs a label.")
        points = _whole_number(entry.get("points", 0), "location priority points", 0, 100)
        places = tuple(_text_list(entry.get("places")))
        if not places:
            raise ValueError(f"Location priority '{label}' needs a places list.")
        found.append(LocationPriority(label=label, points=points, places=places))
    return found


def _role_phrases(value: object) -> list[RolePhrase]:
    if not value:
        return []
    if not isinstance(value, list):
        raise ValueError("role_phrases in shortlist should be a list.")
    found = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("Each role phrase group needs a label, points, and phrases.")
        label = str(entry.get("label") or "").strip() or "role"
        points = _whole_number(entry.get("points", 0), "role phrase points", 0, 100)
        phrases = tuple(_text_list(entry.get("phrases")))
        if not phrases:
            raise ValueError(f"Role group '{label}' needs a phrases list.")
        found.append(RolePhrase(label=label, points=points, phrases=phrases))
    return found


def required_years(text: str) -> int | None:
    """The years of experience a candidate must already have, if the posting says.

    A range such as 2-3 years counts as 2. Company history ("for over 20 years,
    we've been") is ignored. The highest remaining number is the bar.
    """
    if not text:
        return None
    found: list[int] = []
    for pattern in _YEAR_PATTERNS:
        for match in pattern.finditer(text):
            sentence = _sentence(text, match.start(), match.end())
            if _looks_like_company_age(sentence):
                continue
            if pattern is not _RANGE and re.search(
                r"\d+\s*(?:to|-|–|—|/)\s*$", text[: match.start()]
            ):
                continue
            if pattern in (_PLUS, _RANGE) and not (
                _looks_like_experience(_nearby(text, match.start(), match.end()))
                or _has_experience_word(match.group(0))
            ):
                continue
            years = int(match.group("a"))
            end = match.groupdict().get("b")
            if end:
                years = min(years, int(end))
            if 1 <= years <= 20:
                found.append(years)
    for match in _WORD_YEARS.finditer(text):
        sentence = _sentence(text, match.start(), match.end())
        window = _nearby(text, match.start(), match.end())
        if _looks_like_company_age(sentence) or not _looks_like_experience(window):
            continue
        word = match.group("w").lower().replace("ü", "u")
        mapped = _YEAR_WORDS.get(word) or _YEAR_WORDS.get(match.group("w").lower())
        if mapped:
            found.append(mapped)
    return max(found) if found else None


def _nearby(text: str, start: int, end: int, window: int = 50) -> str:
    return text[max(0, start - window) : min(len(text), end + window)]


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("?", 0, start))
    rights = [pos for pos in (text.find(".", end), text.find("!", end), text.find("?", end)) if pos != -1]
    right = min(rights) if rights else len(text)
    return text[left + 1 if left != -1 else 0 : right]


def _looks_like_company_age(snippet: str) -> bool:
    lower = snippet.lower()
    if any(cue in lower for cue in _COMPANY_AGE_CUES):
        return True
    if re.search(r"ist ein .{0,80}mit über \d+", lower):
        return True
    if re.search(
        r"for (?:over|more than)\s+\d+\s+years?,?\s+(?:we(?:'ve| have)|the company)",
        lower,
    ):
        return True
    return False


def _looks_like_experience(snippet: str) -> bool:
    lower = snippet.lower()
    return any(cue in lower for cue in _EXPERIENCE_CUES)


def _has_experience_word(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in _EXPERIENCE_WORDS)


def detect_language(text: str) -> tuple[str | None, float]:
    """(language code, probability). Short or unclear text returns (None, 0)."""
    if detect_langs is None:
        return None, 0.0
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) < 25:
        return None, 0.0
    try:
        guesses = detect_langs(cleaned)
    except LangDetectException:
        return None, 0.0
    if not guesses:
        return None, 0.0
    best = max(guesses, key=lambda item: item.prob)
    return best.lang.lower(), float(best.prob)


def title_drop_reason(row: dict, rules: Rules, excludes: tuple[str, ...] | None = None) -> str | None:
    """Why the title fails, or None when the row stays."""
    title = clean_text(row.get("title"))
    job_type = clean_text(row.get("job_type"))
    phrases = rules.title_exclude if excludes is None else excludes
    for phrase in phrases:
        if _exclude_hit(title, phrase):
            if _internship_phrase(phrase) or phrase_matches(job_type, phrase):
                return f"internship ({phrase})"
            return f"seniority in title ({phrase})"
    if phrase_matches(job_type, "internship") or phrase_matches(job_type, "intern"):
        return f"internship ({job_type or 'job type'})"
    if rules.title_include and not any(phrase_matches(title, phrase) for phrase in rules.title_include):
        return "title does not include a required word"
    return None


def _exclude_hit(title: str, phrase: str) -> bool:
    # "stage" is an internship in French and also an ordinary English word.
    if normalise(phrase) == ["stage"]:
        return bool(re.match(r"\s*stage\b", title, re.I))
    return phrase_matches(title, phrase)


def _internship_phrase(phrase: str) -> bool:
    tokens = set(normalise(phrase))
    markers = {
        "intern",
        "internship",
        "werkstudent",
        "werkstudentin",
        "praktikant",
        "praktikantin",
        "praktikum",
        "stagiaire",
        "stagiair",
        "tirocinio",
        "tirocinante",
        "stagista",
        "becario",
        "becaria",
        "stazysta",
        "praktik",
        "stage",
    }
    if tokens & markers:
        return True
    return "working" in tokens and "student" in tokens


def _excludes_for(rules: Rules, roles: list[str]) -> tuple[str, ...]:
    """Keep a seniority word when the user is actually searching for that level."""
    kept = []
    for phrase in rules.title_exclude:
        if any(phrase_matches(role, phrase) for role in roles if role):
            continue
        kept.append(phrase)
    return tuple(kept)


def _negated(text: str, phrase: str) -> bool:
    lower = text.casefold()
    folded = phrase.casefold()
    return any(
        pattern in lower
        for pattern in (
            f"not a {folded}",
            f"not an {folded}",
            f"no {folded}",
            f"non-{folded}",
            f"non {folded}",
        )
    )


def junior_evidence(title: str, description: str) -> tuple[str, str]:
    """('title'|'posting'|'years'|'', phrase or years label). Empty means no evidence."""
    for phrase in _TITLE_JUNIOR:
        if phrase_matches(title, phrase) and not _negated(title, phrase):
            return "title", phrase
    for phrase in _BODY_JUNIOR:
        if phrase_matches(description, phrase) and not _negated(description, phrase):
            return "posting", phrase
    years = required_years(description)
    if years is not None and years <= 2:
        label = f"{years} year" if years == 1 else f"{years} years"
        return "years", label
    return "", ""


def language_drop_reason(text: str, rules: Rules, *, title_only: bool = False) -> str | None:
    if not rules.allowed_languages:
        return None
    lang, prob = detect_language(text)
    threshold = rules.title_only_probability if title_only else rules.language_min_probability
    if lang is None or prob < threshold:
        return None
    if lang in rules.allowed_languages:
        return None
    name = _LANG_NAMES.get(lang, lang)
    return f"posting language is {name} ({prob:.0%})"


def _keyword_hit(text: str, word: str) -> bool:
    if len(word) <= 3:
        return phrase_matches(text, word)
    return word.casefold() in text.casefold()


def score_row(row: dict, rules: Rules) -> tuple[int, str]:
    """0-100 and a one-line reason. Missing years are not treated as junior."""
    title = clean_text(row.get("title"))
    body = _body_text(row)
    weights = rules.weights
    role_points, role_why = _role_score(title, clean_text(row.get("role_searched")), rules)
    kind, evidence = junior_evidence(title, body)
    if kind == "title":
        junior_points = weights.get("junior_title", 20)
        junior_why = f"the title says {evidence}"
    elif kind == "posting":
        junior_points = weights.get("junior_posting", 16)
        junior_why = f"the posting says {evidence}"
    elif kind == "years":
        years = required_years(body) or 0
        key = "junior_years_1" if years <= 1 else "junior_years_2"
        junior_points = weights.get(key, 14)
        junior_why = f"asks for {evidence}"
    else:
        junior_points = 0
        junior_why = ""
    years = _years_for(row)
    if years is None:
        exp_points = weights.get("experience_unspecified", 0)
        exp_why = "years requirement not stated"
    elif years <= 1:
        exp_points = weights.get("experience_years_1", 15)
        exp_why = f"asks for {years} year" if years == 1 else f"asks for {years} years"
    elif years == 2:
        exp_points = weights.get("experience_years_2", 12)
        exp_why = "asks for 2 years"
    else:
        exp_points = weights.get("experience_stated", 0)
        exp_why = f"asks for {years} years"
    lang_points, lang_why = _language_score(row, rules)
    loc_points, loc_why = _location_score(row, rules)
    key_points, key_why = _keyword_score(f"{title} {body}", rules)
    total = max(0, min(100, role_points + junior_points + exp_points + lang_points + loc_points + key_points))
    bits = [role_why]
    bits.append(junior_why or "seniority not stated")
    if exp_why and exp_why not in (junior_why or ""):
        bits.append(exp_why)
    if lang_why:
        bits.append(lang_why)
    if loc_why:
        bits.append(loc_why)
    if key_why:
        bits.append(f"keywords: {key_why}")
    status = clean_text(row.get("description_status"))
    if status == "snippet":
        bits.append(
            "only a short snippet was available, so a years requirement later in the posting may have been missed"
        )
    elif status == "twin":
        note = clean_text(row.get("twin_note")) or "another posting for the same role"
        bits.append(f"checked against {note}")
    elif status == "unverified":
        bits.append("the full description could not be read")
    reason = "; ".join(bit for bit in bits if bit)
    if reason:
        reason = reason[0].upper() + reason[1:]
        if not reason.endswith("."):
            reason += "."
    return total, reason


def _role_score(title: str, role_searched: str, rules: Rules) -> tuple[int, str]:
    best: tuple[int, str] | None = None
    for group in rules.role_phrases:
        for phrase in group.phrases:
            if phrase_matches(title, phrase) or (role_searched and phrase_matches(role_searched, phrase)):
                if best is None or group.points > best[0]:
                    best = (group.points, group.label)
                break
    if best:
        return best
    if role_searched and phrase_matches(title, role_searched):
        return rules.weights.get("role_match", 30), f"matches the {role_searched} search"
    return rules.weights.get("role_other", 8), "related role"


def _language_score(row: dict, rules: Rules) -> tuple[int, str]:
    if not rules.allowed_languages:
        return 0, ""
    lang, prob = detect_language(_body_text(row) or clean_text(row.get("title")))
    if lang is None or prob < rules.language_min_probability:
        return 0, "language not detected"
    if lang not in rules.allowed_languages:
        return 0, ""
    name = _LANG_NAMES.get(lang, lang)
    if lang == rules.allowed_languages[0]:
        return rules.weights.get("language", 10), f"{name} posting"
    return rules.weights.get("language_secondary", 7), f"{name} posting"


def _location_score(row: dict, rules: Rules) -> tuple[int, str]:
    if not rules.location_priorities:
        return 0, ""
    blob = f"{clean_text(row.get('location'))} {clean_text(row.get('place_searched'))}"
    for priority in rules.location_priorities:
        if any(phrase_matches(blob, place) for place in priority.places):
            return priority.points, f"{priority.label} location"
    if rules.other_location_points:
        return rules.other_location_points, "other location"
    return 0, ""


def _keyword_score(text: str, rules: Rules) -> tuple[int, str]:
    if not rules.keywords:
        return 0, ""
    hits = [word for word in rules.keywords if _keyword_hit(text, word)]
    if not hits:
        return 0, ""
    each = rules.weights.get("keyword_each", 3)
    cap = rules.weights.get("keyword_cap", 10)
    return min(cap, each * len(hits)), ", ".join(hits[:4])


def _body_text(row: dict) -> str:
    own = clean_text(row.get("description"))
    twin = clean_text(row.get("twin_text"))
    if len(twin) > len(own):
        return twin
    return own


def _years_for(row: dict) -> int | None:
    found = []
    for text in (clean_text(row.get("description")), clean_text(row.get("twin_text"))):
        years = required_years(text)
        if years is not None:
            found.append(years)
    return max(found) if found else None


def normalize_row(row: dict) -> dict:
    """Accept spreadsheet headings or the keys the rest of the program uses."""
    cleaned = {}
    for key, value in row.items():
        mapped = HEADER_TO_KEY.get(str(key).strip(), str(key).strip())
        cleaned[mapped] = clean_text(value)
    return cleaned


def read_jobs(path: str | Path) -> list[dict]:
    """Rows from a jobs.csv or jobs.xlsx written by this program."""
    file_path = Path(path)
    if not file_path.exists():
        raise ValueError(f"Could not find {file_path}.")
    if file_path.suffix.lower() in {".xlsx", ".xlsm"}:
        return _read_xlsx(file_path)
    return _read_csv(file_path)


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [normalize_row(row) for row in csv.DictReader(handle)]


def _read_xlsx(path: Path) -> list[dict]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        workbook.close()
        return []
    names = [clean_text(cell) for cell in header]
    found = []
    for values in rows:
        record = {
            names[index]: "" if value is None else value
            for index, value in enumerate(values)
            if index < len(names) and names[index]
        }
        if any(clean_text(value) for value in record.values()):
            found.append(normalize_row(record))
    workbook.close()
    return found


class _MarkupText(HTMLParser):
    """Text inside LinkedIn's public description block."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = dict(attrs).get("class") or ""
        if self._depth:
            if tag == "div":
                self._depth += 1
            if tag in {"p", "br", "li", "div", "h1", "h2", "h3"}:
                self._chunks.append(" ")
        elif "show-more-less-html__markup" in str(classes):
            self._depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self._depth and tag == "div":
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._chunks.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._chunks)).strip()


def description_from_html(html: str) -> str:
    """Plain text from a public LinkedIn job page, or a blank string."""
    if not html or "show-more-less-html__markup" not in html:
        return ""
    parser = _MarkupText()
    parser.feed(html)
    return parser.text()


def linkedin_job_id(url: str) -> str:
    match = re.search(r"/jobs/view/(\d+)", url or "")
    return match.group(1) if match else ""


def fetch_linkedin_description(
    url: str,
    get,
    sleeper,
    attempts: int = 3,
    pause: float = 2,
) -> str:
    """Read one public LinkedIn job description.

    get(url) returns (status code, body) or raises. 429 and brief outages are
    retried with a pause. A refusal (403) is not retried. Returns '' when the
    page cannot be read.
    """
    job_id = linkedin_job_id(url)
    if not job_id:
        return ""
    pages = (
        f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}",
        url,
    )
    for attempt in range(max(1, attempts)):
        page = pages[min(attempt, len(pages) - 1)]
        try:
            status, body = get(page)
        except Exception as exc:
            if transient_reason(exc) is None or attempt == attempts - 1:
                return ""
            sleeper(retry_delay(pause, attempt))
            continue
        if status == 200:
            text = description_from_html(body or "")
            if text:
                return text
        elif _status_reason(status) is None or attempt == attempts - 1:
            return ""
        if attempt == attempts - 1:
            return ""
        sleeper(retry_delay(pause, attempt))
    return ""


def _status_reason(status: int) -> str | None:
    if status == 429:
        return "too many requests"
    if status in _RETRY_STATUS:
        return "the site was busy"
    return None


def default_get(url: str) -> tuple[int, str]:
    """One polite request to a public LinkedIn page. No login and no proxy list."""
    from curl_cffi import requests as cfreq

    response = cfreq.get(
        url,
        timeout=20,
        impersonate="chrome",
        headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    return int(response.status_code), response.text or ""


def load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _cache_text(cache: dict, url: str) -> str:
    value = cache.get(url)
    if isinstance(value, str) and value.strip():
        return value.strip()
    job_id = linkedin_job_id(url)
    if not job_id:
        return ""
    for key, stored in cache.items():
        if linkedin_job_id(str(key)) == job_id and isinstance(stored, str) and stored.strip():
            return stored.strip()
    return ""


def _is_linkedin(row: dict) -> bool:
    return "linkedin" in clean_text(row.get("source")).casefold()


def _short_text(row: dict, rules: Rules) -> bool:
    return len(clean_text(row.get("description"))) <= rules.snippet_characters


def enrich_descriptions(
    rows: list[dict],
    rules: Rules,
    cache: dict,
    *,
    cache_path: Path | None,
    get=None,
    sleeper=time.sleep,
    skip_fetch: bool = False,
    pause_seconds: float | None = None,
) -> tuple[int, int]:
    """Fill missing text from the cache, then from LinkedIn when that is allowed.

    Returns (fetched, failed). Indeed pages are not requested.
    """
    pause = rules.pause_seconds if pause_seconds is None else pause_seconds
    for row in rows:
        cached = _cache_text(cache, clean_text(row.get("url")))
        own = clean_text(row.get("description"))
        if cached and len(cached) > len(own):
            row["description"] = cached
            row["description_status"] = "cached"
        elif own:
            row["description_status"] = "present"
        elif _is_linkedin(row):
            row["description_status"] = "unverified"
        else:
            row["description_status"] = "snippet" if _short_text(row, rules) else "present"

    if skip_fetch or get is None:
        _mark_short_rows(rows, rules)
        return 0, 0

    pending = [
        row
        for row in rows
        if _is_linkedin(row) and _short_text(row, rules) and clean_text(row.get("url"))
    ]
    fetched = failed = 0
    consecutive = 0
    for index, row in enumerate(pending):
        url = clean_text(row.get("url"))
        print(f"  Reading LinkedIn description {index + 1}/{len(pending)}...", flush=True)
        text = fetch_linkedin_description(url, get, sleeper, pause=pause)
        if text:
            row["description"] = text
            row["description_status"] = "fetched"
            cache[url] = text
            fetched += 1
            consecutive = 0
            if cache_path is not None:
                save_cache(cache_path, cache)
        else:
            row["description_status"] = "unverified"
            failed += 1
            consecutive += 1
        if consecutive >= _MAX_CONSECUTIVE_FETCH_FAILURES:
            print(
                "  LinkedIn stopped returning descriptions. "
                "The remaining rows stay in the list and are marked unread.",
                flush=True,
            )
            for later in pending[index + 1 :]:
                later["description_status"] = "unverified"
                failed += 1
            break
        if index != len(pending) - 1 and pause:
            sleeper(pause)
    if cache_path is not None and cache:
        save_cache(cache_path, cache)
    _mark_short_rows(rows, rules)
    return fetched, failed


def _mark_short_rows(rows: list[dict], rules: Rules) -> None:
    for row in rows:
        if row.get("description_status") in {"unverified", "twin", "cached", "fetched"}:
            continue
        if not _short_text(row, rules):
            continue
        if clean_text(row.get("description")):
            row["description_status"] = "snippet"
        else:
            row["description_status"] = "unverified"


def _source_label(source: str) -> str:
    folded = source.casefold()
    if "linkedin" in folded and "indeed" not in folded:
        return "LinkedIn"
    if folded == "indeed":
        return "Indeed"
    if source:
        return source[0].upper() + source[1:]
    return "another site"


def _titles_align(left: str, right: str) -> bool:
    left_tokens = set(normalise(_core_title(left)))
    right_tokens = set(normalise(_core_title(right)))
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    shorter, longer = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    if not shorter <= longer:
        return False
    return len(shorter) / len(longer) >= 0.75


def _core_title(title: str) -> str:
    return re.sub(r"\([^)]*\)", " ", title)


def match_twins(rows: list[dict], snippet_characters: int = 280) -> int:
    """Point a short row at a longer posting for the same role at the same company.

    Returns how many rows borrowed text. A short Indeed preview is not copied
    onto another row. The two rows must share the searched place or the city,
    so the same title in two countries stays separate. A suburb and the city
    next door still match when both rows were found by the same search.
    """
    groups: dict[str, list[dict]] = {}
    for row in rows:
        key = company_name_key(row.get("company"))
        if key:
            groups.setdefault(key, []).append(row)
    borrowed = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        for row in group:
            best = ""
            source = ""
            for other in group:
                if other is row:
                    continue
                if not _titles_align(clean_text(row.get("title")), clean_text(other.get("title"))):
                    continue
                if not _places_compatible(row, other):
                    continue
                other_text = clean_text(other.get("description"))
                if len(other_text) <= snippet_characters:
                    continue
                if len(other_text) > len(best):
                    best = other_text
                    source = _source_label(clean_text(other.get("source")))
            own = clean_text(row.get("description"))
            if best and len(best) > len(own) + 40:
                row["twin_text"] = best
                row["twin_note"] = (
                    f"the {source} posting for the same role at {clean_text(row.get('company'))}"
                )
                row["description_status"] = "twin"
                borrowed += 1
    return borrowed


def _places_compatible(left: dict, right: dict) -> bool:
    """True when both rows were searched in the same place, or name the same city."""
    left_place = clean_text(left.get("place_searched")).casefold()
    right_place = clean_text(right.get("place_searched")).casefold()
    if left_place and right_place and (
        left_place == right_place or left_place in right_place or right_place in left_place
    ):
        return True
    left_city = city_key(left.get("location"))
    right_city = city_key(right.get("location"))
    if left_city and left_city == right_city:
        return True
    blob_left = f"{left.get('location', '')} {left.get('place_searched', '')}".casefold()
    blob_right = f"{right.get('location', '')} {right.get('place_searched', '')}".casefold()
    if left_city and re.search(rf"\b{re.escape(left_city)}\b", blob_right):
        return True
    if right_city and re.search(rf"\b{re.escape(right_city)}\b", blob_left):
        return True
    return False


def _company_drop(row: dict, rules: Rules) -> str | None:
    company = clean_text(row.get("company"))
    for name in rules.exclude_companies:
        if phrase_matches(company, name) or name.casefold() in company.casefold():
            return f"excluded company ({name})"
    return None


def _country_drop(row: dict, rules: Rules) -> str | None:
    blob = f"{clean_text(row.get('location'))} {clean_text(row.get('place_searched'))}"
    description = f"{clean_text(row.get('description'))} {clean_text(row.get('twin_text'))}".casefold()
    for country in rules.exclude_countries:
        if phrase_matches(blob, country):
            return f"excluded country ({country})"
        folded = country.casefold()
        for pattern in (f"based in {folded}", f"headquartered in {folded}", f"hq in {folded}"):
            if pattern in description:
                return f"excluded country ({country})"
    return None


def _description_drop(row: dict, rules: Rules) -> str | None:
    text = _body_text(row).casefold()
    for phrase in rules.description_exclude:
        if phrase.casefold() in text:
            return f"excluded phrase in the posting ({phrase})"
    return None


def run_shortlist(
    rows: list[dict],
    rules: Rules | None = None,
    *,
    output_path: str | Path | None = None,
    funnel_json: str | Path | None = None,
    funnel_log: str | Path | None = None,
    cache_path: str | Path | None = None,
    roles: list[str] | None = None,
    get=None,
    sleeper=time.sleep,
    skip_fetch: bool = False,
    pause_seconds: float | None = None,
) -> dict:
    """Filter, score, and write the workbook. Returns the funnel and the top rows."""
    rules = rules or load_rules()
    prepared = [normalize_row(row) for row in rows]
    role_names = list(roles or [])
    for row in prepared:
        searched = clean_text(row.get("role_searched"))
        if searched and searched not in role_names:
            role_names.append(searched)
    excludes = _excludes_for(rules, role_names)
    started = time.perf_counter()
    total = len(prepared)
    funnel: list[tuple[str, int]] = [("Starting listings", total)]
    drops: dict[str, Counter] = {
        "title": Counter(),
        "experience": Counter(),
        "language": Counter(),
        "other": Counter(),
    }

    kept = []
    for row in prepared:
        reason = title_drop_reason(row, rules, excludes)
        if reason:
            drops["title"][reason] += 1
        else:
            kept.append(row)
    funnel.append(("After title filter", len(kept)))

    cache = load_cache(Path(cache_path)) if cache_path else {}
    fetched, failed = enrich_descriptions(
        kept,
        rules,
        cache,
        cache_path=Path(cache_path) if cache_path else None,
        get=None if skip_fetch else get,
        sleeper=sleeper,
        skip_fetch=skip_fetch,
        pause_seconds=pause_seconds,
    )
    twins = match_twins(kept, rules.snippet_characters)

    stage = []
    for row in kept:
        years = _years_for(row)
        if (
            rules.max_required_years is not None
            and years is not None
            and years >= rules.max_required_years
        ):
            own_years = required_years(clean_text(row.get("description")))
            borrowed = row.get("twin_text") and (own_years is None or own_years < years)
            note = f" ({row.get('twin_note')})" if borrowed else ""
            reason = f"requires {years}+ years{note}"
            drops["experience"][reason] += 1
        else:
            stage.append(row)
    kept = stage
    funnel.append(("After experience filter", len(kept)))

    stage = []
    if rules.allowed_languages:
        for row in kept:
            body = _body_text(row)
            if not body:
                reason = language_drop_reason(clean_text(row.get("title")), rules, title_only=True)
            else:
                reason = language_drop_reason(body, rules)
            if reason:
                drops["language"][reason] += 1
            else:
                stage.append(row)
        kept = stage
    funnel.append(("After language filter", len(kept)))

    if rules.exclude_companies or rules.exclude_countries or rules.description_exclude:
        stage = []
        for row in kept:
            reason = _company_drop(row, rules) or _country_drop(row, rules) or _description_drop(row, rules)
            if reason:
                drops["other"][reason] += 1
            else:
                stage.append(row)
        kept = stage
        funnel.append(("After excluded companies, countries, and phrases", len(kept)))

    for row in kept:
        score, reason = score_row(row, rules)
        row["score"] = score
        row["reason"] = reason
        row["required_years"] = _years_for(row)
        lang, prob = detect_language(_body_text(row) or clean_text(row.get("title")))
        row["detected_language"] = f"{_LANG_NAMES.get(lang, lang)} ({prob:.0%})" if lang else ""
    kept.sort(key=lambda item: clean_text(item.get("date_posted")), reverse=True)
    kept.sort(key=lambda item: int(item["score"]), reverse=True)
    top = kept[: rules.top_n]
    funnel.append(("Top-N", len(top)))

    elapsed = time.perf_counter() - started
    meta = {
        "Top-N": rules.top_n,
        "Seconds": round(elapsed, 2),
        "Descriptions fetched this run": fetched,
        "Description fetches that failed": failed,
        "Rows that used another site's description": twins,
        "Rows still missing a full description": sum(
            1 for row in kept if row.get("description_status") in {"snippet", "unverified"}
        ),
    }
    payload = {
        "funnel": [
            {"stage": name, "count": count, "share_of_start": (count / total if total else 0)}
            for name, count in funnel
        ],
        "drop_reasons": {name: dict(counter) for name, counter in drops.items()},
        "meta": meta,
        "top": [
            {
                "rank": index,
                "score": row["score"],
                "title": clean_text(row.get("title")),
                "company": clean_text(row.get("company")),
                "location": clean_text(row.get("location")),
                "place": clean_text(row.get("place_searched")),
                "reason": row["reason"],
                "url": clean_text(row.get("url")),
                "description_status": clean_text(row.get("description_status")),
            }
            for index, row in enumerate(top, start=1)
        ],
    }
    if output_path is not None:
        write_workbook(Path(output_path), kept, top, funnel, drops, meta)
    if funnel_json is not None:
        Path(funnel_json).parent.mkdir(parents=True, exist_ok=True)
        Path(funnel_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if funnel_log is not None:
        _write_log(Path(funnel_log), funnel, drops)
    for name, count in funnel:
        print(f"{name}: {count}", flush=True)
    if output_path is not None:
        print(f"Shortlist: {output_path}", flush=True)
        print(f"Open the Top-N sheet. It has the {len(top)} jobs to read first.", flush=True)
    return payload


def _write_log(path: Path, funnel: list[tuple[str, int]], drops: dict[str, Counter]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{name}: {count}" for name, count in funnel]
    lines.append("")
    for stage, counter in drops.items():
        if not counter:
            continue
        lines.append(stage)
        for reason, count in counter.most_common():
            lines.append(f"  {count}  {reason}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_workbook(
    path: Path,
    ranked: list[dict],
    top: list[dict],
    funnel: list[tuple[str, int]],
    drops: dict[str, Counter],
    meta: dict,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(bold=True, color="FFFFFF")
    body_font = Font(name="Calibri", size=11)
    top_fill = PatternFill("solid", fgColor="E8F0E8")
    thin_align = Alignment(vertical="top", wrap_text=True)

    funnel_sheet = workbook.active
    funnel_sheet.title = "Funnel"
    funnel_sheet.append(["Stage", "Listings", "Share of start", "Share of previous"])
    start = funnel[0][1] if funnel else 0
    previous = None
    for name, count in funnel:
        share = count / start if start else 0
        versus = count / previous if previous else 1
        funnel_sheet.append([name, count, round(share, 4), round(versus, 4)])
        previous = count
    funnel_sheet.append([])
    funnel_sheet.append(["What this file is", ""])
    funnel_sheet.append(
        [
            "Top-N is the list to read. Ranked is every job that passed the filters. "
            "The full search is still in jobs.xlsx.",
            "",
        ]
    )
    funnel_sheet.append(
        [
            "A job is not treated as junior just because it never asks for 3 years. "
            "The reason says seniority not stated when the posting does not say.",
            "",
        ]
    )
    funnel_sheet.append(
        [
            "Indeed often sends only a short preview. This program does not open Indeed "
            "job pages. When the same role at the same company has a longer description "
            "on another site, that text is used and the reason says so.",
            "",
        ]
    )
    for key, value in meta.items():
        funnel_sheet.append([key, value])
    funnel_sheet.append([])
    funnel_sheet.append(["Why rows were left out"])
    for stage, counter in drops.items():
        if not counter:
            continue
        funnel_sheet.append([stage])
        for reason, count in counter.most_common(20):
            funnel_sheet.append(["", reason, count])
    for cell in funnel_sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
    funnel_sheet.column_dimensions["A"].width = 64
    funnel_sheet.column_dimensions["B"].width = 18
    funnel_sheet.column_dimensions["C"].width = 18
    funnel_sheet.column_dimensions["D"].width = 20
    funnel_sheet.freeze_panes = "A2"
    funnel_sheet.auto_filter.ref = f"A1:D{max(1, len(funnel) + 1)}"

    ranked_sheet = workbook.create_sheet("Ranked")
    top_sheet = workbook.create_sheet("Top-N")
    _fill_job_sheet(ranked_sheet, ranked, header_fill, header_font, body_font, thin_align, None)
    _fill_job_sheet(top_sheet, top, header_fill, header_font, body_font, thin_align, top_fill)
    workbook.active = top_sheet
    workbook.save(path)


def _fill_job_sheet(sheet, rows, header_fill, header_font, body_font, alignment, fill) -> None:
    sheet.append(list(_SHEET_COLUMNS))
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    url_column = _SHEET_COLUMNS.index("URL") + 1
    for index, row in enumerate(rows, start=1):
        description = _body_text(row)
        if len(description) > 32000:
            description = description[:32000]
        values = [
            index,
            row.get("score", ""),
            safe_cell(row.get("reason", "")),
            safe_cell(clean_text(row.get("title"))),
            safe_cell(clean_text(row.get("company"))),
            safe_cell(clean_text(row.get("location"))),
            safe_cell(clean_text(row.get("place_searched"))),
            safe_cell(clean_text(row.get("date_posted"))),
            safe_cell(clean_text(row.get("source"))),
            safe_cell(clean_text(row.get("url"))),
            safe_cell(clean_text(row.get("role_searched"))),
            safe_cell(clean_text(row.get("level"))),
            safe_cell(clean_text(row.get("languages"))),
            safe_cell(clean_text(row.get("visa"))),
            safe_cell(_status_label(row)),
            "" if row.get("required_years") is None else row.get("required_years"),
            safe_cell(clean_text(row.get("detected_language"))),
            safe_cell(description),
        ]
        sheet.append(values)
        row_number = sheet.max_row
        link = _http_link(clean_text(row.get("url")))
        if link:
            cell = sheet.cell(row_number, url_column)
            cell.hyperlink = link
            cell.font = Font(color="0563C1", underline="single")
        for cell in sheet[row_number]:
            if cell.font is None or not cell.font.underline:
                cell.font = body_font
            cell.alignment = alignment
            if fill is not None:
                cell.fill = fill
        sheet.row_dimensions[row_number].height = 36
    widths = {
        "A": 8,
        "B": 10,
        "C": 62,
        "D": 40,
        "E": 28,
        "F": 32,
        "G": 28,
        "H": 14,
        "I": 16,
        "J": 42,
        "K": 22,
        "L": 12,
        "M": 22,
        "N": 22,
        "O": 42,
        "P": 16,
        "Q": 20,
        "R": 55,
    }
    for letter, width in widths.items():
        sheet.column_dimensions[letter].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(_SHEET_COLUMNS))}{max(1, sheet.max_row)}"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True


def _status_label(row: dict) -> str:
    status = clean_text(row.get("description_status"))
    if status == "twin":
        return clean_text(row.get("twin_note")) or "read from another posting for the same role"
    if status == "cached":
        return "full description from the saved cache"
    if status == "fetched":
        return "full description read from the public job page"
    if status == "snippet":
        return "short snippet only"
    if status == "unverified":
        return "description unavailable"
    return "description included"


def output_paths(jobs_path: Path) -> tuple[Path, Path, Path, Path]:
    """Workbook, funnel json, funnel log, and description cache beside the jobs file."""
    folder = jobs_path.resolve().parent
    return (
        folder / "shortlist.xlsx",
        folder / "shortlist-funnel.json",
        folder / "shortlist-funnel.log",
        folder / "description_cache.json",
    )
