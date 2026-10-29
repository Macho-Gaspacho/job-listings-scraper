"""Main entry point for the job listings scraper.

Usage:
    python scrape.py          # normal run, writes CSV/XLSX locally
    python scrape.py --daily  # also commits and pushes seen state
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import load_config
from daily import git_commit_and_push
from save_results import save_csv, save_xlsx
from sources import run_all_sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape job listings")
    parser.add_argument("--daily", action="store_true", help="Commit and push seen state")
    args = parser.parse_args()

    config = load_config()
    results = run_all_sources(config)
    save_csv(results, "output/jobs.csv")
    save_xlsx(results, "output/jobs.xlsx")

    if args.daily:
        git_commit_and_push(
            ["data/seen_jobs.json", "output/new_jobs.csv", "output/last_run.json"],
            "Daily job scrape",
        )

if __name__ == "__main__":
    main()
