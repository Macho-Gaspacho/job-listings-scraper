"""Plain questions that write profile/cv_profile.yaml from what the person types.

Nothing here is an example fact. Empty answers skip that section.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from cv.profile import ProfileError, load_profile


_HEADER = (
    "# Facts typed into the CV interview.\n"
    "# The generator does not add employers, dates, or skills.\n\n"
)

_NO_WORK = frozenset(
    {
        "no",
        "nope",
        "none",
        "no work",
        "no work experience",
        "no work experience yet",
        "i have no work experience",
        "i don't have work experience",
        "i dont have work experience",
        "i don't have any work experience",
        "i dont have any work experience",
    }
)

_RATINGS = {
    "1": "A1",
    "2": "A2",
    "3": "B1",
    "4": "B2",
    "5": "C1",
    "6": "C2",
    "a few words": "A1",
    "simple conversations": "A2",
    "everyday conversations": "B1",
    "comfortable at work": "B2",
    "fluent": "C1",
    "native or near-native": "C2",
    "native": "C2",
    "a1": "A1",
    "a2": "A2",
    "b1": "B1",
    "b2": "B2",
    "c1": "C1",
    "c2": "C2",
}


class _Cancelled(Exception):
    """The person closed the questions before the profile was written."""


class _IO:
    def __init__(self, input_func, output) -> None:
        self.input_func = input_func
        self.output = output

    def say(self, text: str) -> None:
        self.output(text)

    def ask(self, prompt: str) -> str:
        try:
            return self.input_func(prompt)
        except EOFError as exc:
            raise _Cancelled() from exc


def run_interview(input_func, output, profile_path) -> int:
    """Write the profile. An existing file is kept unless the person says yes."""
    path = Path(profile_path)
    io = _IO(input_func, output)
    try:
        if path.is_file():
            answer = io.ask(
                f"A CV profile already exists at {path}. Overwrite it with new answers? (y/N) "
            )
            if answer.strip().lower() not in {"y", "yes"}:
                io.say("Left the existing profile unchanged.")
                return 0
        data = _collect(io)
    except _Cancelled:
        io.say("Stopped. Nothing was written.")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    path.write_text(_HEADER + dumped, encoding="utf-8")
    try:
        load_profile(path)
    except (OSError, ProfileError) as exc:
        path.unlink(missing_ok=True)
        io.say(str(exc))
        return 1
    io.say(f"Saved {path}")
    return 0


def _collect(io: _IO) -> dict:
    name = _require_name(io)
    email = io.ask("Email address (press Enter to skip): ").strip()
    phone = io.ask("Phone number (press Enter to skip): ").strip()
    city = io.ask("City where you live (press Enter to skip): ").strip()
    summary = io.ask("Short summary in your own words (press Enter to skip): ").strip()
    io.say("Paid work comes next. If you have none, type no work experience yet.")
    experience = _collect_roles(
        io,
        "Employer for paid work (press Enter to skip): ",
        "Job title (press Enter to skip): ",
        stop_on_no_work=True,
    )
    experience.extend(
        _collect_roles(
            io,
            "Organisation you volunteered with (press Enter to skip): ",
            "Volunteer role (press Enter to skip): ",
        )
    )
    experience.extend(_collect_projects(io))
    experience.extend(
        _collect_roles(
            io,
            "Who was the family or informal work for (press Enter to skip): ",
            "Short title for that work (press Enter to skip): ",
        )
    )
    return {
        "contact": {
            "full_name": name,
            "email": _kept(email),
            "phone": _kept(phone),
            "location": _kept(city),
        },
        "summary": _kept(summary),
        "photo": {"path": "", "include": False},
        "personal": {
            "include": False,
            "date_of_birth": "",
            "nationality": "",
            "marital_status": "",
        },
        "signature": {"include": False, "place": ""},
        "gdpr_consent": False,
        "references_on_request": False,
        "document_language": "en",
        "experience": experience,
        "education": _collect_studies(io),
        "skills": _collect_skills(io),
        "languages": _collect_languages(io),
        "certifications": _collect_certifications(io),
        "links": _collect_links(io),
    }


def _require_name(io: _IO) -> str:
    while True:
        name = io.ask("What is your full name? ").strip()
        if name and not _blank(name):
            return name
        io.say("A name is required. Everything else can be skipped.")


def _collect_roles(io: _IO, first_prompt: str, title_prompt: str, stop_on_no_work: bool = False):
    found = []
    while True:
        employer = io.ask(first_prompt).strip()
        if _blank(employer) or (stop_on_no_work and _no_work(employer)):
            break
        title = io.ask(title_prompt).strip()
        if _blank(title):
            io.say("That was left out because it needs a title.")
            continue
        item = _rest_of_role(io, employer, title)
        if item:
            found.append(item)
    return found


def _collect_projects(io: _IO) -> list:
    found = []
    while True:
        title = io.ask("School or university project name (press Enter to skip): ").strip()
        if _blank(title):
            break
        school = io.ask("School, university, or group (press Enter to skip): ").strip()
        if _blank(school):
            io.say("That project was left out because it needs the school or group.")
            continue
        item = _rest_of_role(io, school, title)
        if item:
            found.append(item)
    return found


def _rest_of_role(io: _IO, employer: str, title: str) -> dict | None:
    location = io.ask("Where was this (press Enter to skip): ").strip()
    start = io.ask("Start date (press Enter to skip): ").strip()
    end = io.ask("End date, or present if this is current (press Enter to skip): ").strip()
    io.say("Type one fact about what you did. Press Enter on a blank line when you are finished.")
    bullets = []
    while True:
        fact = io.ask("Fact (press Enter to skip): ").strip()
        if _blank(fact):
            break
        bullets.append(fact)
    if not bullets:
        io.say("That was left out because it needs one fact you did.")
        return None
    return {
        "employer": employer,
        "title": title,
        "location": _kept(location),
        "start": _kept(start),
        "end": _kept(end),
        "bullets": bullets,
    }


def _collect_studies(io: _IO) -> list:
    found = []
    while True:
        institution = io.ask("School, college, or university (press Enter to skip): ").strip()
        if _blank(institution):
            break
        degree = io.ask("Qualification (press Enter to skip): ").strip()
        field = io.ask("Subject (press Enter to skip): ").strip()
        start = io.ask("Start date (press Enter to skip): ").strip()
        end = io.ask("End date, or present if this is current (press Enter to skip): ").strip()
        found.append(
            {
                "institution": institution,
                "degree": _kept(degree),
                "field": _kept(field),
                "start": _kept(start),
                "end": _kept(end),
            }
        )
    return found


def _collect_skills(io: _IO) -> list:
    found = []
    while True:
        name = io.ask("A skill you have (press Enter to skip): ").strip()
        if _blank(name):
            break
        evidence = io.ask("Where did you use it (press Enter to skip): ").strip()
        found.append({"name": name, "evidence": _kept(evidence)})
    return found


def _collect_languages(io: _IO) -> list:
    found = []
    while True:
        name = io.ask("A language you use (press Enter to skip): ").strip()
        if _blank(name):
            break
        io.say("  1. A few words")
        io.say("  2. Simple conversations")
        io.say("  3. Everyday conversations")
        io.say("  4. Comfortable at work")
        io.say("  5. Fluent")
        io.say("  6. Native or near-native")
        level = _rating(io)
        if not level:
            io.say("That language was left out because it needs a rating.")
            continue
        found.append({"name": name, "level": level})
    return found


def _rating(io: _IO) -> str:
    while True:
        raw = io.ask("How well do you use it? Type 1 to 6, or press Enter to skip: ").strip()
        if _blank(raw):
            return ""
        level = _RATINGS.get(" ".join(raw.casefold().split()))
        if level:
            return level
        io.say("Type a number from 1 to 6.")


def _collect_certifications(io: _IO) -> list:
    found = []
    while True:
        name = io.ask("Certificate or licence name (press Enter to skip): ").strip()
        if _blank(name):
            break
        issuer = io.ask("Who issued it (press Enter to skip): ").strip()
        when = io.ask("Date (press Enter to skip): ").strip()
        found.append({"name": name, "issuer": _kept(issuer), "date": _kept(when)})
    return found


def _collect_links(io: _IO) -> list:
    found = []
    while True:
        label = io.ask("Link label (press Enter to skip): ").strip()
        if _blank(label):
            break
        url = io.ask("Link address (press Enter to skip): ").strip()
        if _blank(url):
            io.say("That link was left out because it needs an address.")
            continue
        found.append({"label": label, "url": url})
    return found


def _blank(value: str) -> bool:
    text = value.strip().casefold()
    return text in {"", "skip"}


def _kept(value: str) -> str:
    if _blank(value):
        return ""
    return value.strip()


def _no_work(value: str) -> bool:
    return " ".join(value.casefold().split()) in _NO_WORK
