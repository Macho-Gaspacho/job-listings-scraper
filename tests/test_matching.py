"""Whole-word title matching. No job sites are contacted."""

import pytest

from matching import normalise, phrase_matches


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Software-Entwickler", ["software", "entwickler"]),
        ("Engineer, Software", ["engineer", "software"]),
        ("Développeur", ["developpeur"]),
        ("Enfermería", ["enfermeria"]),
        ("Köchin", ["kochin"]),
        ("Pielęgniarka", ["pielegniarka"]),
        ("C++ Developer", ["c", "developer"]),
        ("develop*", ["develop*"]),
        ("  ", []),
    ],
)
def test_normalise_strips_accents_and_splits_on_punctuation(text, expected):
    assert normalise(text) == expected


@pytest.mark.parametrize(
    ("title", "phrase", "expected"),
    [
        ("Three-shift Chef", "hr", False),
        ("Waiter", "it", False),
        ("Waitress", "it", False),
        ("Thread", "hr", False),
        ("Seniority Lead", "senior", False),
        ("Internal Auditor", "intern", False),
        ("HR Business Partner", "hr", True),
        ("Human Resources Manager", "human resources", True),
        ("Software-Entwickler (m/w/d)", "software entwickler", True),
        ("Softwareentwickler", "software entwickler", False),
        ("Projekt-Manager", "projekt manager", True),
        ("Engineer, Software", "software engineer", True),
        ("Senior Product Manager", "product manager", True),
        ("PRODUCT OWNER (Milan)", "product owner", True),
        ("Strategy Associate", "product manager", False),
        ("Développeur logiciel", "developpeur", True),
        ("Enfermero de urgencias", "enfermero", True),
        ("Infermiere", "infermiere", True),
        ("Coordinatore Infermieristico", "infermieristico", True),
        ("Kierowca ciężarowy", "kierowca", True),
        ("Verpleegkundige", "verpleegkundige", True),
        ("Software Developer", "develop*", True),
        ("Entwicklung", "entwickl*", True),
        ("Engineering Manager", "develop*", False),
        ("Senior Software Developer", "software develop*", True),
        ("Köchin", "kochin", True),
        ("", "nurse", False),
        ("Nurse", "", False),
    ],
)
def test_phrase_matches_whole_tokens_in_any_order(title, phrase, expected):
    assert phrase_matches(title, phrase) is expected
