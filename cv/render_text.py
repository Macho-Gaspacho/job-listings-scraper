"""Markdown, HTML, the match report, and the cover-letter skeleton.

These renderers print facts from the profile and headings from the preset.
They do not add employers, dates, or skills from the job posting.
"""

from __future__ import annotations

from cv.presets import (
    field_label,
    format_date,
    include_photo,
    personal_fields_for,
    section_title,
)


WORDS_PER_PAGE = 400


def estimate_pages(text: str) -> int:
    """A rough page count. It is not a layout engine."""
    words = text.split()
    if not words:
        return 1
    return max(1, (len(words) + WORDS_PER_PAGE - 1) // WORDS_PER_PAGE)


def document_blocks(document) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for section in document.preset.section_order:
        blocks.extend(_section(document, section))
    return blocks


def render_markdown(document) -> str:
    lines = []
    for kind, text in document_blocks(document):
        if kind == "h1":
            lines.append(f"# {text}")
        elif kind == "h2":
            lines.append(f"## {text}")
        elif kind == "h3":
            lines.append(f"### {text}")
        elif kind == "bullet":
            lines.append(f"- {text}")
        elif kind == "image":
            lines.append(f"![]({text})")
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_html(document) -> str:
    escaped = (
        render_markdown(document).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return "<html><body><pre>\n" + escaped + "\n</pre></body></html>\n"


def render_cover_letter(document) -> str:
    """Name the vacancy from the job row, then quote facts from the profile."""
    profile = document.profile
    job = document.job
    lines = [
        profile.full_name,
        f"Applying for {job.get('title', '')} at {job.get('company', '')}.",
        "",
        profile.summary,
        "",
    ]
    for experience in document.experiences:
        for bullet in experience.bullets:
            lines.append(f"- {bullet.text}")
    lines.append("")
    for line in (profile.email, profile.phone, profile.location):
        if line:
            lines.append(line)
    return "\n".join(lines).strip() + "\n"


def render_match_report(document) -> str:
    """Gaps live here. They are not copied onto the CV."""
    report = document.report
    job = document.job
    lines = [
        "# Match report",
        "",
        "This is not part of the CV. Missing keywords are gaps. They were not added to the CV.",
        "",
        f"Job: {job.get('title', '')} — {job.get('company', '')}",
        "",
        "## Covered by your evidence",
    ]
    lines.extend(_bullets(report.covered))
    lines.extend(["", "## Missing (not added)"])
    lines.extend(_bullets(report.missing))
    lines.extend(["", "## Not selected from your profile"])
    lines.extend(_bullets(report.not_selected))
    if report.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in report.warnings)
    if document.preset.review_notes:
        lines.extend(["", "## Check these conventions"])
        lines.extend(f"- {note}" for note in document.preset.review_notes)
    return "\n".join(lines).strip() + "\n"


def _bullets(items: tuple[str, ...]) -> list[str]:
    if not items:
        return ["- None"]
    return [f"- {item}" for item in items]


def _section(document, section: str) -> list[tuple[str, str]]:
    preset = document.preset
    profile = document.profile
    title = section_title(preset, section)
    if section == "contact":
        return _contact(document)
    if section == "summary":
        if not profile.summary:
            return []
        return [("h2", title), ("p", profile.summary)]
    if section == "experience":
        return _experience(document, title)
    if section == "education":
        return _education(document, title)
    if section == "skills":
        return _skills(document, title)
    if section == "languages":
        return _languages(document, title)
    if section == "certifications":
        return _certifications(document, title)
    if section == "links":
        return _links(document, title)
    if section == "references":
        if not preset.references_line or not profile.references_on_request:
            return []
        return [("h2", title), ("p", preset.references_line)]
    if section == "consent":
        if not preset.consent_line or not profile.gdpr_consent:
            return []
        return [("p", preset.consent_line)]
    if section == "signature":
        if not preset.signature or not profile.signature_opt_in:
            return []
        blocks = [("h2", title)]
        if profile.signature_place:
            blocks.append(("p", profile.signature_place))
        blocks.append(("p", "Ort, Datum"))
        blocks.append(("p", "________________"))
        return blocks
    return []


def _contact(document) -> list[tuple[str, str]]:
    profile = document.profile
    blocks = [("h1", profile.full_name)]
    for line in (profile.email, profile.phone, profile.location):
        if line:
            blocks.append(("p", line))
    for field, value in personal_fields_for(document.preset, profile).items():
        blocks.append(("p", f"{field_label(document.preset, field)}: {value}"))
    if include_photo(document.preset, profile):
        blocks.append(("image", profile.photo_path))
    return blocks


def _experience(document, title: str) -> list[tuple[str, str]]:
    if not document.experiences:
        return []
    blocks = [("h2", title)]
    for item in document.experiences:
        experience = item.experience
        blocks.append(("h3", experience.title))
        blocks.append(("p", experience.employer))
        if experience.location:
            blocks.append(("p", experience.location))
        start = format_date(experience.start, document.preset)
        end = format_date(experience.end, document.preset)
        when = " – ".join(part for part in (start, end) if part)
        if when:
            blocks.append(("p", when))
        for bullet in item.bullets:
            blocks.append(("bullet", bullet.text))
    return blocks


def _education(document, title: str) -> list[tuple[str, str]]:
    if not document.profile.education:
        return []
    blocks = [("h2", title)]
    ordered = sorted(
        document.profile.education,
        key=lambda item: _end_key(item.end),
        reverse=True,
    )
    for item in ordered:
        if item.degree:
            blocks.append(("h3", item.degree))
        blocks.append(("p", item.institution))
        if item.field:
            blocks.append(("p", item.field))
        start = format_date(item.start, document.preset)
        end = format_date(item.end, document.preset)
        when = " – ".join(part for part in (start, end) if part)
        if when:
            blocks.append(("p", when))
    return blocks


def _skills(document, title: str) -> list[tuple[str, str]]:
    if not document.skills:
        return []
    blocks = [("h2", title)]
    for item in document.skills:
        if item.skill.evidence:
            blocks.append(("bullet", f"{item.skill.name} — {item.skill.evidence}"))
        else:
            blocks.append(("bullet", item.skill.name))
    return blocks


def _languages(document, title: str) -> list[tuple[str, str]]:
    languages = document.profile.languages
    if not languages:
        return []
    blocks = [("h2", title)]
    if document.preset.id == "eu_europass":
        # One overall CEFR level. Empty sub-skills are not filled in.
        blocks.append(("p", "Language | CEFR"))
        for language in languages:
            blocks.append(("p", f"{language.name} | {language.level}"))
        return blocks
    for language in languages:
        blocks.append(("bullet", f"{language.name} — {language.level}"))
    return blocks


def _certifications(document, title: str) -> list[tuple[str, str]]:
    items = document.profile.certifications
    if not items:
        return []
    blocks = [("h2", title)]
    for item in items:
        detail = item.name
        if item.issuer:
            detail = f"{detail} — {item.issuer}"
        if item.date:
            detail = f"{detail} ({format_date(item.date, document.preset)})"
        blocks.append(("bullet", detail))
    return blocks


def _links(document, title: str) -> list[tuple[str, str]]:
    if not document.profile.links:
        return []
    blocks = [("h2", title)]
    for link in document.profile.links:
        blocks.append(("p", f"{link.label}: {link.url}"))
    return blocks


def _end_key(value: str) -> int:
    from cv.presets import year_of

    year = year_of(value)
    if year is None:
        return 0
    return year
