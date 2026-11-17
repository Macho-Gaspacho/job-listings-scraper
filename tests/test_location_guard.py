"""Indeed and LinkedIn rows from another country are dropped. Other sources are not."""

import pytest

from config import Place, Settings
from scrape import collect_listings


_CASES = [
    ("italy", "Milan, Italy", "Milan, Lombardy, Italy", True),
    ("italy", "Milan, Italy", "Milano", True),
    ("italy", "Milan, Italy", "", True),
    ("italy", "Milan, Italy", "Milano, TX", False),
    ("italy", "Milan, Italy", "Milan, TN", False),
    ("italy", "Milan, Italy", "Austin, Texas, United States", False),
    ("italy", "Milan, Italy", "Lugano, Switzerland", False),
    ("germany", "Berlin, Germany", "Berlin, Berlin, Germany", True),
    ("germany", "Berlin, Germany", "Frankfurt, Hesse, DE", True),
    ("germany", "Berlin, Germany", "Frankfort, KY", False),
    ("usa", "Austin, United States", "Austin, TX", True),
    ("netherlands", "Amsterdam, Netherlands", "Amsterdam, North Holland, Netherlands", True),
    ("netherlands", "Amsterdam, Netherlands", "Amsterdam, NY", False),
]


def _settings(tmp_path, country: str, place_name: str, remote: bool = False) -> Settings:
    return Settings(
        roles=["Analyst"],
        places=[
            Place(
                name=place_name,
                indeed_location=place_name,
                linkedin_location=place_name,
                remote=remote,
            )
        ],
        sites=["indeed"],
        country=country,
        results_per_search=5,
        posted_within_days=14,
        pause_seconds=0,
        fetch_descriptions=False,
        snippet_characters=80,
        output_dir=tmp_path,
        csv_path=tmp_path / "jobs.csv",
        excel_path=tmp_path / "jobs.xlsx",
        seen_file=tmp_path / "seen.json",
        require_title_match=False,
    )


def _fetch(location: str):
    def fetch(_role, _place, site):
        return [
            {
                "title": "Analyst",
                "company": "ACME",
                "location": location,
                "date_posted": "2026-11-01",
                "source": site,
                "source_type": "aggregator",
                "url": "https://example.test/job",
                "description": "",
            }
        ]

    return fetch


@pytest.mark.parametrize(("country", "place_name", "location", "kept"), _CASES)
def test_aggregator_location_guard(tmp_path, capsys, country, place_name, location, kept):
    rows, failures = collect_listings(
        _settings(tmp_path, country, place_name),
        _fetch(location),
        pause=lambda _seconds: None,
    )
    output = capsys.readouterr().out
    assert failures == 0
    assert (len(rows) == 1) is kept
    if kept:
        assert "dropped as another country" not in output
    else:
        assert "1 dropped as another country" in output


def test_remote_place_keeps_rows_the_office_guard_would_drop(tmp_path, capsys):
    rows, failures = collect_listings(
        _settings(tmp_path, "italy", "Remote", remote=True),
        _fetch("Milano, TX"),
        pause=lambda _seconds: None,
    )
    assert failures == 0
    assert len(rows) == 1
    assert "dropped as another country" not in capsys.readouterr().out
