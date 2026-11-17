"""Arbeitnow parsing and the Berlin location rules. No network."""

import json
from pathlib import Path

from boards import fetch_arbeitnow, filter_board_jobs, parse_arbeitnow
from config import load_config


_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "arbeitnow.json"


def _payload() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _settings(tmp_path, remote: bool):
    remote_block = ""
    if remote:
        remote_block = """
  - name: Remote
    indeed_location: Germany
    linkedin_location: Germany
    remote: true
"""
    body = f"""
roles: [Software Engineer]
require_title_match: true
title_keywords:
  Software Engineer: [software engineer]
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
    remote: false
{remote_block}country: germany
sources:
  - id: arbeitnow
    enabled: true
    kind: job board
"""
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return load_config(path)


def test_parse_arbeitnow_fields():
    rows = parse_arbeitnow(_payload())
    assert [row["company"] for row in rows] == ["Acme", "Beta", "Gamma"]
    assert rows[0]["title"] == "Software Engineer"
    assert rows[0]["location"] == "Berlin"
    assert rows[0]["is_remote"] is False
    assert rows[0]["url"] == "https://www.arbeitnow.com/jobs/berlin"
    assert rows[0]["source"] == "arbeitnow"
    assert rows[0]["date_posted"] == "2025-11-15"
    assert rows[0]["description"] == "Build APIs in Berlin."
    assert rows[2]["is_remote"] is True
    assert "<" not in rows[0]["description"]


def test_berlin_search_keeps_berlin_and_not_munich(tmp_path):
    settings = _settings(tmp_path, remote=False)
    kept = filter_board_jobs(parse_arbeitnow(_payload()), settings, "job board")
    companies = [row["company"] for row in kept]
    assert "Acme" in companies
    assert "Beta" not in companies
    assert kept[0]["source_type"] == "job board"
    assert kept[0]["source"] == "arbeitnow"
    assert kept[0]["place_searched"] == "Berlin, Germany"


def test_remote_row_stays_when_the_search_includes_remote(tmp_path):
    # Germany's location rules already keep a generic "Remote" row, because
    # the default remote regions include worldwide. Adding a remote place
    # keeps that row as well. Munich stays out either way.
    without = _settings(tmp_path, remote=False)
    with_remote = _settings(tmp_path, remote=True)
    for settings in (without, with_remote):
        companies = [
            row["company"]
            for row in filter_board_jobs(parse_arbeitnow(_payload()), settings, "job board")
        ]
        assert "Gamma" in companies
        assert "Beta" not in companies


def test_fetch_stops_on_a_null_next_link_and_waits_between_pages():
    pages = {
        1: {"data": [{"title": "One", "company_name": "A", "location": "Berlin", "remote": False,
                      "url": "https://example.com/1", "created_at": 1763222400, "description": "x"}],
            "links": {"next": "https://www.arbeitnow.com/api/job-board-api?page=2"}},
        2: {"data": [], "links": {"next": "https://www.arbeitnow.com/api/job-board-api?page=3"}},
    }
    calls = []
    waits = []

    def getter(url: str) -> bytes:
        calls.append(url)
        page = 1 if "page=1" in url else 2
        return json.dumps(pages[page]).encode("utf-8")

    rows = fetch_arbeitnow(getter, sleep=waits.append)
    assert [row["title"] for row in rows] == ["One"]
    assert len(calls) == 2
    assert waits == [1]
