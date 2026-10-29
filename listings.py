"""Turn raw job postings into clean spreadsheet rows.

This file does not talk to Indeed or LinkedIn. It only cleans text,
drops duplicate links, and decides which rows are new.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable
from urllib.parse import urlparse, urlunparse


def clean_text(value: object) -> str:
    """Collapse whitespace and drop the odd control character."""
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(url: str) -> str:
    """Drop tracking parameters and a trailing slash, so the same ad is one link."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    # Keep the path, drop query and fragment.
    cleaned = urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    return cleaned.lower()


def identity_keys(row: dict) -> tuple[str, str]:
    """Two rows are the same job when the company and the title match, ignoring case."""
    company = clean_text(row.get("Company")).casefold()
    title = clean_text(row.get("Title")).casefold()
    return company, title


def dedupe(rows: Iterable[dict]) -> list[dict]:
    """Keep the first copy of each company + title pair."""
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for row in rows:
        key = identity_keys(row)
        if key in seen or key == ("", ""):
            continue
        seen.add(key)
        unique.append(row)
    return unique


def title_is_relevant(title: str, keywords: list[str]) -> bool:
    """True when the title contains one of the role keywords."""
    lowered = clean_text(title).casefold()
    return any(keyword.casefold() in lowered for keyword in keywords)


def apply_new_flags(rows: list[dict], seen_keys: set[tuple[str, str]]) -> list[dict]:
    """Mark each row New or Seen based on the memory file."""
    for row in rows:
        key = identity_keys(row)
        row["Status"] = "Seen" if key in seen_keys else "New"
    return rows


def sort_rows(rows: list[dict]) -> list[dict]:
    """New rows first, then by company, then by title."""
    return sorted(
        rows,
        key=lambda row: (
            row.get("Status") != "New",
            clean_text(row.get("Company")).casefold(),
            clean_text(row.get("Title")).casefold(),
        ),
    )
