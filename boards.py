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
from listings import (
    blocks_europe,
    classify_place,
    clean_text,
    date_text,
    roles_for_title,
    snippet,
)

USER_AGENT = "milan-job-scraper/1.0 (personal job search; public feeds only)"

# Remote-board feeds. Product and marketing are the categories that
# overlap the roles in config.yaml. The full "all jobs" feed is much noisier.
# The old "remote-marketing-jobs" address now answers with a redirect and
# no new address, so the sales-and-marketing feed is used instead.
# Management is included because project-manager roles are posted there.
WE_WORK_REMOTELY_FEEDS = (
    "https://weworkremotely.com/categories/remote-product-jobs.rss",
    "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss",
    "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
)


def http_get(url: str) -> bytes:
    """Download one public URL. Raises RuntimeError when the site says no."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, */*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read(20_000_000)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except Exception as exc:
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


def filter_board_jobs(
    jobs: list[dict],
    settings: Settings,
    source_type: str,
    check_region_text: bool = False,
) -> list[dict]:
    """Keep jobs whose title matches a role and whose location is Milan or EU-remote."""
    kept = []
    for job in jobs:
        description = job.get("description") or ""
        if check_region_text and blocks_europe(description):
            continue
        roles = roles_for_title(
            job.get("title") or "",
            settings.roles,
            settings.title_keywords,
            settings.require_title_match,
        )
        if not roles:
            continue
        place = classify_place(job.get("location") or "", bool(job.get("is_remote")))
        if not place:
            continue
        kept.append(
            {
                "title": clean_text(job.get("title")),
                "company": clean_text(job.get("company")),
                "location": clean_text(job.get("location")),
                "date_posted": _iso_date(job.get("date_posted")),
                "source": clean_text(job.get("source")),
                "source_type": source_type,
                "url": clean_text(job.get("url")),
                "description": snippet(description, settings.snippet_characters),
                "role_searched": "; ".join(roles),
                "place_searched": place,
            }
        )
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
    """Ashby's public posting API. Hybrid office jobs outside Milan are dropped later."""
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
        milan = False
        eu_office = False
        for office in offices:
            title = office.get("title") or ""
            country = office.get("country") or {}
            labels.append(title or country.get("name") or "")
            blob = f"{title} {country.get('name') or ''}".lower()
            if "milan" in blob or "milano" in blob:
                milan = True
            if country.get("euMember"):
                eu_office = True
        location = "; ".join(label for label in labels if label)
        # Remote only matters when the job is not already in the Milan office.
        is_remote = bool(job.get("availableAsRemoteInDefaultCountries")) and eu_office and not milan
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


def _remote_jobs(source_id: str, getter) -> list[dict]:
    if source_id == "we_work_remotely":
        rows = []
        errors = []
        for index, url in enumerate(WE_WORK_REMOTELY_FEEDS):
            if index:
                time.sleep(1)
            try:
                rows.extend(parse_we_work_remotely(getter(url)))
            except Exception as exc:
                errors.append(str(exc))
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
                print(f"  Skipped ({exc}).", flush=True)
                found = []
            else:
                print(f"  Kept {len(found)} matching listings.", flush=True)
        else:
            source_id = str(target)
            print(f"Reading remote board {source_id.replace('_', ' ')}...", flush=True)
            try:
                found = filter_board_jobs(
                    _remote_jobs(source_id, getter),
                    settings,
                    "remote board",
                    check_region_text=True,
                )
            except Exception as exc:
                failures += 1
                print(f"  Skipped ({exc}).", flush=True)
                found = []
            else:
                print(f"  Kept {len(found)} matching listings.", flush=True)
        rows.extend(found)
        if settings.pause_seconds and index != len(steps) - 1:
            pause(settings.pause_seconds)
    return rows, failures
