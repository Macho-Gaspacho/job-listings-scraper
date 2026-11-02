"""Tests for public career-page and job-board parsers. No network calls."""

import pytest

from boards import (
    filter_board_jobs,
    parse_bending_spoons,
    parse_greenhouse,
    parse_remote_ok,
    parse_we_work_remotely,
    we_work_remotely_feed_urls,
)
from config import load_config


def _settings(tmp_path, body):
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return load_config(path)


def _search(name, indeed, country, remote_where):
    remote = ""
    if remote_where:
        remote = f"""
  - name: Remote
    indeed_location: {remote_where}
    linkedin_location: {remote_where}
    remote: true
"""
    return f"""
roles: [Product Manager]
require_title_match: true
title_keywords:
  Product Manager: [product manager]
locations:
  - name: {name}
    indeed_location: {indeed}
    linkedin_location: {indeed}
{remote}country: {country}
sources:
  - id: indeed
    enabled: true
    kind: aggregator
"""


_USERS = {
    "berlin": ("Berlin, Germany", "Berlin, Germany", "germany", "Germany"),
    "austin": ("Austin, United States", "Austin, TX", "usa", "United States"),
    "london": ("London, UK", "London, United Kingdom", "uk", "United Kingdom"),
    "toronto": ("Toronto, Canada", "Toronto, ON", "canada", "Canada"),
}

_BOARD_JOBS = [
    ("berlin-office", "Berlin, Germany", False),
    ("milan-office", "Milan, Italy", False),
    ("remote-de", "Remote - Germany", True),
    ("remote-us-only", "Remote - US only", True),
    ("remote-usa", "Remote - USA", True),
    ("remote-eu", "Remote (EU only)", True),
    ("nyc", "New York, NY", False),
    ("austin", "Austin, TX", False),
    ("london", "London, UK", False),
    ("toronto", "Toronto, Canada", False),
    ("engineer", "Berlin, Germany", False),
]

_EXPECTED = {
    "berlin": {
        "berlin-office": "Berlin, Germany",
        "remote-de": "Remote",
        "remote-eu": "Remote",
    },
    "austin": {
        "austin": "Austin, United States",
        "remote-usa": "Remote",
        "remote-us-only": "Remote",
    },
    "london": {"london": "London, UK"},
    "toronto": {"toronto": "Toronto, Canada"},
}


def _jobs():
    rows = []
    for key, location, is_remote in _BOARD_JOBS:
        title = "Backend Engineer" if key == "engineer" else "Product Manager"
        rows.append(
            {
                "title": title,
                "company": "Example",
                "location": location,
                "is_remote": is_remote,
                "date_posted": "2026-10-01",
                "url": f"https://example.com/{key}",
                "description": "A role.",
                "source": "Example careers",
            }
        )
    return rows


@pytest.mark.parametrize("user", ["berlin", "austin", "london", "toronto"])
def test_filter_board_jobs_follows_each_users_places(tmp_path, user):
    settings = _settings(tmp_path, _search(*_USERS[user]))
    rows = filter_board_jobs(_jobs(), settings, "company site")
    found = {row["url"].rsplit("/", 1)[-1]: row["place_searched"] for row in rows}
    assert found == _EXPECTED[user]


def test_greenhouse_keeps_the_matching_office_and_the_snippet(tmp_path):
    settings = _settings(tmp_path, _search(*_USERS["berlin"]))
    jobs = parse_greenhouse(
        {
            "jobs": [
                {
                    "title": "Product Manager",
                    "absolute_url": "https://job-boards.greenhouse.io/example/jobs/1",
                    "location": {"name": "Berlin, Germany"},
                    "updated_at": "2026-10-01T00:00:00Z",
                    "content": "<p>Own the payments roadmap.</p>",
                },
                {
                    "title": "Backend Engineer",
                    "absolute_url": "https://job-boards.greenhouse.io/example/jobs/2",
                    "location": {"name": "Berlin, Germany"},
                    "content": "Build APIs.",
                },
                {
                    "title": "Product Manager",
                    "absolute_url": "https://job-boards.greenhouse.io/example/jobs/3",
                    "location": {"name": "Milan, Italy"},
                    "content": "Office job.",
                },
            ]
        },
        "Example",
    )
    rows = filter_board_jobs(jobs, settings, "company site")
    assert len(rows) == 1
    assert rows[0]["title"] == "Product Manager"
    assert rows[0]["place_searched"] == "Berlin, Germany"
    assert rows[0]["source_type"] == "company site"
    assert rows[0]["source"] == "Example careers"
    assert rows[0]["description"] == "Own the payments roadmap."
    assert rows[0]["date_posted"] == "2026-10-01"


