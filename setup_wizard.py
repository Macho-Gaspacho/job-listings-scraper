"""Ask a few plain questions and write config.yaml.

Run it directly, or use `python scrape.py --setup`.
No Python knowledge is required.
"""

from __future__ import annotations

import argparse
import functools
import shutil
import sys
from pathlib import Path

import yaml

from urllib.parse import urlparse

from config import KNOWN_SYSTEMS, Candidate
from enrichment import canonical_job_type
from places import norm, resolve_place
from regions import INDEED_COUNTRIES, canonical_country, english_name, fold_text
from source_map import auto_words, chosen_sources, recommend
from synonyms import suggestions_for


HEADER = """# Created by the setup wizard.
# To change this search, run:  python scrape.py --setup
# You can also edit this file, then run:  python scrape.py
#
# The search writes output/shortlist.xlsx. Open the Top-N sheet.
# That is the short list. output/jobs.xlsx is the full search.
# shortlist.enabled below is true. Set it to false to turn the short list off.
# To change what it keeps, see the README. You only add the lines you want to change.

"""

SOURCE_NOTES = """Which websites should we search?
Press Enter (or type: any) and we pick the best mix for your country and job. This is the recommended choice.
Or type numbers, separated by commas:
  1. Company career pages — you apply on the company's own site. Least crowded.
  2. Country and startup job boards — where we have one for your country.
  3. Remote job boards — only useful if you want remote work.
  4. Indeed
  5. LinkedIn
Indeed and LinkedIn have the most applicants per job, so we put them last."""

SYSTEM_NOTES = (
    "  greenhouse     boards.greenhouse.io/NAME",
    "  lever          jobs.lever.co/NAME",
    "  ashby          jobs.ashbyhq.com/NAME",
    "  workable       apply.workable.com/NAME",
    "  recruitee      NAME.recruitee.com",
    "  teamtailor     the full https address of the jobs.rss feed",
    "  bendingspoons  only for Bending Spoons; leave the token empty",
)

# Remote areas Indeed cannot search as a country. LinkedIn can.
_LINKEDIN_REGIONS = {
    "europe": "Europe",
    "eu": "Europe",
    "eea": "Europe",
    "european": "Europe",
    "worldwide": "Worldwide",
    "world": "Worldwide",
    "anywhere": "Worldwide",
    "global": "Worldwide",
}


class WizardCancelled(Exception):
    """The person closed the questions before saving."""


class IO:
    """One question at a time. Tests can pass their own input and output."""

    def __init__(self, input_func, output) -> None:
        self.input_func = input if input_func is None else input_func
        self.output = print if output is None else output

    def say(self, text: str) -> None:
        self.output(text)

    def ask(self, prompt: str) -> str:
        try:
            return self.input_func(prompt)
        except EOFError as exc:
            raise WizardCancelled() from exc

    def yes_no(self, question: str, default: bool) -> bool:
        hint = "Y/n" if default else "y/N"
        while True:
            raw = self.ask(f"{question} ({hint}) ").strip().lower()
            if raw == "":
                return default
            if raw in {"y", "yes"}:
                return True
            if raw in {"n", "no"}:
                return False
            self.say("Please type y or n.")


def launcher_name() -> str:
    """The double-click file for this computer."""
    if sys.platform == "win32":
        return "start.bat"
    if sys.platform == "darwin":
        return "start.command"
    return "start.sh"


def split_csv(raw: str) -> list[str]:
    seen: list[str] = []
    folded = {item.lower() for item in seen}
    for part in raw.split(","):
        text = " ".join(part.strip().split())
        if text and text.lower() not in folded:
            seen.append(text)
            folded.add(text.lower())
    return seen


_YES = {"", "y", "yes", "да", "si", "sì", "ja", "oui"}
_NO = {"n", "no", "нет"}
# Visa and language questions treat Enter as skip or "no", so empty is not a yes.
_ANSWER_YES = {"y", "yes", "да", "si", "sì", "ja", "oui", "sí"}
_ANSWER_NO = {"n", "no", "нет", "nein", "non"}


def parse_place_full(raw: str):
    """The full place resolution, including confirm and choose."""
    return resolve_place(raw)


def accepted_place(result) -> dict:
    """The place dict saved after ok, an accepted confirm, or a country."""
    if result.status == "remote":
        return {"kind": "remote"}
    if result.status == "country_only":
        label = english_name(result.country)
        return {
            "kind": "country",
            "name": label,
            "country": result.country,
            "label": label,
            "indeed": result.country in INDEED_COUNTRIES,
        }
    label = english_name(result.country)
    return {
        "kind": "city",
        "name": result.label,
        "country": result.country,
        "label": label,
        "indeed": result.country in INDEED_COUNTRIES,
    }


def parse_place(raw: str) -> tuple[dict | None, str | None]:
    """A city and country, a country on its own, or Remote.

    Returns (place, error kind). confirm and choose need another question.
    A city's name is the English label, such as "Milan, Italy".
    """
    result = parse_place_full(raw)
    if result.status in {"ok", "country_only", "remote"}:
        return accepted_place(result), None
    if result.status == "confirm":
        return None, "confirm"
    if result.status == "choose":
        return None, "choose"
    if result.status == "unknown" and result.detail == "city":
        return None, "city"
    if result.status == "empty":
        return None, "empty"
    return None, "country"


