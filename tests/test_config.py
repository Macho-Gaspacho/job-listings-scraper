"""Tests for reading config.yaml."""

from pathlib import Path

import pytest

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
