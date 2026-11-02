"""Tests for the optional daily git publish. No job sites are contacted."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

import daily


def _load_automation():
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "automation"
        / "daily_git_commit.py"
    )
    spec = importlib.util.spec_from_file_location("daily_git_commit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo, *args, check=True):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


def _opt_in():
    return {
        "daily_git": {
            "enabled": True,
            "i_understand_this_is_public_if_repo_is_public": True,
        }
    }


def _write_daily_files(repo: Path) -> None:
    (repo / "data").mkdir()
    (repo / "output").mkdir()
    (repo / "data" / "seen_jobs.json").write_text(
        '{"seen_keys": ["url:https://example.com/a"]}\n',
        encoding="utf-8",
    )
    (repo / "output" / "new_jobs.csv").write_text("New since last run\n", encoding="utf-8")
    (repo / "output" / "last_run.json").write_text('{"new_listings": 0}\n', encoding="utf-8")


def test_scrape_help_does_not_offer_daily(capsys):
    from scrape import main

    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0
    assert "--daily" not in capsys.readouterr().out


def test_daily_module_refuses_to_push_even_with_the_opt_in(tmp_path):
    with pytest.raises(RuntimeError, match="Refusing to push"):
        daily.push_daily_commit(tmp_path, _opt_in())
    with pytest.raises(RuntimeError, match="Refusing to commit"):
        daily.commit_daily_files(tmp_path, message="no")


def test_git_push_lives_only_in_the_opt_in_script():
    root = Path(__file__).resolve().parents[1]
    found = []
    for path in root.rglob("*.py"):
        if any(part in {".venv", "tests", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        if "git push" in text or '"push"' in text or "'push'" in text:
            found.append(path.relative_to(root).as_posix())
    assert found == ["examples/automation/daily_git_commit.py"]


def test_commit_daily_files_commits_only_the_memory_files(tmp_path):
    module = _load_automation()
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _write_daily_files(tmp_path)
    (tmp_path / "notes.txt").write_text("do not commit me\n", encoding="utf-8")

    module.commit_daily_files(tmp_path, message="Record the daily job search.")

    names = _git(tmp_path, "show", "--name-only", "--pretty=format:", "HEAD").stdout.split()
    assert set(names) == {
        "data/seen_jobs.json",
        "output/new_jobs.csv",
        "output/last_run.json",
    }
    status = _git(tmp_path, "status", "--short").stdout
    assert "notes.txt" in status
    assert "seen_jobs.json" not in status


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"daily_git": {}},
        {"daily_git": {"enabled": True}},
        {"daily_git": {"i_understand_this_is_public_if_repo_is_public": True}},
        {"daily_git": {"enabled": True, "i_understand_this_is_public_if_repo_is_public": False}},
        {
            "daily_git": {
                "enabled": "true",
                "i_understand_this_is_public_if_repo_is_public": "true",
            }
        },
    ],
)
def test_push_refuses_unless_both_flags_are_boolean_true(tmp_path, raw):
    module = _load_automation()
    with pytest.raises(RuntimeError, match="PRIVATE"):
        module.push_daily_commit(tmp_path, raw)


def test_push_with_opt_in_publishes_to_the_remote(tmp_path):
    module = _load_automation()
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    origin.mkdir()
    repo.mkdir()
    _git(origin, "init", "--bare")
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "remote", "add", "origin", origin.as_uri())
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "branch", "-M", "main")
    _write_daily_files(repo)

    module.push_daily_commit(repo, _opt_in())

    shown = _git(origin, "ls-tree", "-r", "--name-only", "main").stdout.split()
    assert "README.md" in shown


def test_cli_commits_and_pushes_when_opted_in(tmp_path, capsys):
    module = _load_automation()
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    origin.mkdir()
    repo.mkdir()
    _git(origin, "init", "--bare")
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "remote", "add", "origin", origin.as_uri())
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "branch", "-M", "main")
    _git(repo, "push", "-u", "origin", "HEAD")
    _write_daily_files(repo)
    config = repo / "config.yaml"
    config.write_text(
        "daily_git:\n"
        "  enabled: true\n"
        "  i_understand_this_is_public_if_repo_is_public: true\n",
        encoding="utf-8",
    )

    code = module.main(["--config", str(config), "--repo", str(repo)])

    assert code == 0
    shown = _git(origin, "ls-tree", "-r", "--name-only", "main").stdout
    assert "data/seen_jobs.json" in shown
    assert "output/new_jobs.csv" in shown
    assert "Only use with a PRIVATE repo; this publishes your job search history" in capsys.readouterr().out


def test_cli_refuses_before_git_add_when_the_opt_in_is_missing(tmp_path, capsys):
    module = _load_automation()
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _write_daily_files(repo)
    config = repo / "config.yaml"
    config.write_text("roles:\n  - Nurse\n", encoding="utf-8")

    code = module.main(["--config", str(config), "--repo", str(repo)])

    assert code == 2
    output = capsys.readouterr().out
    assert "Only use with a PRIVATE repo; this publishes your job search history" in output
    assert _git(repo, "log", "--oneline", check=False).returncode != 0
