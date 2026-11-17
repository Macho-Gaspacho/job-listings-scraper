"""Source choice, role families, and sort order. No network."""

from pathlib import Path

import pytest

from config import load_config
from listings import sort_rows
from setup_wizard import build_config, parse_sources
from source_map import recommend, role_family


def _office(name: str, search_indeed: bool = True) -> dict:
    return {
        "name": name,
        "indeed_location": name,
        "linkedin_location": name,
        "remote": False,
        "search_indeed": search_indeed,
    }


def _remote(area: str, search_indeed: bool) -> dict:
    return {
        "name": "Remote",
        "indeed_location": area,
        "linkedin_location": area,
        "remote": True,
        "search_indeed": search_indeed,
    }


_ROLES = [
    ("Data Analyst", "data", False),
    ("Senior Software Engineer", "tech", False),
    ("product manager", "product_project", False),
    ("Program Manager", "product_project", False),
    ("Strategy Consultant", "consulting", False),
    ("Investment Banking Analyst", "finance", False),
    ("Risk Manager", "finance", False),
    ("Graduate Data Scientist", "data", True),
    ("Marketing Manager", "marketing", False),
    ("Physician", "medicine", False),
    ("Junior Business Analyst", "data", True),
    ("Store Manager", "other", False),
]


@pytest.mark.parametrize(("role", "family", "graduate"), _ROLES)
def test_role_family(role, family, graduate):
    assert role_family(role) == (family, graduate)


_AUTO = [
    "",
    "any",
    "Any",
    "ANY",
    "any site",
    "any website",
    "any relevant site",
    "any relevant website",
    "all",
    "любой",
    "любые",
    "любой сайт",
    "все",
    "не знаю",
    "незнаю",
    "без разницы",
    "qualsiasi",
    "tutti",
    "non so",
    "egal",
    "alle",
    "weiß nicht",
    "weiss nicht",
    "n'importe",
    "tous",
    "je ne sais pas",
    "cualquiera",
    "todos",
    "no sé",
    "no se",
    "don't know",
    "dont know",
    "idk",
    "?",
    "recommended",
    "best",
]


@pytest.mark.parametrize("typed", _AUTO)
def test_parse_sources_auto(typed):
    assert parse_sources(typed) == "auto"


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("1", {"company"}),
        ("1,3", {"company", "remote"}),
        ("4, 5", {"indeed", "linkedin"}),
        ("indeed", {"indeed"}),
        ("linkedin,1", {"linkedin", "company"}),
        ("arbeitnow", {"board:arbeitnow"}),
    ],
)
def test_parse_sources_groups(typed, expected):
    assert parse_sources(typed) == expected


@pytest.mark.parametrize("typed", ["7", "indeed, xyz"])
def test_parse_sources_rejects_unknown_answers(typed):
    assert parse_sources(typed) is None


_RECOMMENDATIONS = [
    (
        "germany",
        [_office("Berlin, Germany")],
        ["software engineer"],
        ("arbeitnow", "indeed", "linkedin"),
        {"welcome_to_the_jungle", "bundesagentur_link"},
        {"epso_traineeships"},
    ),
    (
        "italy",
        [_office("Milan, Italy")],
        ["product manager"],
        ("indeed", "linkedin"),
        {"welcome_to_the_jungle", "eures"},
        {"wellfound"},
    ),
    (
        "netherlands",
        [_office("Amsterdam, Netherlands"), _remote("Netherlands", True)],
        ["data analyst"],
        ("remotive", "we_work_remotely", "remote_ok", "indeed", "linkedin"),
        {"welcome_to_the_jungle"},
        set(),
    ),
    (
        "italy",
        [_remote("Europe", False)],
        ["data scientist"],
        ("remotive", "we_work_remotely", "remote_ok", "working_nomads", "linkedin"),
        set(),
        set(),
    ),
    (
        "uk",
        [_office("London, United Kingdom")],
        ["strategy consultant"],
        ("indeed", "linkedin"),
        {"welcome_to_the_jungle", "wellfound"},
        {"eures"},
    ),
    (
        "italy",
        [_office("Milan, Italy")],
        ["graduate data analyst"],
        ("indeed", "linkedin"),
        {"un_careers_internships"},
        {"epso_traineeships"},
    ),
    (
        "armenia",
        [_office("Yerevan, Armenia", search_indeed=False)],
        ["project manager"],
        ("linkedin",),
        {"linkedin_jobs_search_link", "eures"},
        set(),
    ),
]


@pytest.mark.parametrize(
    ("country", "places", "roles", "sources", "include", "exclude"),
    _RECOMMENDATIONS,
)
def test_recommend(country, places, roles, sources, include, exclude):
    result = recommend(country, places, roles)
    assert result.sources == sources
    assert include <= set(result.link_outs)
    assert not (exclude & set(result.link_outs))


def test_germany_explanation_names_the_mix():
    result = recommend("germany", [_office("Berlin, Germany")], ["software engineer"])
    text = "\n".join(result.explanation)
    assert text.splitlines()[0] == "Recommended for a tech job in Germany:"
    assert "company career pages, if you add companies in the next step." in text
    assert "Then: Arbeitnow." in text
    assert "Remote boards:" not in text
    assert "Welcome to the Jungle" in text
    assert "output/links.md" in text
    assert text.splitlines()[-1] == "  Last: Indeed, LinkedIn (most applicants per job)."


def test_auto_config_enables_arbeitnow_for_germany():
    places = [_office("Berlin, Germany")]
    result = recommend("germany", places, ["software engineer"])
    data = build_config(
        ["software engineer"],
        places,
        "germany",
        [],
        {},
        [],
        set(result.sources),
        [],
        require_title_match=True,
        results_per_search=20,
        posted_within_days=14,
        source_choice="auto",
        link_outs=list(result.link_outs),
    )
    by_id = {item["id"]: item for item in data["sources"]}
    assert by_id["arbeitnow"] == {"id": "arbeitnow", "enabled": True, "kind": "job board"}
    assert by_id["indeed"]["enabled"] is True
    assert by_id["remotive"]["enabled"] is False
    assert data["source_choice"] == "auto"
    assert "bundesagentur_link" in data["link_outs"]


def test_example_configs_still_load():
    root = Path(__file__).resolve().parents[1] / "examples"
    paths = sorted(root.glob("*.yaml"))
    assert paths
    for path in paths:
        settings = load_config(path)
        assert settings.roles
        assert settings.link_outs == ()
        assert settings.job_boards == []


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        (
            [
                {"title": "A", "is_new": "yes", "source_type": "aggregator", "date_posted": "2026-11-15"},
                {"title": "B", "is_new": "yes", "source_type": "company site", "date_posted": "2026-11-01"},
                {"title": "C", "is_new": "no", "source_type": "company site", "date_posted": "2026-11-16"},
            ],
            ["B", "A", "C"],
        ),
        (
            [
                {"title": "D", "is_new": "no", "source_type": "remote board", "date_posted": "2026-11-10"},
                {"title": "E", "is_new": "no", "source_type": "job board", "date_posted": "2026-11-01"},
            ],
            ["E", "D"],
        ),
        (
            [
                {
                    "title": "F",
                    "is_new": "no",
                    "source_type": "aggregator, company site",
                    "date_posted": "2026-11-01",
                },
                {"title": "G", "is_new": "no", "source_type": "aggregator", "date_posted": "2026-11-16"},
            ],
            ["F", "G"],
        ),
    ],
)
def test_sort_rows_prefers_the_less_crowded_source(rows, expected):
    assert [row["title"] for row in sort_rows(rows)] == expected
