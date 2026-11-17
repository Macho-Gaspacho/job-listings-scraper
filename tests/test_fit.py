"""Visa fit, language fit, and the questions that set them. No network."""

from pathlib import Path

import pytest
from openpyxl import load_workbook

from config import Candidate, load_config
from enrichment import (
    bind_candidate,
    detect_languages,
    detect_visa,
    language_fit,
    posting_language,
    visa_fit,
)
from listings import row_from_hit, sort_rows
from matching import sequence_matches
from save_results import write_outputs
from scrape import hide_poor_fits
from setup_wizard import IO, ask_languages, ask_visa, run_wizard


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


def _io(answers: list[str]) -> tuple[Script, IO]:
    script = Script(answers)
    return script, IO(script.input, script.output)


@pytest.mark.parametrize(
    ("text", "phrase", "expected"),
    [
        ("No relocation. Visa sponsorship available.", "no sponsorship", False),
        ("We offer no sponsorship for this role", "no sponsorship", True),
        ("Fließend Deutsch und Englisch", "fließend deutsch", True),
        ("Deutsch: fließend", "fließend deutsch", False),
        ("Sehr gute Deutschkenntnisse", "deutschkenntnisse", True),
        ("relocation support provided", "relocation support", True),
    ],
)
def test_sequence_matches_requires_words_together(text, phrase, expected):
    assert sequence_matches(text, phrase) is expected


def test_existing_deutsch_phrase_covers_a_colon():
    assert detect_languages("Deutsch: fließend") == ["German"]


@pytest.mark.parametrize(
    ("typed", "stored", "unknown"),
    [
        ("", None, ""),
        ("English, Russian", ("English", "Russian"), ""),
        ("английский, русский, итальянский", ("English", "Russian", "Italian"), ""),
        ("inglese,  tedesco", ("English", "German"), ""),
        ("Englisch, Deutsch, Klingon", ("English", "German"), "Klingon"),
        ("EN, DE", ("English", "German"), ""),
        ("english, English", ("English",), ""),
    ],
)
def test_spoken_languages_are_canonical(typed, stored, unknown):
    script, io = _io([typed])
    assert ask_languages(io) == stored
    if unknown:
        assert f'I don\'t know "{unknown}", so it was left out.' in script.text
    else:
        assert "I don't know" not in script.text


def test_an_unknown_language_is_asked_again_once():
    script, io = _io(["Klingon", "English"])
    assert ask_languages(io) == ("English",)
    assert 'I don\'t know "Klingon", so it was left out.' in script.text

    script, io = _io(["Klingon", ""])
    assert ask_languages(io) is None


@pytest.mark.parametrize(
    ("needs_visa", "detected", "expected"),
    [
        (None, "Sponsorship offered", ""),
        (None, "Unknown", ""),
        (None, "No sponsorship", ""),
        (False, "Sponsorship offered", ""),
        (False, "Unknown", ""),
        (False, "No sponsorship", ""),
        (True, "Sponsorship offered", "Sponsorship mentioned"),
        (True, "Unknown", "Not stated"),
        (True, "No sponsorship", "Says no sponsorship"),
    ],
)
def test_visa_fit_labels(needs_visa, detected, expected):
    assert visa_fit(detected, needs_visa) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("No relocation. Visa sponsorship available.", "Sponsorship offered"),
        ("Unfortunately we are unable to sponsor visas for this role.", "No sponsorship"),
        ("We will sponsor a Blue Card for the right candidate.", "Sponsorship offered"),
        ("You must have the right to work in the UK.", "No sponsorship"),
        ("Wir unterstützen bei der Blauen Karte.", "Unknown"),
        (
            "Visa sponsorship available. Candidates must be authorised to work in the EU.",
            "Unknown",
        ),
        ("Great team, hybrid work.", "Unknown"),
        ("Kennismigrant visa can be arranged.", "Sponsorship offered"),
    ],
)
def test_detect_visa_reads_consecutive_phrases(text, expected):
    assert detect_visa(text) == expected


@pytest.mark.parametrize(
    ("spoken", "required", "written", "expected"),
    [
        (None, ["German"], "German", ""),
        (("English", "Russian"), [], "", "Not stated"),
        (("English", "Russian"), ["English"], "", "OK"),
        (("English", "Russian"), ["German"], "", "Needs German"),
        (("English", "Russian"), [], "German", "Posting in German"),
        (("English", "German"), [], "German", "OK"),
        (("English", "Italian"), ["Italian", "English"], "Italian", "OK"),
        (("English",), ["Dutch", "English"], "", "Needs Dutch"),
        (("English",), ["German", "French"], "", "Needs German, French"),
    ],
)
def test_language_fit_precedence(spoken, required, written, expected):
    assert language_fit(required, written, spoken) == expected


