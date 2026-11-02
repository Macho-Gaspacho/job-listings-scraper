"""Salary, job type, level, language, and visa fields. No network."""

import pytest

from boards import (
    parse_ashby,
    parse_greenhouse,
    parse_lever,
    parse_remote_ok,
    parse_teamtailor,
    parse_workable,
)
from listings import row_from_hit


def _hit(**overrides):
    base = {
        "title": "Software Engineer",
        "company": "Acme",
        "location": "Berlin, Germany",
        "site": "indeed",
        "job_url": "https://example.com/jobs/1",
        "description": "Build software.",
    }
    base.update(overrides)
    return base


def _row(**overrides):
    limit = overrides.pop("snippet_characters", 80)
    return row_from_hit(_hit(**overrides), role="Engineer", place="Berlin", snippet_characters=limit)


def test_row_from_hit_formats_a_yearly_euro_range():
    row = _row(min_amount=40000, max_amount=50000, currency="EUR", interval="yearly")
    assert row["salary"] == "40,000–50,000 EUR/year"
    assert row["salary_min"] == 40000
    assert row["salary_max"] == 50000
    assert row["salary_currency"] == "EUR"
    assert row["salary_period"] == "yearly"


@pytest.mark.parametrize(
    ("amounts", "currency", "interval", "expected"),
    [
        ((45000, 45000), "GBP", "yearly", "45,000 GBP/year"),
        ((20, 25), "USD", "hourly", "20–25 USD/hour"),
        ((8000, 10000), "PLN", "monthly", "8,000–10,000 PLN/month"),
        ((40000, None), "EUR", "yearly", "40,000 EUR/year"),
        ((None, None), "EUR", "yearly", ""),
    ],
)
def test_salary_format_covers_several_currencies(amounts, currency, interval, expected):
    low, high = amounts
    row = _row(min_amount=low, max_amount=high, currency=currency, interval=interval)
    assert row["salary"] == expected


def test_missing_salary_and_remote_stay_blank_or_unknown():
    row = _row(is_remote=None)
    assert row["salary"] == ""
    assert row["salary_min"] is None
    assert row["is_remote"] == "Unknown"
    assert row["job_type"] == ""
    assert row["level"] == "Unknown"
    assert row["languages"] == ""
    assert row["visa"] == "Unknown"


def test_remote_and_job_type_are_normalised():
    row = _row(is_remote=True, job_type="fulltime")
    assert row["is_remote"] == "Yes"
    office = _row(is_remote=False, job_type="parttime, contract")
    assert office["is_remote"] == "No"
    assert office["job_type"] == "Part-time, Contract"


@pytest.mark.parametrize(
    ("title", "level"),
    [
        ("Software Engineer Intern", "Entry"),
        ("Junior Data Analyst", "Entry"),
        ("Graduate Scheme", "Entry"),
        ("Entry Level Nurse", "Entry"),
        ("Stagista marketing", "Entry"),
        ("Praktikant Softwareentwicklung", "Entry"),
        ("Stagiaire data", "Entry"),
        ("Becario de ventas", "Entry"),
        ("Werkstudent IT", "Entry"),
        ("Stażysta finansów", "Entry"),
        ("Stagiair finance", "Entry"),
        ("Senior Product Manager", "Senior"),
        ("Lead Designer", "Senior"),
        ("Principal Engineer", "Senior"),
        ("Head of Marketing", "Senior"),
        ("Software Engineer", "Unknown"),
        ("Internal Communications", "Unknown"),
    ],
)
def test_level_is_inferred_from_title_words_in_several_languages(title, level):
    assert _row(title=title)["level"] == level


def test_linkedin_job_level_wins_over_the_title():
    assert _row(title="Software Engineer", job_level="Entry level")["level"] == "Entry"
    assert _row(title="Nurse", job_level="Mid-Senior level")["level"] == "Senior"
    assert _row(title="Junior Nurse", job_level="Associate")["level"] == "Entry"


def test_a_title_that_says_both_entry_and_senior_stays_unknown():
    assert _row(title="Senior Intern")["level"] == "Unknown"


@pytest.mark.parametrize(
    ("description", "languages"),
    [
        ("Must be fluent German and happy to travel.", "German"),
        ("Wir brauchen Deutsch fließend im Team.", "German"),
        ("Cerchiamo italiano madrelingua per il supporto.", "Italian"),
        ("Nous demandons un français courant à l'écrit.", "French"),
        ("Je spreekt vloeiend Nederlands met klanten.", "Dutch"),
        ("Se requiere español nativo para la tienda.", "Spanish"),
        ("Wymagany biegły język polski.", "Polish"),
        ("É preciso português fluente no atendimento.", "Portuguese"),
        ("Native English is required for this desk.", "English"),
        ("Build the roadmap with the team.", ""),
    ],
)
def test_required_languages_are_guessed_from_several_languages(description, languages):
    row = _row(description=description)
    assert row["languages"] == languages


