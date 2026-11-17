"""Read public career pages and job-board feeds.

Each function talks to one public page, API, or RSS feed. Nothing here
logs in or tries to get around a block. If a feed says no, that source
is skipped and the others are still saved.

Company boards are fetched once per company, then filtered locally.
They are not searched once per role, which keeps the number of requests small.
"""

from __future__ import annotations

import json
import math
import re
import ssl
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse

from config import Company, Settings
from enrichment import describe_posting, job_type_text, passes_filters
from environment import certificate_hint, network_problem, report_skip
from matching import normalise
from regions import (
    COUNTRY_ALIASES,
    NATIVE_NAMES,
    build_location_rules,
    canonical_country,
    contains_phrase,
    english_name,
    looks_remote,
)
from listings import (
    classify_place,
    clean_text,
    date_text,
    excluded_region,
    roles_for_title,
    snippet,
    title_is_excluded,
)

VERSION = "1.0"
USER_AGENT = (
    f"job-listings-scraper/{VERSION} "
    "(+https://github.com/Macho-Gaspacho/job-listings-scraper)"
)

# The public all-jobs feed. Checked once: it returns RSS (HTTP 200).
# A config can list categories instead. See we_work_remotely_feed_urls.
DEFAULT_WWR_FEED = "https://weworkremotely.com/remote-jobs.rss"
ARBEITNOW_API = "https://www.arbeitnow.com/api/job-board-api?page={page}"


# Seconds to wait before try 2 and try 3. Retry-After replaces these when it
# is a whole number of seconds, and is never allowed to be longer than 30.
_RETRY_WAITS = (2, 5)
_RETRY_CAP_SECONDS = 30


def http_get(url: str, sleep=time.sleep) -> bytes:
    """Download one public URL. Raises RuntimeError when the site says no.

    A 429, a 5xx, or a timeout is tried up to 3 times. `sleep` is called with
    the seconds to wait between tries so tests can record the waits instead of
    pausing.
    """
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return _read_url(url)
        except Exception as exc:
            last_error = exc
            if attempt == 2 or not _should_retry(exc):
                _reraise_download(exc)
            sleep(_wait_seconds(exc, _RETRY_WAITS[attempt]))
    raise RuntimeError("the site could not be reached") from last_error


