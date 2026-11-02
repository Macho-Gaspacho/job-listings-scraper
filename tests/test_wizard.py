"""Wizard questions write a real config. No job sites are contacted."""

from pathlib import Path

import pytest

from config import load_config
from listings import title_is_relevant
from scrape import main
from setup_wizard import launcher_name, parse_place, resolve_remote_area, run_wizard


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
            "n",
            "",
            "backend, python",
            "senior, intern",
            "1,2",
            "",
            "",
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
    assert settings.results_per_search == 20
    assert settings.posted_within_days == 14
    assert settings.title_keywords["Software Engineer"] == ["software engineer", "backend", "python"]
    assert settings.title_keywords["Data Analyst"] == ["data analyst", "backend", "python"]
    assert settings.exclude_keywords == ["senior", "intern"]
    assert "Next time just double-click start.command" in script.text
    assert "When you are ready, run: python scrape.py" not in script.text
    assert "python scrape.py --setup" in config.read_text(encoding="utf-8")


def test_parse_place_accepts_a_country_a_city_or_remote():
    italy, italy_error = parse_place("Italy")
    assert italy_error is None
    assert italy["kind"] == "country"
    assert italy["country"] == "italy"
    assert italy["indeed"] is True
    assert italy["name"] == "Italy"

    armenia, armenia_error = parse_place("Armenia")
    assert armenia_error is None
    assert armenia["country"] == "armenia"
    assert armenia["indeed"] is False

    remote, remote_error = parse_place("Remote")
    assert remote_error is None
    assert remote == {"kind": "remote"}

    city, city_error = parse_place("Madrid, Spain")
    assert city_error is None
    assert city["kind"] == "city"
    assert city["country"] == "spain"

    missing, missing_error = parse_place("Berlin")
    assert missing is None
    assert missing_error == "country"


def test_resolve_remote_area_accepts_countries_and_linkedin_regions():
    assert resolve_remote_area("Europe") == ("Europe", None, False)
    assert resolve_remote_area("Worldwide") == ("Worldwide", None, False)
    assert resolve_remote_area("France") == ("France", "france", True)
    assert resolve_remote_area("Serbia") == ("Serbia", "serbia", False)
    assert resolve_remote_area("Georgia") == ("Georgia", "georgia", False)
    assert resolve_remote_area("a nearby village") is None


def test_launcher_name_follows_the_operating_system(monkeypatch):
    monkeypatch.setattr("setup_wizard.sys.platform", "win32")
    assert launcher_name() == "start.bat"
    monkeypatch.setattr("setup_wizard.sys.platform", "darwin")
    assert launcher_name() == "start.command"


@pytest.mark.parametrize(
    ("country_name", "code", "title", "word"),
    [
        ("Italy", "italy", "Infermiere", "infermiere"),
        ("Germany", "germany", "Krankenpfleger", "krankenpfleger"),
        ("Spain", "spain", "Enfermero de urgencias", "enfermero"),
        ("Poland", "poland", "Pielęgniarka", "pielęgniarka"),
        ("Netherlands", "netherlands", "Verpleegkundige", "verpleegkundige"),
    ],
)
def test_wizard_country_wide_search_keeps_local_nurse_titles(
    tmp_path, country_name, code, title, word
):
    script, config = _run(
        tmp_path,
        [
            "Nurse",
            country_name,
            "n",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "n",
        ],
    )
    settings = load_config(config)
    assert settings.country == code
    assert [place.name for place in settings.places] == [country_name]
    assert settings.places[0].remote is False
    assert settings.places[0].indeed_location == country_name
    assert settings.places[0].linkedin_location == country_name
    assert settings.places[0].distance_miles is None
    assert settings.places[0].search_indeed is True
    assert settings.require_title_match is True
    assert settings.results_per_search == 20
    assert settings.posted_within_days == 14
    assert word in settings.title_keywords["Nurse"]
    assert title_is_relevant(title, settings.title_keywords["Nurse"])
    assert "Also accept these titles?" in script.text
    assert "starter set" in script.text
    assert "Press Enter for 20" in script.text
    assert "Press Enter for 14" in script.text
    assert "Next time just double-click start.command" in script.text


def test_wizard_leaves_indeed_off_for_a_country_it_does_not_cover(tmp_path):
    script, config = _run(
        tmp_path,
        [
            "Nurse",
            "Armenia",
            "n",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "n",
        ],
    )
    settings = load_config(config)
    assert settings.country == "armenia"
    assert settings.places[0].name == "Armenia"
    assert settings.places[0].indeed_location == "Armenia"
    assert settings.places[0].search_indeed is False
    assert settings.sites == ["linkedin"]
    assert "Indeed does not cover Armenia" in script.text
    assert "Indeed was left off" in script.text


def test_wizard_remote_in_another_country_can_stay_on_linkedin_only(tmp_path):
    script, config = _run(
        tmp_path,
        [
            "Nurse",
            "Berlin, Germany",
            "y",
            "France",
            "1",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "n",
        ],
    )
    settings = load_config(config)
    assert settings.country == "germany"
    assert settings.places[0].name == "Berlin, Germany"
    assert settings.places[0].search_indeed is True
    assert settings.places[1].name == "Remote"
    assert settings.places[1].indeed_location == "France"
    assert settings.places[1].search_indeed is False
    assert settings.sites == ["indeed", "linkedin"]
    assert "Indeed can only search one country" in script.text
    assert "LinkedIn only" in script.text


def test_wizard_treats_europe_as_a_linkedin_only_remote_area(tmp_path):
    script, config = _run(
        tmp_path,
        [
            "Chef",
            "Madrid, Spain",
            "y",
            "Europe",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "n",
        ],
    )
    settings = load_config(config)
    assert settings.country == "spain"
    assert settings.places[0].search_indeed is True
    assert settings.places[1].remote is True
    assert settings.places[1].indeed_location == "Europe"
    assert settings.places[1].linkedin_location == "Europe"
    assert settings.places[1].search_indeed is False
    assert settings.sites == ["indeed", "linkedin"]
    assert "cannot search Europe" in script.text
    assert "LinkedIn only" in script.text
    assert "cocinero" in settings.title_keywords["Chef"]


def test_wizard_can_skip_remote_and_save_a_company(tmp_path):
    _script, config = _run(
        tmp_path,
        [
            "Nurse, Doctor",
            "Milan, Italy",
            "n",
            "y",
            "",
            "",
            "",
            "1,4",
            "Example Hospital",
            "workday",
            "greenhouse",
            "examplehospital",
            "n",
            "",
            "",
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
    assert "infermiere" in settings.title_keywords["Nurse"]
    assert "medico" in settings.title_keywords["Doctor"]
    assert title_is_relevant("Infermiere", settings.title_keywords["Nurse"])


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
    assert settings.require_title_match is False
    assert settings.results_per_search == 20
    assert settings.posted_within_days == 14
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
        "n",
        "",
        "",
        "",
        "2",
        "",
        "",
        "n",
        "Teacher",
        "Paris, France",
        "n",
        "n",
        "",
        "",
        "",
        "2",
        "",
        "",
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
