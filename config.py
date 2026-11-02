"""Read config.yaml into a small settings object.

Edit config.yaml to change what is searched. This file only checks
that the settings make sense and turns them into something the rest
of the program can use.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from regions import (
    INDEED_COUNTRIES,
    OTHER_COUNTRIES,
    LocationFilter,
    LocationRules,
    build_location_rules,
    canonical_country,
    country_from_places,
    english_name,
    system_timezone_name,
    validate_timezone,
)


# Sites python-jobspy knows how to ask. A config turns on the ones it wants.
KNOWN_SITES = ("indeed", "linkedin", "google", "glassdoor", "zip_recruiter")

# Every source a person can switch on or off in config.yaml.
# The kind becomes the "Source type" column in the spreadsheet.
KNOWN_SOURCES = {
    "indeed": "aggregator",
    "linkedin": "aggregator",
    "google": "aggregator",
    "glassdoor": "aggregator",
    "zip_recruiter": "aggregator",
    "company_pages": "company site",
    "we_work_remotely": "remote board",
    "remote_ok": "remote board",
    "remotive": "remote board",
    "working_nomads": "remote board",
}

# Public applicant-tracking systems the company list can use.
KNOWN_SYSTEMS = (
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "recruitee",
    "teamtailor",
    "bendingspoons",
)


@dataclass
class Place:
    """One place to search, such as a city or remote work in a country."""

    name: str
    indeed_location: str
    linkedin_location: str
    remote: bool = False
    distance_miles: int | None = None
    search_indeed: bool = True


@dataclass
class Company:
    """One employer whose public careers page we read directly."""

    name: str
    system: str
    token: str = ""
    enabled: bool = True


@dataclass
class Filters:
    """Optional limits. Empty means the row is kept."""

    job_types: tuple[str, ...] = ()
    levels: tuple[str, ...] = ()
    min_salary: int | float | None = None
    exclude_title_words: tuple[str, ...] = ()
    exclude_if_language_required: tuple[str, ...] = ()
    only_visa_sponsorship: bool = False


@dataclass
class Settings:
    """Everything scrape.py needs, already checked."""

    roles: list[str]
    places: list[Place]
    sites: list[str]
    country: str
    results_per_search: int
    posted_within_days: int
    pause_seconds: float
    fetch_descriptions: bool
    snippet_characters: int
    output_dir: Path
    csv_path: Path
    excel_path: Path
    seen_file: Path
    require_title_match: bool = False
    title_keywords: dict[str, list[str]] | None = None
    exclude_keywords: list[str] | None = None
    company_pages_enabled: bool = False
    remote_boards: list[str] | None = None
    companies: list[Company] | None = None
    timezone: str = ""
    location_rules: LocationRules | None = None
    wwr_categories: tuple[str, ...] | None = None
    filters: Filters | None = None


def _text_list(values: object) -> list[str]:
    if not values:
        return []
    if not isinstance(values, list):
        raise ValueError("Expected a list in config.yaml.")
    return [str(item).strip() for item in values if str(item).strip()]


def _load_sources(raw: dict) -> tuple[list[str], bool, list[str]]:
    """Return enabled Indeed/LinkedIn sites, whether company pages are on, and remote boards."""
    sources = raw.get("sources")
    if sources is None:
        sites = [site.lower() for site in _text_list(raw.get("sites"))]
        if not sites:
            raise ValueError("Add at least one source under 'sources' in config.yaml.")
        unknown = [site for site in sites if site not in KNOWN_SITES]
        if unknown:
            names = ", ".join(KNOWN_SITES)
            raise ValueError(f"Unknown site '{unknown[0]}'. Choose from: {names}.")
        return sites, False, []

    if not isinstance(sources, list):
        raise ValueError("'sources' in config.yaml should be a list.")
    sites = []
    company_pages = False
    remote_boards = []
    for entry in sources:
        if not isinstance(entry, dict) or not str(entry.get("id") or "").strip():
            raise ValueError("Each source needs an id, such as indeed or company_pages.")
        source_id = str(entry["id"]).strip().lower()
        if source_id not in KNOWN_SOURCES:
            known = ", ".join(KNOWN_SOURCES)
            raise ValueError(f"Unknown source '{source_id}'. Choose from: {known}.")
        kind = str(entry.get("kind") or KNOWN_SOURCES[source_id]).strip().lower()
        expected = KNOWN_SOURCES[source_id]
        if kind != expected:
            raise ValueError(f"Source '{source_id}' should have kind '{expected}'.")
        if not bool(entry.get("enabled", True)):
            continue
        if expected == "aggregator":
            sites.append(source_id)
        elif source_id == "company_pages":
            company_pages = True
        elif expected == "remote board":
            remote_boards.append(source_id)
    return sites, company_pages, remote_boards


def _load_companies(value: object) -> list[Company]:
    if not value:
        return []
    if not isinstance(value, list):
        raise ValueError("'companies' in config.yaml should be a list.")
    companies = []
    for entry in value:
        if not isinstance(entry, dict) or not str(entry.get("name") or "").strip():
            raise ValueError("Each company needs a name.")
        system = str(entry.get("system") or "").strip().lower()
        if system not in KNOWN_SYSTEMS:
            names = ", ".join(KNOWN_SYSTEMS)
            raise ValueError(f"Unknown system '{system}' for {entry.get('name')}. Choose from: {names}.")
        token = str(entry.get("token") or "").strip()
        if system == "teamtailor" and not token.startswith("http"):
            raise ValueError(f"{entry.get('name')} needs a token that is the https address of its jobs RSS feed.")
        if system not in {"bendingspoons"} and not token:
            raise ValueError(f"{entry.get('name')} needs a token (the public id in its careers URL).")
        companies.append(
            Company(
                name=str(entry["name"]).strip(),
                system=system,
                token=token,
                enabled=bool(entry.get("enabled", True)),
            )
        )
    return companies


def _provided(raw: dict, key: str):
    """The value under key, or None when the setting was left out."""
    if key not in raw:
        return None
    value = raw.get(key)
    if value is None or value == "":
        return None
    return value


def _whole_number(value: object, key: str, low: int, high: int) -> int:
    """A whole number in range, or a sentence that names the key and the range."""
    if type(value) is int and low <= value <= high:
        return value
    raise ValueError(f"{key} must be a whole number from {low} to {high}.")


def _pause_seconds(raw: dict) -> float:
    value = _provided(raw, "pause_seconds")
    if value is None:
        return 2.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("pause_seconds must be a number from 1 upward.")
    if value < 1:
        raise ValueError("pause_seconds must be a number from 1 upward.")
    return float(value)


def _optional_phrases(block: dict, key: str) -> tuple[str, ...] | None:
    """None when the key was left out. An empty list is kept as empty."""
    if key not in block:
        return None
    return tuple(_text_list(block.get(key)))


def _load_location_filter(raw: dict) -> LocationFilter | None:
    block = raw.get("location_filter")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ValueError(
            "location_filter in config.yaml should be a group of lists: "
            "offices, remote_regions, and exclude_regions."
        )
    return LocationFilter(
        offices=_optional_phrases(block, "offices"),
        remote_regions=_optional_phrases(block, "remote_regions"),
        exclude_regions=_optional_phrases(block, "exclude_regions"),
    )


def _load_country(raw: dict, places: list[Place], sites: list[str]) -> str:
    """The country for this search. Taken from the first office when the file leaves it out."""
    provided = raw.get("country", None)
    if provided is None or not str(provided).strip():
        derived = country_from_places(places)
        if not derived:
            raise ValueError(
                "config.yaml does not set country, and none of the locations names a country "
                "this program recognises. Add a country, such as germany or armenia, "
                "or name a place like Berlin, Germany."
            )
        country = derived
    else:
        country = canonical_country(str(provided))
    if country in INDEED_COUNTRIES:
        return country
    written = english_name(country) if country else str(provided).strip()
    if country in OTHER_COUNTRIES:
        if "indeed" in sites:
            raise ValueError(
                f"Indeed does not cover {written}. "
                "Turn Indeed off and use LinkedIn, or choose a country Indeed supports."
            )
        return country
    raise ValueError(
        f"Country '{str(provided).strip() if provided else written}' is not one this program recognises. "
        "Use an English name such as Germany, Italy, Armenia, or United States."
    )


def _load_timezone(raw: dict) -> str:
    provided = raw.get("timezone", None)
    if provided is None or not str(provided).strip():
        return system_timezone_name()
    return validate_timezone(str(provided))


def _load_filters(raw: dict) -> Filters:
    """Optional filters. A missing block keeps every row."""
    if "filters" not in raw or raw.get("filters") is None:
        return Filters()
    block = raw.get("filters")
    if not isinstance(block, dict):
        raise ValueError("filters in config.yaml should be a group of settings.")
    from enrichment import canonical_job_type, canonical_language, canonical_level

    job_types = []
    for item in _text_list(block.get("job_types")):
        name = canonical_job_type(item)
        if not name:
            choices = ", ".join(("Full-time", "Part-time", "Contract", "Internship", "Temporary"))
            raise ValueError(f"Unknown job type '{item}'. Choose from: {choices}.")
        if name not in job_types:
            job_types.append(name)
    levels = []
    for item in _text_list(block.get("levels")):
        name = canonical_level(item)
        if not name:
            raise ValueError(f"Unknown level '{item}'. Choose from: Entry, Senior, Unknown.")
        if name not in levels:
            levels.append(name)
    languages = []
    for item in _text_list(block.get("exclude_if_language_required")):
        name = canonical_language(item)
        if not name:
            raise ValueError(
                f"Unknown language '{item}'. Use an English name such as German, Dutch, Spanish, or Polish."
            )
        if name not in languages:
            languages.append(name)
    if "min_salary" in block and block.get("min_salary") not in (None, ""):
        amount = block.get("min_salary")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            raise ValueError("min_salary must be a number, such as 30000.")
        minimum = int(amount) if isinstance(amount, float) and amount.is_integer() else amount
    else:
        minimum = None
    if "only_visa_sponsorship" in block and not isinstance(block.get("only_visa_sponsorship"), bool):
        raise ValueError("only_visa_sponsorship must be true or false.")
    if "exclude_title_words" in block and not isinstance(block.get("exclude_title_words"), list):
        raise ValueError("exclude_title_words in config.yaml should be a list.")
    return Filters(
        job_types=tuple(job_types),
        levels=tuple(levels),
        min_salary=minimum,
        exclude_title_words=tuple(_text_list(block.get("exclude_title_words"))),
        exclude_if_language_required=tuple(languages),
        only_visa_sponsorship=bool(block.get("only_visa_sponsorship", False)),
    )


def _wwr_categories(raw: dict) -> tuple[str, ...] | None:
    """Category names from the we_work_remotely source, or None to use the default feed."""
    sources = raw.get("sources")
    if not isinstance(sources, list):
        return None
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("id") or "").strip().lower() != "we_work_remotely":
            continue
        if "categories" not in entry:
            return None
        return tuple(_text_list(entry.get("categories")))
    return None


def load_config(path: str | Path) -> Settings:
    """Load settings. Paths in the file are relative to the file's folder."""
    config_path = Path(path)
    if not config_path.exists():
        raise ValueError(f"Could not find {config_path}.")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("config.yaml should be a set of named settings, not a list.")

    root = config_path.resolve().parent
    roles = _text_list(raw.get("roles"))
    if not roles:
        raise ValueError("Add at least one role under 'roles' in config.yaml.")

    places = []
    for entry in raw.get("locations") or []:
        if not isinstance(entry, dict) or not str(entry.get("name") or "").strip():
            raise ValueError("Each item under 'locations' needs a name.")
        distance = entry.get("distance_miles")
        if distance in (None, ""):
            miles = None
        else:
            miles = _whole_number(distance, "distance_miles", 0, 200)
        if "search_indeed" in entry and not isinstance(entry.get("search_indeed"), bool):
            raise ValueError("search_indeed must be true or false.")
        places.append(
            Place(
                name=str(entry["name"]).strip(),
                indeed_location=str(
                    entry.get("indeed_location") or entry["name"]
                ).strip(),
                linkedin_location=str(
                    entry.get("linkedin_location")
                    or entry.get("indeed_location")
                    or entry["name"]
                ).strip(),
                remote=bool(entry.get("remote", False)),
                distance_miles=miles,
                search_indeed=bool(entry.get("search_indeed", True)),
            )
        )
    if not places:
        raise ValueError("Add at least one location under 'locations' in config.yaml.")

    sites, company_pages_enabled, remote_boards = _load_sources(raw)
    companies = _load_companies(raw.get("companies"))
    if not sites and not company_pages_enabled and not remote_boards:
        raise ValueError("Turn on at least one source in config.yaml.")

    results_value = _provided(raw, "results_per_search")
    results = 10 if results_value is None else _whole_number(results_value, "results_per_search", 1, 200)
    days_value = _provided(raw, "posted_within_days")
    days = 30 if days_value is None else _whole_number(days_value, "posted_within_days", 1, 365)

    raw_keywords = raw.get("title_keywords") or {}
    if not isinstance(raw_keywords, dict):
        raise ValueError("title_keywords in config.yaml should be a group of roles.")
    title_keywords = {
        str(role).strip(): _text_list(phrases) for role, phrases in raw_keywords.items()
    }
    if "exclude_keywords" in raw and not isinstance(raw.get("exclude_keywords"), list):
        raise ValueError("exclude_keywords in config.yaml should be a list.")
    exclude_keywords = _text_list(raw.get("exclude_keywords"))

    country = _load_country(raw, places, sites)
    location_filter = _load_location_filter(raw)

    output = raw.get("output") or {}
    if not isinstance(output, dict):
        raise ValueError("The 'output' section in config.yaml should be a group of names.")
    output_dir = root / str(output.get("directory") or "output")
    return Settings(
        roles=roles,
        places=places,
        sites=sites,
        country=country,
        results_per_search=results,
        posted_within_days=days,
        pause_seconds=_pause_seconds(raw),
        fetch_descriptions=bool(raw.get("fetch_descriptions", True)),
        snippet_characters=int(raw.get("snippet_characters") or 280),
        output_dir=output_dir,
        csv_path=output_dir / str(output.get("csv") or "jobs.csv"),
        excel_path=output_dir / str(output.get("excel") or "jobs.xlsx"),
        seen_file=root / str(output.get("seen_file") or "data/seen_jobs.json"),
        require_title_match=bool(raw.get("require_title_match", False)),
        title_keywords=title_keywords,
        exclude_keywords=exclude_keywords,
        company_pages_enabled=company_pages_enabled,
        remote_boards=remote_boards,
        companies=companies,
        timezone=_load_timezone(raw),
        location_rules=build_location_rules(places, country, location_filter),
        wwr_categories=_wwr_categories(raw),
        filters=_load_filters(raw),
    )
