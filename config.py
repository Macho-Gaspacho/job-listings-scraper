"""Read config.yaml into a small settings object.

Edit config.yaml to change what is searched. This file only checks
that the settings make sense and turns them into something the rest
of the program can use.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


# Sites python-jobspy knows how to ask. The default config only turns on
# the ones that returned real Milan listings when this project was tested.
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
    """One place to search, such as Milan or remote work in Italy."""

    name: str
    indeed_location: str
    linkedin_location: str
    remote: bool = False
    distance_miles: int | None = None


@dataclass
class Company:
    """One employer whose public careers page we read directly."""

    name: str
    system: str
    token: str = ""
    enabled: bool = True


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
    company_pages_enabled: bool = False
    remote_boards: list[str] | None = None
    companies: list[Company] | None = None


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
                distance_miles=None if distance in (None, "") else int(distance),
            )
        )
    if not places:
        raise ValueError("Add at least one location under 'locations' in config.yaml.")

    sites, company_pages_enabled, remote_boards = _load_sources(raw)
    companies = _load_companies(raw.get("companies"))
    if not sites and not company_pages_enabled and not remote_boards:
        raise ValueError("Turn on at least one source in config.yaml.")

    results = int(raw.get("results_per_search") or 10)
    days = int(raw.get("posted_within_days") or 30)
    if results < 1:
        raise ValueError("results_per_search should be at least 1.")
    if days < 1:
        raise ValueError("posted_within_days should be at least 1.")

    raw_keywords = raw.get("title_keywords") or {}
    if not isinstance(raw_keywords, dict):
        raise ValueError("title_keywords in config.yaml should be a group of roles.")
    title_keywords = {
        str(role).strip(): _text_list(phrases) for role, phrases in raw_keywords.items()
    }

    output = raw.get("output") or {}
    if not isinstance(output, dict):
        raise ValueError("The 'output' section in config.yaml should be a group of names.")
    output_dir = root / str(output.get("directory") or "output")
    return Settings(
        roles=roles,
        places=places,
        sites=sites,
        country=str(raw.get("country") or "italy").strip().lower(),
        results_per_search=results,
        posted_within_days=days,
        pause_seconds=float(raw.get("pause_seconds") or 0),
        fetch_descriptions=bool(raw.get("fetch_descriptions", True)),
        snippet_characters=int(raw.get("snippet_characters") or 280),
        output_dir=output_dir,
        csv_path=output_dir / str(output.get("csv") or "jobs.csv"),
        excel_path=output_dir / str(output.get("excel") or "jobs.xlsx"),
        seen_file=root / str(output.get("seen_file") or "data/seen_jobs.json"),
        require_title_match=bool(raw.get("require_title_match", False)),
        title_keywords=title_keywords,
        company_pages_enabled=company_pages_enabled,
        remote_boards=remote_boards,
        companies=companies,
    )
