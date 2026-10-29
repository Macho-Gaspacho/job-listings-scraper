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


HEADER = """# Created by the setup wizard.
# To change this search, run:  python scrape.py --setup
# You can also edit this file, then run:  python scrape.py

"""

# Country names Indeed accepts. Kept here so the wizard can check an answer
# without importing the job-board library.
INDEED_COUNTRIES = {
    "argentina",
    "australia",
    "austria",
    "bahrain",
    "belgium",
    "brazil",
    "canada",
    "chile",
    "china",
    "colombia",
    "costa rica",
    "czech republic",
    "denmark",
    "ecuador",
    "egypt",
    "finland",
    "france",
    "germany",
    "greece",
    "hong kong",
    "hungary",
    "india",
    "indonesia",
    "ireland",
    "israel",
    "italy",
    "japan",
    "kuwait",
    "luxembourg",
    "malaysia",
    "mexico",
    "morocco",
    "netherlands",
    "new zealand",
    "nigeria",
    "norway",
    "oman",
    "pakistan",
    "panama",
    "peru",
    "philippines",
    "poland",
    "portugal",
    "qatar",
    "romania",
    "saudi arabia",
    "singapore",
    "south africa",
    "south korea",
    "spain",
    "sweden",
    "switzerland",
    "taiwan",
    "thailand",
    "türkiye",
    "ukraine",
    "united arab emirates",
    "uk",
    "usa",
    "uruguay",
    "venezuela",
    "vietnam",
}

COUNTRY_ALIASES = {
    "czechia": "czech republic",
    "turkey": "türkiye",
    "uae": "united arab emirates",
    "united kingdom": "uk",
    "u.k.": "uk",
    "great britain": "uk",
    "britain": "uk",
    "england": "uk",
    "scotland": "uk",
    "wales": "uk",
    "us": "usa",
    "u.s.": "usa",
    "u.s.a.": "usa",
    "united states": "usa",
    "united states of america": "usa",
    "america": "usa",
    "italia": "italy",
    "deutschland": "germany",
    "espana": "spain",
    "españa": "spain",
    "holland": "netherlands",
    "the netherlands": "netherlands",
}

SOURCE_NOTES = (
    "  1. Indeed — a large job board. A good default for most cities.",
    "  2. LinkedIn — public job posts. A long run can be slow, and LinkedIn sometimes blocks it.",
    "  3. Remote boards — We Work Remotely and Remote OK. Useful for remote jobs.",
    "     These boards still keep Milan offices or remote roles open in Europe.",
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


def split_csv(raw: str) -> list[str]:
    seen: list[str] = []
    folded = {item.lower() for item in seen}
    for part in raw.split(","):
        text = " ".join(part.strip().split())
        if text and text.lower() not in folded:
            seen.append(text)
            folded.add(text.lower())
    return seen


def country_code(name: str) -> str | None:
    text = " ".join(name.strip().lower().split())
    text = COUNTRY_ALIASES.get(text, text)
    if text in INDEED_COUNTRIES:
        return text
    return None


def parse_place(raw: str) -> tuple[tuple[str, str, str] | None, str | None]:
    """Return ((location, country code, country label), error kind)."""
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) < 2:
        return None, "comma"
    label = parts[-1]
    code = country_code(label)
    if code is None:
        return None, "country"
    return (", ".join(parts), code, label), None


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


def keywords_for(roles: list[str], extras: list[str]) -> dict[str, list[str]]:
    """Phrases a title must contain.

    Extra words replace the job title as the filter, so the title has to
    contain one of them. With no extras, the job title itself is the filter.
    The scraper keeps a title when it contains any one of these phrases.
    """
    table: dict[str, list[str]] = {}
    for role in roles:
        source = extras or [role]
        phrases: list[str] = []
        for phrase in source:
            lowered = phrase.strip().lower()
            if lowered and lowered not in phrases:
                phrases.append(lowered)
        table[role] = phrases
    return table


