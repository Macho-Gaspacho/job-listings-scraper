"""Tests for public career-page and job-board parsers. No network calls."""

from boards import (
    filter_board_jobs,
    parse_bending_spoons,
    parse_greenhouse,
    parse_remote_ok,
    parse_we_work_remotely,
)
from config import load_config


def _settings(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
roles:
  - Product Manager
locations:
  - name: Milan, Italy
    indeed_location: Milan
    linkedin_location: Milan
sites: [indeed]
require_title_match: true
title_keywords:
  Product Manager:
    - product manager
""",
        encoding="utf-8",
    )
    return load_config(path)


def test_greenhouse_keeps_a_milan_product_manager_and_drops_a_paris_engineer(tmp_path):
    settings = _settings(tmp_path)
    jobs = parse_greenhouse(
        {
            "jobs": [
                {
                    "title": "Product Manager",
                    "absolute_url": "https://job-boards.greenhouse.io/satispay/jobs/1",
                    "location": {"name": "Milan, Italy"},
                    "updated_at": "2026-10-01T00:00:00Z",
                    "content": "<p>Own the payments roadmap.</p>",
                },
                {
                    "title": "Backend Engineer",
                    "absolute_url": "https://job-boards.greenhouse.io/satispay/jobs/2",
                    "location": {"name": "Milan, Italy"},
                    "content": "Build APIs.",
                },
                {
                    "title": "Product Manager",
                    "absolute_url": "https://job-boards.greenhouse.io/example/jobs/3",
                    "location": {"name": "Paris, France"},
                    "content": "Office job.",
                },
            ]
        },
        "Satispay",
    )
    rows = filter_board_jobs(jobs, settings, "company site")
    assert len(rows) == 1
    assert rows[0]["title"] == "Product Manager"
    assert rows[0]["place_searched"] == "Milan, Italy"
    assert rows[0]["source_type"] == "company site"
    assert rows[0]["source"] == "Satispay careers"
    assert rows[0]["description"] == "Own the payments roadmap."
    assert rows[0]["date_posted"] == "2026-10-01"


def test_bending_spoons_keeps_the_milan_role_and_drops_the_us_role(tmp_path):
    settings = _settings(tmp_path)
    page = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"list":[
      {"id":"milan-job","jobTitle":"Product manager","highLevelDescription":"<p>Milan product.</p>",
       "availableAsRemoteInDefaultCountries": false,
       "officeLocations":[{"title":"Milan (Italy)","country":{"name":"Italy","euMember":true}}]},
      {"id":"us-job","jobTitle":"Product manager, US","highLevelDescription":"US only",
       "availableAsRemoteInDefaultCountries": false,
       "officeLocations":[{"title":"New York (NY)","country":{"name":"United States","euMember":false}}]}
    ]}}}
    </script>
    """
    rows = filter_board_jobs(parse_bending_spoons(page), settings, "company site")
    assert [row["url"] for row in rows] == ["https://jobs.bendingspoons.com/positions/milan-job"]
    assert rows[0]["place_searched"] == "Milan, Italy"


def test_remote_feeds_drop_us_only_roles(tmp_path):
    settings = _settings(tmp_path)
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
