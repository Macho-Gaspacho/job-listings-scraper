"""Daily run helpers: commit and push seen state.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_commit_and_push(files: list[str], message: str) -> None:
    subprocess.run(["git", "add", *files], check=True)
    subprocess.run(["git", "commit", "-m", message], check=True)
    subprocess.run(["git", "push"], check=True)
