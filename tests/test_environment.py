"""Plain-language checks for Python, packages, and Mac certificates."""

from pathlib import Path

from config import Place, Settings
from environment import (
    certificate_hint,
    missing_package_message,
    python_version_problem,
)
from scrape import collect_listings


def test_old_python_explains_what_to_install():
    message = python_version_problem((3, 9, 7))
    assert message is not None
    assert "3.10" in message
    assert "https://www.python.org/downloads/" in message
    assert "3.9.7" in message


def test_python_3_10_is_new_enough():
    assert python_version_problem((3, 10, 0)) is None
    assert python_version_problem((3, 12, 1)) is None


def test_missing_package_tells_you_to_install_requirements():
    message = missing_package_message(ModuleNotFoundError("No module named 'yaml'"))
    assert "pip install -r requirements.txt" in message
    assert "yaml" in message


def test_certificate_hint_prints_once_for_macos():
    certificate_hint.shown = False
    certificate_hint.platform = "darwin"
    certificate_hint.version = (3, 12, 0)
    exc = OSError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    first = certificate_hint.note(exc)
    second = certificate_hint.note(exc)
    assert first is not None
    assert 'Install Certificates.command' in first
    assert "Python 3.12" in first
    assert second is None
    certificate_hint.platform = None
    certificate_hint.version = None
    certificate_hint.shown = False


def test_certificate_hint_is_silent_on_windows():
    certificate_hint.shown = False
    certificate_hint.platform = "win32"
    certificate_hint.version = (3, 12, 0)
    message = certificate_hint.note(OSError("CERTIFICATE_VERIFY_FAILED"))
    assert message is None
    certificate_hint.platform = None
    certificate_hint.version = None
    certificate_hint.shown = False


def test_a_certificate_failure_during_search_is_explained_once(capsys):
    certificate_hint.shown = False
    certificate_hint.platform = "darwin"
    certificate_hint.version = (3, 12, 0)
    settings = Settings(
        roles=["Teacher"],
        places=[
            Place(
                name="Paris, France",
                indeed_location="Paris, France",
                linkedin_location="Paris, France",
            )
        ],
        sites=["indeed", "linkedin"],
        country="france",
        results_per_search=1,
        posted_within_days=30,
        pause_seconds=0,
        fetch_descriptions=False,
        snippet_characters=80,
        output_dir=None,
        csv_path=None,
        excel_path=None,
        seen_file=None,
    )

    def fetch(_role, _place, _site):
        raise OSError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    _rows, failures = collect_listings(settings, fetch, pause=lambda _seconds: None)
    assert failures == 2
    output = capsys.readouterr().out
    assert output.count("Install Certificates.command") == 1
    certificate_hint.platform = None
    certificate_hint.version = None
    certificate_hint.shown = False


def test_launchers_prepare_a_venv_and_can_be_double_clicked():
    import os
    import stat

    root = Path(__file__).resolve().parents[1]
    shell = (root / "start.sh").read_text(encoding="utf-8")
    command = (root / "start.command").read_text(encoding="utf-8")
    bat = (root / "start.bat").read_text(encoding="utf-8")
    assert "python3.12" in shell
    assert "requirements.txt" in shell
    assert "scrape.py" in shell
    assert ".venv" in shell
    assert "requirements.txt" in bat
    assert "scrape.py" in bat
    assert ".venv" in bat
    assert "start.sh" in command
    for name in ("start.sh", "start.command"):
        mode = (root / name).stat().st_mode
        assert mode & stat.S_IXUSR
        assert os.access(root / name, os.X_OK)
