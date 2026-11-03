"""Launcher question: search, or make a CV from a saved job row."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from cv.jobs import load_job_rows


CV_MENU_LABEL = "Make a CV for one of these jobs"
_FORMATS = "us_resume, uk_cv, de_lebenslauf, eu_europass, it_cv, fr_cv"


def run_launcher_menu(
    input_func,
    output,
    jobs_path,
    profile_path,
    output_dir,
    run_search,
    today: date | None = None,
    default_format: str = "us_resume",
) -> int:
    output("What do you want to do?")
    output("  1. Search for jobs")
    output(f"  2. {CV_MENU_LABEL}")
    while True:
        choice = input_func("> ").strip().lower()
        if choice in {"", "1", "search"}:
            return int(run_search())
        if choice in {"2", "cv"}:
            return _make_cv(
                input_func,
                output,
                jobs_path,
                profile_path,
                output_dir,
                today,
                default_format,
            )
        output("Please type 1 or 2.")


def _make_cv(input_func, output, jobs_path, profile_path, output_dir, today, default_format) -> int:
    from cv.cli import run_cv

    path = Path(jobs_path)
    if not path.is_file():
        output(f"No jobs file at {path}. Search for jobs first.")
        return 1
    rows = load_job_rows(path)
    if not rows:
        output("The jobs file has no rows yet.")
        return 1
    output(CV_MENU_LABEL)
    for row in rows:
        output(f"  {row['row_number']}. {row.get('title', '')} — {row.get('company', '')}")
    picked = input_func("Which row number or URL? ").strip()
    chosen = input_func(f"Format ({_FORMATS}) [{default_format}] ").strip()
    return run_cv(
        picked,
        chosen or default_format,
        path,
        profile_path,
        output_dir,
        today=today,
    )
