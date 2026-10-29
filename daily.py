"""Commit the small set of files a daily run must keep.

A later run may happen on a new computer. The memory of listings already
seen has to be in the repository, not only on the computer that searched.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


# These three files are the whole daily record. Nothing else is committed.
DAILY_PATHS = (
    "data/seen_jobs.json",
    "output/new_jobs.csv",
    "output/last_run.json",
)


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run one git command in the project folder."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result


def commit_daily_files(repo_dir: str | Path, message: str) -> bool:
    """Commit the seen-jobs memory, the new-jobs sheet, and the run summary.

    Other changed files are left unstaged. Returns False when those three
    files are already committed and nothing in them changed.
    """
    repo = Path(repo_dir)
    missing = [path for path in DAILY_PATHS if not (repo / path).is_file()]
    if missing:
        raise RuntimeError("Missing daily files: " + ", ".join(missing))
    # -f adds the files even if an ignore rule would otherwise skip them.
    _git(repo, "add", "-f", "--", *DAILY_PATHS)
    staged = _git(repo, "diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        print("Daily files already match the last commit.")
        return False
    if staged.returncode != 1:
        detail = (staged.stderr or staged.stdout).strip()
        raise RuntimeError(f"git diff --cached failed: {detail}")
    _git(repo, "commit", "-m", message)
    print("Committed the daily files.")
    return True


def push_daily_commit(repo_dir: str | Path) -> None:
    """Publish the commit so a fresh computer can pull it.

    A dropped connection is retried. The waits are 4s, 8s, 16s, then 32s.
    """
    repo = Path(repo_dir)
    delays = (4, 8, 16, 32)
    last_error = "git push failed"
    for attempt in range(len(delays) + 1):
        result = _git(repo, "push", "-u", "origin", "HEAD", check=False)
        if result.returncode == 0:
            print("Pushed the daily files.")
            return
        last_error = (result.stderr or result.stdout).strip() or last_error
        if attempt == len(delays):
            break
        print(f"Push did not finish ({last_error}). Trying again.", flush=True)
        time.sleep(delays[attempt])
    raise RuntimeError(f"git push failed: {last_error}")
