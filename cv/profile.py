"""Load the CV profile. This file is the only source of facts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


class ProfileError(ValueError):
    """The profile is missing or does not match the expected shape."""


@dataclass(frozen=True)
class Experience:
    employer: str
    title: str
    location: str
    start: str
    end: str
    bullets: tuple[str, ...]


@dataclass(frozen=True)
class Education:
    institution: str
    degree: str
    field: str
    start: str
    end: str


@dataclass(frozen=True)
class Skill:
    name: str
    evidence: str


@dataclass(frozen=True)
class LanguageSkill:
    name: str
    level: str


@dataclass(frozen=True)
class Certification:
    name: str
    issuer: str
    date: str


@dataclass(frozen=True)
class Link:
    label: str
    url: str


@dataclass(frozen=True)
class PersonalFields:
    include: bool
    date_of_birth: str
    nationality: str
    marital_status: str


@dataclass(frozen=True)
class Profile:
    full_name: str
    email: str
    phone: str
    location: str
    summary: str
    experience: tuple[Experience, ...]
    education: tuple[Education, ...]
    skills: tuple[Skill, ...]
    languages: tuple[LanguageSkill, ...]
    certifications: tuple[Certification, ...]
    links: tuple[Link, ...]
    photo_path: str
    photo_opt_in: bool
    personal: PersonalFields
    references_on_request: bool
    signature_place: str
    signature_opt_in: bool
    gdpr_consent: bool
    document_language: str


def load_profile(path: str | Path) -> Profile:
    """Read cv_profile.yaml. A missing file tells the person how to start."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ProfileError(
            "There is no CV profile yet. Copy profile/cv_profile.example.yaml "
            "to profile/cv_profile.yaml and write your own facts. "
            "The generator does not invent jobs, dates, or skills."
        )
    try:
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"Could not read the CV profile: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError("The CV profile should be a YAML mapping.")
    return profile_from_mapping(data, file_path)


def profile_from_mapping(data: dict, file_path: Path | None = None) -> Profile:
    contact = _mapping(data.get("contact"), "contact")
    full_name = _text(contact.get("full_name"))
    if not full_name:
        raise ProfileError("contact.full_name is required. The generator will not invent a name.")
    photo = data.get("photo") or {}
    if isinstance(photo, str):
        photo = {"path": photo, "include": False}
    if not isinstance(photo, dict):
        raise ProfileError("photo should be a mapping with path and include.")
    personal_raw = data.get("personal") or {}
    if not isinstance(personal_raw, dict):
        raise ProfileError("personal should be a mapping.")
    signature = data.get("signature") or {}
    if not isinstance(signature, dict):
        raise ProfileError("signature should be a mapping.")
    photo_path = _resolve_photo(_text(photo.get("path")), file_path)
    return Profile(
        full_name=full_name,
        email=_text(contact.get("email")),
        phone=_text(contact.get("phone")),
        location=_text(contact.get("location")),
        summary=_text(data.get("summary")),
        experience=_experience(data.get("experience")),
        education=_education(data.get("education")),
        skills=_skills(data.get("skills")),
        languages=_languages(data.get("languages")),
        certifications=_certifications(data.get("certifications")),
        links=_links(data.get("links")),
        photo_path=photo_path,
        photo_opt_in=_flag(photo.get("include")),
        personal=PersonalFields(
            include=_flag(personal_raw.get("include")),
            date_of_birth=_text(personal_raw.get("date_of_birth")),
            nationality=_text(personal_raw.get("nationality")),
            marital_status=_text(personal_raw.get("marital_status")),
        ),
        references_on_request=_flag(data.get("references_on_request")),
        signature_place=_text(signature.get("place")),
        signature_opt_in=_flag(signature.get("include")),
        gdpr_consent=_flag(data.get("gdpr_consent")),
        document_language=_text(data.get("document_language")) or "en",
    )


def profile_text(profile: Profile) -> str:
    """Every fact string, joined. Used to check that output stays inside the profile."""
    parts = [
        profile.full_name,
        profile.email,
        profile.phone,
        profile.location,
        profile.summary,
        profile.photo_path,
        profile.personal.date_of_birth,
        profile.personal.nationality,
        profile.personal.marital_status,
        profile.signature_place,
    ]
    for item in profile.experience:
        parts.extend(
            [item.employer, item.title, item.location, item.start, item.end, *item.bullets]
        )
    for item in profile.education:
        parts.extend([item.institution, item.degree, item.field, item.start, item.end])
    for item in profile.skills:
        parts.extend([item.name, item.evidence])
    for item in profile.languages:
        parts.extend([item.name, item.level])
    for item in profile.certifications:
        parts.extend([item.name, item.issuer, item.date])
    for item in profile.links:
        parts.extend([item.label, item.url])
    return "\n".join(part for part in parts if part)


