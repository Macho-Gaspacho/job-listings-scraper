"""Salary, job type, level, language, and visa for one posting.

Language and visa come from words in the description. They are guesses.
The word lists live in signals/requirements.yaml. Matching uses the same
whole-word rules as job titles.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from matching import normalise, phrase_matches


JOB_TYPES = ("Full-time", "Part-time", "Contract", "Internship", "Temporary")
LEVELS = ("Entry", "Senior", "Unknown")

# python-jobspy's own yearly multipliers. Hourly uses 40 hours * 52 weeks.
YEARLY_FACTOR = {
    "yearly": 1,
    "monthly": 12,
    "weekly": 52,
    "daily": 260,
    "hourly": 2080,
}

_PERIOD_LABEL = {
    "yearly": "year",
    "monthly": "month",
    "weekly": "week",
    "daily": "day",
    "hourly": "hour",
}

_PERIOD_NAME = {
    "yearly": "yearly",
    "year": "yearly",
    "annual": "yearly",
    "annually": "yearly",
    "monthly": "monthly",
    "month": "monthly",
    "weekly": "weekly",
    "week": "weekly",
    "daily": "daily",
    "day": "daily",
    "hourly": "hourly",
    "hour": "hourly",
}

# Letters only, so "Full-time", "full_time", and "FullTime" share one key.
_JOB_TYPE_KEYS = {
    "fulltime": "Full-time",
    "permanent": "Full-time",
    "parttime": "Part-time",
    "contract": "Contract",
    "contractor": "Contract",
    "internship": "Internship",
    "intern": "Internship",
    "temporary": "Temporary",
    "temp": "Temporary",
}

_JOBSPY_TYPE = {
    "Full-time": "fulltime",
    "Part-time": "parttime",
    "Contract": "contract",
    "Internship": "internship",
    "Temporary": "temporary",
}

_LANGUAGE_NAMES = {
    "english": "English",
    "german": "German",
    "deutsch": "German",
    "french": "French",
    "francais": "French",
    "spanish": "Spanish",
    "espanol": "Spanish",
    "italian": "Italian",
    "italiano": "Italian",
    "dutch": "Dutch",
    "nederlands": "Dutch",
    "polish": "Polish",
    "polski": "Polish",
    "portuguese": "Portuguese",
    "portugues": "Portuguese",
}

_VISA_NO = "No sponsorship"
_VISA_YES = "Sponsorship offered"
_VISA_UNKNOWN = "Unknown"
_GUESSED = " (guessed from the text)"


def _missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and value != value)


def _text(value: object) -> str:
    if _missing(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    return text


def signals_path() -> Path:
    """The word lists that ship with this project."""
    return Path(__file__).resolve().parent / "signals" / "requirements.yaml"


@lru_cache(maxsize=1)
def load_signals() -> dict:
    """Level, language, and visa phrases from signals/requirements.yaml."""
    path = signals_path()
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("signals/requirements.yaml should be a group of lists.")
    languages = loaded.get("languages") or {}
    if not isinstance(languages, dict):
        raise ValueError("languages in signals/requirements.yaml should be a group of lists.")
    return {
        "level_entry": _phrase_list(loaded.get("level_entry"), "level_entry"),
        "level_senior": _phrase_list(loaded.get("level_senior"), "level_senior"),
        "languages": {
            str(name): _phrase_list(phrases, str(name)) for name, phrases in languages.items()
        },
        "visa_no": _phrase_list(loaded.get("visa_no"), "visa_no"),
        "visa_yes": _phrase_list(loaded.get("visa_yes"), "visa_yes"),
    }


def _phrase_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} in signals/requirements.yaml should be a list.")
    return tuple(str(item).strip() for item in value if str(item).strip())


def _letters(value: object) -> str:
    return "".join(char for char in _text(value).casefold() if char.isalpha())


def canonical_job_type(value: object) -> str:
    """One of the five job types, or a blank string when the text is not one of them."""
    return _JOB_TYPE_KEYS.get(_letters(value), "")


def job_type_text(value: object) -> str:
    """Normalise one value or a comma-separated list of job types."""
    names = []
    for token in _tokens(value):
        name = canonical_job_type(token)
        if name and name not in names:
            names.append(name)
    return ", ".join(names)


def jobspy_job_type(name: str) -> str:
    """The job_type string Indeed accepts in python-jobspy 1.4.0."""
    return _JOBSPY_TYPE[name]


def canonical_level(value: object) -> str:
    """Entry, Senior, or Unknown. A blank string when the text is not a level."""
    key = _text(value).casefold()
    for level in LEVELS:
        if level.casefold() == key:
            return level
    return ""


def canonical_language(value: object) -> str:
    """The English name of a language this file knows, or a blank string."""
    key = "".join(token[:-1] if token.endswith("*") else token for token in normalise(value))
    return _LANGUAGE_NAMES.get(key, "")


def _tokens(value: object) -> list[str]:
    if isinstance(value, list):
        tokens = []
        for item in value:
            tokens.extend(_tokens(item))
        return tokens
    text = _text(value)
    if not text:
        return []
    return [part.strip() for part in _split_list(text) if part.strip()]


def _split_list(text: str) -> list[str]:
    current = []
    parts = []
    for char in text:
        if char in ",;/|":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _number(value: object) -> float | None:
    if isinstance(value, bool) or _missing(value) or value == "":
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return float(value)
    text = _text(value).replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number <= 0:
        return None
    return number


def _stored_amount(value: float | None) -> int | float | None:
    if value is None:
        return None
    if float(value).is_integer():
        return int(value)
    return float(value)


def _first_amount(hit: dict, *keys: str) -> int | float | None:
    for key in keys:
        if key not in hit:
            continue
        number = _number(hit.get(key))
        if number is not None:
            return _stored_amount(number)
    return None


def _first_text(hit: dict, *keys: str) -> str:
    for key in keys:
        if key not in hit:
            continue
        text = _text(hit.get(key))
        if text:
            return text
    return ""


def _format_amount(value: int | float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    text = f"{float(value):,.2f}".rstrip("0").rstrip(".")
    return text


def format_salary(low, high, currency: str, period: str) -> str:
    """A range such as 40,000–50,000 EUR/year. Blank when no amount is known."""
    amounts = [amount for amount in (low, high) if amount is not None]
    if not amounts:
        return ""
    if len(amounts) == 2 and amounts[0] == amounts[1]:
        shown = _format_amount(amounts[0])
    elif len(amounts) == 2:
        shown = f"{_format_amount(amounts[0])}\u2013{_format_amount(amounts[1])}"
    else:
        shown = _format_amount(amounts[0])
    label = _PERIOD_LABEL.get(period, "")
    if currency and label:
        return f"{shown} {currency}/{label}"
    if currency:
        return f"{shown} {currency}"
    if label:
        return f"{shown}/{label}"
    return shown


def remote_label(value: object) -> str:
    """Yes, No, or Unknown."""
    if isinstance(value, str):
        folded = value.strip().casefold()
        if folded in {"yes", "true", "y"}:
            return "Yes"
        if folded in {"no", "false", "n"}:
            return "No"
        return "Unknown"
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unknown"


def _matched_level(text: object, signals: dict) -> str | None:
    """Entry, Senior, an empty conflict, or None when the text has no level word."""
    entry = any(phrase_matches(text, phrase) for phrase in signals["level_entry"])
    senior = any(phrase_matches(text, phrase) for phrase in signals["level_senior"])
    if entry and senior:
        return ""
    if entry:
        return "Entry"
    if senior:
        return "Senior"
    return None


def infer_level(title: object, job_level: object, signals: dict | None = None) -> str:
    """Entry, Senior, or Unknown.

    A level sent by the site wins. Otherwise the title is checked.
    Words such as intern and senior are whole words, so intern does not
    match internal. Entry and senior together stay Unknown.
    """
    table = load_signals() if signals is None else signals
    stated = _matched_level(job_level, table)
    if stated is not None:
        return stated or "Unknown"
    inferred = _matched_level(title, table)
    if inferred:
        return inferred
    return "Unknown"


def detect_languages(text: object, signals: dict | None = None) -> list[str]:
    """English names of languages the description appears to require."""
    table = load_signals() if signals is None else signals
    found = []
    for name, phrases in table["languages"].items():
        if any(phrase_matches(text, phrase) for phrase in phrases):
            found.append(str(name))
    return found


def detect_visa(text: object, signals: dict | None = None) -> str:
    """No sponsorship, Sponsorship offered, or Unknown.

    Both kinds of sentence in one posting stay Unknown.
    """
    table = load_signals() if signals is None else signals
    denied = any(phrase_matches(text, phrase) for phrase in table["visa_no"])
    offered = any(phrase_matches(text, phrase) for phrase in table["visa_yes"])
    if denied and offered:
        return _VISA_UNKNOWN
    if denied:
        return _VISA_NO
    if offered:
        return _VISA_YES
    return _VISA_UNKNOWN


def visa_text(status: str) -> str:
    """Label a guessed visa value. Unknown stays Unknown."""
    if status in {_VISA_NO, _VISA_YES}:
        return status + _GUESSED
    return _VISA_UNKNOWN


def visa_status(value: object) -> str:
    """The short visa value, with or without the guessed-from-the-text label."""
    text = _text(value).casefold()
    if text.startswith(_VISA_NO.casefold()):
        return _VISA_NO
    if text.startswith(_VISA_YES.casefold()):
        return _VISA_YES
    return _VISA_UNKNOWN


def describe_posting(hit: dict) -> dict:
    """Fields that can be filtered and written to the spreadsheet."""
    title = _text(hit.get("title"))
    low = _first_amount(hit, "min_amount", "salary_min")
    high = _first_amount(hit, "max_amount", "salary_max")
    currency = _first_text(hit, "currency", "salary_currency").upper()
    period = _PERIOD_NAME.get(_first_text(hit, "interval", "salary_period").casefold(), "")
    raw_type = hit.get("job_type")
    if not _text(raw_type):
        for key in ("commitment", "employmentType", "employment_type"):
            if _text(hit.get(key)):
                raw_type = hit.get(key)
                break
    languages = detect_languages(hit.get("description") or "")
    remote = remote_label(hit.get("is_remote")) if "is_remote" in hit else "Unknown"
    return {
        "salary": format_salary(low, high, currency, period),
        "salary_min": low,
        "salary_max": high,
        "salary_currency": currency,
        "salary_period": period,
        "job_type": job_type_text(raw_type),
        "is_remote": remote,
        "level": infer_level(title, hit.get("job_level")),
        "languages": ", ".join(languages),
        "visa": visa_text(detect_visa(hit.get("description") or "")),
    }


def filters_active(filters) -> bool:
    """True when the config asks to drop any rows."""
    if filters is None:
        return False
    return bool(
        filters.job_types
        or filters.levels
        or filters.min_salary is not None
        or filters.exclude_title_words
        or filters.exclude_if_language_required
        or filters.only_visa_sponsorship
    )


def yearly_pay(row: dict) -> float | None:
    """The lower known amount in yearly terms, or None when it cannot be compared.

    Monthly pay is multiplied by 12, hourly by 2,080, weekly by 52, and daily
    by 260. A missing amount or a missing period is left unknown.
    """
    factor = YEARLY_FACTOR.get(_text(row.get("salary_period")).casefold())
    if factor is None:
        return None
    amounts = []
    for key in ("salary_min", "salary_max"):
        number = _number(row.get(key))
        if number is not None:
            amounts.append(number * factor)
    if not amounts:
        return None
    return min(amounts)


def passes_filters(row: dict, filters) -> bool:
    """False when a row breaks a filter the user turned on.

    A blank job type, a blank language list, and an unknown salary stay.
    Unknown is a real level, so a levels list that leaves it out drops it.
    """
    if not filters_active(filters):
        return True
    title = row.get("title") or ""
    if any(phrase_matches(title, phrase) for phrase in filters.exclude_title_words):
        return False
    if filters.job_types:
        found = [part.strip() for part in _text(row.get("job_type")).split(",") if part.strip()]
        if found and not any(part in filters.job_types for part in found):
            return False
    if filters.levels:
        level = _text(row.get("level")) or "Unknown"
        if level not in filters.levels:
            return False
    if filters.min_salary is not None:
        amount = yearly_pay(row)
        if amount is not None and amount < float(filters.min_salary):
            return False
    if filters.exclude_if_language_required:
        blocked = {name.casefold() for name in filters.exclude_if_language_required}
        found = [part.strip().casefold() for part in _text(row.get("languages")).split(",") if part.strip()]
        if any(name in blocked for name in found):
            return False
    if filters.only_visa_sponsorship and visa_status(row.get("visa")) == _VISA_NO:
        return False
    return True
