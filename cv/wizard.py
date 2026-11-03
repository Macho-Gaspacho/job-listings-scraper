"""Launcher question: search, make a CV, or answer the CV interview."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from cv.jobs import load_job_rows, select_job
from cv.presets import list_presets
from cv.suggest import suggest_format


CV_MENU_LABEL = "Make a CV for one of these jobs"
INTERVIEW_MENU_LABEL = "I don't have a CV yet - help me make one"


def run_launcher_menu(
    input_func,
    output,
    jobs_path,
    profile_path,
    output_dir,
    run_search,
    today: date | None = None,
    default_format: str | None = None,
) -> int:
    output("What do you want to do?")
    output("  1. Search for jobs")
    output(f"  2. {CV_MENU_LABEL}")
    output(f"  3. {INTERVIEW_MENU_LABEL}")
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
        if choice in {"3", "interview"}:
            from cv.interview import run_interview

            return run_interview(input_func, output, profile_path)
        output("Please type 1, 2, or 3.")


def _make_cv(input_func, output, jobs_path, profile_path, output_dir, today, default_format) -> int:
    from cv.cli import run_cv

    path = Path(profile_path)
    if not path.is_file():
        output("There is no CV profile yet.")
        output(INTERVIEW_MENU_LABEL)
        answer = input_func("Answer a few questions and save your answers? (Y/n) ").strip().lower()
        if answer not in {"", "y", "yes"}:
            output("Nothing was written. You can start the questions later.")
            return 1
        from cv.interview import run_interview

        code = run_interview(input_func, output, path)
        if code != 0 or not path.is_file():
            return code or 1
    jobs_file = Path(jobs_path)
    if not jobs_file.is_file():
        output(f"No jobs file at {jobs_file}. Search for jobs first.")
        return 1
    rows = load_job_rows(jobs_file)
    if not rows:
        output("The jobs file has no rows yet.")
        return 1
    output(CV_MENU_LABEL)
    for row in rows:
        output(f"  {row['row_number']}. {row.get('title', '')} — {row.get('company', '')}")
    picked = input_func("Which row number or URL? ").strip()
    if default_format:
        suggestion = default_format
        output(f"Using format {suggestion}.")
    else:
        try:
            suggestion = suggest_format(select_job(rows, picked))
        except LookupError:
            suggestion = "us_resume"
        output(f"Suggested format: {suggestion}")
    formats = ", ".join(list_presets())
    chosen = input_func(f"Format ({formats}) [{suggestion}] ").strip()
    return run_cv(
        picked,
        chosen or suggestion,
        jobs_file,
        path,
        output_dir,
        today=today,
    )