def resolve_remote_area(raw: str) -> tuple[str, str | None, bool] | None:
    """(label, country code or None, Indeed can search it), or None."""
    key = fold_text(raw)
    if key in _LINKEDIN_REGIONS:
        return _LINKEDIN_REGIONS[key], None, False
    code = canonical_country(raw)
    if code is None:
        return None
    return english_name(code), code, code in INDEED_COUNTRIES


_SOURCE_NUMBERS = {
    "1": "company",
    "2": "board",
    "3": "remote",
    "4": "indeed",
    "5": "linkedin",
}
_SOURCE_NAMES = {
    "indeed": "indeed",
    "linkedin": "linkedin",
    "arbeitnow": "board:arbeitnow",
}


def _source_text(raw: str) -> str:
    """Normalise a websites answer. A lone ? stays. Other trailing ! and ? are removed."""
    text = norm(raw)
    if text == "?":
        return text
    return text.rstrip("!?").strip()


def parse_sources(raw: str) -> str | set[str] | None:
    """'auto', a set of groups, or None when the answer should be asked again.

    Groups are company, board, remote, indeed, linkedin, and board:arbeitnow.
    """
    text = _source_text(raw)
    if text == "" or text in auto_words():
        return "auto"
    picked: set[str] = set()
    for part in text.split(","):
        token = part.strip()
        if not token:
            continue
        source = _SOURCE_NUMBERS.get(token) or _SOURCE_NAMES.get(token)
        if source is None:
            return None
        picked.add(source)
    if not picked:
        return None
    return picked


