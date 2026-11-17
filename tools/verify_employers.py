# ruff: noqa: E402
"""Check the public career pages listed under employers/. Maintainers only.

The job search never imports or runs this file. It uses the same public
endpoints as boards._company_jobs, with a 20 second timeout, at most four
requests at once, and at least half a second between calls to one host.
A 404 is not retried. A 429 or a 5xx is retried once after five seconds.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import argparse
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import yaml

from boards import USER_AGENT, Company, _HostGate, _company_jobs, _ssl_context, company_host
from places import resolve_place
from regions import NATIVE_NAMES, _country_in_text, contains_phrase, english_name

_EMPLOYERS = _ROOT / "employers"
_REMOTE_WORDS = ("Europe", "EMEA", "EU", "European")
_JOB_CACHE: dict[tuple[str, str, str], tuple[list[dict], BaseException | None]] = {}


def status_name(exc: BaseException | None, jobs_total: int) -> str:
    """ok, empty, not_found, blocked, or error:<Class>."""
    if exc is None:
        return "ok" if jobs_total else "empty"
    code = getattr(exc, "code", None)
    if code == 404:
        return "not_found"
    if code in {403, 429}:
        return "blocked"
    return f"error:{type(exc).__name__}"


def job_remote_europe(location: str, is_remote: bool = False) -> bool:
    """True when the text says Remote and Europe, EMEA, or EU."""
    del is_remote
    text = location or ""
    if not contains_phrase("remote", text):
        return False
    return any(contains_phrase(word, text) for word in _REMOTE_WORDS)


def _segment_in_country(location: str, country: str, hub_cities: list[str]) -> bool:
    text = " ".join(str(location or "").split())
    if not text:
        return False
    named = _country_in_text(text)
    if named == country:
        return True
    if contains_phrase(english_name(country), text):
        return True
    native = NATIVE_NAMES.get(country) or ""
    if native and contains_phrase(native, text):
        return True
    if named and named != country:
        return False
    for city in hub_cities:
        if not contains_phrase(city, text):
            continue
        found = resolve_place(city)
        if found.country in {None, country}:
            return True
        if found.status == "choose" and any(choice[1] == country for choice in found.choices):
            return True
    found = resolve_place(text)
    if found.country == country and found.status in {"ok", "confirm", "country_only"}:
        return True
    head = text.split(",")[0].strip()
    if head and head != text:
        found = resolve_place(head)
        if found.country == country and found.status in {"ok", "confirm"}:
            return True
    return False


def job_in_country(location: str, country: str, hub_cities: list[str]) -> bool:
    """True when the location names this country or one of its hub cities."""
    if country == "europe_remote":
        return job_remote_europe(location)
    text = str(location or "")
    parts = [text] + [part.strip() for part in text.split(";") if part.strip()]
    return any(_segment_in_country(part, country, list(hub_cities or [])) for part in parts)


def count_jobs(jobs: list[dict], country: str, hub_cities: list[str]) -> tuple[int, int]:
    """(jobs_total, jobs_in_country). europe_remote counts Remote + Europe/EMEA/EU."""
    total = len(jobs or [])
    kept = 0
    for job in jobs or []:
        location = str(job.get("location") or "")
        if country == "europe_remote":
            if job_remote_europe(location, bool(job.get("is_remote"))):
                kept += 1
        elif job_in_country(location, country, hub_cities):
            kept += 1
    return total, kept


def _read_once(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, */*"},
    )
    context = _ssl_context()
    with urllib.request.urlopen(request, timeout=20, context=context) as response:
        return response.read(20_000_000)


def polite_get(url: str, sleep=time.sleep) -> bytes:
    """One download. Retry once after 5 seconds on HTTP 429 or 5xx. Never on 404."""
    try:
        return _read_once(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 or exc.code not in {429} and not 500 <= exc.code <= 599:
            raise
        sleep(5)
        return _read_once(url)


def _company_from(entry: dict) -> Company:
    families = entry.get("families") or []
    if isinstance(families, str):
        families = [families]
    return Company(
        name=str(entry.get("name") or "").strip(),
        system=str(entry.get("system") or "").strip().casefold(),
        token=str(entry.get("token") or "").strip(),
        enabled=entry.get("enabled", True) is not False,
        region=str(entry.get("region") or "").strip().casefold(),
        families=tuple(str(item).strip() for item in families if str(item).strip()),
    )


def _files(country: str) -> list[Path]:
    if country:
        return [_EMPLOYERS / f"{country}.yaml"]
    return sorted(_EMPLOYERS.glob("*.yaml"))


def _check_file(path: Path, sleep=time.sleep) -> tuple[dict, list[dict]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    country = str(raw.get("country") or path.stem)
    entries = [item for item in (raw.get("employers") or []) if isinstance(item, dict)]
    gate = _HostGate(sleep, time.monotonic)

    def _load(company: Company):
        key = (company.system, company.token.casefold(), company.region)
        if key in _JOB_CACHE:
            return _JOB_CACHE[key]

        def _call():
            return _company_jobs(company, lambda url: polite_get(url, sleep=sleep))

        try:
            jobs = gate.run(company_host(company), _call)
            _JOB_CACHE[key] = (jobs, None)
        except Exception as exc:
            _JOB_CACHE[key] = ([], exc)
        return _JOB_CACHE[key]

    companies = [_company_from(entry) for entry in entries]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_load, company) for company in companies]
        for future in as_completed(futures):
            future.result()
    rows = []
    for entry, company in zip(entries, companies):
        jobs, exc = _JOB_CACHE[(company.system, company.token.casefold(), company.region)]
        hubs = entry.get("hub_cities") or []
        if isinstance(hubs, str):
            hubs = [hubs]
        total, in_country = count_jobs(jobs, country, [str(city) for city in hubs])
        status = status_name(exc, total)
        rows.append(
            {
                "entry": entry,
                "name": company.name,
                "system": company.system,
                "token": company.token,
                "status": status,
                "jobs_total": total,
                "jobs_in_country": in_country,
            }
        )
    return raw, rows


def _print_table(rows: list[dict]) -> None:
    print(f"{'name':24} {'system':14} {'token':24} {'status':18} {'total':6} {'in_country':10}")
    for row in rows:
        print(
            f"{row['name'][:24]:24} {row['system'][:14]:14} {row['token'][:24]:24} "
            f"{row['status'][:18]:18} {row['jobs_total']:6} {row['jobs_in_country']:10}"
        )


def _write(path: Path, raw: dict, rows: list[dict]) -> None:
    raw["checked_on"] = date.today().isoformat()
    for row in rows:
        entry = row["entry"]
        entry["last_check"] = {
            "status": row["status"],
            "jobs_total": row["jobs_total"],
            "jobs_in_country": row["jobs_in_country"],
        }
        entry["enabled"] = row["status"] == "ok"
    text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False)
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check curated employer career pages.")
    parser.add_argument("--country", default="", help="One country file, such as netherlands.")
    parser.add_argument("--write", action="store_true", help="Update last_check and checked_on.")
    args = parser.parse_args(argv)
    paths = _files(args.country.strip().casefold())
    if not paths:
        print("No employer files to check.", file=sys.stderr)
        return 1
    for path in paths:
        if not path.is_file():
            print(f"Missing {path.name}", file=sys.stderr)
            return 1
        print(path.name, flush=True)
        raw, rows = _check_file(path)
        _print_table(rows)
        if args.write:
            _write(path, raw, rows)
            print(f"Updated {path.name}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
