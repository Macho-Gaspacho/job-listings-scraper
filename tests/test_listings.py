"""Tests for cleaning, deduplicating, and flagging job listings."""

from datetime import date

import pytest

from config import Place
from listings import (
    apply_new_flags,
    classify_place,
    company_name_key,
    dedupe,
    excluded_region,
    listing_key,
    row_from_hit,
    snippet,
    sort_rows,
    title_is_relevant,
)
from regions import build_location_rules, canonical_country


def test_snippet_strips_html_and_collapses_whitespace():
    raw = "<p>Lead  the   research.</p>\n<p>Talk to customers.</p>"
    assert snippet(raw, 200) == "Lead the research. Talk to customers."


def test_snippet_turns_markdown_links_into_plain_text():
    raw = "See the [team page](https://example.com/team) for details."
    assert snippet(raw, 200) == "See the team page for details."


def test_snippet_trims_on_a_word_boundary():
    raw = "one two three four five"
    assert snippet(raw, 14) == "one two three…"


def test_snippet_of_empty_values_is_blank():
    assert snippet(None, 50) == ""
    assert snippet("   ", 50) == ""
    assert snippet(float("nan"), 50) == ""


def test_row_from_hit_maps_jobspy_fields():
    row = row_from_hit(
        {
            "title": " Product Manager ",
            "company": "Prada",
            "location": "Milano, LOM, Italy",
            "date_posted": date(2026, 10, 20),
            "site": "indeed",
            "job_url": "https://it.indeed.com/viewjob?jk=abc",
            "description": "<p>Own the roadmap.</p>",
        },
        role="Product Manager",
        place="Milan, Italy",
        snippet_characters=80,
    )
    assert row["title"] == "Product Manager"
    assert row["company"] == "Prada"
    assert row["location"] == "Milano, LOM, Italy"
    assert row["date_posted"] == "2026-10-20"
    assert row["source"] == "indeed"
    assert row["url"] == "https://it.indeed.com/viewjob?jk=abc"
    assert row["description"] == "Own the roadmap."
    assert row["role_searched"] == "Product Manager"
    assert row["place_searched"] == "Milan, Italy"


def test_row_from_hit_drops_a_posting_with_no_title():
    assert row_from_hit({"company": "Prada"}, "PM", "Milan", 80) is None


def test_listing_key_prefers_the_url_and_ignores_tracking_fragments():
    left = listing_key({"url": "https://it.indeed.com/viewjob?jk=ABC/", "title": "A"})
    right = listing_key(
        {"url": "https://it.indeed.com/viewjob?jk=abc#apply", "title": "B"}
    )
    assert left == right


def test_listing_key_falls_back_to_title_company_and_location():
    key = listing_key(
        {"title": "PMO  Lead", "company": "ACME", "location": "Milan", "url": ""}
    )
    assert key == "text:pmo lead|acme|milan"


def test_dedupe_merges_the_same_link_found_by_two_roles():
    rows = [
        {
            "title": "PMO",
            "company": "ACME",
            "location": "Milan",
            "date_posted": "2026-10-01",
            "source": "indeed",
            "url": "https://it.indeed.com/viewjob?jk=1",
            "description": "Short.",
            "role_searched": "PMO",
            "place_searched": "Milan, Italy",
        },
        {
            "title": "PMO",
            "company": "ACME",
            "location": "Milan",
            "date_posted": "2026-10-01",
            "source": "indeed",
            "url": "https://it.indeed.com/viewjob?jk=1",
            "description": "A longer description of the same job.",
            "role_searched": "Project Manager",
            "place_searched": "Remote",
        },
    ]
    kept = dedupe(rows)
    assert len(kept) == 1
    assert kept[0]["role_searched"] == "PMO; Project Manager"
    assert kept[0]["place_searched"] == "Milan, Italy; Remote"
    assert kept[0]["description"] == "A longer description of the same job."


