"""Read public career pages and job-board feeds.

Each function talks to one public page, API, or RSS feed. Nothing here
logs in or tries to get around a block. If a feed says no, that source
is skipped and the others are still saved.

Company boards are fetched once per company, then filtered locally.
They are not searched once per role, which keeps the number of requests small.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

from config import Company, Settings
from environment import certificate_hint, network_problem, report_skip
from regions import build_location_rules
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


def _read_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, */*"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
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
        if not roles:
            continue
        location = job.get("location") or ""
        is_remote = bool(job.get("is_remote"))
        place = classify_place(location, is_remote, rules)
        if not place:
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
                "date_posted": job.get("updated_at") or job.get("first_published") or "",
                "url": job.get("absolute_url") or "",
                "description": job.get("content") or "",
                "source": f"{company} careers",
            }
        )
    return rows


def parse_lever(payload: list, company: str) -> list[dict]:
    """Lever's public postings API."""
    rows = []
    for job in payload or []:
        location = ((job.get("categories") or {}).get("location")) or ""
        workplace = str(job.get("workplaceType") or "")
        rows.append(
            {
                "title": job.get("text") or "",
                "company": company,
                "location": location,
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
                "location": location or title,
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
        body = getter(f"https://api.lever.co/v0/postings/{token}?mode=json")
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
    raise RuntimeError(f"unknown remote board '{source_id}'")


def collect_board_listings(settings: Settings, pause=time.sleep, getter=http_get) -> tuple[list[dict], int]:
    """Fetch every enabled company page and remote board.

    Returns the kept rows and how many feeds failed.
    """
    rows: list[dict] = []
    failures = 0
    steps: list[tuple[str, object]] = []
    if settings.company_pages_enabled:
        for company in settings.companies or []:
            if company.enabled:
                steps.append(("company", company))
    for source_id in settings.remote_boards or []:
        steps.append(("remote", source_id))

    for index, (kind, target) in enumerate(steps):
        if kind == "company":
            company = target
            label = f"{company.name} ({company.system})"
            print(f"Reading {label} careers page...", flush=True)
            try:
                found = filter_board_jobs(
                    _company_jobs(company, getter),
                    settings,
                    "company site",
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
