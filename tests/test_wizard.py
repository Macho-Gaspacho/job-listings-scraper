"""Wizard questions write a real config. No job sites are contacted."""

from pathlib import Path

from config import load_config
from scrape import main
from setup_wizard import run_wizard


class Script:
    """Feed answers one prompt at a time and keep the text the user would see."""

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


def _run(tmp_path: Path, answers: list[str], run_search=None) -> tuple[Script, Path]:
    config = tmp_path / "config.yaml"
    script = Script(answers)
    code = run_wizard(
        config,
        input_func=script.input,
        output=script.output,
        run_search=run_search,
    )
    assert code == 0
    assert script.answers == []
    return script, config


def test_wizard_writes_a_config_from_answers(tmp_path):
    script, config = _run(
        tmp_path,
        [
            "Software Engineer, Data Analyst",
            "Berlin, Germany",
            "y",
            "",
            "backend, python",
            "1,2",
            "y",
            "n",
        ],
    )
    assert "Project Manager, Product Manager" in script.text
    assert "Berlin, Germany" in script.text
    assert "Indeed" in script.text
    assert "LinkedIn" in script.text
    assert "Remote" in script.text or "remote" in script.text
    assert "career" in script.text.lower()
    assert not (tmp_path / "config.backup.yaml").exists()

    settings = load_config(config)
    assert settings.roles == ["Software Engineer", "Data Analyst"]
    assert settings.country == "germany"
    assert settings.require_title_match is True
    assert settings.places[0].name == "Berlin, Germany"
    assert settings.places[0].remote is False
    assert settings.places[0].indeed_location == "Berlin, Germany"
    assert settings.places[0].distance_miles == 30
    assert settings.places[1].name == "Remote"
    assert settings.places[1].remote is True
    assert settings.places[1].indeed_location == "Germany"
    assert settings.sites == ["indeed", "linkedin"]
    assert settings.company_pages_enabled is False
    assert settings.remote_boards == []
    assert settings.companies == []
    assert settings.pause_seconds == 2
    assert settings.title_keywords["Software Engineer"] == ["backend", "python"]
    assert settings.title_keywords["Data Analyst"] == ["backend", "python"]
    assert "python scrape.py --setup" in config.read_text(encoding="utf-8")


def test_wizard_can_skip_remote_and_save_a_company(tmp_path):
    _script, config = _run(
        tmp_path,
        [
            "Nurse, Doctor",
            "Milan, Italy",
            "n",
            "",
            "1,4",
            "Example Hospital",
            "workday",
            "greenhouse",
            "examplehospital",
            "n",
            "y",
            "n",
        ],
    )
    settings = load_config(config)
    assert [place.name for place in settings.places] == ["Milan, Italy"]
    assert settings.country == "italy"
    assert settings.sites == ["indeed"]
    assert settings.company_pages_enabled is True
    assert settings.companies[0].name == "Example Hospital"
    assert settings.companies[0].system == "greenhouse"
    assert settings.companies[0].token == "examplehospital"
    assert settings.remote_boards == []


def test_wizard_defaults_and_offers_to_search(tmp_path):
    searched = []

    def run_search(path: Path) -> int:
        searched.append(Path(path))
        return 0

    _script, config = _run(
        tmp_path,
        [
            "C++ Developer",
            "Austin, United States",
            "",
            "",
            "",
            "",
            "",
            "y",
        ],
        run_search=run_search,
    )
    settings = load_config(config)
    assert settings.roles == ["C++ Developer"]
    assert settings.title_keywords["C++ Developer"] == ["c++ developer"]
    assert settings.country == "usa"
    assert settings.places[1].remote is True
    assert settings.places[1].indeed_location == "United States"
    assert settings.sites == ["indeed", "linkedin"]
    assert searched == [config]


def test_wizard_backs_up_an_existing_config_only_after_confirmation(tmp_path):
    config = tmp_path / "config.yaml"
    original = (
        "roles:\n  - Old Role\n"
        "locations:\n  - name: Old City\n"
        "    indeed_location: Old City\n"
        "    linkedin_location: Old City\n"
        "sources:\n  - id: indeed\n    enabled: true\n    kind: aggregator\n"
        "country: italy\n"
    )
    config.write_text(original, encoding="utf-8")
    seen = {"rejected": False}

    class Watching(Script):
        def input(self, prompt: str = "") -> str:
            if "config.yaml" in prompt and self.answers and self.answers[0] == "n":
                assert config.read_text(encoding="utf-8") == original
                assert not (tmp_path / "config.backup.yaml").exists()
                seen["rejected"] = True
            return super().input(prompt)

    answers = [
        "Teacher",
        "Paris, France",
        "n",
        "",
        "2",
        "n",
        "Teacher",
        "Paris, France",
        "n",
        "",
        "2",
        "y",
        "n",
    ]
    script = Watching(answers)
    code = run_wizard(config, input_func=script.input, output=script.output, run_search=lambda _path: 0)
    assert code == 0
    assert seen["rejected"] is True
    assert script.answers == []
    backup = tmp_path / "config.backup.yaml"
    assert backup.read_text(encoding="utf-8") == original
    settings = load_config(config)
    assert settings.roles == ["Teacher"]
    assert settings.country == "france"
    assert settings.sites == ["linkedin"]


def test_missing_config_starts_the_wizard(tmp_path, monkeypatch, capsys):
    config = tmp_path / "config.yaml"
    seen = {}

    def fake_wizard(path, input_func=None, output=None, run_search=None):
        seen["path"] = Path(path)
        seen["run_search"] = run_search
        return 7

    monkeypatch.setattr("setup_wizard.run_wizard", fake_wizard)
    code = main(["--config", str(config)])
    assert code == 7
    assert seen["path"] == config
    assert seen["run_search"] is not None
    assert "Could not read the config file" not in capsys.readouterr().out


def test_setup_flag_runs_the_wizard_when_config_exists(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("roles: []\n", encoding="utf-8")
    seen = {}

    def fake_wizard(path, input_func=None, output=None, run_search=None):
        seen["path"] = Path(path)
        return 0

    monkeypatch.setattr("setup_wizard.run_wizard", fake_wizard)
    code = main(["--config", str(config), "--setup"])
    assert code == 0
    assert seen["path"] == config


def test_existing_config_runs_the_search_without_the_wizard(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
roles: [Teacher]
locations:
  - name: Paris, France
    indeed_location: Paris, France
    linkedin_location: Paris, France
sources:
  - id: indeed
    enabled: true
    kind: aggregator
country: france
output:
  directory: output
  csv: jobs.csv
  excel: jobs.xlsx
  seen_file: data/seen_jobs.json
""",
        encoding="utf-8",
    )

    def fail_wizard(*_args, **_kwargs):
        raise AssertionError("wizard should not run")

    monkeypatch.setattr("setup_wizard.run_wizard", fail_wizard)
    monkeypatch.setattr("scrape.collect_board_listings", lambda *_args, **_kwargs: ([], 0))
    monkeypatch.setattr("scrape.collect_listings", lambda *_args, **_kwargs: ([], 0))
    code = main(["--config", str(config)])
    assert code == 0
    assert (tmp_path / "output" / "jobs.csv").exists()
