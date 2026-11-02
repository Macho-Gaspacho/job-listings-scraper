"""Tests for reading config.yaml."""

from pathlib import Path

import pytest

from boards import filter_board_jobs
from config import load_config


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
roles:
  - Product Manager
  - PMO
locations:
  - name: Milan, Italy
    indeed_location: Milan, Lombardy, Italy
    linkedin_location: Milan, Lombardy, Italy
    remote: false
    distance_miles: 30
  - name: Remote
    indeed_location: Italy
    linkedin_location: Italy
    remote: true
sites:
  - indeed
  - linkedin
country: italy
results_per_search: 8
posted_within_days: 21
pause_seconds: 1.5
fetch_descriptions: false
snippet_characters: 120
require_title_match: true
title_keywords:
  Product Manager:
    - product manager
    - product owner
output:
  directory: output
  csv: jobs.csv
  excel: jobs.xlsx
  seen_file: data/seen_jobs.json
""",
        encoding="utf-8",
    )
    return path


def test_load_config_reads_roles_places_and_paths(tmp_path):
    settings = load_config(_write(tmp_path))
    assert settings.roles == ["Product Manager", "PMO"]
    assert settings.places[0].name == "Milan, Italy"
    assert settings.places[0].remote is False
    assert settings.places[0].distance_miles == 30
    assert settings.places[1].remote is True
    assert settings.sites == ["indeed", "linkedin"]
    assert settings.country == "italy"
    assert settings.results_per_search == 8
    assert settings.posted_within_days == 21
    assert settings.pause_seconds == 1.5
    assert settings.fetch_descriptions is False
    assert settings.snippet_characters == 120
    assert settings.require_title_match is True
    assert settings.title_keywords["Product Manager"] == [
        "product manager",
        "product owner",
    ]
    assert settings.output_dir == tmp_path / "output"
    assert settings.csv_path == tmp_path / "output" / "jobs.csv"
    assert settings.excel_path == tmp_path / "output" / "jobs.xlsx"
    assert settings.seen_file == tmp_path / "data" / "seen_jobs.json"


def test_load_config_rejects_an_empty_role_list(tmp_path):
    path = _write(tmp_path)
    path.write_text("roles: []\nlocations: []\nsites: [indeed]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="role"):
        load_config(path)


def test_load_config_reads_sources_and_companies(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
roles: [Product Manager]
locations:
  - name: Milan, Italy
    indeed_location: Milan
    linkedin_location: Milan
sources:
  - id: indeed
    enabled: false
    kind: aggregator
  - id: company_pages
    enabled: true
    kind: company site
  - id: remote_ok
    enabled: true
    kind: remote board
  - id: remotive
    enabled: false
    kind: remote board
companies:
  - name: Satispay
    system: ashby
    token: satispay
  - name: PayFit
    system: teamtailor
    token: https://careers.payfit.com/jobs.rss
    enabled: false
""",
        encoding="utf-8",
    )
    settings = load_config(path)
    assert settings.sites == []
    assert settings.company_pages_enabled is True
    assert settings.remote_boards == ["remote_ok"]
    assert settings.companies[0].name == "Satispay"
    assert settings.companies[0].system == "ashby"
    assert settings.companies[1].enabled is False


def test_load_config_rejects_an_unknown_site(tmp_path):
    path = _write(tmp_path)
    text = path.read_text(encoding="utf-8").replace("- indeed", "- not-a-site")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="not-a-site"):
        load_config(path)


def _places_config(tmp_path, body: str):
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_country_is_derived_from_the_first_office(tmp_path):
    path = _places_config(
        tmp_path,
        """
roles: [Software Engineer]
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
  - name: Remote
    indeed_location: Germany
    linkedin_location: Germany
    remote: true
sources:
  - id: indeed
    enabled: true
    kind: aggregator
""",
    )
    settings = load_config(path)
    assert settings.country == "germany"
    assert settings.location_rules.remote_regions[0] == "Germany"
    assert "Europe" in settings.location_rules.remote_regions


def test_country_aliases_are_accepted(tmp_path):
    path = _places_config(
        tmp_path,
        """
roles: [Designer]
locations:
  - name: Austin, United States
    indeed_location: Austin, TX
    linkedin_location: Austin, TX
sources:
  - id: indeed
    enabled: true
    kind: aggregator
country: United States
""",
    )
    assert load_config(path).country == "usa"


