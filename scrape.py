"""Collect job postings and save them to a spreadsheet.

Run it from the project folder, after the libraries are installed:

    python scrape.py

The first run asks a few questions and writes config.yaml.
To change the search later:

    python scrape.py --setup
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

if __name__ == "__main__" and sys.version_info < (3, 10):
    from environment import python_version_problem

    print(python_version_problem(sys.version_info))
    raise SystemExit(1)

from zoneinfo import ZoneInfo

try:
    import yaml

    import setup_wizard
    from boards import collect_board_listings
    from config import Settings, load_config
    from daily import commit_daily_files, push_daily_commit
    from environment import certificate_hint, python_version_problem
    from listings import apply_new_flags, dedupe, identity_keys, sort_rows, title_is_relevant
    from save_results import load_seen, save_seen, write_daily_files, write_outputs
    from sources import fetch_listings
except ModuleNotFoundError as exc:
    if __name__ == "__main__":
        from environment import missing_package_message

        print(missing_package_message(exc))
        raise SystemExit(1) from exc
    raise


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
        for site in settings.sites
    ]
    rows: list[dict] = []
    failures = 0
    for index, (role, place, site) in enumerate(searches):
        print(f'Searching {site} for "{role}" in {place.name}...', flush=True)
        try:
            found = fetch(role, place, site)
        except Exception as exc:
            failures += 1
            print(f"  Skipped ({exc}).", flush=True)
            hint = certificate_hint.note(exc)
            if hint:
                print(hint, flush=True)
            found = []
        else:
            phrases = (settings.title_keywords or {}).get(role, [])
            # Job sites return loosely related titles. When the config lists
            # phrases for this role, keep only titles that contain one of them.
            if settings.require_title_match and phrases:
                before = len(found)
                found = [
                    row
                    for row in found
                    if title_is_relevant(row.get("title", ""), phrases)
                ]
                print(
                    f"  Found {before}, kept {len(found)} with a matching title.",
                    flush=True,
                )
            else:
                print(f"  Found {len(found)}.", flush=True)
        rows.extend(found)
        # Wait between searches, but not after the last one.
        if settings.pause_seconds and index != len(searches) - 1:
            pause(settings.pause_seconds)
    return dedupe(rows), failures


def _run_search(config_path: Path, daily: bool) -> int:
    """Load a saved config, search, and write the spreadsheet."""
    project_dir = Path(__file__).resolve().parent
    try:
        settings = load_config(config_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Could not read the config file: {exc}")
        return 1

    seen = load_seen(settings.seen_file)
    board_rows, board_failures = collect_board_listings(settings)
    aggregator_rows: list[dict] = []
    aggregator_failures = 0
    if settings.sites:
        aggregator_rows, aggregator_failures = collect_listings(
            settings,
            lambda role, place, site: fetch_listings(settings, role, place, site),
        )
    # Dedupe again across company pages, remote boards, and Indeed/LinkedIn.
    rows = dedupe(board_rows + aggregator_rows)
    rows = sort_rows(apply_new_flags(rows, seen))
    write_outputs(rows, settings.csv_path, settings.excel_path)
    remembered = set(seen)
    for row in rows:
        remembered |= identity_keys(row)
    save_seen(settings.seen_file, remembered)

    # Rome time, so a morning run lines up with the clock in Milan.
    run_at = datetime.now(ZoneInfo("Europe/Rome"))
    new_csv = settings.output_dir / "new_jobs.csv"
    last_run = settings.output_dir / "last_run.json"
    summary = write_daily_files(rows, new_csv, last_run, run_at)
    print()
    print(f"Saved {len(rows)} listings ({summary['new_listings']} new).")
    print(f"Excel: {settings.excel_path}")
    print(f"CSV:   {settings.csv_path}")
    print(f"New since last run: {new_csv}")
    print(f"Run summary: {last_run}")
    if not rows:
        print(
            "No listings came back. Try a broader role, add a company in "
            "config.yaml, or raise posted_within_days."
        )
    failures = board_failures + aggregator_failures
    searches = len(settings.roles) * len(settings.places) * len(settings.sites)
    company_count = sum(1 for company in settings.companies or [] if company.enabled)
    attempts = searches + (company_count if settings.company_pages_enabled else 0)
    attempts += len(settings.remote_boards or [])
    if attempts and failures == attempts:
        print("Every search failed. Check your internet connection and config.yaml.")
        print("The daily files were written locally and were not committed.")
        return 1
    if daily:
        day = f"{run_at.day} {run_at.strftime('%B %Y')}"
        message = (
            f"Record the daily job search for {day}.\n\n"
            f"{summary['new_listings']} new listings out of {summary['total_listings']}."
        )
        try:
            commit_daily_files(project_dir, message)
            push_daily_commit(project_dir)
        except RuntimeError as exc:
            print(exc)
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Load the config, search, and write the spreadsheet. Returns a status code."""
    problem = python_version_problem(sys.version_info)
    if problem:
        print(problem)
        return 1

    project_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Collect job listings into a CSV file and an Excel file."
    )
    parser.add_argument(
        "--config",
        default=str(project_dir / "config.yaml"),
        help="Path to the settings file. The default is config.yaml next to this script.",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Answer a few questions and write config.yaml.",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help=(
            "After the search, commit and push the seen-jobs memory, "
            "the new-jobs sheet, and the run summary."
        ),
    )
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if args.setup or not config_path.exists():
        if not config_path.exists():
            print("There is no config.yaml yet. Answer a few questions and one will be created.")
        return setup_wizard.run_wizard(
            config_path,
            run_search=lambda path: _run_search(Path(path), daily=args.daily),
        )
    return _run_search(config_path, daily=args.daily)


if __name__ == "__main__":
    sys.exit(main())