def test_dedupe_prefers_the_company_site_when_the_title_and_company_match():
    rows = [
        {
            "title": "Product Manager",
            "company": "Satispay S.r.l.",
            "location": "Milan",
            "date_posted": "2026-10-01",
            "source": "indeed",
            "source_type": "aggregator",
            "url": "https://it.indeed.com/viewjob?jk=1",
            "description": "From Indeed.",
            "role_searched": "Product Manager",
            "place_searched": "Milan, Italy",
        },
        {
            "title": "Product Manager",
            "company": "Satispay",
            "location": "Milan, Italy",
            "date_posted": "2026-10-02",
            "source": "Satispay careers",
            "source_type": "company site",
            "url": "https://jobs.ashbyhq.com/satispay/1",
            "description": "Apply on the company site.",
            "role_searched": "Product Manager",
            "place_searched": "Milan, Italy",
        },
    ]
    kept = dedupe(rows)
    assert len(kept) == 1
    assert kept[0]["url"] == "https://jobs.ashbyhq.com/satispay/1"
    assert kept[0]["source_type"] == "company site"
    assert "indeed" in kept[0]["source"]
    assert "Satispay careers" in kept[0]["source"]
    assert company_name_key("Satispay S.r.l.") == "satispay"


def test_same_title_and_company_is_not_new_if_another_link_was_saved():
    rows = dedupe(
        [
            {
                "title": "Product Manager",
                "company": "Satispay",
                "location": "Milan",
                "source": "indeed",
                "source_type": "aggregator",
                "url": "https://it.indeed.com/viewjob?jk=9",
                "description": "",
                "role_searched": "Product Manager",
                "place_searched": "Milan, Italy",
                "date_posted": "",
            },
            {
                "title": "Product Manager",
                "company": "Satispay",
                "location": "Milan",
                "source": "Satispay careers",
                "source_type": "company site",
                "url": "https://jobs.ashbyhq.com/satispay/9",
                "description": "",
                "role_searched": "Product Manager",
                "place_searched": "Milan, Italy",
                "date_posted": "",
            },
        ]
    )
    seen = {"url:https://it.indeed.com/viewjob?jk=9"}
    flagged = apply_new_flags(rows, seen)
    assert flagged[0]["is_new"] == "no"
    assert flagged[0]["source_type"] == "company site"


def _rules(country, places):
    built = [
        Place(
            name=name,
            indeed_location=indeed,
            linkedin_location=indeed,
            remote=remote,
        )
        for name, indeed, remote in places
    ]
    return build_location_rules(built, canonical_country(country), None)


_PROFILES = {
    "milan": (
        "italy",
        [
            ("Milan, Italy", "Milan, Lombardy, Italy", False),
            ("Remote", "Italy", True),
        ],
    ),
    "berlin": (
        "germany",
        [
            ("Berlin, Germany", "Berlin, Germany", False),
            ("Remote", "Germany", True),
        ],
    ),
    "austin": (
        "usa",
        [
            ("Austin, United States", "Austin, TX", False),
            ("Remote", "United States", True),
        ],
    ),
    "london": (
        "uk",
        [
            ("London, UK", "London, United Kingdom", False),
            ("Remote", "United Kingdom", True),
        ],
    ),
    "toronto": (
        "canada",
        [
            ("Toronto, Canada", "Toronto, ON", False),
            ("Remote", "Canada", True),
        ],
    ),
    "remote": ("germany", [("Remote", "Germany", True)]),
}