def test_missing_country_without_a_recognisable_place_raises(tmp_path):
    path = _places_config(
        tmp_path,
        """
roles: [Designer]
locations:
  - name: Remote
    indeed_location: Worldwide
    linkedin_location: Worldwide
    remote: true
sources:
  - id: indeed
    enabled: true
    kind: aggregator
""",
    )
    with pytest.raises(ValueError, match="does not set country"):
        load_config(path)


def test_unknown_country_raises_a_plain_message(tmp_path):
    path = _places_config(
        tmp_path,
        """
roles: [Designer]
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
sources:
  - id: indeed
    enabled: true
    kind: aggregator
country: narnia
""",
    )
    with pytest.raises(ValueError, match="narnia"):
        load_config(path)


def test_timezone_defaults_to_the_computer_zone(tmp_path):
    from regions import system_timezone_name

    path = _places_config(
        tmp_path,
        """
roles: [Designer]
locations:
  - name: Toronto, Canada
    indeed_location: Toronto, ON
    linkedin_location: Toronto, ON
sources:
  - id: indeed
    enabled: true
    kind: aggregator
""",
    )
    settings = load_config(path)
    assert settings.country == "canada"
    assert settings.timezone == system_timezone_name()


def test_timezone_can_be_set_and_rejects_a_fake_name(tmp_path):
    path = _places_config(
        tmp_path,
        """
roles: [Designer]
locations:
  - name: Austin, United States
    indeed_location: Austin, TX
    linkedin_location: Austin, TX
sources:
  - id: indeed
    enabled: true
    kind: aggregator
timezone: America/Chicago
""",
    )
    assert load_config(path).timezone == "America/Chicago"
    path.write_text(path.read_text(encoding="utf-8").replace("America/Chicago", "Not/AZone"), encoding="utf-8")
    with pytest.raises(ValueError, match="Not/AZone"):
        load_config(path)


def test_location_filter_and_remote_board_categories_are_read(tmp_path):
    path = _places_config(
        tmp_path,
        """
roles: [Designer]
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
sources:
  - id: we_work_remotely
    enabled: true
    kind: remote board
    categories:
      - product
      - https://weworkremotely.com/categories/remote-design-jobs.rss
location_filter:
  offices: ["Kreuzberg"]
  remote_regions: ["EU"]
  exclude_regions: ["UK only"]
""",
    )
    settings = load_config(path)
    assert settings.wwr_categories == (
        "product",
        "https://weworkremotely.com/categories/remote-design-jobs.rss",
    )
    assert settings.location_rules.offices == (("Berlin, Germany", ("Kreuzberg",)),)
    assert settings.location_rules.remote_regions == ("EU",)
    assert settings.location_rules.exclude_regions == ("UK only",)


def test_checked_in_examples_follow_their_own_cities():
    root = Path(__file__).resolve().parents[1]
    berlin = load_config(root / "examples" / "berlin-software-engineer.yaml")
    assert berlin.country == "germany"
    berlin_rows = filter_board_jobs(
        [
            {
                "title": "Software Engineer",
                "company": "A",
                "location": "Berlin, Germany",
                "is_remote": False,
                "url": "https://example.com/berlin",
                "description": "",
                "source": "Example",
            },
            {
                "title": "Software Engineer",
                "company": "A",
                "location": "Milan, Italy",
                "is_remote": False,
                "url": "https://example.com/milan",
                "description": "",
                "source": "Example",
            },
        ],
        berlin,
        "company site",
    )
    assert [row["place_searched"] for row in berlin_rows] == ["Berlin, Germany"]

    milan = load_config(root / "examples" / "milan-product-manager.yaml")
    assert milan.country == "italy"
    assert milan.wwr_categories == ("product", "sales-and-marketing", "management-and-finance")
    milan_rows = filter_board_jobs(
        [
            {
                "title": "Product Manager",
                "company": "A",
                "location": "Milano",
                "is_remote": False,
                "url": "https://example.com/milano",
                "description": "",
                "source": "Example",
            },
            {
                "title": "Product Manager",
                "company": "A",
                "location": "Remote - US only",
                "is_remote": True,
                "url": "https://example.com/us",
                "description": "",
                "source": "Example",
            },
        ],
        milan,
        "company site",
    )
    assert [row["url"] for row in milan_rows] == ["https://example.com/milano"]
    assert milan_rows[0]["place_searched"] == "Milan, Italy"


