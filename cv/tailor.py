"""Pick and reorder profile facts that overlap a job. Never add new ones."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from matching import normalise

from cv.presets import Preset, page_limit, year_of
from cv.profile import Experience, Profile, Skill


# Job ads are full of glue. These tokens are not skills and are not reported as gaps.
_STOPWORDS = frozenset(
    """
    a an the and or but if in on at to for of as by with from into over per via
    this that these those who which what when where while than then also both
    each such only other more most less not no nor so our your their its you we
    they he she it my me our are was were is be been being have has had will
    can may must should would could about across within without using use used
    including include required requirement requirements year years experience
    experienced looking role roles team work working job jobs ability able
    strong good great well new full time position candidate applicants applicant
    und mit der die das ein eine von den dem im zu auf ist sie wir fur fur
    les des une est pour dans avec par sur qui que pas plus une des
    che con per del della una non sono nel alla degli delle
    the a an and or but
    """.split()
)


@dataclass(frozen=True)
class ScoredBullet:
    text: str
    score: int
    hits: tuple[str, ...]


@dataclass(frozen=True)
class ScoredExperience:
    experience: Experience
    bullets: tuple[ScoredBullet, ...]
    score: int


@dataclass(frozen=True)
class ScoredSkill:
    skill: Skill
    score: int
    hits: tuple[str, ...]


@dataclass(frozen=True)
class MatchReport:
    job_keywords: tuple[str, ...]
    covered: tuple[str, ...]
    missing: tuple[str, ...]
    not_selected: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class TailoredDocument:
    profile: Profile
    job: dict
    preset: Preset
    experiences: tuple[ScoredExperience, ...]
    skills: tuple[ScoredSkill, ...]
    report: MatchReport


def extract_keywords(*parts: object) -> tuple[str, ...]:
    """Whole words from the posting, plus numbers such as years asked for."""
    seen: list[str] = []
    folded: set[str] = set()
    for part in parts:
        text = "" if part is None else str(part)
        for token in normalise(text):
            if len(token) < 3 or token in _STOPWORDS or token in folded:
                continue
            folded.add(token)
            seen.append(token)
        for number in re.findall(r"\d+", text):
            if number not in folded:
                folded.add(number)
                seen.append(number)
    return tuple(seen)


def tailor(profile: Profile, job: dict, preset: Preset) -> TailoredDocument:
    keywords = extract_keywords(job.get("title"), job.get("description"), job.get("languages"))
    experiences, skipped_bullets = _select_experience(profile, keywords, preset)
    skills, skipped_skills = _select_skills(profile, keywords)
    covered, missing = _coverage(profile, keywords)
    not_selected = tuple(skipped_bullets + skipped_skills)
    document = TailoredDocument(
        profile=profile,
        job=job,
        preset=preset,
        experiences=tuple(experiences),
        skills=tuple(skills),
        report=MatchReport(
            job_keywords=keywords,
            covered=covered,
            missing=missing,
            not_selected=not_selected,
            warnings=(),
        ),
    )
    return _with_page_warning(document)


def _select_experience(profile: Profile, keywords: tuple[str, ...], preset: Preset):
    scored = []
    any_hit = False
    for role_index, experience in enumerate(profile.experience):
        bullets = []
        for bullet_index, text in enumerate(experience.bullets):
            score, hits = _score(text, keywords)
            bullets.append((bullet_index, ScoredBullet(text=text, score=score, hits=hits)))
            any_hit = any_hit or score > 0
        scored.append((role_index, experience, bullets))
    chosen = []
    skipped = []
    for role_index, experience, bullets in scored:
        ordered = sorted(bullets, key=lambda item: (-item[1].score, item[0]))
        if any_hit:
            kept = tuple(bullet for _index, bullet in ordered if bullet.score > 0)
            for _index, bullet in ordered:
                if bullet.score == 0:
                    skipped.append(bullet.text)
        else:
            kept = tuple(bullet for _index, bullet in ordered)
        if not kept:
            skipped.append(f"{experience.title}, {experience.employer}")
            continue
        role_score = max(bullet.score for bullet in kept)
        chosen.append(
            (
                role_index,
                ScoredExperience(experience=experience, bullets=kept, score=role_score),
            )
        )
    if preset.chronology == "reverse":
        chosen.sort(key=lambda item: (-_end_sort(item[1].experience), item[0]))
    return [item for _index, item in chosen], skipped


def _select_skills(profile: Profile, keywords: tuple[str, ...]):
    scored = []
    any_hit = False
    for index, skill in enumerate(profile.skills):
        text = f"{skill.name} {skill.evidence}".strip()
        score, hits = _score(text, keywords)
        any_hit = any_hit or score > 0
        scored.append((index, ScoredSkill(skill=skill, score=score, hits=hits)))
    if not any_hit:
        return [item for _index, item in scored], []
    kept = []
    skipped = []
    for index, item in sorted(scored, key=lambda pair: (-pair[1].score, pair[0])):
        if item.score > 0:
            kept.append(item)
        else:
            label = item.skill.name
            if item.skill.evidence:
                label = f"{label} — {item.skill.evidence}"
            skipped.append(label)
    return kept, skipped


def _coverage(profile: Profile, keywords: tuple[str, ...]):
    tokens: set[str] = set()
    chunks = [profile.summary]
    for item in profile.experience:
        chunks.extend(
            [item.employer, item.title, item.location, item.start, item.end, *item.bullets]
        )
    for item in profile.education:
        chunks.extend([item.institution, item.degree, item.field, item.start, item.end])
    for item in profile.skills:
        chunks.extend([item.name, item.evidence])
    for item in profile.languages:
        chunks.extend([item.name, item.level])
    for item in profile.certifications:
        chunks.extend([item.name, item.issuer, item.date])
    for chunk in chunks:
        tokens.update(normalise(chunk))
        tokens.update(re.findall(r"\d+", chunk))
    covered = tuple(keyword for keyword in keywords if keyword in tokens)
    missing = tuple(keyword for keyword in keywords if keyword not in tokens)
    return covered, missing


def _score(text: str, keywords: tuple[str, ...]) -> tuple[int, tuple[str, ...]]:
    tokens = set(normalise(text))
    tokens.update(re.findall(r"\d+", text))
    hits = tuple(keyword for keyword in keywords if keyword in tokens)
    return len(hits), hits


def _end_sort(experience: Experience) -> int:
    """Present roles sort first. A missing end year sorts as today inside year_of's caller."""
    year = year_of(experience.end)
    if year is None and (experience.end or "").strip().casefold() in {
        "",
        "present",
        "current",
        "now",
    }:
        return 9999
    return year or 0


def _with_page_warning(document: TailoredDocument) -> TailoredDocument:
    from cv.render_text import estimate_pages, render_markdown

    pages = estimate_pages(render_markdown(document))
    limit = page_limit(document.preset, document.profile)
    if pages <= limit:
        return document
    warning = (
        f"This CV is estimated at {pages} pages. The {document.preset.id} preset allows {limit}. "
        "Shorten it by removing facts you wrote. Nothing was invented to fit the page."
    )
    report = replace(document.report, warnings=document.report.warnings + (warning,))
    return replace(document, report=report)
