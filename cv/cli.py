"""Write a tailored CV for one job row."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from pathlib import Path

from cv.jobs import load_job_rows, select_job
from cv.llm import llm_configured, rephrase_bullets
from cv.presets import load_preset
from cv.profile import ProfileError, load_profile
from cv.render_docx import libreoffice_pdf, render_docx
from cv.render_text import render_cover_letter, render_html, render_markdown, render_match_report
from cv.tailor import tailor


def output_filename(company: str, role: str, on_date: date) -> str:
    return f"CV_{_safe(company)}_{_safe(role)}_{on_date.isoformat()}"


def run_cv(
    row_or_url: str,
    fmt: str,
    jobs_path: str | Path,
    profile_path: str | Path,
    output_dir: str | Path,
    cover: bool = False,
    today: date | None = None,
) -> int:
    on_date = today or date.today()
    try:
        profile = load_profile(profile_path)
    except (OSError, ProfileError) as exc:
        print(exc)
        return 1
    jobs_file = Path(jobs_path)
    if not jobs_file.is_file():
        print(f"No jobs file at {jobs_file}. Run a search first, or pass --jobs.")
        return 1
    try:
        job = select_job(load_job_rows(jobs_file), row_or_url)
    except (OSError, LookupError) as exc:
        print(exc)
        return 1
    try:
        preset = load_preset(fmt)
    except ValueError as exc:
        print(exc)
        return 1
    document = _maybe_rephrase(tailor(profile, job, preset))
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stem = output_filename(str(job.get("company") or ""), str(job.get("title") or ""), on_date)
    docx_path = folder / f"{stem}.docx"
    render_docx(document, docx_path)
    (folder / f"{stem}.md").write_text(render_markdown(document), encoding="utf-8")
    (folder / f"{stem}.html").write_text(render_html(document), encoding="utf-8")
    (folder / f"{stem}_match.md").write_text(render_match_report(document), encoding="utf-8")
    print(f"Saved {docx_path}")
    print(f"Saved {folder / (stem + '.md')}")
    print(f"Match report: {folder / (stem + '_match.md')}")
    if cover:
        cover_name = f"Cover_{_safe(str(job.get('company') or ''))}_{_safe(str(job.get('title') or ''))}_{on_date.isoformat()}.md"
        cover_path = folder / cover_name
        cover_path.write_text(render_cover_letter(document), encoding="utf-8")
        print(f"Saved {cover_path}")
    pdf = libreoffice_pdf(docx_path)
    if pdf is not None:
        print(f"Saved {pdf}")
    return 0


def _maybe_rephrase(document):
    if not llm_configured():
        return document
    originals = [
        bullet.text for experience in document.experiences for bullet in experience.bullets
    ]
    if not originals:
        return document
    result = rephrase_bullets(originals, str(document.job.get("title") or ""), document.profile)
    if not result.used_llm:
        return document
    index = 0
    updated = []
    for experience in document.experiences:
        bullets = []
        for bullet in experience.bullets:
            bullets.append(replace(bullet, text=result.bullets[index]))
            index += 1
        updated.append(replace(experience, bullets=tuple(bullets)))
    report = replace(document.report, warnings=document.report.warnings + result.warnings)
    return replace(document, experiences=tuple(updated), report=report)


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE).strip("_")
    return cleaned or "Unknown"
