"""Tests for search settings and for continuing when one site fails."""

from config import Place, Settings
from scrape import collect_listings
from sources import build_search, fetch_listings, take_records


def _settings(**overrides):
    values = dict(
        roles=["Product Manager"],
        places=[
            Place(
                name="Milan, Italy",
                indeed_location="Milan, Lombardy, Italy",
                linkedin_location="Milan, Lombardy, Italy",
                remote=False,
                distance_miles=30,
            ),
            Place(
                name="Remote",
                indeed_location="Italy",
                linkedin_location="Italy",
                remote=True,
                distance_miles=None,
            ),
        ],
        sites=["indeed", "linkedin"],
        country="italy",
        results_per_search=8,
        posted_within_days=30,
        pause_seconds=9,
        fetch_descriptions=True,
        snippet_characters=280,
        output_dir=None,
        csv_path=None,
        excel_path=None,
        seen_file=None,
    )
    values.update(overrides)
    return Settings(**values)


def test_build_search_for_milan_on_indeed():
    settings = _settings()
    query = build_search(settings, "Product Manager", settings.places[0], "indeed")
    assert query["site_name"] == ["indeed"]
    assert query["search_term"] == "Product Manager"
    assert query["location"] == "Milan, Lombardy, Italy"
    assert query["country_indeed"] == "italy"
    assert query["distance"] == 30
    assert query["hours_old"] == 720
    assert query["results_wanted"] == 8
    assert query["verbose"] is None
    assert "is_remote" not in query
    assert query["fetch_description"] is False


def test_build_search_for_remote_jobs():
    settings = _settings()
    indeed = build_search(settings, "PMO", settings.places[1], "indeed")
    linkedin = build_search(settings, "PMO", settings.places[1], "linkedin")
    assert indeed["is_remote"] is True
    assert indeed["location"] == "Italy"
    assert linkedin["search_term"] == "PMO remote"
    assert linkedin["location"] == "Italy"
    assert linkedin["fetch_description"] is True
    assert "distance" not in linkedin


def test_indeed_country_follows_the_city_when_the_file_names_one():
    settings = _settings(country="netherlands")
    berlin = Place(
        name="Berlin, Germany",
        indeed_location="Berlin, Germany",
        linkedin_location="Berlin, Germany",
        country="germany",
    )
    query = build_search(settings, "Product Manager", berlin, "indeed")
    assert query["country_indeed"] == "germany"


def test_fetch_listings_retries_a_proxy_error_and_not_a_block(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def scrape_jobs(**_kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("ProxyError: proxy connection failed")

        class Frame:
            attrs = {}

            def __len__(self):
                return 1

            def to_dict(self, orient):
                return [
                    {
                        "title": "Product Manager",
                        "company": "ACME",
                        "job_url": "https://example.com/j",
                        "description": "A product manager role.",
                        "location": "Milan",
                    }
                ]

        return Frame()

    monkeypatch.setattr("sources.scrape_jobs", scrape_jobs)
    settings = _settings(pause_seconds=2)
    rows = fetch_listings(
        settings,
        "Product Manager",
        settings.places[0],
        "linkedin",
        sleeper=sleeps.append,
    )
    assert calls["n"] == 3
    assert rows[0]["title"] == "Product Manager"
    assert sleeps == [2, 4]

    calls["n"] = 0

    def blocked(**_kwargs):
        calls["n"] += 1
        raise RuntimeError("LinkedIn blocked this search")

    monkeypatch.setattr("sources.scrape_jobs", blocked)
    try:
        fetch_listings(
            settings,
            "Product Manager",
            settings.places[0],
            "linkedin",
            sleeper=sleeps.append,
        )
    except RuntimeError as exc:
        assert "blocked" in str(exc)
    else:
        raise AssertionError("expected the block to be raised")
    assert calls["n"] == 1


def test_take_records_raises_when_a_site_returns_an_error_and_no_rows():
    class Empty:
        attrs = {"errors": {"glassdoor": "location not found"}}

        def __len__(self):
            return 0

    try:
        take_records(Empty(), "glassdoor")
    except RuntimeError as exc:
        assert "location not found" in str(exc)
    else:
        raise AssertionError("expected an error")


def test_collect_listings_keeps_going_when_one_search_fails():
    settings = _settings(pause_seconds=9)
    calls = []

    def fetch(role, place, site):
        calls.append((role, place.name, site))
        if site == "linkedin" and place.name == "Milan, Italy":
            raise RuntimeError("blocked")
        return [
            {
                "title": f"{role} via {site}",
                "company": "ACME",
                "location": place.name,
                "date_posted": "2026-10-20",
                "source": site,
                "url": f"https://example.com/{site}/{place.name}",
                "description": "A role.",
                "role_searched": role,
                "place_searched": place.name,
            }
        ]

    pauses = []
    rows, failures = collect_listings(settings, fetch, pause=pauses.append)
    assert failures == 1
    # The two Indeed hits share a title and company, but the cities differ,
    # so they stay separate. The LinkedIn hit has a different title.
    assert len(rows) == 3
    indeed_places = sorted(row["place_searched"] for row in rows if row["source"] == "indeed")
    assert indeed_places == ["Milan, Italy", "Remote"]
    assert pauses == [9, 9, 9]
    assert calls[0] == ("Product Manager", "Milan, Italy", "indeed")


def test_collect_listings_drops_titles_that_miss_the_role_keywords():
    settings = _settings(
        require_title_match=True,
        title_keywords={"Product Manager": ["product manager"]},
        pause_seconds=0,
    )
    settings.places = settings.places[:1]
    settings.sites = ["indeed"]

    def fetch(role, place, site):
        return [
            {
                "title": "Senior Product Manager",
                "company": "A",
                "location": "Milan",
                "date_posted": "2026-10-01",
                "source": site,
                "url": "https://example.com/a",
                "description": "",
                "role_searched": role,
                "place_searched": place.name,
            },
            {
                "title": "Strategy Associate",
                "company": "B",
                "location": "Milan",
                "date_posted": "2026-10-01",
                "source": site,
                "url": "https://example.com/b",
                "description": "",
                "role_searched": role,
                "place_searched": place.name,
            },
        ]

    rows, failures = collect_listings(settings, fetch, pause=lambda _seconds: None)
    assert failures == 0
    assert [row["title"] for row in rows] == ["Senior Product Manager"]


def test_collect_listings_drops_excluded_words_as_whole_words():
    settings = _settings(
        require_title_match=False,
        exclude_keywords=["senior", "intern"],
        pause_seconds=0,
    )
    settings.places = settings.places[:1]
    settings.sites = ["indeed"]

    def fetch(role, place, site):
        return [
            {
                "title": "Senior Product Manager",
                "company": "A",
                "location": "Milan",
                "source": site,
                "url": "https://example.com/senior",
                "description": "",
                "role_searched": role,
                "place_searched": place.name,
            },
            {
                "title": "Product Manager Intern",
                "company": "B",
                "location": "Milan",
                "source": site,
                "url": "https://example.com/intern",
                "description": "",
                "role_searched": role,
                "place_searched": place.name,
            },
            {
                "title": "Internal Product Manager",
                "company": "C",
                "location": "Milan",
                "source": site,
                "url": "https://example.com/internal",
                "description": "",
                "role_searched": role,
                "place_searched": place.name,
            },
        ]

    rows, failures = collect_listings(settings, fetch, pause=lambda _seconds: None)
    assert failures == 0
    assert [row["title"] for row in rows] == ["Internal Product Manager"]
