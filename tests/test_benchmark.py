"""Offline checks for the benchmark counts. Nothing here contacts a job site."""

import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest

import setup_wizard
from benchmarks.run_benchmark import load_spec, main, measure


def _query(query_id: str) -> dict:
    for query in load_spec()["queries"]:
        if query["id"] == query_id:
            return query
    raise AssertionError(query_id)


def _row(title, location, source, source_type):
    return {
        "title": title,
        "location": location,
        "source": source,
        "source_type": source_type,
    }


_Q3 = "q3_product_manager_milano_italia"
_Q1 = "q1_data_analyst_amsterdam"
_Q7 = "q7_data_scientist_remote_eu"


@pytest.mark.parametrize(
    ("rows", "query_id", "expected"),
    [
        (
            [_row("Product Manager", "Milan, Lombardy, Italy", "linkedin", "aggregator")],
            _Q3,
            {"total": 1, "relevant_in_sample": "1/1", "wrong_country": 0, "aggregators_%": 100},
        ),
        (
            [_row("Product Manager", "Milano, TX", "linkedin", "aggregator")],
            _Q3,
            {"relevant_in_sample": "0/1", "wrong_country": 1},
        ),
        (
            [_row("Senior Product Owner", "", "greenhouse", "company site")],
            _Q3,
            {"relevant_in_sample": "1/1", "company_pages_%": 100},
        ),
        (
            [_row("Data Analyst", "Amsterdam, North Holland, Netherlands", "indeed", "aggregator")],
            _Q1,
            {"relevant_in_sample": "1/1"},
        ),
        (
            [_row("Warehouse Associate", "Amsterdam", "indeed", "aggregator")],
            _Q1,
            {"relevant_in_sample": "0/1", "wrong_country": 0},
        ),
        (
            [_row("Data Scientist", "Remote - EMEA", "remotive", "remote board")],
            _Q7,
            {"relevant_in_sample": "1/1"},
        ),
        (
            [_row("Data Scientist", "Remote - US only", "remotive", "remote board")],
            _Q7,
            {"relevant_in_sample": "0/1"},
        ),
    ],
)
def test_measure_counts_relevance_and_country(rows, query_id, expected):
    stats = measure(rows, _query(query_id), sample_size=20)
    for key, value in expected.items():
        assert stats[key] == value


def test_http_429_is_blocked_and_the_run_exits_zero(tmp_path):
    def fetch(_role, _place, site):
        if site == "linkedin":
            raise HTTPError(
                "https://www.linkedin.com/jobs",
                429,
                "Too Many Requests",
                Message(),
                None,
            )
        return [
            {
                "title": "Data Analyst",
                "company": "ACME",
                "location": "Amsterdam, Netherlands",
                "date_posted": "2026-11-01",
                "source": site,
                "source_type": "aggregator",
                "url": "https://example.test/analyst",
                "description": "Numbers.",
            }
        ]

    code = main(
        ["--label", "blocked429", "--only", _Q1],
        results_root=tmp_path,
        fetch=fetch,
    )
    saved = json.loads((tmp_path / "blocked429" / "summary.json").read_text(encoding="utf-8"))
    assert code == 0
    assert saved[0]["status"] == "ok"
    assert "linkedin" in saved[0]["blocked"]
    assert saved[0]["total"] == 1


def test_value_error_is_recorded_and_the_run_continues(tmp_path):
    def fetch(_role, _place, site):
        if site == "indeed":
            raise ValueError("not a block")
        return []

    code = main(
        ["--label", "valueerr", "--only", _Q1],
        results_root=tmp_path,
        fetch=fetch,
    )
    saved = json.loads((tmp_path / "valueerr" / "summary.json").read_text(encoding="utf-8"))
    assert code == 0
    assert "indeed:ValueError" in saved[0]["errors"]


def test_unparsed_place_is_rejected_without_searching(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_wizard, "parse_place", lambda _raw: (None, "city"))
    called = []

    def fetch(*args):
        called.append(args)
        return []

    code = main(
        ["--label", "rejected", "--only", "q9_awkward_russian_title_city_only"],
        results_root=tmp_path,
        fetch=fetch,
    )
    saved = json.loads((tmp_path / "rejected" / "summary.json").read_text(encoding="utf-8"))
    assert code == 0
    assert saved[0]["status"].startswith("place_rejected:")
    assert saved[0]["total"] == 0
    assert called == []


def test_runner_does_not_touch_the_users_seen_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sentinel = tmp_path / "data" / "seen_jobs.json"
    sentinel.parent.mkdir()
    original = '{"seen_keys": ["keep"]}\n'
    sentinel.write_text(original, encoding="utf-8")
    project_seen = Path(__file__).resolve().parents[1] / "data" / "seen_jobs.json"
    project_before = project_seen.read_bytes() if project_seen.exists() else None

    def fetch(_role, _place, site):
        return [
            {
                "title": "Data Analyst",
                "company": "ACME",
                "location": "Amsterdam, Netherlands",
                "date_posted": "2026-11-01",
                "source": site,
                "source_type": "aggregator",
                "url": f"https://example.test/{site}",
                "description": "Numbers.",
            }
        ]

    code = main(
        ["--label", "seen", "--only", _Q1],
        results_root=tmp_path / "bench",
        fetch=fetch,
    )
    assert code == 0
    assert sentinel.read_text(encoding="utf-8") == original
    if project_before is None:
        assert not project_seen.exists()
    else:
        assert project_seen.read_bytes() == project_before
    raw_seen = tmp_path / "bench" / "seen" / "raw" / _Q1 / "seen_jobs.json"
    assert raw_seen.is_file()