def test_posting_language_needs_thirty_words_and_a_clear_lead():
    assert posting_language("und der die das mit für wir sie bei auf") == ""
    german = "und der die das mit für wir sie".split()
    filler = [f"topic{index}" for index in range(25)]
    assert posting_language(" ".join(german + filler)) == "German"
    dutch = "het een van voor wij jij kennis".split()
    close = " ".join(german + dutch + [f"zz{index}" for index in range(20)])
    assert posting_language(close) == ""


def _fit_row(title, visa, language, **extra):
    row = {
        "title": title,
        "is_new": "no",
        "source_type": "job board",
        "date_posted": "2026-01-01",
        "visa_fit": visa,
        "language_fit": language,
    }
    row.update(extra)
    return row


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        (
            [
                _fit_row("A", "Not stated", "OK"),
                _fit_row("B", "Sponsorship mentioned", "OK"),
                _fit_row("C", "Says no sponsorship", "OK"),
            ],
            ["B", "A", "C"],
        ),
        (
            [
                _fit_row("D", "Sponsorship mentioned", "Needs German"),
                _fit_row("E", "Not stated", "Not stated"),
            ],
            ["E", "D"],
        ),
        (
            [
                _fit_row("F", "", "", date_posted="2026-01-01"),
                _fit_row("G", "", "", date_posted="2026-02-01"),
            ],
            ["G", "F"],
        ),
        (
            [
                _fit_row("H", "Not stated", "Posting in Dutch"),
                _fit_row("I", "Not stated", "OK"),
            ],
            ["I", "H"],
        ),
    ],
)
def test_sort_rows_puts_good_fits_first(rows, expected):
    assert [row["title"] for row in sort_rows(rows)] == expected


def test_skipped_questions_keep_the_previous_order():
    rows = [
        {"is_new": "no", "date_posted": "2026-10-20", "title": "old-recent"},
        {"is_new": "yes", "date_posted": "2026-10-01", "title": "new-older"},
        {"is_new": "yes", "date_posted": "2026-10-18", "title": "new-newer"},
        {"is_new": "yes", "date_posted": "", "title": "new-undated"},
    ]
    blank = [{**row, "visa_fit": "", "language_fit": ""} for row in rows]
    order = ["new-newer", "new-older", "new-undated", "old-recent"]
    assert [row["title"] for row in sort_rows(rows)] == order
    assert [row["title"] for row in sort_rows(blank)] == order


def test_aggregator_rows_copy_fit_marks_while_a_candidate_is_bound():
    hit = {
        "title": "Engineer",
        "description": "Visa sponsorship available for this role and the team.",
    }
    plain = row_from_hit(hit, "Engineer", "Berlin", 280)
    assert plain["visa_fit"] == ""
    assert plain["language_fit"] == ""
    candidate = Candidate(needs_visa=True, languages=("English",), strict=False)
    with bind_candidate(candidate):
        marked = row_from_hit(hit, "Engineer", "Berlin", 280)
    assert marked["visa"] == "Sponsorship offered (guessed from the text)"
    assert marked["visa_fit"] == "Sponsorship mentioned"
    assert marked["language_fit"] == "Not stated"


def test_strict_filter_drops_blockers_and_reports_the_count(capsys):
    rows = [
        _fit_row("A", "Not stated", "OK"),
        _fit_row("C", "Says no sponsorship", "OK"),
        _fit_row("H", "Not stated", "Posting in Dutch"),
    ]
    strict = Candidate(needs_visa=True, languages=("English",), strict=True)
    kept = hide_poor_fits(rows, strict)
    assert [row["title"] for row in kept] == ["A"]
    assert capsys.readouterr().out.strip() == (
        "Hid 2 jobs that do not fit your visa or language answers."
    )
    assert hide_poor_fits(rows, Candidate()) == rows


