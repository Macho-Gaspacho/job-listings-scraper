"""Publish the daily job-search files with git.

WARNING: Only use with a PRIVATE repo; this publishes your job search history.

If the repository is public, anyone can see the roles, cities, and listings
from your search. The normal commands do not commit or push anything:

    python scrape.py
    start.bat
    start.command

This script refuses to push unless config.yaml contains exactly:

    daily_git:
      enabled: true
      i_understand_this_is_public_if_repo_is_public: true

Both values must be the boolean true. The words "true" in quotes do not count.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import yaml


WARNING = (
    "WARNING: Only use with a PRIVATE repo; this publishes your job search history."
)

# These three files are the whole daily record. Nothing else is committed.
DAILY_PATHS = (
    "data/seen_jobs.json",
    "output/new_jobs.csv",
    "output/last_run.json",
)


def daily_git_opt_in(raw: object) -> bool:
    """True only when both opt-in flags are the boolean true."""
    if not isinstance(raw, dict):
        return False
    block = raw.get("daily_git")
    if not isinstance(block, dict):
        return False
    return (
        block.get("enabled") is True
        and block.get("i_understand_this_is_public_if_repo_is_public") is True
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


def push_daily_commit(repo_dir: str | Path, raw_config: object) -> None:
    """Publish the commit so another computer can pull it.

    Refuses unless the config opts in. A dropped connection is retried.
    The waits are 4s, 8s, 16s, then 32s.
    """
    if not daily_git_opt_in(raw_config):
        raise RuntimeError(
            "Refusing to push. Only use with a PRIVATE repo; this publishes "
            "your job search history. Set daily_git.enabled and "
            "daily_git.i_understand_this_is_public_if_repo_is_public to true "
            "in config.yaml to opt in."
        )
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


def main(argv: list[str] | None = None) -> int:
    """Commit and push the daily files when the config opts in."""
    print(WARNING)
    parser = argparse.ArgumentParser(
        description=(
            "Commit and push the daily job-search files. "
            + WARNING
        )
    )
    parser.add_argument(
        "--config",
        default="",
        help="Path to config.yaml. The default is config.yaml in the project folder.",
    )
    parser.add_argument(
        "--repo",
        default="",
        help="Project folder. The default is the folder that contains this script's parent examples directory.",
    )
    args = parser.parse_args(argv)
    repo = Path(args.repo) if args.repo else Path(__file__).resolve().parents[2]
    config_path = Path(args.config) if args.config else repo / "config.yaml"
    if not config_path.is_file():
        print("Refusing to push. There is no config file to read the opt-in from.")
        return 2
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not daily_git_opt_in(loaded):
        print(
            "Refusing to push. Set daily_git.enabled and "
            "daily_git.i_understand_this_is_public_if_repo_is_public to true "
            "in config.yaml. Only use with a PRIVATE repo; this publishes "
            "your job search history."
        )
        return 2
    try:
        commit_daily_files(repo, "Record the daily job search.")
        push_daily_commit(repo, loaded)
    except RuntimeError as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
