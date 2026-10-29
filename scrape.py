"""Collect job postings and save them to a spreadsheet.

Run it from the project folder, after the libraries are installed:

    python scrape.py

To search for different roles or a different city, edit config.yaml.
You do not need to change this file for ordinary use.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from boards import collect_board_listings
from config import Settings, load_config
from daily import commit_daily_files, push_daily_commit
from listings import apply_new_flags, dedupe, identity_keys, sort_rows, title_is_relevant
from save_results import load_seen, save_seen, write_daily_files, write_outputs
from sources import fetch_listings


def collect_listings(settings: Settings, fetch, pause=time.sleep) -> tuple[list[dict], int]:
    """Search every role, place, and site.

    `fetch(role, place, site)` returns rows, or raises if that one search
    fails. One failure does not throw away the listings already collected.
    The pause between searches is there so we do not hammer the sites.
    """
    searches = [
        (role, place, site)
        for role in settings.roles
        for place in settings.places
        for site in settings.companies + settings.boards
        if site.get("enabled", True)
    ]
    rows: list[dict] = []
    failed = 0
    for role, place, site in searches:
        try:
            found = fetch(role, place, site)
            rows.extend(found)
        except Exception:
            failed += 1
        pause(settings.pause_seconds)
    return rows, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect job listings.")
    parser.add_argument("--daily", action="store_true", help="Commit and push the daily files.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    args = parser.parse_args(argv)

    settings = load_config(args.config)
    seen_path = Path("data/seen_jobs.json")
    output_dir = Path("output")
    seen = load_seen(seen_path)

    def fetch(role: str, place: str, site: dict) -> list[dict]:
        if site.get("type") == "board":
            return collect_board_listings(role, place, site)
        return fetch_listings(role, place, site, requests_get)

    rows, failed = collect_listings(settings, fetch)
    rows = dedupe(rows)
    rows = apply_new_flags(rows, seen)
    rows = sort_rows(rows)
    now = datetime.now(ZoneInfo("Europe/Rome")).isoformat(timespec="seconds")
    for row in rows:
        row["Date found"] = now

    write_outputs(rows, output_dir)
    save_seen(seen_path, rows)
    if args.daily:
        write_daily_files(rows, output_dir, seen_path)
        commit_daily_files(Path("."), f"Daily run {now}")
        push_daily_commit(Path("."))

    print(f"Found {len(rows)} listings, {failed} sources failed.")
    return 0


def requests_get(url: str):
    import requests
    return requests.get(url, timeout=20, headers={"User-Agent": "job-listings-scraper/1.0"})


if __name__ == "__main__":
    raise SystemExit(main())