def _ssl_context():
    """A context that trusts certifi's certificate list.

    Python on a fresh Mac often has no system CA bundle, so HTTPS fails
    until someone sets SSL_CERT_FILE. certifi ships the list. If it cannot
    be imported, the default context is used and the download still runs.
    """
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _read_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, */*"},
    )
    with urllib.request.urlopen(request, timeout=45, context=_ssl_context()) as response:
        return response.read(20_000_000)


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code <= 599
    return _is_timeout(exc)


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, BaseException) and reason is not exc and _is_timeout(reason):
        return True
    return "timed out" in str(exc).lower()


def _wait_seconds(exc: Exception, default: float) -> float:
    if isinstance(exc, urllib.error.HTTPError):
        headers = getattr(exc, "headers", None)
        raw = None if headers is None else headers.get("Retry-After")
        if raw is not None and str(raw).strip().isdigit():
            return min(int(str(raw).strip()), _RETRY_CAP_SECONDS)
    return min(float(default), _RETRY_CAP_SECONDS)


def _reraise_download(exc: Exception) -> None:
    if isinstance(exc, urllib.error.HTTPError):
        raise RuntimeError(f"HTTP {exc.code}") from exc
    raise RuntimeError(str(exc)) from exc


def _iso_date(value: object) -> str:
    """YYYY-MM-DD from a timestamp, an RSS date, or a string the site already formatted."""
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()
    text = str(value).strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return date_text(text)


def _json_bytes(body: bytes):
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("the site did not return readable JSON") from exc


def _location_rules(settings: Settings):
    """Rules saved with the config, or rules built from its places and country."""
    rules = settings.location_rules
    if rules is not None:
        return rules
    return build_location_rules(settings.places, settings.country, None)


def we_work_remotely_feed_urls(categories: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    """Feed addresses for We Work Remotely. No categories means the all-jobs feed."""
    if not categories:
        return (DEFAULT_WWR_FEED,)
    return tuple(_wwr_category_url(category) for category in categories)


def _wwr_category_url(category: str) -> str:
    text = str(category).strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    slug = text.strip().strip("/")
    if slug.endswith(".rss"):
        slug = slug[:-4]
    if slug.startswith("categories/"):
        slug = slug.split("/", 1)[1]
    if slug in {"all", "remote-jobs", "jobs"}:
        return DEFAULT_WWR_FEED
    if not slug.startswith("remote-"):
        if slug.endswith("-jobs"):
            slug = "remote-" + slug
        else:
            slug = f"remote-{slug}-jobs"
    return f"https://weworkremotely.com/categories/{slug}.rss"


# These feeds return a whole board. They are not searched by keyword.
# Indeed and LinkedIn are. Company pages the user added are not in this set.
_WHOLE_BOARD_SOURCES = frozenset(
    {
        "arbeitnow",
        "we_work_remotely",
        "we work remotely",
        "remote_ok",
        "remote ok",
        "remotive",
        "working_nomads",
        "working nomads",
    }
)


def _source_name(job: dict) -> str:
    return clean_text(job.get("source")).casefold()


def _whole_board(job: dict) -> bool:
    """True when this row came from a feed that has no keyword search."""
    return _source_name(job) in _WHOLE_BOARD_SOURCES


def _title_matches_role(title: str, role: str, phrases: list[str] | None) -> bool:
    """True when the title contains the typed role, or an accepted local title.

    Comparison uses the same normalisation as other title checks. Words of
    two letters or fewer are ignored. The words may be in any order.
    """
    haystack = normalise(title)
    seen: set[tuple[str, ...]] = set()
    for phrase in (role, *(phrases or [])):
        words = tuple(word for word in normalise(phrase) if len(word) > 2)
        if not words or words in seen:
            continue
        seen.add(words)
        if all(word in haystack for word in words):
            return True
    return False


def _country_tokens(rules) -> set[str]:
    """Words that name the user's country and nothing more specific."""
    labels = [rules.country, english_name(rules.country), NATIVE_NAMES.get(rules.country, "")]
    for alias, code in COUNTRY_ALIASES.items():
        if code == rules.country:
            labels.append(alias)
    tokens: set[str] = set()
    for label in labels:
        tokens.update(normalise(label))
    return tokens


def _arbeitnow_place_ok(location: str, is_remote: bool, rules) -> bool:
    """Keep Arbeitnow rows in the searched city, or in the country with no city.

    classify_place keeps a row when any office phrase matches. The country
    name is one of those phrases, so Cologne, Germany is kept for a Frankfurt
    search, while a bare Munich is dropped because it names neither phrase.
    This check is only for Arbeitnow. Company pages and remote boards stay
    on classify_place.
    """
    if looks_remote(location, is_remote):
        return True
    for _name, phrases in rules.offices:
        for phrase in phrases:
            if canonical_country(phrase):
                continue
            if contains_phrase(phrase, location):
                return True
    tokens = normalise(location)
    allowed = _country_tokens(rules)
    return bool(tokens) and all(token in allowed for token in tokens)


def filter_board_jobs(
    jobs: list[dict],
    settings: Settings,
    source_type: str,
    check_region_text: bool = False,
) -> list[dict]:
    """Keep jobs whose title matches a role and whose place matches the user's rules."""
    rules = _location_rules(settings)
    kept = []
    for job in jobs:
        description = job.get("description") or ""
        if check_region_text and excluded_region(description, rules):
            continue
        if title_is_excluded(job.get("title") or "", settings.exclude_keywords or []):
            continue
        roles = roles_for_title(
            job.get("title") or "",
            settings.roles,
            settings.title_keywords,
            settings.require_title_match,
        )
        if _whole_board(job):
            keywords = settings.title_keywords or {}
            roles = [
                role
                for role in roles
                if _title_matches_role(job.get("title") or "", role, keywords.get(role))
            ]
        if not roles:
            continue
        location = job.get("location") or ""
        is_remote = bool(job.get("is_remote"))
        place = classify_place(location, is_remote, rules)
        if not place:
            continue
        if _source_name(job) == "arbeitnow" and not _arbeitnow_place_ok(location, is_remote, rules):
            continue
        row = {
            "title": clean_text(job.get("title")),
            "company": clean_text(job.get("company")),
            "location": clean_text(location),
            "date_posted": _iso_date(job.get("date_posted")),
            "source": clean_text(job.get("source")),
            "source_type": source_type,
            "url": clean_text(job.get("url")),
            "description": snippet(description, settings.snippet_characters),
            "role_searched": "; ".join(roles),
            "place_searched": place,
        }
        row.update(describe_posting({**job, "title": row["title"], "description": description}))
        if not passes_filters(row, getattr(settings, "filters", None)):
            continue
        if place == "Remote" and not row["location"] and is_remote:
            row["remote_scope"] = "unspecified"
        kept.append(row)
    return kept


def parse_greenhouse(payload: dict, company: str) -> list[dict]:
    """Greenhouse's public job board: boards-api.greenhouse.io."""
    rows = []
    for job in payload.get("jobs") or []:
        location = ((job.get("location") or {}).get("name")) or ""
        rows.append(
            {
                "title": job.get("title") or "",
                "company": company,
                "location": location,
                "is_remote": "remote" in location.lower(),
                "job_type": _greenhouse_job_type(job),
                "date_posted": job.get("first_published") or job.get("updated_at") or "",
                "url": job.get("absolute_url") or "",
                "description": job.get("content") or "",
                "source": f"{company} careers",
            }
        )
    return rows


def _greenhouse_job_type(job: dict) -> str:
    """Employment type from Greenhouse metadata, when the board sends it."""
    for item in job.get("metadata") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").casefold()
        if "employment" in name or name in {"job type", "commitment", "time type"}:
            return job_type_text(item.get("value"))
    return ""


def parse_lever(payload: list, company: str) -> list[dict]:
    """Lever's public postings API."""
    rows = []
    for job in payload or []:
        categories = job.get("categories") or {}
        location = categories.get("location") or ""
        workplace = str(job.get("workplaceType") or "")
        rows.append(
            {
                "title": job.get("text") or "",
                "company": company,
                "location": location,
                "job_type": job_type_text(categories.get("commitment")),
                "is_remote": "remote" in location.lower() or workplace.lower() == "remote",
                "date_posted": job.get("createdAt") or "",
                "url": job.get("hostedUrl") or "",
                "description": job.get("descriptionPlain") or job.get("description") or "",
                "source": f"{company} careers",
            }
        )
    return rows


def parse_ashby(payload: dict, company: str) -> list[dict]:
    """Ashby's public posting API. Office jobs outside the configured places are dropped later."""
    rows = []
    for job in payload.get("jobs") or []:
        if job.get("isListed") is False:
            continue
        parts = [job.get("location") or ""]
        for extra in job.get("secondaryLocations") or []:
            if isinstance(extra, dict):
                parts.append(extra.get("location") or extra.get("name") or "")
            elif extra:
                parts.append(str(extra))
        location = "; ".join(part for part in parts if part)
        workplace = str(job.get("workplaceType") or "").lower()
        is_remote = workplace == "remote" or (
            bool(job.get("isRemote")) and workplace not in {"hybrid", "onsite"}
        )
        rows.append(
            {
                "title": job.get("title") or "",
                "company": company,
                "location": location,
                "job_type": job_type_text(job.get("employmentType")),
                "is_remote": is_remote,
                "date_posted": job.get("publishedAt") or "",
                "url": job.get("jobUrl") or "",
                "description": job.get("descriptionPlain") or job.get("descriptionHtml") or "",
                "source": f"{company} careers",
            }
        )
    return rows


def parse_workable(payload: dict, company: str) -> list[dict]:
    """Workable's public widget API. It does not include the full description."""
    rows = []
    for job in payload.get("jobs") or []:
        city = job.get("city") or ""
        country = job.get("country") or ""
        location = ", ".join(part for part in (city, country) if part)
        rows.append(
            {
                "title": job.get("title") or "",
                "company": company,
                "location": location,
                "job_type": job_type_text(job.get("employment_type")),
                "is_remote": bool(job.get("telecommuting")),
                "date_posted": job.get("published_on") or job.get("created_at") or "",
                "url": job.get("url") or job.get("application_url") or "",
                "description": job.get("description") or "",
                "source": f"{company} careers",
            }
        )
    return rows


def parse_recruitee(payload: dict, company: str) -> list[dict]:
    """Recruitee's public offers feed, used by some EU companies."""
    rows = []
    for job in payload.get("offers") or []:
        country = job.get("country") or ""
        if isinstance(country, dict):
            country = country.get("name") or ""
        city = job.get("city") or ""
        location = ", ".join(part for part in (str(city), str(country)) if part)
        rows.append(
            {
                "title": job.get("title") or "",
                "company": company,
                "location": location,
                "is_remote": bool(job.get("remote")),
                "date_posted": job.get("published_at") or job.get("created_at") or "",
                "url": job.get("careers_url") or "",
                "description": job.get("description") or "",
                "source": f"{company} careers",
            }
        )
    return rows


def parse_bending_spoons(page_html: str) -> list[dict]:
    """Bending Spoons publishes its open jobs in the public careers page."""
    marker = '<script id="__NEXT_DATA__" type="application/json">'
    start = page_html.find(marker)
    if start < 0:
        raise RuntimeError("the careers page did not include a job list")
    start += len(marker)
    end = page_html.find("</script>", start)
    payload = json.loads(page_html[start:end])
    jobs = payload.get("props", {}).get("pageProps", {}).get("list") or []
    rows = []
    for job in jobs:
        offices = job.get("officeLocations") or []
        labels = []
        listed_in_eu = False
        for office in offices:
            title = office.get("title") or ""
            country = office.get("country") or {}
            if not isinstance(country, dict):
                country = {}
            labels.append(title or country.get("name") or "")
            if country.get("euMember"):
                listed_in_eu = True
        # The same location rules used everywhere else decide if this office,
        # or a remote role open in the EU, is one the user asked for.
        is_remote = bool(job.get("availableAsRemoteInDefaultCountries"))
        if is_remote and listed_in_eu:
            labels.append("EU")
        location = "; ".join(label for label in labels if label)
        job_id = job.get("id") or ""
        rows.append(
            {
                "title": job.get("jobTitle") or "",
                "company": "Bending Spoons",
                "location": location,
                "is_remote": is_remote,
                "date_posted": "",
                "url": f"https://jobs.bendingspoons.com/positions/{job_id}" if job_id else "https://jobs.bendingspoons.com",
                "description": job.get("highLevelDescription") or "",
                "source": "Bending Spoons careers",
            }
        )
    return rows


def _rss_items(body: bytes) -> list[ET.Element]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise RuntimeError("the feed was not valid RSS") from exc
    return list(root.iter("item"))


def _item_text(item: ET.Element, tag: str) -> str:
    element = item.find(tag)
    return unescape(element.text or "") if element is not None and element.text else ""


def parse_we_work_remotely(body: bytes) -> list[dict]:
    """We Work Remotely's public RSS feed. The region tag says where you may live."""
    rows = []
    for item in _rss_items(body):
        raw_title = _item_text(item, "title")
        if ":" in raw_title:
            company, title = raw_title.split(":", 1)
        else:
            company, title = "", raw_title
        region = _item_text(item, "region")
        rows.append(
            {
                "title": title.strip(),
                "company": company.strip(),
                "location": region,
                "is_remote": True,
                "date_posted": _item_text(item, "pubDate"),
                "url": _item_text(item, "link"),
                "description": _item_text(item, "description"),
                "source": "we work remotely",
            }
        )
    return rows


def parse_remote_ok(payload: list) -> list[dict]:
    """Remote OK's public JSON API. The first object is a legal notice, not a job."""
    rows = []
    for job in payload or []:
        if not isinstance(job, dict) or not job.get("position"):
            continue
        rows.append(
            {
                "title": job.get("position") or "",
                "company": job.get("company") or "",
                "location": job.get("location") or "",
                "salary_min": job.get("salary_min"),
                "salary_max": job.get("salary_max"),
                "is_remote": True,
                "date_posted": job.get("epoch") or job.get("date") or "",
                "url": job.get("url") or job.get("apply_url") or "",
                "description": job.get("description") or "",
                "source": "remote ok",
            }
        )
    return rows


def parse_remotive(payload: dict) -> list[dict]:
    """Remotive's public API. It currently returns only a small set of jobs."""
    rows = []
    for job in payload.get("jobs") or []:
        rows.append(
            {
                "title": job.get("title") or "",
                "company": job.get("company_name") or "",
                "location": job.get("candidate_required_location") or "",
                "is_remote": True,
                "date_posted": job.get("publication_date") or "",
                "url": job.get("url") or "",
                "description": job.get("description") or "",
                "source": "remotive",
            }
        )
    return rows


def parse_working_nomads(payload: list) -> list[dict]:
    """Working Nomads' public JSON feed."""
    rows = []
    for job in payload or []:
        if not isinstance(job, dict):
            continue
        rows.append(
            {
                "title": job.get("title") or "",
                "company": job.get("company_name") or "",
                "location": job.get("location") or "",
                "is_remote": True,
                "date_posted": job.get("pub_date") or "",
                "url": job.get("url") or "",
                "description": job.get("description") or "",
                "source": "working nomads",
            }
        )
    return rows


def _plain_html(value: object) -> str:
    """Drop HTML tags. The same pattern listings.snippet uses, without cutting the text."""
    text = unescape(str(value or ""))
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_arbeitnow(payload: dict) -> list[dict]:
    """Arbeitnow's public job-board API. created_at is unix seconds."""
    rows = []
    for job in (payload or {}).get("data") or []:
        if not isinstance(job, dict):
            continue
        rows.append(
            {
                "title": job.get("title") or "",
                "company": job.get("company_name") or "",
                "location": job.get("location") or "",
                "is_remote": bool(job.get("remote")),
                "url": job.get("url") or "",
                "date_posted": _iso_date(job.get("created_at")),
                "description": _plain_html(job.get("description") or ""),
                "source": "arbeitnow",
            }
        )
    return rows


def fetch_arbeitnow(getter, sleep=time.sleep) -> list[dict]:
    """At most three pages, one second apart. Stop on an empty page or no next link."""
    rows = []
    for page in range(1, 4):
        if page > 1:
            sleep(1)
        payload = _json_bytes(getter(ARBEITNOW_API.format(page=page)))
        if not isinstance(payload, dict):
            break
        chunk = parse_arbeitnow(payload)
        rows.extend(chunk)
        links = payload.get("links") or {}
        if not chunk or not links.get("next"):
            break
    return rows


def parse_teamtailor(body: bytes, company: str) -> list[dict]:
    """A company's public Teamtailor RSS feed, for example careers.example.com/jobs.rss."""
    rows = []
    for item in _rss_items(body):
        title = _item_text(item, "title")
        description = _item_text(item, "description")
        location = ""
        for element in item:
            if element.tag.lower().endswith("location") and element.text:
                location = unescape(element.text)
                break
        blob = f"{title} {description[:400]}"
        rows.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "is_remote": "remote" in blob.lower(),
                "date_posted": _item_text(item, "pubDate"),
                "url": _item_text(item, "link"),
                "description": description,
                "source": f"{company} careers",
            }
        )
    return rows


def _company_jobs(company: Company, getter) -> list[dict]:
    """Download one company and turn the payload into raw jobs."""
    system = company.system
    token = company.token
    if system == "greenhouse":
        body = getter(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
        return parse_greenhouse(_json_bytes(body), company.name)
    if system == "lever":
        host = "api.eu.lever.co" if (company.region or "").casefold() == "eu" else "api.lever.co"
        body = getter(f"https://{host}/v0/postings/{token}?mode=json")
        payload = _json_bytes(body)
        if not isinstance(payload, list):
            raise RuntimeError("Lever did not return a job list")
        return parse_lever(payload, company.name)
    if system == "ashby":
        body = getter(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
        return parse_ashby(_json_bytes(body), company.name)
    if system == "workable":
        body = getter(f"https://apply.workable.com/api/v1/widget/accounts/{token}")
        return parse_workable(_json_bytes(body), company.name)
    if system == "recruitee":
        body = getter(f"https://{token}.recruitee.com/api/offers/")
        return parse_recruitee(_json_bytes(body), company.name)
    if system == "teamtailor":
        body = getter(token)
        return parse_teamtailor(body, company.name)
    if system == "bendingspoons":
        body = getter("https://jobs.bendingspoons.com")
        return parse_bending_spoons(body.decode("utf-8", "replace"))
    raise RuntimeError(f"unknown job system '{system}'")


def _remote_jobs(source_id: str, getter, settings: Settings) -> list[dict]:
    if source_id == "we_work_remotely":
        rows = []
        errors = []
        feeds = we_work_remotely_feed_urls(getattr(settings, "wwr_categories", None))
        for index, url in enumerate(feeds):
            if index:
                time.sleep(1)
            try:
                rows.extend(parse_we_work_remotely(getter(url)))
            except Exception as exc:
                hint = certificate_hint.note(exc)
                if hint:
                    print(hint, flush=True)
                lines = str(exc).strip().splitlines()
                detail = network_problem(exc) or (lines[0] if lines else "")
                errors.append(detail or exc.__class__.__name__)
        # One category feed can move without taking the others with it.
        if not rows and errors:
            raise RuntimeError(errors[0])
        if errors:
            print(f"  One feed was skipped ({errors[0]}).", flush=True)
        return rows
    if source_id == "remote_ok":
        payload = _json_bytes(getter("https://remoteok.com/api"))
        if not isinstance(payload, list):
            raise RuntimeError("Remote OK did not return a job list")
        return parse_remote_ok(payload)
    if source_id == "remotive":
        return parse_remotive(_json_bytes(getter("https://remotive.com/api/remote-jobs")))
    if source_id == "working_nomads":
        payload = _json_bytes(getter("https://www.workingnomads.com/api/exposed_jobs"))
        if not isinstance(payload, list):
            raise RuntimeError("Working Nomads did not return a job list")
        return parse_working_nomads(payload)
    if source_id == "arbeitnow":
        return fetch_arbeitnow(getter)
    raise RuntimeError(f"unknown remote board '{source_id}'")


_CURATED_CAP = 60
_HOST_GAP_SECONDS = 0.5


def company_host(company: Company) -> str:
    """The host a company request is limited against."""
    system = company.system
    if system == "greenhouse":
        return "boards-api.greenhouse.io"
    if system == "lever":
        if (company.region or "").casefold() == "eu":
            return "api.eu.lever.co"
        return "api.lever.co"
    if system == "ashby":
        return "api.ashbyhq.com"
    if system == "workable":
        return "apply.workable.com"
    if system == "recruitee":
        return "recruitee.com"
    if system == "teamtailor":
        return (urlparse(company.token).hostname or "teamtailor").lower()
    if system == "bendingspoons":
        return "jobs.bendingspoons.com"
    return system


def _fold_name(value: object) -> str:
    return unicodedata.normalize("NFKC", "" if value is None else str(value)).casefold()


def _search_family(roles) -> str:
    from source_map import _family_of

    family, _graduate = _family_of([str(role) for role in roles or []])
    return family


def select_companies(companies, roles) -> list[Company]:
    """User-typed companies, then up to 60 curated ones that fit the role.

    The same public board is kept once. A company the user typed wins.
    Curated boards are the ones with the most jobs in the country.
    """
    family = _search_family(roles)
    enabled = [company for company in companies or [] if company.enabled]
    users: list[Company] = []
    user_keys: set[tuple[str, str]] = set()
    for company in enabled:
        if company.curated:
            continue
        key = (company.system, company.token.casefold())
        if key in user_keys:
            continue
        user_keys.add(key)
        users.append(company)
    curated: list[Company] = []
    seen: set[tuple[str, str]] = set()
    ranked = sorted(
        (company for company in enabled if company.curated),
        key=lambda company: (-int(company.jobs_in_country or 0), _fold_name(company.name)),
    )
    for company in ranked:
        key = (company.system, company.token.casefold())
        if key in user_keys or key in seen:
            continue
        names = {item.casefold() for item in company.families}
        if family != "other" and family not in names:
            continue
        seen.add(key)
        curated.append(company)
        if len(curated) >= _CURATED_CAP:
            break
    return users + curated


def _http_code(exc: BaseException) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    match = re.search(r"\bHTTP(?: Error)? (\d{3})\b", str(exc))
    if match:
        return int(match.group(1))
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, BaseException) and cause is not exc:
        return _http_code(cause)
    return None


def _blocked_or_missing(exc: BaseException) -> bool:
    return _http_code(exc) in {403, 404, 429}


class _HostGate:
    """One request at a time per host, with a gap between them."""

    def __init__(self, sleep, clock) -> None:
        self.sleep = sleep
        self.clock = clock
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}

    def run(self, host: str, fn):
        with self._guard:
            lock = self._locks.setdefault(host, threading.Lock())
        with lock:
            previous = self._last.get(host)
            now = self.clock()
            if previous is not None and now - previous < _HOST_GAP_SECONDS:
                self.sleep(_HOST_GAP_SECONDS - (now - previous))
                now = self.clock()
            self._last[host] = now
            return fn()


def _row_sort_key(row: dict) -> tuple[str, str, str]:
    return (
        _fold_name(row.get("company")),
        _fold_name(row.get("title")),
        str(row.get("url") or ""),
    )


def collect_company_pages(
    companies,
    getter,
    settings: Settings,
    sleep=time.sleep,
    clock=None,
    roles=None,
) -> tuple[list[dict], int]:
    """Read company career pages on a few threads, without crowding one host.

    Returns the kept rows and how many company pages failed.
    """
    if clock is None:
        clock = time.monotonic
    if roles is None:
        roles = list(getattr(settings, "roles", None) or [])
    selected = select_companies(companies, roles)
    if not selected:
        return [], 0
    seconds = math.ceil(len(selected) / 4 * 1.5)
    print(f"Reading {len(selected)} company career pages (about {seconds} s)...", flush=True)
    gate = _HostGate(sleep, clock)
    results: dict[int, tuple[list[dict], BaseException | None]] = {}

    def _one(company: Company):
        try:
            jobs = gate.run(company_host(company), lambda: _company_jobs(company, getter))
            return company, jobs, None
        except Exception as exc:
            return company, [], exc

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_one, company) for company in selected]
        for future in as_completed(futures):
            company, jobs, exc = future.result()
            results[id(company)] = (jobs, exc)

    failures = 0
    blocked: list[str] = []
    kept: list[dict] = []
    for company in selected:
        jobs, exc = results[id(company)]
        if exc is not None:
            failures += 1
            if _blocked_or_missing(exc):
                blocked.append(company.name)
            else:
                report_skip(exc)
            continue
        kept.extend(filter_board_jobs(jobs, settings, "company site"))
    kept.sort(key=_row_sort_key)
    if blocked:
        names = ", ".join(blocked)
        print(
            f"Skipped {len(blocked)} company pages (blocked or not found): {names}.",
            flush=True,
        )
    return kept, failures


def collect_board_listings(settings: Settings, pause=time.sleep, getter=http_get) -> tuple[list[dict], int]:
    """Fetch every enabled company page and remote board.

    Returns the kept rows and how many feeds failed.
    """
    rows: list[dict] = []
    failures = 0
    steps: list[tuple[str, object]] = []
    for source_id in getattr(settings, "job_boards", None) or []:
        steps.append(("job", source_id))
    for source_id in settings.remote_boards or []:
        steps.append(("remote", source_id))
    if settings.company_pages_enabled:
        chosen = select_companies(settings.companies or [], settings.roles)
        if chosen:
            found, failed = collect_company_pages(
                settings.companies or [],
                getter,
                settings,
                sleep=pause,
                roles=settings.roles,
            )
            rows.extend(found)
            failures += failed
            if steps and settings.pause_seconds:
                pause(settings.pause_seconds)

    for index, (kind, target) in enumerate(steps):
        if kind == "job":
            source_id = str(target)
            print(f"Reading job board {source_id.replace('_', ' ')}...", flush=True)
            try:
                found = filter_board_jobs(
                    _remote_jobs(source_id, getter, settings),
                    settings,
                    "job board",
                )
            except Exception as exc:
                failures += 1
                report_skip(exc)
                found = []
            else:
                print(f"  Kept {len(found)} matching listings.", flush=True)
        else:
            source_id = str(target)
            print(f"Reading remote board {source_id.replace('_', ' ')}...", flush=True)
            try:
                found = filter_board_jobs(
                    _remote_jobs(source_id, getter, settings),
                    settings,
                    "remote board",
                    check_region_text=True,
                )
            except Exception as exc:
                failures += 1
                report_skip(exc)
                found = []
            else:
                print(f"  Kept {len(found)} matching listings.", flush=True)
        rows.extend(found)
        if settings.pause_seconds and index != len(steps) - 1:
            pause(settings.pause_seconds)
    return rows, failures