@pytest.mark.parametrize(
    ("user", "location", "is_remote", "expected"),
    [
        ("milan", "Milan, Italy", False, "Milan, Italy"),
        ("milan", "Milano, Milan, Italy", False, "Milan, Italy"),
        ("milan", "Paris", False, None),
        ("milan", "Paris", True, None),
        ("milan", "Remote - Italy", True, "Remote"),
        ("milan", "Remote - US only", True, None),
        ("milan", "Anywhere in the World", True, "Remote"),
        ("milan", "United States", True, None),
        ("milan", "London", True, None),
        ("milan", "Remote", False, "Remote"),
        ("milan", "Europe, USA", True, "Remote"),
        ("milan", "Finland", True, None),
        ("milan", "", True, "Remote"),
        ("berlin", "Berlin, Germany", False, "Berlin, Germany"),
        ("berlin", "Milan, Italy", False, None),
        ("berlin", "Remote - Germany", True, "Remote"),
        ("berlin", "Remote - US only", True, None),
        ("berlin", "Remote (EU only)", True, "Remote"),
        ("austin", "Austin, TX", False, "Austin, United States"),
        ("austin", "New York, NY", False, None),
        ("austin", "Remote - USA", True, "Remote"),
        ("austin", "Remote (EU only)", True, None),
        ("austin", "Remote - US only", True, "Remote"),
        ("london", "London, UK", False, "London, UK"),
        ("london", "Berlin, Germany", False, None),
        ("toronto", "Toronto, Canada", False, "Toronto, Canada"),
        ("toronto", "Vancouver, BC", False, None),
        ("remote", "Berlin, Germany", False, None),
        ("remote", "Remote - Germany", True, "Remote"),
        ("remote", "Remote - US only", True, None),
        ("remote", "", True, "Remote"),
    ],
)
def test_classify_place_follows_the_configured_places(user, location, is_remote, expected):
    rules = _rules(*_PROFILES[user])
    assert classify_place(location, is_remote, rules) == expected


@pytest.mark.parametrize(
    ("text", "excluded"),
    [
        ("Bonus only for top performers", False),
        ("remote user research", False),
        ("Remote - US only", True),
        ("Headquarters: Remote, US", True),
        ("based in the united states only", True),
        ("Remote - Germany", False),
        ("Remote (EU only)", False),
    ],
)
def test_excluded_region_uses_whole_phrases_for_a_germany_search(text, excluded):
    rules = _rules(*_PROFILES["berlin"])
    assert excluded_region(text, rules) is excluded


def test_excluded_region_keeps_the_users_own_country_limit():
    austin = _rules(*_PROFILES["austin"])
    assert excluded_region("Remote - US only", austin) is False
    assert excluded_region("Remote (EU only)", austin) is True


def test_dedupe_keeps_different_jobs_at_the_same_company():
    rows = [
        {
            "title": "Product Manager",
            "company": "Satispay",
            "location": "Milan",
            "source": "linkedin",
            "url": "https://www.linkedin.com/jobs/view/1",
            "description": "",
            "role_searched": "Product Manager",
            "place_searched": "Milan, Italy",
            "date_posted": "",
        },
        {
            "title": "Senior Product Manager",
            "company": "Satispay",
            "location": "Milan",
            "source": "linkedin",
            "url": "https://www.linkedin.com/jobs/view/2",
            "description": "",
            "role_searched": "Product Manager",
            "place_searched": "Milan, Italy",
            "date_posted": "",
        },
    ]
    assert len(dedupe(rows)) == 2


def test_apply_new_flags_marks_only_unseen_listings():
    rows = [
        {"url": "https://example.com/old", "title": "Old", "company": "", "location": ""},
        {"url": "https://example.com/new", "title": "New", "company": "", "location": ""},
    ]
    seen = {listing_key(rows[0])}
    flagged = apply_new_flags(rows, seen)
    assert flagged[0]["is_new"] == "no"
    assert flagged[1]["is_new"] == "yes"


def test_title_match_ignores_capital_letters_and_extra_words():
    phrases = ["product manager", "product owner"]
    assert title_is_relevant("Senior Product Manager", phrases)
    assert title_is_relevant("PRODUCT OWNER (Milan)", phrases)
    assert not title_is_relevant("Strategy Associate", phrases)
    assert title_is_relevant("Anything", [])


def test_sort_puts_new_jobs_first_and_newest_dates_above_older_ones():
    rows = [
        {"is_new": "no", "date_posted": "2026-10-20", "title": "old-recent"},
        {"is_new": "yes", "date_posted": "2026-10-01", "title": "new-older"},
        {"is_new": "yes", "date_posted": "2026-10-18", "title": "new-newer"},
        {"is_new": "yes", "date_posted": "", "title": "new-undated"},
    ]
    titles = [row["title"] for row in sort_rows(rows)]
    assert titles == ["new-newer", "new-older", "new-undated", "old-recent"]
