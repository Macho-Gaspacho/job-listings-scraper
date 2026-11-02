"""Ask a few plain questions and write config.yaml.

Run it directly, or use `python scrape.py --setup`.
No Python knowledge is required.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml

from config import KNOWN_SYSTEMS
from enrichment import canonical_job_type
from regions import INDEED_COUNTRIES, canonical_country, english_name, fold_text
from synonyms import suggestions_for


HEADER = """# Created by the setup wizard.
# To change this search, run:  python scrape.py --setup
# You can also edit this file, then run:  python scrape.py

"""

SOURCE_NOTES = (
    "  1. Indeed — a large job board. A good default for most cities.",
    "  2. LinkedIn — public job posts. A long run can be slow, and LinkedIn sometimes blocks it.",
    "  3. Remote boards — We Work Remotely and Remote OK. Useful for remote jobs.",
    "     Remote boards follow the cities and countries you just chose.",
    "  4. Company career pages — employers you name next. You apply on the company's own site.",
)

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
    return "start.command"


def split_csv(raw: str) -> list[str]:
    seen: list[str] = []
    folded = {item.lower() for item in seen}
    for part in raw.split(","):
        text = " ".join(part.strip().split())
        if text and text.lower() not in folded:
            seen.append(text)
            folded.add(text.lower())
    return seen


def parse_place(raw: str) -> tuple[dict | None, str | None]:
    """A city and country, a country on its own, or Remote.

    Returns (place, error kind). error kind is "comma" or "country".
    """
    text = " ".join(raw.strip().split())
    if not text:
        return None, "empty"
    if fold_text(text) == "remote":
        return {"kind": "remote"}, None
    if "," not in raw:
        code = canonical_country(text)
        if code:
            label = english_name(code)
            return {
                "kind": "country",
                "name": label,
                "country": code,
                "label": label,
                "indeed": code in INDEED_COUNTRIES,
            }, None
        if len(text.split()) >= 2:
            return None, "comma"
        return None, "country"
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) < 2:
        return None, "comma"
    code = canonical_country(parts[-1])
    if code is None:
        return None, "country"
    label = english_name(code)
    return {
        "kind": "city",
        "name": ", ".join(parts),
        "country": code,
        "label": label,
        "indeed": code in INDEED_COUNTRIES,
    }, None


def resolve_remote_area(raw: str) -> tuple[str, str | None, bool] | None:
    """(label, country code or None, Indeed can search it), or None."""
    key = fold_text(raw)
    if key in _LINKEDIN_REGIONS:
        return _LINKEDIN_REGIONS[key], None, False
    code = canonical_country(raw)
    if code is None:
        return None
    return english_name(code), code, code in INDEED_COUNTRIES


def parse_sources(raw: str) -> set[str] | None:
    text = raw.strip().lower()
    if text == "":
        return {"indeed", "linkedin"}
    if text == "all":
        return {"indeed", "linkedin", "remote", "company_pages"}
    names = {
        "1": "indeed",
        "2": "linkedin",
        "3": "remote",
        "4": "company_pages",
        "indeed": "indeed",
        "linkedin": "linkedin",
        "remote": "remote",
        "company": "company_pages",
        "companies": "company_pages",
    }
    picked: set[str] = set()
    for part in text.split(","):
        token = part.strip()
        if not token:
            continue
        source = names.get(token)
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
        places.append(
            {
                "name": place["name"],
                "indeed_location": place["name"],
                "linkedin_location": place["name"],
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
) -> dict:
    use_companies = "company_pages" in sources and bool(companies)
    data = {
        "roles": roles,
        "require_title_match": require_title_match,
        "title_keywords": keywords_for(roles, extras, accepted),
        "locations": [_place_block(place) for place in places],
        "sources": [
            {"id": "company_pages", "enabled": use_companies, "kind": "company site"},
            {"id": "we_work_remotely", "enabled": "remote" in sources, "kind": "remote board"},
            {"id": "remote_ok", "enabled": "remote" in sources, "kind": "remote board"},
            {"id": "remotive", "enabled": False, "kind": "remote board"},
            {"id": "working_nomads", "enabled": False, "kind": "remote board"},
            {"id": "indeed", "enabled": "indeed" in sources, "kind": "aggregator"},
            {"id": "linkedin", "enabled": "linkedin" in sources, "kind": "aggregator"},
        ],
        "companies": [
            {
                "name": company["name"],
                "system": company["system"],
                "token": company["token"],
                "enabled": True,
            }
            for company in companies
        ],
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
    return (
        "Here is the search that will be saved:\n"
        f"  Job titles: {roles}\n"
        f"  Places: {'; '.join(places)}\n"
        f"{filter_line}{exclude_line}{extra_line}\n"
        f"  Results per search: {data['results_per_search']}\n"
        f"  Posted within days: {data['posted_within_days']}\n"
        f"  Websites: {', '.join(enabled) or 'none'}\n"
        f"  Companies: {company_line}"
    )


def ask_roles(io: IO) -> list[str]:
    while True:
        io.say("")
        io.say("Which job titles are you looking for?")
        io.say("Separate them with commas. Example: Project Manager, Product Manager")
        roles = split_csv(io.ask("> "))
        if roles:
            return roles
        io.say("Please type at least one job title. Example: Project Manager, Product Manager")


def ask_place(io: IO) -> dict:
    while True:
        io.say("")
        io.say("Which place should we search?")
        io.say("Type a city and a country, a country on its own, or Remote.")
        io.say("Examples: Berlin, Germany    Italy    Remote")
        io.say("For the US state of Georgia, type the city and United States.")
        parsed, problem = parse_place(io.ask("> "))
        if parsed is not None:
            if parsed["kind"] != "remote" and not parsed["indeed"]:
                io.say(
                    f"Indeed does not cover {parsed['label']}. "
                    "LinkedIn will be used for this search. Indeed will be left off."
                )
            return parsed
        if problem == "country":
            io.say(
                "That country was not recognised. Use the English name, "
                "such as Germany, Italy, Armenia, or United States."
            )
        else:
            io.say(
                "Type a city and a country separated by a comma, a country on its own, or Remote. "
                "Examples: Berlin, Germany    Italy    Remote"
            )


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


def ask_visa(io: IO) -> bool:
    io.say("")
    io.say("Do you need visa sponsorship?")
    io.say("Yes keeps jobs that offer sponsorship and jobs that do not say. It drops jobs that say they will not sponsor a visa.")
    io.say("This is guessed from the text, so it can be wrong.")
    return io.yes_no("Do you need visa sponsorship?", default=False)


def ask_exclude(io: IO) -> list[str]:
    io.say("")
    io.say("Words that should reject a job title (optional).")
    io.say("A job is dropped when the title contains one of these words on its own.")
    io.say("Example: senior, intern. The word intern does not reject internal.")
    io.say("Leave this blank to skip.")
    return split_csv(io.ask("> "))


def ask_sources(io: IO, indeed_ok: bool) -> set[str]:
    while True:
        io.say("")
        io.say("Which websites should we search?")
        io.say("Type the numbers, separated by commas. Press Enter for the usual choice: 1,2")
        for line in SOURCE_NOTES:
            io.say(line)
        if not indeed_ok:
            io.say("Indeed does not cover this country, so option 1 will be left off.")
        picked = parse_sources(io.ask("Your choice [1,2]: "))
        if not picked:
            io.say("Please type numbers from the list, like 1,2.")
            continue
        if not indeed_ok and "indeed" in picked:
            picked.discard("indeed")
            io.say("Indeed was left off because it does not cover this country.")
        if not picked:
            picked = {"linkedin"}
            io.say("LinkedIn will be used.")
        return picked


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


def ask_system(io: IO) -> str:
    io.say("")
    io.say("Which hiring system does that company use?")
    io.say("Look at the careers address and match it to one of these:")
    for line in SYSTEM_NOTES:
        io.say(line)
    known = ", ".join(KNOWN_SYSTEMS)
    while True:
        system = io.ask("Hiring system: ").strip().lower()
        if system in KNOWN_SYSTEMS:
            return system
        io.say(f"Please type one of: {known}.")


def ask_token(io: IO, system: str) -> str:
    io.say("")
    if system == "bendingspoons":
        io.say("Bending Spoons does not need a token. Press Enter.")
        io.ask("Token: ")
        return ""
    io.say("Public id from the careers address (token). This is not a password.")
    if system == "teamtailor":
        io.say("Paste the full https address of the jobs.rss feed.")
    else:
        io.say("Example: if the address ends in /acme, the token is acme.")
    while True:
        token = io.ask("Token: ").strip()
        if system == "teamtailor" and not token.startswith("http"):
            io.say("Teamtailor needs the full https address of the jobs RSS feed.")
            continue
        if token:
            return token
        io.say("Please type the public id from the careers address.")


def ask_companies(io: IO) -> list[dict]:
    companies: list[dict] = []
    io.say("")
    io.say("Company career pages are optional. Press Enter to skip.")
    while True:
        io.say("")
        io.say("Company name (or press Enter to skip):")
        name = io.ask("> ").strip()
        if not name:
            break
        system = ask_system(io)
        token = ask_token(io, system)
        companies.append({"name": name, "system": system, "token": token})
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
        visa_sponsorship = ask_visa(io)
        sources = ask_sources(io, indeed_ok)
        companies = ask_companies(io) if "company_pages" in sources else []
        if "company_pages" in sources and not companies:
            io.say("No companies were added, so company career pages will be left off.")
            sources.discard("company_pages")
        places = places_from(place, remote)
        sources = _finish_sources(io, sources, indeed_ok, places)
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
            visa_sponsorship=visa_sponsorship,
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
