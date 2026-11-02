"""Daily git publishing does not live here.

The script that can commit and push a job search is
examples/automation/daily_git_commit.py.

It refuses to push unless config.yaml sets both of these to true:

    daily_git:
      enabled: true
      i_understand_this_is_public_if_repo_is_public: true

Only use that script with a PRIVATE repo. It publishes your job search history.
A normal run of scrape.py keeps every file on your computer.
"""

from __future__ import annotations


def commit_daily_files(*_args, **_kwargs):
    """Refuse. Committing the search history is opt-in, in the example script."""
    raise RuntimeError(
        "Refusing to commit from daily.py. "
        "Use examples/automation/daily_git_commit.py, and only with a PRIVATE repo."
    )


def push_daily_commit(*_args, **_kwargs):
    """Refuse. Pushing the search history is opt-in, in the example script."""
    raise RuntimeError(
        "Refusing to push. Only use with a PRIVATE repo; this publishes your "
        "job search history. The opt-in lives in "
        "examples/automation/daily_git_commit.py and requires "
        "daily_git.enabled and daily_git.i_understand_this_is_public_if_repo_is_public."
    )
