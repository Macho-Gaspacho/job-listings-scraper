"""Ask Indeed and LinkedIn for listings, through python-jobspy.

python-jobspy reads public search pages. It does not log in, and this
project does not try to get around a block. If a site says no, the
search is skipped and the other sites are still saved.
"""

from __future__ import annotations

import logging

from jobspy import scrape_jobs
from jobspy.util import log_handler

from config import Place, Settings
from listings import row_from_hit


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
        "country_indeed": settings.country,
        # None leaves the logger level alone, so a normal run stays quiet.
        # A detailed run asks the library for its own messages.
        "verbose": 2 if verbose else None,
        "fetch_description": bool(settings.fetch_descriptions and site == "linkedin"),
    }
    if place.remote and site == "indeed":
        query["is_remote"] = True
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


def fetch_listings(settings: Settings, role: str, place: Place, site: str, verbose: bool = False) -> list[dict]:
    """Run one search and return cleaned rows. Raises if the site fails."""
    quiet_library_logs(verbose)
    frame = scrape_jobs(**build_search(settings, role, place, site, verbose=verbose))
    rows = []
    for record in take_records(frame, site):
        row = row_from_hit(record, role, place.name, settings.snippet_characters)
        if row is not None:
            rows.append(row)
    return rows
