"""Country aliases and the location rules derived from a config."""

from config import Place
from regions import (
    LocationFilter,
    build_location_rules,
    canonical_country,
    contains_phrase,
    default_remote_regions,
    fold_text,
)


def _place(name, indeed, remote=False):
    return Place(
        name=name,
        indeed_location=indeed,
        linkedin_location=indeed,
        remote=remote,
    )


def test_aliases_map_to_indeed_country_codes():
    assert canonical_country("Italia") == "italy"
    assert canonical_country("Deutschland") == "germany"
    assert canonical_country("United States") == "usa"
    assert canonical_country("España") == "spain"
    assert canonical_country("Turkey") == "türkiye"
    assert canonical_country("United Kingdom") == "uk"
    assert canonical_country("narnia") is None


def test_remote_regions_include_europe_only_for_an_eu_country():
    italy = default_remote_regions("italy")
    assert italy[:2] == ("Italy", "Italia")
    assert "Europe" in italy
    assert "EU" in italy
    assert "EMEA" in italy
    assert "Worldwide" in italy
    germany = default_remote_regions("germany")
    assert "Deutschland" in germany
    assert "Europe" in germany
    usa = default_remote_regions("usa")
    assert "United States" in usa
    assert "Europe" not in usa
    assert "EU" not in usa
    assert "EMEA" not in usa
    uk = default_remote_regions("uk")
    assert "United Kingdom" in uk
    assert "Europe" not in uk


def test_offices_are_city_and_country_words_from_each_place():
    rules = build_location_rules(
        [
            _place("Berlin, Germany", "Berlin, Germany"),
            _place("Munich, Germany", "Munich, Germany"),
            _place("Remote", "Germany", remote=True),
        ],
        "germany",
        None,
    )
    names = [name for name, _phrases in rules.offices]
    assert names == ["Berlin, Germany", "Munich, Germany"]
    berlin = {fold_text(phrase) for phrase in rules.offices[0][1]}
    assert "berlin" in berlin
    assert "germany" in berlin
    assert "munich" not in berlin


def test_a_remote_only_search_has_no_office_words():
    rules = build_location_rules(
        [_place("Remote", "Germany", remote=True)],
        "germany",
        None,
    )
    assert rules.offices == ()
    assert "Germany" in rules.remote_regions


def test_an_explicit_filter_replaces_the_derived_lists():
    rules = build_location_rules(
        [_place("Berlin, Germany", "Berlin, Germany")],
        "germany",
        LocationFilter(
            offices=("Kreuzberg", "Berlin"),
            remote_regions=("EU",),
            exclude_regions=("UK only",),
        ),
    )
    assert rules.offices == (("Berlin, Germany", ("Kreuzberg", "Berlin")),)
    assert rules.remote_regions == ("EU",)
    assert rules.exclude_regions == ("UK only",)


def test_whole_words_do_not_match_inside_longer_words():
    assert contains_phrase("us", "remote user research") is False
    assert contains_phrase("us only", "Bonus only for top performers") is False
    assert contains_phrase("india", "Finland") is False
    assert contains_phrase("usa", "Remote - USA") is True
    assert contains_phrase("Munchen", "München") is True
