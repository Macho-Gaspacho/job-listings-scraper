"""Russian job titles are offered in English. No network."""

import pytest

from setup_wizard import IO, ask_roles
from synonyms import suggestions_for


class Script:
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.transcript: list[str] = []

    def output(self, text: str) -> None:
        self.transcript.append(str(text))

    def input(self, prompt: str = "") -> str:
        self.transcript.append(str(prompt))
        if not self.answers:
            raise AssertionError(f"Wizard asked another question: {prompt}")
        return self.answers.pop(0)

    @property
    def text(self) -> str:
        return "\n".join(self.transcript)


@pytest.mark.parametrize(
    ("typed", "answers", "expected"),
    [
        ("менеджер проектов", [""], ["project manager"]),
        ("Менеджер Проектов", ["y"], ["project manager"]),
        ("продакт-менеджер", [""], ["product manager"]),
        ("аналитик данных, дата сайентист", ["", ""], ["data analyst", "data scientist"]),
        ("менеджер проектов", ["n"], ["менеджер проектов"]),
        ("кладовщик", [""], ["кладовщик"]),
        ("кладовщик", ["warehouse"], ["warehouse"]),
        ("Projektmanager", [], ["Projektmanager"]),
        ("project manager", [], ["project manager"]),
    ],
)
def test_russian_titles_are_offered_in_english(typed, answers, expected):
    script = Script([typed, *answers])
    roles = ask_roles(IO(script.input, script.output))
    assert roles == expected
    assert script.answers == []
    if typed == "кладовщик":
        assert "is not in English" in script.text
        assert "the country you choose" in script.text
    else:
        assert "is not in English" not in script.text
    if any("\u0400" <= char <= "\u04FF" for char in typed) and typed != "кладовщик":
        assert "usually" in script.text
    if typed in {"Projektmanager", "project manager"}:
        assert "usually" not in script.text


def test_a_replaced_title_is_what_local_suggestions_use():
    script = Script(["менеджер проектов", ""])
    roles = ask_roles(IO(script.input, script.output))
    assert roles == ["project manager"]
    assert "project manager" in suggestions_for(roles, "germany")
    assert suggestions_for(["менеджер проектов"], "germany") == {}


def test_obvious_russian_inflections_use_the_same_english_title():
    script = Script(["менеджера проектов", ""])
    roles = ask_roles(IO(script.input, script.output))
    assert roles == ["project manager"]