def test_language_is_read_past_the_spreadsheet_snippet():
    filler = "word " * 80
    row = _row(description=filler + "Must be fluent German.", snippet_characters=40)
    assert row["languages"] == "German"
    assert len(row["description"]) <= 40
    assert "German" not in row["description"]


@pytest.mark.parametrize(
    ("description", "visa"),
    [
        ("We offer no visa sponsorship for this role.", "No sponsorship (guessed from the text)"),
        ("Applicants must have the right to work in Germany.", "No sponsorship (guessed from the text)"),
        ("Visa sponsorship available for the right person.", "Sponsorship offered (guessed from the text)"),
        ("Relocation support is part of the package.", "Sponsorship offered (guessed from the text)"),
        ("Geen visumsponsoring voor deze functie.", "No sponsorship (guessed from the text)"),
        ("Ofrecemos patrocinio de visado.", "Sponsorship offered (guessed from the text)"),
        ("Nie oferujemy sponsorowania wizy.", "No sponsorship (guessed from the text)"),
        ("A quiet office in the city centre.", "Unknown"),
    ],
)
def test_visa_wording_is_guessed_and_labelled(description, visa):
    assert _row(description=description)["visa"] == visa


def test_conflicting_visa_sentences_stay_unknown():
    text = "Visa sponsorship available. Applicants must have the right to work."
    assert _row(description=text)["visa"] == "Unknown"


def test_greenhouse_uses_first_published_and_employment_metadata():
    jobs = parse_greenhouse(
        {
            "jobs": [
                {
                    "title": "Nurse",
                    "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
                    "location": {"name": "Madrid, Spain"},
                    "first_published": "2026-01-15T00:00:00Z",
                    "updated_at": "2026-03-01T00:00:00Z",
                    "content": "<p>Ward work.</p>",
                    "metadata": [{"name": "Employment Type", "value": "Full-time"}],
                }
            ]
        },
        "Acme",
    )
    assert jobs[0]["date_posted"] == "2026-01-15T00:00:00Z"
    row = row_from_hit(
        {**jobs[0], "job_url": jobs[0]["url"]},
        role="Nurse",
        place="Madrid",
        snippet_characters=80,
    )
    assert row["date_posted"] == "2026-01-15"
    assert row["job_type"] == "Full-time"


def test_lever_ashby_and_workable_job_types():
    lever = parse_lever(
        [
            {
                "text": "Stagiaire",
                "categories": {"commitment": "Internship", "location": "Paris"},
                "hostedUrl": "https://jobs.lever.co/acme/1",
            }
        ],
        "Acme",
    )
    ashby = parse_ashby(
        {
            "jobs": [
                {
                    "title": "Engineer",
                    "employmentType": "FullTime",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                    "isListed": True,
                }
            ]
        },
        "Acme",
    )
    workable = parse_workable(
        {
            "jobs": [
                {
                    "title": "Analyst",
                    "employment_type": "part_time",
                    "city": "Amsterdam",
                    "country": "Netherlands",
                    "url": "https://apply.workable.com/acme/1",
                }
            ]
        },
        "Acme",
    )
    assert lever[0]["job_type"] == "Internship"
    assert ashby[0]["job_type"] == "Full-time"
    assert workable[0]["job_type"] == "Part-time"


def test_remote_ok_keeps_salary_numbers():
    jobs = parse_remote_ok(
        [
            {"legal": "notice"},
            {
                "position": "Engineer",
                "company": "Acme",
                "salary_min": 60000,
                "salary_max": 80000,
                "url": "https://remoteok.com/jobs/1",
                "description": "Remote work.",
            },
        ]
    )
    row = row_from_hit(jobs[0], role="Engineer", place="Remote", snippet_characters=80)
    assert row["salary_min"] == 60000
    assert row["salary_max"] == 80000
    assert row["salary"] == "60,000–80,000"


def test_teamtailor_never_uses_the_title_as_the_location():
    body = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Verpleegkundige Amsterdam</title>
        <link>https://careers.example.com/jobs/1</link>
        <description>Werk in het ziekenhuis.</description>
      </item>
      <item>
        <title>Engineer</title>
        <link>https://careers.example.com/jobs/2</link>
        <description>Build things.</description>
        <location>Warsaw, Poland</location>
      </item>
    </channel></rss>
    """.encode()
    jobs = parse_teamtailor(body, "Acme")
    assert jobs[0]["location"] == ""
    assert jobs[0]["title"] == "Verpleegkundige Amsterdam"
    assert jobs[1]["location"] == "Warsaw, Poland"