def test_fit_cells_are_shaded_in_excel(tmp_path):
    excel = tmp_path / "jobs.xlsx"
    write_outputs(
        [
            _fit_row("Good", "Sponsorship mentioned", "OK"),
            _fit_row("Blocked", "Says no sponsorship", "Needs German"),
            _fit_row("Plain", "Not stated", "Not stated"),
        ],
        tmp_path / "jobs.csv",
        excel,
    )
    sheet = load_workbook(excel)["Jobs"]
    headers = [cell.value for cell in sheet[1]]
    visa_col = headers.index("Visa fit") + 1
    language_col = headers.index("Language fit") + 1
    assert sheet.cell(2, visa_col).fill.fgColor.rgb == "FFD9EAD3"
    assert sheet.cell(3, visa_col).fill.fgColor.rgb == "FFF4CCCC"
    assert sheet.cell(3, language_col).fill.fgColor.rgb == "FFF4CCCC"
    assert sheet.cell(4, visa_col).fill.patternType is None
    csv_text = (tmp_path / "jobs.csv").read_text(encoding="utf-8-sig")
    assert "Sponsorship mentioned" in csv_text
    assert "Needs German" in csv_text


def test_config_without_candidate_stays_unanswered(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
roles: [Nurse]
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
country: germany
sources:
  - id: indeed
    enabled: true
    kind: aggregator
""",
        encoding="utf-8",
    )
    settings = load_config(path)
    assert settings.candidate.needs_visa is None
    assert settings.candidate.languages is None
    assert settings.candidate.strict is False


def test_config_reads_a_candidate_block(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
roles: [Nurse]
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
country: germany
sources:
  - id: indeed
    enabled: true
    kind: aggregator
candidate:
  needs_visa: true
  languages: [English, Russian]
  strict: false
""",
        encoding="utf-8",
    )
    settings = load_config(path)
    assert settings.candidate == Candidate(
        needs_visa=True, languages=("English", "Russian"), strict=False
    )


def test_remote_only_visa_question_names_the_countries_you_chose():
    script, io = _io([""])
    assert ask_visa(io, "Germany", remote_only=True) is None
    assert "the countries you chose" in script.text

    script, io = _io(["maybe", "nope", "later"])
    assert ask_visa(io, "Germany") is None
    assert "work in Germany" in script.text
    assert script.text.count("Please type y or n, or press Enter to skip.") == 3


def _berlin(fit: list[str]) -> list[str]:
    """Nurse in Berlin, no remote, then the visa answers, then save and stop."""
    return (
        ["Nurse", "Berlin, Germany", "n"]
        + ["", "", "", "", "", ""]
        + fit
        + ["", "", "", "", "", "n"]
    )


def _run(tmp_path: Path, fit: list[str]) -> tuple[Script, Path]:
    config = tmp_path / "config.yaml"
    script = Script(_berlin(fit))
    code = run_wizard(
        config,
        input_func=script.input,
        output=script.output,
        run_search=lambda _path: 0,
    )
    assert code == 0, script.text
    assert script.answers == [], script.text
    return script, config


def test_skipping_both_questions_writes_no_candidate_block(tmp_path):
    script, config = _run(tmp_path, ["", ""])
    text = config.read_text(encoding="utf-8")
    assert "candidate:" not in text
    assert "only_visa_sponsorship" not in text
    assert "Hide jobs that clearly do not fit" not in script.text
    settings = load_config(config)
    assert settings.candidate.needs_visa is None
    assert settings.candidate.languages is None
    assert settings.filters.only_visa_sponsorship is False


def test_visa_yes_and_languages_are_saved_without_a_strict_filter(tmp_path):
    script, config = _run(tmp_path, ["y", "English, Russian", ""])
    settings = load_config(config)
    assert settings.candidate.needs_visa is True
    assert settings.candidate.languages == ("English", "Russian")
    assert settings.candidate.strict is False
    assert settings.filters.only_visa_sponsorship is False
    assert "Visa: you need sponsorship (jobs that mention it first)" in script.text
    assert "Languages you work in: English, Russian" in script.text
    assert "Hide jobs that do not fit: no" in script.text


def test_visa_no_does_not_ask_the_strict_question(tmp_path):
    script, config = _run(tmp_path, ["n", ""])
    assert "Hide jobs that clearly do not fit" not in script.text
    settings = load_config(config)
    assert settings.candidate.needs_visa is False
    assert settings.candidate.languages is None
    assert settings.candidate.strict is False
    assert "Visa: you do not need sponsorship" in script.text


def test_strict_yes_is_saved_when_languages_are_skipped(tmp_path):
    _script, config = _run(tmp_path, ["y", "", "y"])
    settings = load_config(config)
    assert settings.candidate.needs_visa is True
    assert settings.candidate.languages is None
    assert settings.candidate.strict is True
