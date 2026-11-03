"""Optional rephrasing through the user's own OpenAI-compatible endpoint.

Off unless CV_LLM_API_KEY and CV_LLM_BASE_URL are both set.
The request contains bullet text and the job title only.
Photo, date of birth, and contact details are not sent.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass

from cv.profile import Profile, profile_text


# Closed-class words a rephrase may add. Content words must already be in the profile.
_GLUE = frozenset(
    """
    a an the and or but if in on at to for of as by with from into over per via
    this that these those who which what when where while than then also both
    each such only other more most less not no nor so our your their its you we
    they i he she it my me your our during before after across within without
    about
    """.split()
)

_SYSTEM = (
    "You rephrase CV bullets. Hard rule: use only the facts provided. "
    "Do not add employers, dates, numbers, tools, skills, degrees, or certifications "
    "that are not written in the bullets. "
    "Return a JSON array of strings, one per bullet, in the same order."
)


@dataclass(frozen=True)
class RephraseResult:
    bullets: tuple[str, ...]
    warnings: tuple[str, ...]
    used_llm: bool


def llm_configured() -> bool:
    return bool(os.environ.get("CV_LLM_API_KEY", "").strip()) and bool(
        os.environ.get("CV_LLM_BASE_URL", "").strip()
    )


def rephrase_bullets(bullets, job_title: str, profile: Profile, opener=None) -> RephraseResult:
    """Rephrase bullets. Any ungrounded reply is thrown away and the original is kept."""
    originals = tuple(str(bullet) for bullet in bullets)
    if not llm_configured():
        return RephraseResult(originals, (), False)
    if opener is None:
        opener = urllib.request.urlopen
    try:
        content = _request(opener, originals, job_title)
    except Exception as exc:
        warning = f"LLM request failed ({exc.__class__.__name__}). Kept the original bullets."
        return RephraseResult(originals, (warning,), True)
    parsed = _parse_list(content)
    if parsed is None or len(parsed) != len(originals):
        warning = "LLM reply was not a JSON list of the same length. Kept the original bullets."
        return RephraseResult(originals, (warning,), True)
    kept = []
    warnings = []
    for source, candidate in zip(originals, parsed):
        bad = ungrounded_tokens(candidate, profile)
        if not candidate.strip() or bad:
            kept.append(source)
            shown = ", ".join(bad) if bad else "empty reply"
            warnings.append(
                "Rejected an LLM bullet because it was not grounded in the profile "
                f"({shown}). Kept the original."
            )
        else:
            kept.append(candidate.strip())
    return RephraseResult(tuple(kept), tuple(warnings), True)


def ungrounded_tokens(candidate: str, profile: Profile) -> list[str]:
    """Numbers and words that are neither glue nor written in the profile."""
    raw = profile_text(profile)
    allowed_words = {token.casefold() for token in re.findall(r"[A-Za-z][A-Za-z0-9+#]*", raw)}
    allowed_words |= _GLUE
    allowed_numbers = set(re.findall(r"\d+", raw))
    bad = []
    for number in re.findall(r"\d+", candidate):
        if number not in allowed_numbers:
            bad.append(number)
    for word in re.findall(r"[A-Za-z][A-Za-z0-9+#]*", candidate):
        if word.casefold() not in allowed_words:
            bad.append(word)
    return bad


def _request(opener, bullets: tuple[str, ...], job_title: str) -> str:
    key = os.environ["CV_LLM_API_KEY"].strip()
    base = os.environ["CV_LLM_BASE_URL"].strip()
    # Job title and bullets only. Contact, photo, and date of birth stay on this computer.
    user = json.dumps(
        {"job_title": job_title, "bullets": list(bullets)},
        ensure_ascii=False,
    )
    payload = {
        "model": os.environ.get("CV_LLM_MODEL", "gpt-4o-mini"),
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
    }
    request = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with opener(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    return str(body["choices"][0]["message"]["content"])


def _parse_list(content: str) -> list[str] | None:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list) and all(isinstance(item, str) for item in data):
        return data
    return None
