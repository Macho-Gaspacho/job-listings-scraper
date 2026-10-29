"""Tests for saving the daily-run memory into git. No job sites are contacted."""

import subprocess

from daily import commit_daily_files


def _git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def test_commit_daily_files_commits_only_the_memory_files(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "data" / "seen_jobs.json").write_text('{"seen_keys": ["url:https://example.com/a"]}\n', encoding="utf-8")
    (tmp_path / "output" / "new_jobs.csv").write_text("New since last run\n", encoding="utf-8")
    (tmp_path / "output" / "last_run.json").write_text('{"new_listings": 0}\n', encoding="utf-8")
    (tmp_path / "notes.txt").write_text("do not commit me\n", encoding="utf-8")

    commit_daily_files(tmp_path, message="Record the daily job search.")

    names = _git(tmp_path, "show", "--name-only", "--pretty=format:", "HEAD").stdout.split()
    assert set(names) == {
        "data/seen_jobs.json",
        "output/new_jobs.csv",
        "output/last_run.json",
    }
    status = _git(tmp_path, "status", "--short").stdout
    assert "notes.txt" in status
    assert "seen_jobs.json" not in status