def test_bending_spoons_uses_the_same_place_rules(tmp_path):
    page = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"list":[
      {"id":"milan-job","jobTitle":"Product manager","highLevelDescription":"<p>Office role.</p>",
       "availableAsRemoteInDefaultCountries": false,
       "officeLocations":[{"title":"Milan (Italy)","country":{"name":"Italy","euMember":true}}]},
      {"id":"berlin-job","jobTitle":"Product manager","highLevelDescription":"<p>Office role.</p>",
       "availableAsRemoteInDefaultCountries": false,
       "officeLocations":[{"title":"Berlin (Germany)","country":{"name":"Germany","euMember":true}}]},
      {"id":"us-job","jobTitle":"Product manager","highLevelDescription":"US only",
       "availableAsRemoteInDefaultCountries": false,
       "officeLocations":[{"title":"New York (NY)","country":{"name":"United States","euMember":false}}]}
    ]}}}
    </script>
    """
    parsed = parse_bending_spoons(page)
    assert [job["is_remote"] for job in parsed] == [False, False, False]
    assert "Milan" not in parsed[1]["location"]
    milan = _settings(tmp_path, _search("Milan, Italy", "Milan, Lombardy, Italy", "italy", "Italy"))
    kept = filter_board_jobs(parsed, milan, "company site")
    assert [row["url"] for row in kept] == ["https://jobs.bendingspoons.com/positions/milan-job"]
    assert kept[0]["place_searched"] == "Milan, Italy"
    berlin = _settings(tmp_path, _search(*_USERS["berlin"]))
    kept = filter_board_jobs(parsed, berlin, "company site")
    assert [row["url"] for row in kept] == ["https://jobs.bendingspoons.com/positions/berlin-job"]
    assert kept[0]["place_searched"] == "Berlin, Germany"


def test_remote_feeds_follow_the_users_country(tmp_path):
    settings = _settings(tmp_path, _search(*_USERS["berlin"]))
    rss = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Upsun: Product Manager</title>
        <region>Anywhere in the World</region>
        <link>https://weworkremotely.com/jobs/1</link>
        <pubDate>Wed, 21 Oct 2026 12:00:00 +0000</pubDate>
        <description>Work from Europe.</description>
      </item>
      <item>
        <title>Maven: Product Manager</title>
        <region>Anywhere in the World</region>
        <link>https://weworkremotely.com/jobs/2</link>
        <description>Headquarters: Remote, US</description>
      </item>
    </channel></rss>
    """
    rows = filter_board_jobs(
        parse_we_work_remotely(rss.encode()),
        settings,
        "remote board",
        check_region_text=True,
    )
    assert [row["company"] for row in rows] == ["Upsun"]
    assert rows[0]["source_type"] == "remote board"
    assert rows[0]["date_posted"] == "2026-10-21"

    remote_ok = parse_remote_ok(
        [
            {"legal": "notice"},
            {
                "position": "Product Manager",
                "company": "Spiralyze",
                "location": "Worldwide",
                "epoch": 1761004800,
                "url": "https://remoteok.com/jobs/1",
                "description": "Remote product work.",
            },
            {
                "position": "Product Manager",
                "company": "Local",
                "location": "Melbourne",
                "url": "https://remoteok.com/jobs/2",
                "description": "Australia.",
            },
        ]
    )
    kept = filter_board_jobs(remote_ok, settings, "remote board", check_region_text=True)
    assert [row["company"] for row in kept] == ["Spiralyze"]

    blank = parse_remote_ok(
        [
            {
                "position": "Product Manager",
                "company": "Unspecified",
                "location": "",
                "url": "https://remoteok.com/jobs/3",
                "description": "Remote product work.",
            }
        ]
    )
    blank_rows = filter_board_jobs(blank, settings, "remote board", check_region_text=True)
    assert blank_rows[0]["place_searched"] == "Remote"
    assert blank_rows[0]["remote_scope"] == "unspecified"

    described = parse_we_work_remotely(
        """<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Acme: Product Manager</title>
            <region>Anywhere in the World</region>
            <link>https://weworkremotely.com/jobs/3</link>
            <description>Bonus only for top performers. This is remote user research.</description>
          </item>
          <item>
            <title>Other: Product Manager</title>
            <region>Anywhere in the World</region>
            <link>https://weworkremotely.com/jobs/4</link>
            <description>Headquarters: Remote, US</description>
          </item>
        </channel></rss>
        """.encode()
    )
    described_rows = filter_board_jobs(described, settings, "remote board", check_region_text=True)
    assert [row["company"] for row in described_rows] == ["Acme"]
    austin = _settings(tmp_path, _search(*_USERS["austin"]))
    austin_rows = filter_board_jobs(described, austin, "remote board", check_region_text=True)
    assert {row["company"] for row in austin_rows} == {"Acme", "Other"}


def test_we_work_remotely_feed_urls_default_to_the_all_jobs_feed():
    assert we_work_remotely_feed_urls(None) == ("https://weworkremotely.com/remote-jobs.rss",)
    assert we_work_remotely_feed_urls(()) == ("https://weworkremotely.com/remote-jobs.rss",)
    assert we_work_remotely_feed_urls(("product", "https://example.com/jobs.rss")) == (
        "https://weworkremotely.com/categories/remote-product-jobs.rss",
        "https://example.com/jobs.rss",
    )
