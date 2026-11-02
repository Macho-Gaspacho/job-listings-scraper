"""Shipped title lists. The file is local; nothing is translated online."""

import pytest

from listings import title_is_relevant
from synonyms import LANGUAGES, catalog_path, load_catalog, suggestions_for


def test_synonym_file_is_a_hand_written_starter_list():
    text = catalog_path().read_text(encoding="utf-8")
    assert "starter" in text.lower()
    assert "hand" in text.lower()


def test_every_synonym_entry_has_a_non_empty_list_for_each_language():
    catalog = load_catalog()
    assert len(catalog) >= 30
    for role, entry in catalog.items():
        assert isinstance(entry, dict), role
        for language in LANGUAGES:
            phrases = entry.get(language)
            assert phrases, f"{role} has no {language} titles"
            assert all(str(phrase).strip() for phrase in phrases)


@pytest.mark.parametrize(
    ("country", "title"),
    [
        ("italy", "Infermiere"),
        ("italy", "Coordinatore Infermieristico"),
        ("italy", "OSS"),
        ("germany", "Krankenpfleger (m/w/d)"),
        ("germany", "Software-Entwickler (m/w/d)"),
        ("germany", "Softwareentwickler (m/w/d)"),
        ("spain", "Enfermero de urgencias"),
        ("poland", "Pielęgniarka"),
        ("netherlands", "Verpleegkundige"),
    ],
)
def test_local_titles_match_when_the_country_synonyms_are_used(country, title):
    role = "Software Engineer" if "Entwickler" in title or "Softwareentwickler" in title else "Nurse"
    phrases = suggestions_for([role], country)[role]
    assert phrases
    assert title_is_relevant(title, phrases)