def build_config(
    roles: list[str],
    location_name: str,
    country: str,
    remote_where: str | None,
    extras: list[str],
    sources: set[str],
    companies: list[dict],
) -> dict:
    places = [
        {
            "name": location_name,
            "indeed_location": location_name,
            "linkedin_location": location_name,
            "remote": False,
            "distance_miles": 30,
        }
    ]
    if remote_where:
        places.append(
            {
                "name": "Remote",
                "indeed_location": remote_where,
                "linkedin_location": remote_where,
                "remote": True,
            }
        )
    use_companies = "company_pages" in sources and bool(companies)
    return {
        "roles": roles,
        "require_title_match": True,
        "title_keywords": keywords_for(roles, extras),
        "locations": places,
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
        "results_per_search": 10,
        "posted_within_days": 30,
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


def summary_text(data: dict) -> str:
    roles = ", ".join(data["roles"])
    places = []
    for place in data["locations"]:
        if place.get("remote"):
            places.append(f"remote in {place['indeed_location']}")
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
    words = []
    for phrases in data["title_keywords"].values():
        for phrase in phrases:
            if phrase not in words:
                words.append(phrase)
    return (
        "Here is the search that will be saved:\n"
        f"  Job titles: {roles}\n"
        f"  Places: {'; '.join(places)}\n"
        f"  A title must contain one of: {', '.join(words)}\n"
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


def ask_place(io: IO) -> tuple[str, str, str]:
    while True:
        io.say("")
        io.say("Which city and country?")
        io.say("Example: Berlin, Germany")
        parsed, problem = parse_place(io.ask("> "))
        if parsed is not None:
            return parsed
        if problem == "country":
            io.say(
                "That country is not in Indeed's list. Use the English name, "
                "such as Germany, France, Italy, United States, or United Kingdom."
            )
        else:
            io.say(
                "Please type a city and a country, separated by a comma. "
                "Example: Berlin, Germany"
            )


def ask_remote(io: IO, country_label: str) -> str | None:
    io.say("")
    io.say("Also include remote jobs?")
    io.say("Remote means a job you can do from home.")
    if not io.yes_no("Include remote jobs?", default=True):
        return None
    io.say("")
    io.say("Remote jobs in which country or region?")
    io.say(f"Press Enter to use {country_label}.")
    raw = io.ask("> ").strip()
    return raw or country_label


def ask_keywords(io: IO) -> list[str]:
    io.say("")
    io.say("Extra words that must appear in the job title (optional).")
    io.say("Leave this blank to keep jobs whose title contains the job title you typed.")
    io.say("Or type words, separated by commas. Example: senior, lead")
    io.say("A job is then kept only when its title contains one of those words.")
    return split_csv(io.ask("> "))


def ask_sources(io: IO) -> set[str]:
    while True:
        io.say("")
        io.say("Which websites should we search?")
        io.say("Type the numbers, separated by commas. Press Enter for the usual choice: 1,2")
        for line in SOURCE_NOTES:
            io.say(line)
        picked = parse_sources(io.ask("Your choice [1,2]: "))
        if picked:
            return picked
        io.say("Please type numbers from the list, like 1,2.")


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


def _ask_and_save(path: Path, io: IO, run_search) -> int:
    io.say("Answer a few questions. This writes config.yaml for your job search.")
    io.say("You do not need to edit any code. Press Enter to accept a choice shown in [brackets].")
    while True:
        roles = ask_roles(io)
        location_name, country, country_label = ask_place(io)
        remote_where = ask_remote(io, country_label)
        extras = ask_keywords(io)
        sources = ask_sources(io)
        companies = ask_companies(io) if "company_pages" in sources else []
        if "company_pages" in sources and not companies:
            io.say("No companies were added, so company career pages will be left off.")
            sources.discard("company_pages")
        if not sources:
            io.say("Indeed and LinkedIn will be used, because no other website was selected.")
            sources = {"indeed", "linkedin"}
        data = build_config(
            roles,
            location_name,
            country,
            remote_where,
            extras,
            sources,
            companies,
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
            io.say("Not searching yet. When you are ready, run: python scrape.py")
            return 0
        io.say("Starting the search. Leave this window open.")
        if run_search is None:
            import scrape

            return int(scrape.main(["--config", str(path)]))
        return int(run_search(path))


def main(argv: list[str] | None = None) -> int:
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


if __name__ == "__main__":
    sys.exit(main())
