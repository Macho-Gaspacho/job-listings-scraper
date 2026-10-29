"""Fetch listings from remote boards and aggregators.

Indeed and LinkedIn are the crowded ones. Remote OK and We Work Remotely
are the public remote feeds. This file does not log in. A block ends that
source for the run.
"""

from __future__ import annotations

import re
from typing import Callable
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from listings import clean_text, title_is_relevant


def collect_board_listings(role: str, place: str, board: dict) -> list[dict]:
    """One board. Returns rows, or raises if that board fails."""
    name = board.get("name") or ""
    if name == "We Work Remotely":
        return fetch_weworkremotely(role, place)
    if name == "Remote OK":
        return fetch_remoteok(role, place)
    if name == "Indeed":
        return fetch_indeed(role, place)
    if name == "LinkedIn":
        return fetch_linkedin(role, place)
    return []


def fetch_weworkremotely(role: str, place: str) -> list[dict]:
    url = f"https://weworkremotely.com/remote-jobs/search?term={quote_plus(role)}"
    response = requests.get(url, timeout=20, headers={"User-Agent": "job-listings-scraper/1.0"})
    response.raise_for_status()
    return parse_weworkremotely(response.text, role, place)


def parse_weworkremotely(html: str, role: str, place: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for li in soup.select("li.feature, li.view-all"):
        title_el = li.select_one(".title")
        company_el = li.select_one(".company")
        link_el = li.select_one("a")
        if not title_el or not link_el:
            continue
        title = clean_text(title_el.get_text())
        company = clean_text(company_el.get_text()) if company_el else ""
        link = urljoin("https://weworkremotely.com", link_el.get("href") or "")
        if title_is_relevant(title, [role]):
            rows.append({
                "Title": title,
                "Company": company,
                "Location": place,
                "Source": "We Work Remotely",
                "Source type": "remote board",
                "Link": link,
            })
    return rows


def fetch_remoteok(role: str, place: str) -> list[dict]:
    url = f"https://remoteok.com/remote-{quote_plus(role)}-jobs"
    response = requests.get(url, timeout=20, headers={"User-Agent": "job-listings-scraper/1.0"})
    response.raise_for_status()
    return parse_remoteok(response.text, role, place)


def parse_remoteok(html: str, role: str, place: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for tr in soup.select("tr.job"):
        title_el = tr.select_one("h2")
        company_el = tr.select_one("h3")
        link_el = tr.select_one("a")
        if not title_el:
            continue
        title = clean_text(title_el.get_text())
        company = clean_text(company_el.get_text()) if company_el else ""
        link = urljoin("https://remoteok.com", link_el.get("href") or "") if link_el else ""
        if title_is_relevant(title, [role]):
            rows.append({
                "Title": title,
                "Company": company,
                "Location": place,
                "Source": "Remote OK",
                "Source type": "remote board",
                "Link": link,
            })
    return rows


def fetch_indeed(role: str, place: str) -> list[dict]:
    url = f"https://it.indeed.com/jobs?q={quote_plus(role)}&l={quote_plus(place)}"
    response = requests.get(url, timeout=20, headers={"User-Agent": "job-listings-scraper/1.0"})
    response.raise_for_status()
    return parse_indeed(response.text, role, place)


def parse_indeed(html: str, role: str, place: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for card in soup.select(".job_seen_beacon, .tapItem"):
        title_el = card.select_one("h2, .jobTitle")
        company_el = card.select_one(".companyName")
        link_el = card.select_one("a")
        if not title_el:
            continue
        title = clean_text(title_el.get_text())
        company = clean_text(company_el.get_text()) if company_el else ""
        link = urljoin("https://it.indeed.com", link_el.get("href") or "") if link_el else ""
        if title_is_relevant(title, [role]):
            rows.append({
                "Title": title,
                "Company": company,
                "Location": place,
                "Source": "Indeed",
                "Source type": "aggregator",
                "Link": link,
            })
    return rows


def fetch_linkedin(role: str, place: str) -> list[dict]:
    url = f"https://www.linkedin.com/jobs/search?keywords={quote_plus(role)}&location={quote_plus(place)}"
    response = requests.get(url, timeout=20, headers={"User-Agent": "job-listings-scraper/1.0"})
    response.raise_for_status()
    return parse_linkedin(response.text, role, place)


def parse_linkedin(html: str, role: str, place: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for card in soup.select(".base-card, .job-search-card"):
        title_el = card.select_one(".base-search-card__title, h3")
        company_el = card.select_one(".base-search-card__subtitle, h4")
        link_el = card.select_one("a")
        if not title_el:
            continue
        title = clean_text(title_el.get_text())
        company = clean_text(company_el.get_text()) if company_el else ""
        link = link_el.get("href") or "" if link_el else ""
        if title_is_relevant(title, [role]):
            rows.append({
                "Title": title,
                "Company": company,
                "Location": place,
                "Source": "LinkedIn",
                "Source type": "aggregator",
                "Link": link,
            })
    return rows
