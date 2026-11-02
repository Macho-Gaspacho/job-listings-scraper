"""Optional config filters. Missing salary or job type does not drop a row."""

from pathlib import Path

import pytest

from boards import filter_board_jobs
from config import Filters, Place, Settings, load_config
from enrichment import passes_filters
from listings import row_from_hit
from scrape import collect_listings
from sources import build_search


def _filters(**overrides) -> Filters:
    values = dict(
        job_types=(),
        levels=(),
        min_salary=None,
        exclude_title_words=(),
        exclude_if_language_required=(),
        only_visa_sponsorship=False,
    )
    values.update(overrides)
    return Filters(**values)


def _row(**overrides):
    base = {
        "title": "Software Engineer",
        "company": "Acme",
        "location": "Berlin",
        "salary": "",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "",
        "salary_period": "",
        "job_type": "",
        "is_remote": "Unknown",
        "level": "Unknown",
        "languages": "",
        "visa": "Unknown",
    }
    base.update(overrides)
    return base


def test_min_salary_keeps_unknown_pay_and_compares_known_yearly_amounts():
    rules = _filters(min_salary=30000)
    kept = _row(salary_min=40000, salary_max=50000, salary_currency="EUR", salary_period="yearly")
    low = _row(salary_min=25000, salary_max=28000, salary_currency="USD", salary_period="yearly")
    pounds = _row(salary_min=10, salary_max=12, salary_currency="GBP", salary_period="hourly")
    zloty = _row(salary_min=8000, salary_max=9000, salary_currency="PLN", salary_period="monthly")
    blank = _row()
    no_period = _row(salary_min=1000, salary_max=2000, salary_currency="EUR", salary_period="")
    assert passes_filters(kept, rules) is True
    assert passes_filters(low, rules) is False
    assert passes_filters(pounds, rules) is False
    assert passes_filters(zloty, rules) is True
    assert passes_filters(blank, rules) is True
    assert passes_filters(no_period, rules) is True


def test_hourly_and_monthly_pay_is_converted_before_the_yearly_minimum():
    rules = _filters(min_salary=30000)
    hourly = _row(salary_min=20, salary_currency="USD", salary_period="hourly")
    monthly = _row(salary_min=2500, salary_currency="EUR", salary_period="monthly")
    weekly = _row(salary_min=400, salary_currency="GBP", salary_period="weekly")
    assert passes_filters(hourly, rules) is True
    assert passes_filters(monthly, rules) is True
    assert passes_filters(weekly, rules) is False


def test_unknown_job_type_and_level_are_kept_until_the_user_names_them():
    types = _filters(job_types=("Full-time", "Internship"))
    assert passes_filters(_row(job_type="Full-time"), types) is True
    assert passes_filters(_row(job_type="Part-time"), types) is False
    assert passes_filters(_row(job_type=""), types) is True
    levels = _filters(levels=("Entry", "Unknown"))
    assert passes_filters(_row(level="Entry"), levels) is True
    assert passes_filters(_row(level="Unknown"), levels) is True
    assert passes_filters(_row(level="Senior"), levels) is False
    entry_only = _filters(levels=("Entry",))
    assert passes_filters(_row(level="Unknown"), entry_only) is False


def test_title_words_languages_and_visa_filters():
    words = _filters(exclude_title_words=("senior", "lead"))
    assert passes_filters(_row(title="Senior Engineer"), words) is False
    assert passes_filters(_row(title="Lead Designer"), words) is False
    assert passes_filters(_row(title="Internal Engineer"), words) is True
    languages = _filters(exclude_if_language_required=("German",))
    assert passes_filters(_row(languages="German"), languages) is False
    assert passes_filters(_row(languages="German, English"), languages) is False
    assert passes_filters(_row(languages="Dutch"), languages) is True
    assert passes_filters(_row(languages="Spanish"), languages) is True
    assert passes_filters(_row(languages=""), languages) is True
    visa = _filters(only_visa_sponsorship=True)
    assert passes_filters(_row(visa="No sponsorship (guessed from the text)"), visa) is False
    assert passes_filters(_row(visa="Sponsorship offered (guessed from the text)"), visa) is True
    assert passes_filters(_row(visa="Unknown"), visa) is True
    assert passes_filters(_row(visa="No sponsorship (guessed from the text)"), _filters()) is True


def test_load_config_reads_optional_filters(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
roles: [Nurse]
locations:
  - name: Warsaw, Poland
    indeed_location: Warsaw, Poland
    linkedin_location: Warsaw, Poland
country: poland
sources:
  - id: indeed
    enabled: true
    kind: aggregator
filters:
  job_types: [full-time, internship]
  levels: [entry, unknown]
  min_salary: 30000
  exclude_title_words: [senior, lead]
  exclude_if_language_required: [German, Dutch]
  only_visa_sponsorship: false
""",
        encoding="utf-8",
    )
    settings = load_config(path)
    assert settings.filters.job_types == ("Full-time", "Internship")
    assert settings.filters.levels == ("Entry", "Unknown")
    assert settings.filters.min_salary == 30000
    assert settings.filters.exclude_title_words == ("senior", "lead")
    assert settings.filters.exclude_if_language_required == ("German", "Dutch")
    assert settings.filters.only_visa_sponsorship is False


def test_load_config_without_filters_drops_nothing_for_missing_fields(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
roles: [Teacher]
locations:
  - name: Madrid, Spain
    indeed_location: Madrid, Spain
    linkedin_location: Madrid, Spain
country: spain
sources:
  - id: linkedin
    enabled: true
    kind: aggregator
""",
        encoding="utf-8",
    )
    settings = load_config(path)
    assert passes_filters(_row(), settings.filters) is True


