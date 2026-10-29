"""Commit and push the three files a daily run produces."""

from __future__ import annotations

import subprocess
from pathlib import Path


def commit_daily_files(repo_root: Path, message: str) -> None:
    """Stage the three daily files and commit them."""
    files = [
        "data/seen_jobs.json",
        "output/new_jobs.csv",
        "output/last_run.json",
    ]
    subprocess.run(["git", "add", *files], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_root, check=True)


def push_daily_commit(repo_root: Path) -> None:
    """Push the commit that holds the daily files."""
    subprocess.run(["git", "push"], cwd=repo_root, check=True)
