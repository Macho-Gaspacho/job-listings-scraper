"""Turn raw job postings into clean spreadsheet rows.

This file does not talk to Indeed or LinkedIn. It only cleans text,
drops duplicate links, and decides which rows are new.
"""

from __future__ import annotations

import re


# The spreadsheet columns, in order. The first name is the key used in code.
# The second name is the heading a person sees in Excel.
OUTPUT_FIELDS = [
    ("is_new", "New since last run"),
    ("title", "Title"),
    ("company", "Company"),
    ("location", "Location"),
    ("date_posted", "Date posted"),
    ("source", "Source"),
    ("source_type", "Source type"),
    ("url", "URL"),
    ("description", "Description"),
    ("role_searched", "Role searched"),
    ("place_searched", "Place searched"),
]


def _missing(value: object) -> bool:
    """True for None and for the NaN value pandas uses for empty cells."""
    return value is None or (isinstance(value, float) and value != value)


def clean_text(value: object) -> str:
    """A single-line string, or a blank string when the site sent nothing."""
    if _missing(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    return text


def snippet(value: object, limit: int = 280) -> str:
    """A short plain-text preview of a job description.

    Job sites send HTML or Markdown. Excel is easier to scan when that
    is flattened to one paragraph and cut on a word boundary.
    """
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    # Keep one character free for the ellipsis, and don't cut mid-word
    # when the cut lands in the middle of a word.
    window = text[: max(limit - 1, 1)]
    if len(text) > len(window) and text[len(window)] != " " and " " in window:
        window = window.rsplit(" ", 1)[0]
    return window.rstrip() + "…"


def date_text(value: object) -> str:
    """YYYY-MM-DD, or blank when the site did not give a date."""
    if _missing(value):
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    text = clean_text(value)
    return text[:10]


def normalize_url(url: object) -> str:
    """The same link written the same way, so duplicates can be spotted.

    Fragments (#apply) and a trailing slash are ignored. The query string
    is kept, because Indeed puts the job id there (?jk=...).
    """
    text = clean_text(url)
    if not text:
        return ""
    return text.split("#", 1)[0].rstrip("/").lower()


# Least crowded source wins when the same role is posted in more than one place.
SOURCE_RANK = {
    "company site": 0,
    "startup board": 1,
    "remote board": 2,
    "aggregator": 3,
}

# Words that are not part of a company name. "Satispay S.r.l." and "Satispay"
# are the same employer.
_COMPANY_SUFFIXES = (
    "srl",
    "spa",
    "ltd",
    "limited",
    "inc",
    "gmbh",
    "sas",
    "bv",
    "se",
    "plc",
    "llc",
    "ag",
)


def _words(value: object) -> str:
    return " ".join(clean_text(value).lower().split())


def company_name_key(value: object) -> str:
    """Lowercase company name without legal suffixes or punctuation."""
    text = _words(value).replace(".", "")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    parts = [part for part in text.split() if part not in _COMPANY_SUFFIXES]
    return " ".join(parts)


def title_company_key(row: dict) -> str:
    """Same job title at the same company, ignoring the website it came from."""
    title = _words(row.get("title"))
    company = company_name_key(row.get("company"))
    if not title or not company:
        return ""
    return f"role:{title}|{company}"


def listing_key(row: dict) -> str:
    """A stable id for one posting.

    The link is the best id. When a site does not give one, the title,
    company, and location together stand in for it.
    """
    url = normalize_url(row.get("url") or row.get("job_url"))
    if url:
        return "url:" + url
    parts = [
        _words(row.get("title")),
        _words(row.get("company")),
        _words(row.get("location")),
    ]
    return "text:" + "|".join(parts)


def identity_keys(row: dict) -> set[str]:
    """Every id that should count as 'already seen' for this row.

    A merged row remembers the link from each source, plus title + company,
    so the same role is not marked new just because a second site listed it.
    """
    stored = row.get("_keys")
    if stored:
        return set(stored)
    keys = set()
    url = normalize_url(row.get("url") or row.get("job_url"))
    if url:
        keys.add("url:" + url)
    role_key = title_company_key(row)
    if role_key:
        keys.add(role_key)
    if not keys:
        keys.add(listing_key(row))
    return keys


def row_from_hit(hit: dict, role: str, place: str, snippet_characters: int) -> dict | None:
    """Map one result from python-jobspy into a spreadsheet row."""
    title = clean_text(hit.get("title"))
    if not title:
        return None
    return {
        "title": title,
        "company": clean_text(hit.get("company")),
        "location": clean_text(hit.get("location")),
        "date_posted": date_text(hit.get("date_posted")),
        "source": clean_text(hit.get("source") or hit.get("site")),
        "source_type": clean_text(hit.get("source_type")) or "aggregator",
        "url": clean_text(hit.get("url") or hit.get("job_url")),
        "description": snippet(hit.get("description"), snippet_characters),
        "role_searched": role,
        "place_searched": place,
    }


def _join_unique(existing: str, extra: str, separator: str) -> str:
    """Append a value that is not already in a joined list."""
    parts = [part.strip() for part in (existing or "").split(separator) if part.strip()]
    for piece in [part.strip() for part in (extra or "").split(separator) if part.strip()]:
        if piece not in parts:
            parts.append(piece)
    return separator.join(parts)


def _merge_rows(current: dict, incoming: dict) -> dict:
    """Keep the less crowded source, and remember both links."""
    current_rank = SOURCE_RANK.get(current.get("source_type") or "aggregator", 9)
    incoming_rank = SOURCE_RANK.get(incoming.get("source_type") or "aggregator", 9)
    if incoming_rank < current_rank:
        winner, other = incoming, current
    else:
        winner, other = current, incoming
    merged = dict(winner)
    merged["role_searched"] = _join_unique(
        winner.get("role_searched", ""), other.get("role_searched", ""), "; "
    )
    merged["place_searched"] = _join_unique(
        winner.get("place_searched", ""), other.get("place_searched", ""), "; "
    )
    merged["source"] = _join_unique(winner.get("source", ""), other.get("source", ""), ", ")
    if len(other.get("description") or "") > len(merged.get("description") or ""):
        merged["description"] = other["description"]
    if not merged.get("date_posted") and other.get("date_posted"):
        merged["date_posted"] = other["date_posted"]
    merged["_keys"] = identity_keys(current) | identity_keys(incoming) | identity_keys(merged)
    return merged


def dedupe(rows: list[dict]) -> list[dict]:
    """Keep one row per link, and one row per title + company.

    The same posting is often found by more than one role, and the same
    role is often listed on Indeed and on the company's own site. The
    company site is kept when both exist, because that is where you apply.
    """
    kept: list[dict] = []
    position: dict[str, int] = {}
    for row in rows:
        keys = identity_keys(row)
        found = next((position[key] for key in keys if key in position), None)
        if found is not None:
            kept[found] = _merge_rows(kept[found], row)
            for key in identity_keys(kept[found]):
                position[key] = found
            continue
        stored = dict(row)
        stored["_keys"] = keys
        index = len(kept)
        kept.append(stored)
        for key in keys:
            position[key] = index
    return kept


def apply_new_flags(rows: list[dict], seen: set[str]) -> list[dict]:
    """Mark rows that were not saved on an earlier run.

    A row is not new when its link was saved before, or when the same
    title and company were saved from another site.
    """
    flagged = []
    for row in rows:
        updated = dict(row)
        updated["is_new"] = "no" if identity_keys(updated) & seen else "yes"
        flagged.append(updated)
    return flagged


def roles_for_title(title: str, roles: list[str], keywords: dict[str, list[str]] | None, require_match: bool) -> list[str]:
    """Which configured roles this title belongs to.

    With the filter on, a title must contain a phrase for that role.
    A title can match more than one role.
    """
    matched = []
    table = keywords or {}
    for role in roles:
        phrases = table.get(role) or []
        if require_match and phrases:
            if title_is_relevant(title, phrases):
                matched.append(role)
        elif title_is_relevant(title, phrases):
            matched.append(role)
    return matched


# Cities and countries a student in Milan can realistically work from,
# either in the office or remotely.
_MILAN_WORDS = ("milan", "milano", "lombardy", "lombardia")
_EU_WORDS = (
    "italy",
    "italia",
    "france",
    "germany",
    "spain",
    "netherlands",
    "portugal",
    "belgium",
    "austria",
    "ireland",
    "sweden",
    "denmark",
    "poland",
    "finland",
    "greece",
    "luxembourg",
    "switzerland",
    "norway",
    "europe",
    "european",
    "emea",
    "worldwide",
    "anywhere",
    "global",
    "paris",
    "berlin",
    "amsterdam",
    "barcelona",
    "madrid",
    "lisbon",
    "dublin",
    "vienna",
    "munich",
    "rome",
    "roma",
    "brussels",
    "stockholm",
    "copenhagen",
    "warsaw",
    "prague",
    "zurich",
    "lyon",
    "bologna",
    "turin",
    "torino",
)
_BLOCK_WORDS = (
    "united states",
    "u.s.",
    "usa",
    "canada",
    "india",
    "australia",
    "brazil",
    "singapore",
    "japan",
    "korea",
    "mexico",
    "philippines",
    "argentina",
    "latam",
    "latin america",
    "melbourne",
    "united kingdom",
    "london",
)


def classify_place(location: str, is_remote: bool = False) -> str | None:
    """Return 'Milan, Italy', 'Remote', or None when the job is somewhere else.

    Milan office jobs are kept. Remote jobs are kept when they can be done
    from Italy or the EU, or when they say worldwide. US-only, UK-only, and
    other non-EU offices are left out.
    """
    text = _words(location)
    if any(word in text for word in _MILAN_WORDS):
        return "Milan, Italy"
    remoteish = is_remote or any(
        word in text for word in ("remote", "anywhere", "worldwide", "work from home", "da remoto", "lavoro da casa")
    )
    if not remoteish:
        return None
    if re.search(r"\b(us|usa|u\.s\.|united states|canada|uk|united kingdom)\s+only\b", text):
        return None
    # Match whole words so "finland" is not treated as "india".
    def mentioned(phrase: str) -> bool:
        return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None

    eu_places = [word for word in _EU_WORDS if mentioned(word)]
    open_region = any(mentioned(word) for word in ("europe", "european", "emea", "worldwide", "anywhere", "global"))
    generic = text.strip() in {"remote", "global", "worldwide", "anywhere"} or (is_remote and not text)
    has_block = any(mentioned(word) for word in _BLOCK_WORDS) or bool(re.search(r"(?<![a-z0-9])us(?![a-z0-9])", text))
    # A role listed in Poland and the United States is still open in Europe.
    # A role listed only in the US, the UK, or London is not.
    if eu_places or open_region or generic:
        if has_block and not eu_places and not open_region:
            return None
        return "Remote"
    if has_block:
        return None
    return None


def blocks_europe(text: str) -> bool:
    """True when the advert says the person must be outside Europe."""
    lowered = _words(text)
    phrases = (
        "united states only",
        "us only",
        "usa only",
        "u s only",
        "must be located in the united states",
        "must be based in the united states",
        "must reside in the united states",
        "us residents only",
        "north america only",
        "remote us",
        "remote, us",
        "uk only",
        "united kingdom only",
    )
    return any(phrase in lowered for phrase in phrases)


def title_is_relevant(title: str, phrases: list[str]) -> bool:
    """True when the title contains one of the phrases, ignoring capitals.

    An empty phrase list means "do not filter", so every title is kept.
    """
    if not phrases:
        return True
    haystack = " ".join(title.lower().split())
    for phrase in phrases:
        needle = " ".join(phrase.lower().split())
        if needle and needle in haystack:
            return True
    return False


def sort_rows(rows: list[dict]) -> list[dict]:
    """New listings first, and within that group the newest date first."""

    def sort_key(row: dict) -> tuple:
        new_first = 0 if row.get("is_new") == "yes" else 1
        raw = row.get("date_posted") or ""
        parts = raw.split("-")
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            # Negative numbers so a later date sorts first.
            date_key = tuple(-int(part) for part in parts)
        else:
            date_key = (0, 0, 0)
        return (new_first, date_key)

    return sorted(rows, key=sort_key)
