"""Collect job postings and save them to a spreadsheet.

Run it from the project folder, after the libraries are installed:

    python scrape.py

To search for different roles or a different city, edit config.yaml.

A daily run that remembers what it has already seen:

    python scrape.py --daily

"""

from __future__ import annotations

import argparse
from pathlib import Path

from config import load_config
from daily import run_daily
from save_results import write_results
from sources import collect


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily", action="store_true")
    args = parser.parse_args()

    config = load_config("config.yaml")
    listings = collect(config)
    write_results(listings, Path("output"))

    if args.daily:
        run_daily()

if __name__ == "__main__":
    main()