def _experience(value: object) -> tuple[Experience, ...]:
    items = _optional_list(value, "experience")
    built = []
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise ProfileError(f"experience item {index} should be a mapping.")
        bullets = tuple(_text(bullet) for bullet in _optional_list(raw.get("bullets"), "bullets"))
        bullets = tuple(bullet for bullet in bullets if bullet)
        employer = _text(raw.get("employer"))
        title = _text(raw.get("title"))
        if not employer or not title or not bullets:
            raise ProfileError(
                f"experience item {index} needs an employer, a title, and at least one bullet."
            )
        built.append(
            Experience(
                employer=employer,
                title=title,
                location=_text(raw.get("location")),
                start=_text(raw.get("start")),
                end=_text(raw.get("end")),
                bullets=bullets,
            )
        )
    return tuple(built)


def _education(value: object) -> tuple[Education, ...]:
    built = []
    for index, raw in enumerate(_optional_list(value, "education"), start=1):
        if not isinstance(raw, dict):
            raise ProfileError(f"education item {index} should be a mapping.")
        institution = _text(raw.get("institution"))
        if not institution:
            raise ProfileError(f"education item {index} needs an institution.")
        built.append(
            Education(
                institution=institution,
                degree=_text(raw.get("degree")),
                field=_text(raw.get("field")),
                start=_text(raw.get("start")),
                end=_text(raw.get("end")),
            )
        )
    return tuple(built)


def _skills(value: object) -> tuple[Skill, ...]:
    built = []
    for index, raw in enumerate(_optional_list(value, "skills"), start=1):
        if not isinstance(raw, dict):
            raise ProfileError(f"skills item {index} should be a mapping.")
        name = _text(raw.get("name"))
        if not name:
            raise ProfileError(f"skills item {index} needs a name.")
        built.append(Skill(name=name, evidence=_text(raw.get("evidence"))))
    return tuple(built)


def _languages(value: object) -> tuple[LanguageSkill, ...]:
    built = []
    for index, raw in enumerate(_optional_list(value, "languages"), start=1):
        if not isinstance(raw, dict):
            raise ProfileError(f"languages item {index} should be a mapping.")
        name = _text(raw.get("name"))
        level = _text(raw.get("level")).upper()
        if not name or level not in CEFR_LEVELS:
            raise ProfileError(
                f"Language {name or index!r} needs a CEFR level "
                "(A1, A2, B1, B2, C1, or C2), not a free-text label."
            )
        built.append(LanguageSkill(name=name, level=level))
    return tuple(built)


def _certifications(value: object) -> tuple[Certification, ...]:
    built = []
    for index, raw in enumerate(_optional_list(value, "certifications"), start=1):
        if not isinstance(raw, dict):
            raise ProfileError(f"certifications item {index} should be a mapping.")
        name = _text(raw.get("name"))
        if not name:
            raise ProfileError(f"certifications item {index} needs a name.")
        built.append(
            Certification(
                name=name,
                issuer=_text(raw.get("issuer")),
                date=_text(raw.get("date")),
            )
        )
    return tuple(built)


def _links(value: object) -> tuple[Link, ...]:
    built = []
    for index, raw in enumerate(_optional_list(value, "links"), start=1):
        if not isinstance(raw, dict):
            raise ProfileError(f"links item {index} should be a mapping.")
        label = _text(raw.get("label"))
        url = _text(raw.get("url"))
        if not label or not url:
            raise ProfileError(f"links item {index} needs a label and a url.")
        built.append(Link(label=label, url=url))
    return tuple(built)


def _resolve_photo(path_text: str, file_path: Path | None) -> str:
    if not path_text:
        return ""
    raw = Path(path_text)
    if raw.is_file():
        return str(raw)
    if file_path is None:
        return path_text
    beside = file_path.parent / raw
    if beside.is_file():
        return str(beside)
    project = file_path.parent.parent / raw
    if project.is_file():
        return str(project)
    return path_text


def _optional_list(value: object, label: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProfileError(f"{label} should be a list.")
    return value


def _mapping(value: object, label: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProfileError(f"{label} should be a mapping.")
    return value


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y"}
    return bool(value)
