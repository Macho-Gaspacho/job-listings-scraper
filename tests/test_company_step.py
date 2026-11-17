"""Career-page answers, including pasted addresses. No network."""

import pytest

from setup_wizard import IO, ask_companies, detect_system


class Script:
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.transcript: list[str] = []

    def output(self, text: str) -> None:
        self.transcript.append(str(text))

    def input(self, prompt: str = "") -> str:
        self.transcript.append(str(prompt))
        if not self.answers:
            raise AssertionError(f"Another question was asked: {prompt}")
        return self.answers.pop(0)

    @property
    def text(self) -> str:
        return "\n".join(self.transcript)


def _companies(answers: list[str]) -> tuple[list[dict], str]:
    script = Script(answers)
    found = ask_companies(IO(script.input, script.output))
    assert script.answers == []
    return found, script.text


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://boards.greenhouse.io/stripe", ("greenhouse", "stripe")),
        ("https://job-boards.greenhouse.io/stripe/jobs/123", ("greenhouse", "stripe")),
        ("https://job-boards.eu.greenhouse.io/acme", ("greenhouse", "acme")),
        ("https://jobs.lever.co/spotify", ("lever", "spotify")),
        ("https://jobs.eu.lever.co/acme/abc-123", ("lever", "acme")),
        ("https://jobs.ashbyhq.com/openai", ("ashby", "openai")),
        ("https://apply.workable.com/acme/", ("workable", "acme")),
        ("https://acme.recruitee.com/o/data-analyst", ("recruitee", "acme")),
        ("https://acme.teamtailor.com/jobs.rss", ("teamtailor", "https://acme.teamtailor.com/jobs.rss")),
        ("https://acme.teamtailor.com/jobs", ("teamtailor", "https://acme.teamtailor.com/jobs.rss")),
        ("https://www.acme.com/careers", None),
        ("boards.greenhouse.io/stripe", ("greenhouse", "stripe")),
    ],
)
def test_detect_system(url, expected):
    assert detect_system(url) == expected


def test_enter_skips_companies():
    assert _companies([""])[0] == []


def test_pasted_lever_url_uses_the_token_as_the_name():
    companies, _text = _companies(["https://jobs.lever.co/spotify", "n"])
    assert companies == [{"name": "spotify", "system": "lever", "token": "spotify"}]


def test_two_wrong_systems_skip_the_company():
    companies, text = _companies(["Acme", "foo", "bar", "n"])
    assert companies == []
    assert "Skipped Acme" in text


def test_named_company_with_a_system_and_token():
    companies, _text = _companies(["Acme", "greenhouse", "acme", "n"])
    assert companies == [{"name": "Acme", "system": "greenhouse", "token": "acme"}]


def test_unknown_system_words_skip_the_company():
    companies, _text = _companies(["Acme", "не знаю", "n"])
    assert companies == []


def test_blank_token_skips_the_company():
    companies, _text = _companies(["Acme", "greenhouse", "", "n"])
    assert companies == []


def test_unknown_careers_url_can_be_skipped():
    companies, _text = _companies(["https://www.acme.com/careers", "skip", "n"])
    assert companies == []


def test_eu_lever_page_is_added_with_region():
    companies, text = _companies(["https://jobs.eu.lever.co/acme", "n"])
    assert companies == [{"name": "acme", "system": "lever", "token": "acme", "region": "eu"}]
    assert "not supported" not in text
