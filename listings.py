"""Turn raw job postings into clean spreadsheet rows.

This file does not talk to Indeed or LinkedIn. It only cleans text,
drops duplicate links, and decides which rows are new.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from listings import Listing


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def is_new(listing: Listing, seen: set[str]) -> bool:
    return listing.id not in seen


def mark_seen(listings: list[Listing], seen: set[str]) -> None:
    for listing in listings:
        seen.add(listing.id)


def to_row(listing: Listing, is_new_flag: bool) -> dict[str, Any]:
    return {
        "title": listing.title,
        "company": listing.company,
        "location": listing.location,
        "url": listing.url,
        "source": listing.source,
        "source_type": listing.source_type,
        "posted_at": listing.posted_at.isoformat() if listing.posted_at else "",
        "is_new": is_new_flag,
    }
