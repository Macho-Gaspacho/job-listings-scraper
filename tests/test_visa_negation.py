"""A visa refusal must not be shown as sponsorship offered."""

import pytest

from enrichment import detect_visa


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("We offer no visa sponsorship for this role.", "No sponsorship"),
        ("We cannot provide visa sponsorship.", "No sponsorship"),
        ("Unfortunately we are not able to offer visa sponsorship.", "No sponsorship"),
        ("We are unable to provide visa sponsorship.", "No sponsorship"),
        ("We do not provide relocation support or visa sponsorship.", "No sponsorship"),
        ("No sponsorship offered.", "No sponsorship"),
        ("Sin patrocinio de visado.", "No sponsorship"),
        ("Visa sponsorship is available.", "Sponsorship offered"),
        ("Visa sponsorship available for the right candidate.", "Sponsorship offered"),
        ("We can not sponsor visas.", "No sponsorship"),
        ("We will not sponsor work permits.", "No sponsorship"),
        ("Applicants must hold a valid work permit.", "No sponsorship"),
        ("You must be eligible to work in the EU.", "No sponsorship"),
        ("We sponsor visas. Relocation package included.", "Sponsorship offered"),
        ("The role is based in Berlin.", "Unknown"),
    ],
)
def test_a_refusal_is_not_read_as_sponsorship(text, expected):
    assert detect_visa(text) == expected