def test_load_config_rejects_an_unknown_job_type(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
roles: [Teacher]
locations:
  - name: Rome, Italy
    indeed_location: Rome, Italy
    linkedin_location: Rome, Italy
country: italy
sources:
  - id: indeed
    enabled: true
    kind: aggregator
filters:
  job_types: [seasonal]
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="job type"):
        load_config(path)


def _settings(**overrides):
    place = Place(
        name="Berlin, Germany",
        indeed_location="Berlin, Germany",
        linkedin_location="Berlin, Germany",
        remote=False,
    )
    remote = Place(
        name="Remote",
        indeed_location="Germany",
        linkedin_location="Germany",
        remote=True,
    )
    values = dict(
        roles=["Engineer"],
        places=[place, remote],
        sites=["indeed", "linkedin"],
        country="germany",
        results_per_search=5,
        posted_within_days=14,
        pause_seconds=0,
        fetch_descriptions=False,
        snippet_characters=80,
        output_dir=Path("output"),
        csv_path=Path("output/jobs.csv"),
        excel_path=Path("output/jobs.xlsx"),
        seen_file=Path("data/seen_jobs.json"),
        filters=_filters(job_types=("Full-time",)),
    )
    values.update(overrides)
    return Settings(**values)


def test_indeed_gets_one_job_type_and_linkedin_does_not():
    settings = _settings()
    indeed = build_search(settings, "Engineer", settings.places[0], "indeed")
    linkedin = build_search(settings, "Engineer", settings.places[0], "linkedin")
    assert indeed["job_type"] == "fulltime"
    assert "job_type" not in linkedin
    remote = build_search(settings, "Engineer", settings.places[1], "indeed")
    assert remote["is_remote"] is True
    assert remote["job_type"] == "fulltime"
    several = _settings(filters=_filters(job_types=("Full-time", "Internship")))
    mixed = build_search(several, "Engineer", several.places[0], "indeed")
    assert "job_type" not in mixed


def test_collect_listings_applies_filters_and_keeps_unknown_salary(tmp_path):
    settings = _settings(
        filters=_filters(min_salary=30000, job_types=("Full-time",)),
        places=[_settings().places[0]],
        sites=["indeed"],
    )

    def fetch(role, place, site):
        paid = row_from_hit(
            {
                "title": "Engineer",
                "company": "Paid",
                "location": "Berlin",
                "job_url": "https://example.com/paid",
                "description": "Work.",
                "min_amount": 40000,
                "max_amount": 50000,
                "currency": "EUR",
                "interval": "yearly",
                "job_type": "fulltime",
                "site": site,
            },
            role,
            place.name,
            80,
        )
        low = row_from_hit(
            {
                "title": "Engineer",
                "company": "Low",
                "location": "Berlin",
                "job_url": "https://example.com/low",
                "description": "Work.",
                "min_amount": 20000,
                "max_amount": 25000,
                "currency": "EUR",
                "interval": "yearly",
                "job_type": "fulltime",
                "site": site,
            },
            role,
            place.name,
            80,
        )
        unknown = row_from_hit(
            {
                "title": "Engineer",
                "company": "Unknown pay",
                "location": "Berlin",
                "job_url": "https://example.com/unknown",
                "description": "Work.",
                "job_type": "fulltime",
                "site": site,
            },
            role,
            place.name,
            80,
        )
        part_time = row_from_hit(
            {
                "title": "Engineer",
                "company": "Part",
                "location": "Berlin",
                "job_url": "https://example.com/part",
                "description": "Work.",
                "job_type": "parttime",
                "site": site,
            },
            role,
            place.name,
            80,
        )
        return [paid, low, unknown, part_time]

    rows, failures = collect_listings(settings, fetch, pause=lambda _seconds: None)
    assert failures == 0
    assert sorted(row["company"] for row in rows) == ["Paid", "Unknown pay"]


def test_board_rows_are_filtered_with_the_same_rules(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
roles: [Engineer]
require_title_match: true
title_keywords:
  Engineer: [engineer]
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
country: germany
sources:
  - id: company_pages
    enabled: true
    kind: company site
filters:
  levels: [Entry, Unknown]
  exclude_if_language_required: [German]
  only_visa_sponsorship: true
""",
        encoding="utf-8",
    )
    settings = load_config(path)
    jobs = [
        {
            "title": "Engineer",
            "company": "Open",
            "location": "Berlin, Germany",
            "is_remote": False,
            "url": "https://example.com/open",
            "description": "Visa sponsorship available.",
            "source": "Open careers",
        },
        {
            "title": "Senior Engineer",
            "company": "Senior",
            "location": "Berlin, Germany",
            "is_remote": False,
            "url": "https://example.com/senior",
            "description": "Lead the team.",
            "source": "Senior careers",
        },
        {
            "title": "Engineer",
            "company": "German required",
            "location": "Berlin, Germany",
            "is_remote": False,
            "url": "https://example.com/de",
            "description": "You are fluent German.",
            "source": "DE careers",
        },
        {
            "title": "Engineer",
            "company": "No visa",
            "location": "Berlin, Germany",
            "is_remote": False,
            "url": "https://example.com/visa",
            "description": "We offer no visa sponsorship.",
            "source": "Visa careers",
        },
    ]
    rows = filter_board_jobs(jobs, settings, "company site")
    assert [row["company"] for row in rows] == ["Open"]
