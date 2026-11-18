"""Ask Indeed and LinkedIn for listings, through python-jobspy.

python-jobspy reads public search pages. It does not log in, and this
project does not try to get around a block. If a site says no, the
search is skipped and the other sites are still saved.
"""

from __future__ import annotations

import logging
import time

from jobspy import scrape_jobs
from jobspy.util import log_handler

from config import Place, Settings
from enrichment import jobspy_job_type
from listings import row_from_hit
from regions import country_from_places

# A block or a login wall is not retried. A proxy miss, a timeout, or a
# "too many requests" reply is a temporary failure, so the same search is
# tried again after a pause. Nothing here switches proxies or tries to
# look like a different browser.
_STOP_WORDS = (
    "blocked",
    "captcha",
    "forbidden",
    "access denied",
    "403",
    "401",
    "login required",
)
_TRANSIENT_WORDS = (
    ("429", "too many requests"),
    ("too many requests", "too many requests"),
    ("proxy", "proxy error"),
    ("timed out", "timeout"),
    ("timeout", "timeout"),
    ("502", "the site was busy"),
    ("503", "the site was busy"),
    ("504", "the site was busy"),
    ("bad gateway", "the site was busy"),
    ("service unavailable", "the site was busy"),
    ("connection reset", "connection problem"),
    ("connection aborted", "connection problem"),
    ("remote end closed", "connection problem"),
    ("temporarily", "connection problem"),
)


def transient_reason(exc: BaseException) -> str | None:
    """A short reason to try again, or None when the search should be skipped."""
    text = f"{type(exc).__name__} {exc}".casefold()
    if any(word in text for word in _STOP_WORDS):
        return None
    for needle, reason in _TRANSIENT_WORDS:
        if needle in text:
            return reason
    return None


def retry_delay(pause_seconds: float, attempt_index: int) -> float:
    """Seconds to wait before retry number attempt_index (0 is the first retry)."""
    base = max(float(pause_seconds or 1), 1.0)
    return min(60.0, base * (2 ** attempt_index))


def quiet_library_logs(verbose: bool = False) -> None:
    """Hide Indeed/LinkedIn library logs unless a detailed run was asked for.

    python-jobspy attaches its own handler and, when verbose is 0, turns
    errors back on. The handler level stays critical, so those lines stay hidden.
    """
    if verbose:
        logging.getLogger("jobspy").setLevel(logging.INFO)
        logging.getLogger("urllib3").setLevel(logging.INFO)
        log_handler.setLevel(logging.NOTSET)
    else:
        logging.getLogger("jobspy").setLevel(logging.CRITICAL)
        logging.getLogger("urllib3").setLevel(logging.CRITICAL)
        log_handler.setLevel(logging.CRITICAL)


def build_search(settings: Settings, role: str, place: Place, site: str, verbose: bool = False) -> dict:
    """The arguments for one python-jobspy search.

    Indeed has a real "remote jobs only" filter. LinkedIn's public search
    does not, so for a remote place we add the word "remote" to the role.
    Descriptions are already included by Indeed. LinkedIn needs an extra
    page view per job, which is slower, so it follows fetch_descriptions.
    """
    term = role.strip()
    if place.remote and site == "linkedin" and "remote" not in term.lower():
        term = f"{term} remote"
    location = place.linkedin_location if site == "linkedin" else place.indeed_location
    query = {
        "site_name": [site],
        "search_term": term,
        "location": location,
        "results_wanted": settings.results_per_search,
        "hours_old": settings.posted_within_days * 24,
        "country_indeed": place.country or country_from_places([place]) or settings.country,
        # None leaves the logger level alone, so a normal run stays quiet.
        # A detailed run asks the library for its own messages.
        "verbose": 2 if verbose else None,
        "fetch_description": bool(settings.fetch_descriptions and site == "linkedin"),
    }
    if place.remote and site == "indeed":
        query["is_remote"] = True
    # Indeed accepts one job_type (fulltime, parttime, contract, temporary,
    # internship) and is_remote. LinkedIn ignores job_type in jobspy 1.4.0,
    # so it is sent only for Indeed. Several chosen types are filtered after
    # the search, because jobspy takes a single job_type.
    chosen = () if settings.filters is None else settings.filters.job_types
    if site == "indeed" and len(chosen) == 1:
        query["job_type"] = jobspy_job_type(chosen[0])
    if place.distance_miles is not None:
        query["distance"] = place.distance_miles
    return query


def take_records(frame, site: str) -> list[dict]:
    """Pull rows out of a python-jobspy table.

    A site can fail while returning nothing (Glassdoor did this for one city
    during testing). That becomes an error the caller can skip. A warning
    that still came with rows is printed, and the rows are kept.
    """
    errors = {}
    attrs = getattr(frame, "attrs", None)
    if isinstance(attrs, dict):
        errors = attrs.get("errors") or {}
    message = errors.get(site)
    records = frame.to_dict(orient="records") if len(frame) else []
    if message and not records:
        raise RuntimeError(str(message))
    if message and records:
        print(f"  Note from {site}: {message}", flush=True)
    return records


def fetch_listings(
    settings: Settings,
    role: str,
    place: Place,
    site: str,
    verbose: bool = False,
    sleeper=None,
    attempts: int = 3,
) -> list[dict]:
    """Run one search and return cleaned rows. Raises if the site fails.

    A proxy error, a timeout, or HTTP 429 is tried again after a pause.
    A block is not tried again. The pause grows each time and stays under a minute.
    """
    if sleeper is None:
        sleeper = time.sleep
    quiet_library_logs(verbose)
    tries = max(1, attempts)
    frame = None
    for attempt in range(tries):
        try:
            frame = scrape_jobs(**build_search(settings, role, place, site, verbose=verbose))
            records = take_records(frame, site)
            break
        except Exception as exc:
            reason = transient_reason(exc)
            if reason is None or attempt == tries - 1:
                raise
            delay = retry_delay(settings.pause_seconds, attempt)
            print(
                f"  {site} did not answer ({reason}). "
                f"Waiting {delay:.0f} seconds, then trying again.",
                flush=True,
            )
            sleeper(delay)
    rows = []
    for record in records:
        row = row_from_hit(record, role, place.name, settings.snippet_characters)
        if row is not None:
            rows.append(row)
    return rows
