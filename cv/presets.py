"""Country and format presets. The YAML files decide layout, not the code."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from cv.profile import Profile


_PRESENT = {"present", "current", "now", "heute", "oggi", "aujourd'hui", "actuellement"}
_MONTHS = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_MONTHS_LONG = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True)
class Preset:
    id: str
    page_size: str
    max_pages: int
    extended_pages: int
    extended_after_years: int
    photo: str
    personal_fields: tuple[str, ...]
    date_format: str
    present_label: str
    chronology: str
    section_order: tuple[str, ...]
    section_titles: dict[str, dict[str, str]]
    field_labels: dict[str, dict[str, str]]
    language: str
    references_line: str
    signature: bool
    consent_line: str
    review_notes: tuple[str, ...]


def presets_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "cv_templates" / "presets"


def list_presets() -> list[str]:
    return sorted(path.stem for path in presets_dir().glob("*.yaml"))


def load_preset(name: str) -> Preset:
    path = presets_dir() / f"{name}.yaml"
    if not path.is_file():
        known = ", ".join(list_presets()) or "none"
        raise ValueError(f"Unknown CV format {name!r}. Known formats: {known}.")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} should be a YAML mapping.")
    titles = data.get("section_titles") or {}
    labels = data.get("field_labels") or {}
    language = str(data.get("language") or "en")
    if language not in titles:
        raise ValueError(f"{path.name} needs section titles for {language!r}.")
    photo = str(data.get("photo") or "forbidden")
    if photo not in {"forbidden", "optional", "customary"}:
        raise ValueError(f"{path.name} has an unknown photo policy {photo!r}.")
    page_size = str(data.get("page_size") or "a4")
    if page_size not in {"a4", "letter"}:
        raise ValueError(f"{path.name} has an unknown page size {page_size!r}.")
    return Preset(
        id=str(data.get("id") or name),
        page_size=page_size,
        max_pages=int(data.get("max_pages") or 1),
        extended_pages=int(data.get("extended_pages") or data.get("max_pages") or 1),
        extended_after_years=int(data.get("extended_after_years") or 0),
        photo=photo,
        personal_fields=tuple(data.get("personal_fields") or ()),
        date_format=str(data.get("date_format") or "yyyy-mm"),
        present_label=str(data.get("present_label") or "Present"),
        chronology=str(data.get("chronology") or "reverse"),
        section_order=tuple(data.get("section_order") or ()),
        section_titles={key: dict(value) for key, value in titles.items()},
        field_labels={key: dict(value) for key, value in labels.items()},
        language=language,
        references_line=str(data.get("references_line") or ""),
        signature=bool(data.get("signature")),
        consent_line=str(data.get("consent_line") or ""),
        review_notes=tuple(str(note) for note in (data.get("review_notes") or ())),
    )


def section_title(preset: Preset, section: str) -> str:
    """Titles follow the preset language so a Lebenslauf stays German."""
    titles = preset.section_titles.get(preset.language) or {}
    return titles.get(section, section)


def field_label(preset: Preset, field: str) -> str:
    labels = preset.field_labels.get(preset.language) or preset.field_labels.get("en") or {}
    return labels.get(field, field)


def career_years(profile: Profile) -> int:
    """Years from the earliest start to the latest end. Overlaps are not double-counted."""
    starts = []
    ends = []
    for item in profile.experience:
        start = year_of(item.start)
        if start is None:
            continue
        end = year_of(item.end)
        if end is None:
            end = date.today().year
        starts.append(start)
        ends.append(end)
    if not starts:
        return 0
    return max(0, max(ends) - min(starts))


def page_limit(preset: Preset, profile: Profile) -> int:
    if preset.extended_after_years and career_years(profile) >= preset.extended_after_years:
        return preset.extended_pages
    return preset.max_pages


def include_photo(preset: Preset, profile: Profile) -> bool:
    """A photo is never required. Forbidden presets drop it even when the file exists."""
    if preset.photo == "forbidden":
        return False
    if preset.photo not in {"optional", "customary"}:
        return False
    if not profile.photo_opt_in or not profile.photo_path:
        return False
    return Path(profile.photo_path).is_file()


def personal_fields_for(preset: Preset, profile: Profile) -> dict[str, str]:
    """Personal data is included only when the preset allows it and the user opted in."""
    if not profile.personal.include:
        return {}
    chosen = {}
    for field in preset.personal_fields:
        value = getattr(profile.personal, field, "") or ""
        if value:
            chosen[field] = value
    return chosen


def year_of(value: str) -> int | None:
    text = (value or "").strip()
    if not text or text.casefold() in _PRESENT:
        return None
    match = re.search(r"(?:19|20)\d{2}", text)
    if match is None:
        return None
    return int(match.group())


def format_date(value: str, preset: Preset) -> str:
    """Format a date the user already wrote. A bare year stays a year."""
    text = (value or "").strip()
    if not text:
        return ""
    if text.casefold() in _PRESENT:
        return preset.present_label
    year = year_of(text)
    month = _month_of(text)
    if year is None:
        return text
    if month is None:
        return str(year)
    if preset.date_format == "mon_yyyy":
        return f"{_MONTHS[month]} {year}"
    if preset.date_format == "month_yyyy":
        return f"{_MONTHS_LONG[month]} {year}"
    if preset.date_format == "mm.yyyy":
        return f"{month:02d}.{year}"
    if preset.date_format == "mm/yyyy":
        return f"{month:02d}/{year}"
    return f"{year}-{month:02d}"


def _month_of(value: str) -> int | None:
    match = re.search(r"(?:19|20)\d{2}[-/.](\d{1,2})", value.strip())
    if match is None:
        match = re.search(r"(\d{1,2})[-/.](?:19|20)\d{2}", value.strip())
    if match is None:
        return None
    month = int(match.group(1))
    if 1 <= month <= 12:
        return month
    return None