def keywords_for(
    roles: list[str],
    extras: list[str],
    accepted: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Phrases a title may match.

    Each role keeps its own name. Extra words and accepted local titles
    are added. They never replace the role. A title is kept when it
    matches any one of these phrases.
    """
    chosen = accepted or {}
    table: dict[str, list[str]] = {}
    for role in roles:
        phrases: list[str] = []
        for phrase in [role, *chosen.get(role, []), *extras]:
            lowered = phrase.strip().lower()
            if lowered and lowered not in phrases:
                phrases.append(lowered)
        table[role] = phrases
    return table


def _place_block(place: dict) -> dict:
    block = {
        "name": place["name"],
        "indeed_location": place["indeed_location"],
        "linkedin_location": place["linkedin_location"],
        "remote": place["remote"],
    }
    if place.get("distance_miles") is not None:
        block["distance_miles"] = place["distance_miles"]
    if place.get("search_indeed") is False:
        block["search_indeed"] = False
    return block


def places_from(place: dict, remote: dict | None) -> list[dict]:
    """The location blocks for config.yaml."""
    places = []
    if place["kind"] == "city":
        # name is the English label, such as "Milan, Italy", never the typed text.
        english = place["name"]
        places.append(
            {
                "name": english,
                "indeed_location": english,
                "linkedin_location": english,
                "remote": False,
                "distance_miles": 30,
                "search_indeed": bool(place["indeed"]),
            }
        )
    elif place["kind"] == "country":
        places.append(
            {
                "name": place["name"],
                "indeed_location": place["name"],
                "linkedin_location": place["name"],
                "remote": False,
                "search_indeed": bool(place["indeed"]),
            }
        )
    if remote:
        places.append(
            {
                "name": "Remote",
                "indeed_location": remote["label"],
                "linkedin_location": remote["label"],
                "remote": True,
                "search_indeed": bool(remote["indeed"]),
            }
        )
    return places


def _stored_company(company, curated: bool = False) -> dict:
    """One companies: entry. Old user-typed rows stay name, system, token, enabled."""
    if isinstance(company, dict):
        name = company["name"]
        system = company["system"]
        token = company.get("token") or ""
        region = str(company.get("region") or "").strip()
        families = list(company.get("families") or [])
        jobs = company.get("jobs_in_country") or 0
        curated = curated or bool(company.get("curated"))
    else:
        name = company.name
        system = company.system
        token = company.token or ""
        region = company.region or ""
        families = list(company.families or [])
        jobs = company.jobs_in_country or 0
        curated = curated or company.curated
    entry = {
        "name": name,
        "system": system,
        "token": token,
        "enabled": True,
    }
    if region:
        entry["region"] = region
    if families:
        entry["families"] = families
    if curated:
        entry["curated"] = True
        if jobs:
            entry["jobs_in_country"] = int(jobs)
    return entry


def build_config(
    roles: list[str],
    places: list[dict],
    country: str,
    extras: list[str],
    accepted: dict[str, list[str]],
    exclude: list[str],
    sources: set[str],
    companies: list[dict],
    require_title_match: bool,
    results_per_search: int,
    posted_within_days: int,
    job_types: list[str] | None = None,
    hide_senior: bool = False,
    visa_sponsorship: bool = False,
    source_choice: str | None = None,
    link_outs: list[str] | None = None,
    candidate: Candidate | None = None,
) -> dict:
    from source_map import curated_employers

    enabled = set(sources)
    user_rows = [_stored_company(company) for company in companies]
    curated_rows = []
    if source_choice == "auto" or "company_pages" in enabled:
        seen = {(row["system"], str(row.get("token") or "").casefold()) for row in user_rows}
        for company in curated_employers(country, places, roles):
            key = (company.system, company.token.casefold())
            if key in seen:
                continue
            seen.add(key)
            curated_rows.append(_stored_company(company, curated=True))
    merged = user_rows + curated_rows
    if merged:
        enabled.add("company_pages")
    catalog = (
        ("company_pages", "company site"),
        ("arbeitnow", "job board"),
        ("we_work_remotely", "remote board"),
        ("remote_ok", "remote board"),
        ("remotive", "remote board"),
        ("working_nomads", "remote board"),
        ("indeed", "aggregator"),
        ("linkedin", "aggregator"),
    )
    data = {
        "roles": roles,
        "require_title_match": require_title_match,
        "title_keywords": keywords_for(roles, extras, accepted),
        "locations": [_place_block(place) for place in places],
        "sources": [
            {"id": source_id, "enabled": source_id in enabled, "kind": kind}
            for source_id, kind in catalog
        ],
        "companies": merged,
        "country": country,
        "results_per_search": results_per_search,
        "posted_within_days": posted_within_days,
        "pause_seconds": 2,
        "fetch_descriptions": True,
        "snippet_characters": 280,
        "output": {
            "directory": "output",
            "csv": "jobs.csv",
            "excel": "jobs.xlsx",
            "seen_file": "data/seen_jobs.json",
        },
        "shortlist": {"enabled": True},
    }
    if exclude:
        data["exclude_keywords"] = [word.lower() for word in exclude]
    filters = {}
    if job_types:
        filters["job_types"] = list(job_types)
    if hide_senior:
        filters["levels"] = ["Entry", "Unknown"]
    if visa_sponsorship:
        filters["only_visa_sponsorship"] = True
    if filters:
        data["filters"] = filters
    if source_choice:
        data["source_choice"] = source_choice
    if link_outs:
        data["link_outs"] = list(link_outs)
    if candidate is not None and (
        candidate.needs_visa is not None or candidate.languages is not None
    ):
        data["candidate"] = {
            "needs_visa": candidate.needs_visa,
            "languages": None if candidate.languages is None else list(candidate.languages),
            "strict": bool(candidate.strict),
        }
    return data


def summary_text(data: dict) -> str:
    roles = ", ".join(data["roles"])
    places = []
    for place in data["locations"]:
        if place.get("remote"):
            line = f"remote in {place['indeed_location']}"
            if place.get("search_indeed") is False:
                line += " (LinkedIn only)"
            places.append(line)
        else:
            places.append(place["name"])
    labels = {
        "company_pages": "company career pages",
        "we_work_remotely": "We Work Remotely",
        "remote_ok": "Remote OK",
        "remotive": "Remotive",
        "working_nomads": "Working Nomads",
        "arbeitnow": "Arbeitnow",
        "indeed": "Indeed",
        "linkedin": "LinkedIn",
    }
    enabled = [
        labels.get(source["id"], source["id"])
        for source in data["sources"]
        if source["enabled"]
    ]
    companies = data["companies"] or []
    company_line = ", ".join(company["name"] for company in companies) or "none"
    if data.get("require_title_match"):
        words = []
        for phrases in data["title_keywords"].values():
            for phrase in phrases:
                if phrase not in words:
                    words.append(phrase)
        filter_line = f"  A title must match one of: {', '.join(words)}"
    else:
        filter_line = "  Title filter: off. Every result Indeed and LinkedIn return is kept."
    exclude = data.get("exclude_keywords") or []
    exclude_line = f"\n  Skip a title that contains: {', '.join(exclude)}" if exclude else ""
    filters = data.get("filters") or {}
    filter_bits = []
    if filters.get("job_types"):
        filter_bits.append("Job types: " + ", ".join(filters["job_types"]))
    if filters.get("levels"):
        filter_bits.append("Senior roles: hidden")
    if filters.get("only_visa_sponsorship"):
        filter_bits.append("Visa: keep jobs that offer sponsorship or do not say")
    extra_line = "".join(f"\n  {bit}" for bit in filter_bits)
    candidate_line = _candidate_summary(data.get("candidate"))
    return (
        "Here is the search that will be saved:\n"
        f"  Job titles: {roles}\n"
        f"  Places: {'; '.join(places)}\n"
        f"{filter_line}{exclude_line}{extra_line}{candidate_line}\n"
        f"  Results per search: {data['results_per_search']}\n"
        f"  Posted within days: {data['posted_within_days']}\n"
        f"  Websites: {', '.join(enabled) or 'none'}\n"
        f"  Companies: {company_line}\n"
        "  Shortlist: on. After the search, open output/shortlist.xlsx (the Top-N sheet)."
    )


def _candidate_summary(candidate: object) -> str:
    """Lines for the summary. Skipped questions add nothing."""
    if not isinstance(candidate, dict):
        return ""
    lines = []
    needs = candidate.get("needs_visa")
    if needs is True:
        lines.append("Visa: you need sponsorship (jobs that mention it first)")
    elif needs is False:
        lines.append("Visa: you do not need sponsorship")
    languages = candidate.get("languages") or []
    if languages:
        lines.append("Languages you work in: " + ", ".join(str(name) for name in languages))
    if needs is True or languages:
        answer = "yes" if candidate.get("strict") else "no"
        lines.append(f"Hide jobs that do not fit: {answer}")
    return "".join(f"\n  {line}" for line in lines)


def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= char <= "\u04FF" for char in text)


@functools.lru_cache(maxsize=1)
def _ru_titles() -> dict[str, str]:
    path = Path(__file__).resolve().parent / "synonyms" / "ru_titles.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    found = {}
    for key, value in raw.items():
        found[norm(key)] = " ".join(str(value).split())
    return found


@functools.lru_cache(maxsize=1)
def _language_aliases() -> dict[str, str]:
    path = Path(__file__).resolve().parent / "signals" / "language_names.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    aliases = {}
    for canonical, names in raw.items():
        for name in names or []:
            aliases.setdefault(norm(name), str(canonical))
    return aliases


def parse_spoken_languages(raw: str) -> tuple[list[str], list[str]]:
    """Canonical language names, and the words that were not recognised."""
    found: list[str] = []
    unknown: list[str] = []
    aliases = _language_aliases()
    for part in raw.split(","):
        word = " ".join(part.split())
        if not word:
            continue
        canonical = aliases.get(norm(word))
        if canonical is None:
            unknown.append(word)
            continue
        if canonical not in found:
            found.append(canonical)
    return found, unknown


def _folded_answer(raw: str) -> str:
    return raw.strip().casefold()


def _english_role(io: IO, role: str) -> str:
    """Offer the English title for a Russian one. Other titles stay as typed."""
    if not _has_cyrillic(role):
        return role
    english = _ru_titles().get(norm(role))
    if english:
        io.say(
            f'In job ads this is usually "{english}". '
            f'Search for "{english}" instead? (Y/n)'
        )
        for _attempt in range(3):
            raw = _folded_answer(io.ask("> "))
            if raw == "" or raw in _ANSWER_YES:
                return english
            if raw in _ANSWER_NO:
                return role
            io.say("Please type y or n.")
        return role
    io.say(
        f'"{role}" is not in English. Most job ads in the country you choose '
        "use English titles, so this may find few jobs. Type the English title, "
        "or press Enter to keep it."
    )
    typed = io.ask("> ")
    if not typed.strip():
        return role
    return " ".join(typed.split())


def ask_roles(io: IO) -> list[str]:
    while True:
        io.say("")
        io.say("Which job titles are you looking for?")
        io.say("Separate them with commas. Example: Project Manager, Product Manager")
        roles = split_csv(io.ask("> "))
        if not roles:
            io.say("Please type at least one job title. Example: Project Manager, Product Manager")
            continue
        return [_english_role(io, role) for role in roles]


def _confirm_place(io: IO, label: str) -> bool:
    """Yes is the default. Enter, y, or the same word in a few languages accepts."""
    while True:
        raw = io.ask(f"I understood: {label}. Is that right? [Y/n] ").strip().casefold()
        if raw in _YES:
            return True
        if raw in _NO:
            return False
        io.say("Please type y or n.")


def _choose_place(io: IO, typed: str, choices: tuple) -> dict | None:
    io.say(f"There is more than one {typed}. Which one?")
    for index, choice in enumerate(choices, start=1):
        io.say(f"{index}. {choice[2]}")
    io.say("0. None of these, let me type it again")
    shown = {str(index) for index in range(len(choices) + 1)}
    for _attempt in range(3):
        raw = io.ask("> ").strip()
        if raw in shown:
            if raw == "0":
                return None
            _city, country, label = choices[int(raw) - 1]
            return {
                "kind": "city",
                "name": label,
                "country": country,
                "label": english_name(country),
                "indeed": country in INDEED_COUNTRIES,
            }
        io.say("Please type one of the numbers shown.")
    return None


def ask_place(io: IO) -> dict:
    while True:
        io.say("")
        io.say("Which place should we search?")
        io.say("Type a city and a country, a country on its own, or Remote.")
        io.say("Examples: Berlin, Germany    Milano, Italia    Italy    Remote")
        io.say("For the US state of Georgia, type the city and United States.")
        result = parse_place_full(io.ask("> "))
        parsed = None
        if result.status in {"ok", "country_only", "remote"}:
            parsed = accepted_place(result)
        elif result.status == "confirm":
            if _confirm_place(io, result.label):
                parsed = accepted_place(result)
        elif result.status == "choose":
            parsed = _choose_place(io, result.typed, result.choices)
        elif result.status == "unknown" and result.detail == "city":
            io.say(
                f'I could not find "{result.typed}". Please add the country after a comma, '
                "for example: Bergamo, Italy"
            )
        elif result.status == "unknown":
            io.say(
                "That country was not recognised. Use the English name, "
                "such as Germany, Italy, Armenia, or United States. "
                "You can write the country in English, Italian, German, French, Spanish or Russian."
            )
        else:
            io.say(
                "Type a city and a country separated by a comma, a country on its own, or Remote. "
                "Examples: Berlin, Germany    Milano, Italia    Italy    Remote"
            )
        if parsed is None:
            continue
        if parsed["kind"] != "remote" and not parsed["indeed"]:
            io.say(
                f"Indeed does not cover {parsed['label']}. "
                "LinkedIn will be used for this search. Indeed will be left off."
            )
        return parsed


def ask_remote(io: IO, country_code: str | None, country_label: str, place_is_remote: bool) -> dict | None:
    """Where remote jobs should be, or None when remote is skipped."""
    if not place_is_remote:
        io.say("")
        io.say("Also include remote jobs?")
        io.say("Remote means a job you can do from home.")
        if not io.yes_no("Include remote jobs?", default=True):
            return None
    io.say("")
    io.say("Remote jobs in which country or region?")
    if country_label and not place_is_remote:
        io.say(f"Press Enter to use {country_label}.")
    else:
        io.say("Type a country, Europe, or Worldwide.")
    while True:
        raw = io.ask("> ").strip()
        if raw == "" and country_label and not place_is_remote:
            raw = country_label
        if not raw:
            io.say("Type a country, Europe, or Worldwide.")
            continue
        resolved = resolve_remote_area(raw)
        if resolved is None:
            io.say(
                "That is not a country or region this search understands. "
                "Use a country name, Europe, or Worldwide."
            )
            continue
        label, code, on_indeed = resolved
        if code is None:
            io.say(
                f"Indeed can only search one country per config, and it cannot search {label}. "
                "Remote jobs there will be searched on LinkedIn only."
            )
            return {"label": label, "indeed": False, "country": None}
        if not on_indeed:
            io.say(
                f"Indeed does not cover {label}. "
                "Remote jobs there will be searched on LinkedIn only."
            )
            return {"label": label, "indeed": False, "country": code}
        if country_code and code != country_code:
            io.say(
                "Indeed can only search one country per config. "
                f"{label} is a different country from {country_label}."
            )
            io.say(f"  1. Use LinkedIn only for remote jobs in {label}")
            io.say(f"  2. Use {country_label} for remote jobs too")
            while True:
                choice = io.ask("Type 1 or 2: ").strip()
                if choice == "1":
                    return {"label": label, "indeed": False, "country": code}
                if choice == "2":
                    return {"label": country_label, "indeed": True, "country": country_code}
                io.say("Type 1 or 2.")
        return {"label": label, "indeed": True, "country": code}


def ask_home_country(io: IO) -> tuple[str, str, bool]:
    """A country to attach to a LinkedIn-only remote region such as Europe."""
    io.say("")
    io.say("Which country are you based in?")
    io.say("Europe and Worldwide are searched on LinkedIn. The country is used to recognise jobs that are open to you.")
    io.say("Example: Italy")
    while True:
        code = canonical_country(io.ask("> "))
        if code is None:
            io.say("That country was not recognised. Use the English name, such as Italy or Germany.")
            continue
        label = english_name(code)
        indeed_ok = code in INDEED_COUNTRIES
        if not indeed_ok:
            io.say(f"Indeed does not cover {label}. LinkedIn will be used. Indeed will be left off.")
        return code, label, indeed_ok


def resolve_country_and_remote(io: IO, place: dict) -> tuple[dict | None, str, str, bool]:
    """Remote choice, country code, country label, and whether Indeed can be used."""
    if place["kind"] == "remote":
        remote = ask_remote(io, None, "", True)
        assert remote is not None
        if remote["country"] and remote["indeed"]:
            country = remote["country"]
            return remote, country, english_name(country), True
        if remote["country"]:
            country = remote["country"]
            remote = {**remote, "indeed": False}
            return remote, country, english_name(country), country in INDEED_COUNTRIES
        country, label, indeed_ok = ask_home_country(io)
        return {**remote, "indeed": False}, country, label, indeed_ok
    remote = ask_remote(io, place["country"], place["label"], False)
    return remote, place["country"], place["label"], place["indeed"]


def ask_synonyms(io: IO, suggestions: dict[str, list[str]]) -> dict[str, list[str]]:
    if not suggestions:
        return {}
    io.say("")
    io.say("These are common local titles for this search. The lists are a starter set, not every possible title.")
    for role, phrases in suggestions.items():
        io.say(f"  {role}: {', '.join(phrases)}")
    if io.yes_no("Also accept these titles?", default=True):
        return suggestions
    return {}


def ask_keep_all(io: IO, default_yes: bool) -> bool:
    io.say("")
    io.say("You can keep every result, including titles that do not match the words above.")
    return io.yes_no(
        "Keep every result Indeed and LinkedIn return (no title filter)?",
        default=default_yes,
    )


def ask_keywords(io: IO) -> list[str]:
    io.say("")
    io.say("Extra words that also count as a match (optional).")
    io.say("These are added to each job title. They do not replace it.")
    io.say("A job is kept when its title matches the job title, a local title you accepted, or one of these words.")
    io.say("Example: backend, python. Leave this blank to skip.")
    return split_csv(io.ask("> "))


def ask_job_types(io: IO) -> list[str]:
    io.say("")
    io.say("Only certain job types?")
    io.say("You can limit results to Full-time, Part-time, Contract, Internship, or Temporary.")
    if not io.yes_no("Only certain job types?", default=False):
        return []
    while True:
        io.say("Which job types? Separate them with commas. Example: Full-time, Internship")
        chosen = []
        failed = False
        for part in split_csv(io.ask("> ")):
            name = canonical_job_type(part)
            if not name:
                io.say("Use Full-time, Part-time, Contract, Internship, or Temporary.")
                failed = True
                break
            if name not in chosen:
                chosen.append(name)
        if not failed and chosen:
            return chosen
        if not failed:
            return []


def ask_hide_senior(io: IO) -> bool:
    io.say("")
    io.say("Hide senior roles?")
    io.say("Titles such as senior, lead, principal, staff, and head are left out. Other titles stay, including ones with no level.")
    return io.yes_no("Hide senior roles?", default=False)


def ask_visa(io: IO, country_label: str, remote_only: bool = False) -> bool | None:
    """True, False, or None when the question is skipped."""
    where = "the countries you chose" if remote_only else country_label
    io.say("")
    io.say(f"Do you need a visa or work permit to work in {where}?")
    io.say(
        "If yes, jobs that mention sponsorship come first, and jobs that say "
        "they do not sponsor are marked and put at the bottom."
    )
    io.say("Press Enter to skip.")
    for _attempt in range(3):
        raw = _folded_answer(io.ask("Need sponsorship? (y/N) "))
        if raw == "":
            return None
        if raw in _ANSWER_YES:
            return True
        if raw in _ANSWER_NO:
            return False
        io.say("Please type y or n, or press Enter to skip.")
    return None


def ask_languages(io: IO) -> tuple[str, ...] | None:
    """Languages the person can work in, or None when the question is skipped."""
    io.say("")
    io.say("Which languages can you work in? Separate them with commas, in any language.")
    io.say("Example: English, Russian, Italian. Press Enter to skip.")
    for attempt in range(2):
        raw = io.ask("> ")
        if not raw.strip():
            return None
        found, unknown = parse_spoken_languages(raw)
        for word in unknown:
            io.say(f'I don\'t know "{word}", so it was left out.')
        if found:
            return tuple(found)
        if attempt == 0:
            continue
        return None
    return None


def ask_strict_fit(io: IO) -> bool:
    """True hides jobs that clearly do not fit. Enter keeps them, marked."""
    io.say("")
    io.say(
        "Hide jobs that clearly do not fit (they say no sponsorship, "
        "or require a language you did not list)?"
    )
    io.say("Press Enter to keep them, marked at the bottom.")
    for _attempt in range(3):
        raw = _folded_answer(io.ask("Hide them? (y/N) "))
        if raw == "" or raw in _ANSWER_NO:
            return False
        if raw in _ANSWER_YES:
            return True
        io.say("Please type y or n, or press Enter to keep them.")
    return False


def ask_exclude(io: IO) -> list[str]:
    io.say("")
    io.say("Words that should reject a job title (optional).")
    io.say("A job is dropped when the title contains one of these words on its own.")
    io.say("Example: senior, intern. The word intern does not reject internal.")
    io.say("Leave this blank to skip.")
    return split_csv(io.ask("> "))


def ask_sources(io: IO, indeed_ok: bool, country: str, places: list[dict], roles: list[str]) -> str | set[str]:
    """'auto', or the groups the user typed. Two failed answers use the recommended mix."""
    failures = 0
    while True:
        io.say("")
        io.say(SOURCE_NOTES)
        if not indeed_ok:
            io.say("Indeed does not cover this country, so option 4 will be left off.")
        picked = parse_sources(io.ask("Your choice [Enter]: "))
        if picked is None:
            failures += 1
            if failures >= 2:
                io.say("Using the recommended mix.")
                picked = "auto"
            else:
                io.say(
                    "I did not understand that. Press Enter and we pick for you, "
                    "or type numbers like 1,4."
                )
                continue
        if picked == "auto":
            recommendation = recommend(country, places, roles)
            for line in recommendation.explanation:
                io.say(line)
            if not indeed_ok and "indeed" not in recommendation.sources:
                io.say("Indeed was left off because it does not cover this country.")
            return "auto"
        chosen = set(picked)
        if not indeed_ok and "indeed" in chosen:
            chosen.discard("indeed")
            io.say("Indeed was left off because it does not cover this country.")
        if not chosen:
            chosen = {"linkedin"}
            io.say("LinkedIn will be used.")
        return chosen


def ask_number(io: IO, default: int, low: int, high: int) -> int:
    while True:
        raw = io.ask("> ").strip()
        if raw == "":
            return default
        if raw.isdigit():
            number = int(raw)
            if low <= number <= high:
                return number
        io.say(f"Please type a whole number from {low} to {high}, or press Enter for {default}.")


def ask_results_per_search(io: IO) -> int:
    io.say("")
    io.say("How many results should we ask Indeed and LinkedIn for, per search?")
    io.say("A higher number takes longer. Company pages are not limited by this.")
    io.say("Press Enter for 20. Type a whole number from 1 to 200.")
    return ask_number(io, 20, 1, 200)


def ask_posted_within_days(io: IO) -> int:
    io.say("")
    io.say("How many days back should we look?")
    io.say("Older Indeed and LinkedIn posts are skipped. Jobs on a company page are kept while they are open.")
    io.say("Press Enter for 14. Type a whole number from 1 to 365.")
    return ask_number(io, 14, 1, 365)


_SYSTEM_SKIP = {"", "skip", "не знаю", "don't know", "dont know", "idk", "?"}


def _is_system_skip(raw: str) -> bool:
    text = norm(raw)
    if text == "?":
        return True
    return text in {norm(item) for item in _SYSTEM_SKIP if item != "?"}


def _skip_company(io: IO, name: str) -> None:
    io.say(f"Skipped {name}. You can add it later in config.yaml.")


def _career_url(raw: str) -> str:
    text = raw.strip()
    if "://" not in text:
        text = "https://" + text
    return text


def _looks_like_url(raw: str) -> bool:
    text = raw.strip().lower()
    if "://" in text or text.startswith("www."):
        return True
    return "/" in text and "." in text


def _is_eu_lever(raw: str) -> bool:
    host = (urlparse(_career_url(raw)).hostname or "").lower()
    return host == "jobs.eu.lever.co"


def _company_label(raw: str) -> str:
    host = (urlparse(_career_url(raw)).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    label = host.split(".")[0] if host else raw.strip()
    return label or raw.strip()


def detect_system(url: str) -> tuple[str, str] | None:
    """Hiring system and public token from a careers address, or None.

    jobs.eu.lever.co uses the same token as Lever. The caller stores region "eu".
    """
    parsed = urlparse(_career_url(url))
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    if host.endswith(".greenhouse.io") or host == "greenhouse.io":
        if parts:
            return "greenhouse", parts[0]
        return None
    if host in {"jobs.lever.co", "jobs.eu.lever.co"} and parts:
        return "lever", parts[0]
    if host == "jobs.ashbyhq.com" and parts:
        return "ashby", parts[0]
    if host == "apply.workable.com" and parts:
        return "workable", parts[0].strip()
    if host.endswith(".recruitee.com"):
        token = host.split(".")[0]
        if token and token != "www":
            return "recruitee", token
    if host.endswith(".teamtailor.com"):
        token = host.split(".")[0]
        if token and token != "www":
            return "teamtailor", f"https://{token}.teamtailor.com/jobs.rss"
    return None


def ask_system(io: IO, name: str) -> str | None:
    """A hiring system, or None when this company is skipped. At most two wrong answers."""
    io.say("")
    io.say("Which hiring system does that company use?")
    io.say("Look at the careers address and match it to one of these:")
    for line in SYSTEM_NOTES:
        io.say(line)
    known = ", ".join(KNOWN_SYSTEMS)
    wrong = 0
    while True:
        system = norm(io.ask("Hiring system: "))
        if _is_system_skip(system):
            _skip_company(io, name)
            return None
        if system in KNOWN_SYSTEMS:
            return system
        wrong += 1
        if wrong >= 2:
            _skip_company(io, name)
            return None
        for line in SYSTEM_NOTES:
            io.say(line)
        io.say(f"Please type one of: {known}.")


def ask_token(io: IO, system: str, name: str) -> str | None:
    """The public token, or None when this company is skipped.

    Bending Spoons has no token: Enter still adds it. Every other system
    treats Enter or skip as a skip, and stops after three bad answers.
    """
    io.say("")
    if system == "bendingspoons":
        io.say("Bending Spoons does not need a token. Press Enter.")
        raw = io.ask("Token: ").strip()
        if norm(raw) == "skip":
            _skip_company(io, name)
            return None
        return ""
    io.say("Public id from the careers address (token). This is not a password.")
    if system == "teamtailor":
        io.say("Paste the full https address of the jobs.rss feed.")
    else:
        io.say("Example: if the address ends in /acme, the token is acme.")
    bad = 0
    while True:
        token = io.ask("Token: ").strip()
        if _is_system_skip(token):
            _skip_company(io, name)
            return None
        if system == "teamtailor" and not token.lower().startswith("http"):
            bad += 1
            if bad >= 3:
                _skip_company(io, name)
                return None
            io.say("Teamtailor needs the full https address of the jobs RSS feed.")
            continue
        return token


def ask_companies(io: IO) -> list[dict]:
    companies: list[dict] = []
    io.say("")
    io.say("Type a company name, or paste its careers page address. Press Enter to skip.")
    while True:
        io.say("")
        raw = io.ask("> ").strip()
        if not raw:
            break
        if _looks_like_url(raw):
            detected = detect_system(raw)
            if detected:
                system, token = detected
                company = {"name": token, "system": system, "token": token}
                if _is_eu_lever(raw):
                    company["region"] = "eu"
                companies.append(company)
            else:
                label = _company_label(raw)
                system = ask_system(io, label)
                if system:
                    token = ask_token(io, system, label)
                    if token is not None:
                        companies.append({"name": label, "system": system, "token": token})
        else:
            system = ask_system(io, raw)
            if system:
                token = ask_token(io, system, raw)
                if token is not None:
                    companies.append({"name": raw, "system": system, "token": token})
        if not io.yes_no("Add another company?", default=False):
            break
    return companies


def write_config(path: Path, data: dict) -> bool:
    """Write the file. Return True when an older file was copied aside."""
    backed_up = False
    if path.exists():
        shutil.copyfile(path, path.parent / "config.backup.yaml")
        backed_up = True
    body = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    path.write_text(HEADER + body, encoding="utf-8")
    return backed_up


def run_wizard(config_path, input_func=None, output=None, run_search=None) -> int:
    """Ask the questions, write the file, and optionally start the search."""
    path = Path(config_path)
    io = IO(input_func, output)
    try:
        return _ask_and_save(path, io, run_search)
    except WizardCancelled:
        io.say("Stopped. No new config.yaml was written.")
        return 1


def _finish_sources(io: IO, sources: set[str], indeed_ok: bool, places: list[dict]) -> set[str]:
    """Drop Indeed when this search cannot use it, and keep at least one website."""
    chosen = set(sources)
    if not any(place.get("search_indeed", True) for place in places) and "indeed" in chosen:
        chosen.discard("indeed")
        io.say("Indeed was left off because none of these places can be searched on Indeed.")
    if not chosen:
        if indeed_ok:
            io.say("Indeed and LinkedIn will be used, because no other website was selected.")
            return {"indeed", "linkedin"}
        io.say("LinkedIn will be used, because no other website was selected.")
        return {"linkedin"}
    return chosen


def _ask_and_save(path: Path, io: IO, run_search) -> int:
    io.say("Answer a few questions. This writes config.yaml for your job search.")
    io.say("You do not need to edit any code. Press Enter to accept a choice shown in [brackets].")
    while True:
        roles = ask_roles(io)
        place = ask_place(io)
        remote, country, _country_label, indeed_ok = resolve_country_and_remote(io, place)
        suggestions = suggestions_for(roles, country)
        accepted = ask_synonyms(io, suggestions)
        keep_all = ask_keep_all(io, default_yes=not suggestions)
        extras = ask_keywords(io)
        exclude = ask_exclude(io)
        job_types = ask_job_types(io)
        hide_senior = ask_hide_senior(io)
        needs_visa = ask_visa(io, _country_label, remote_only=place["kind"] == "remote")
        spoken = ask_languages(io)
        strict = False
        if needs_visa is True or spoken is not None:
            strict = ask_strict_fit(io)
        candidate = None
        if needs_visa is not None or spoken is not None:
            candidate = Candidate(needs_visa=needs_visa, languages=spoken, strict=strict)
        places = places_from(place, remote)
        choice = ask_sources(io, indeed_ok, country, places, roles)
        want_companies = choice == "auto" or (isinstance(choice, set) and "company" in choice)
        companies = ask_companies(io) if want_companies else []
        if isinstance(choice, set) and "company" in choice and not companies:
            io.say("No companies were added, so company career pages will be left off.")
        enabled, link_ids = chosen_sources(choice, country, places, roles, companies)
        sources = _finish_sources(io, enabled, indeed_ok, places)
        results_per_search = ask_results_per_search(io)
        posted_within_days = ask_posted_within_days(io)
        data = build_config(
            roles,
            places,
            country,
            extras,
            accepted,
            exclude,
            sources,
            companies,
            require_title_match=not keep_all,
            results_per_search=results_per_search,
            posted_within_days=posted_within_days,
            job_types=job_types,
            hide_senior=hide_senior,
            candidate=candidate,
            source_choice="auto" if choice == "auto" else None,
            link_outs=link_ids if choice == "auto" else None,
        )
        io.say("")
        io.say(summary_text(data))
        if path.exists():
            io.say(f"Your current {path.name} will be copied to config.backup.yaml if you save.")
        if not io.yes_no(f"Save this to {path.name}?", default=True):
            io.say("Okay. Let's go through the questions again.")
            continue
        backed_up = write_config(path, data)
        io.say(f"Saved {path.name}.")
        if backed_up:
            io.say("Your previous settings are in config.backup.yaml.")
        io.say("")
        io.say("Search for jobs now? The first run can take several minutes.")
        if not io.yes_no("Search now?", default=True):
            io.say(f"Not searching yet. Next time just double-click {launcher_name()}.")
            return 0
        io.say("Starting the search. Leave this window open.")
        if run_search is None:
            import scrape

            return int(scrape.main(["--config", str(path)]))
        return int(run_search(path))


def main(argv: list[str] | None = None) -> int:
    try:
        parser = argparse.ArgumentParser(
            description="Answer a few questions and write config.yaml."
        )
        parser.add_argument(
            "--config",
            default=str(Path(__file__).resolve().parent / "config.yaml"),
            help="Where to write the settings. The default is config.yaml in this folder.",
        )
        args = parser.parse_args(argv)
        return run_wizard(args.config)
    except KeyboardInterrupt:
        print("Stopped. Nothing was changed.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
