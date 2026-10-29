"""Fetch listings from company career pages.

Each company in config.yaml has a URL that returns a public job feed or page.
This file does not log in. If a page answers with a block, the caller skips it.
"""

from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from listings import clean_text, title_is_relevant


def fetch_listings(role: str, place: str, site: dict, fetch: Callable) -> list[dict]:
    """One company career page. Returns rows, or raises if that page fails."""
    url = site.get("url") or ""
    company = site.get("name") or ""
    if not url:
        return []
    response = fetch(url)
    response.raise_for_status()
    return parse_career_page(response.text, url, company, role, place)


def parse_career_page(html: str, base_url: str, company: str, role: str, place: str) -> list[dict]:
    """Pull job titles and links from a Greenhouse, Lever, Ashby, or plain page."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    # Greenhouse style
    for opening in soup.select(".opening a, .opening"):
        title = clean_text(opening.get_text())
        link = opening.get("href") or ""
        if title and title_is_relevant(title, [role]):
            rows.append({
                "Title": title,
                "Company": company,
                "Location": place,
                "Source": company,
                "Source type": "company site",
                "Link": urljoin(base_url, link),
            })
    # Lever style
    for posting in soup.select(".posting a, .posting"):
        title = clean_text(posting.get_text())
        link = posting.get("href") or ""
        if title and title_is_relevant(title, [role]):
            rows.append({
                "Title": title,
                "Company": company,
                "Location": place,
                "Source": company,
                "Source type": "company site",
                "Link": urljoin(base_url, link),
            })
    # Plain page fallback: any link that looks like a job
    if not rows:
        for a in soup.select("a"):
            title = clean_text(a.get_text())
            link = a.get("href") or ""
            if title and title_is_relevant(title, [role]) and len(title) < 120:
                rows.append({
                    "Title": title,
                    "Company": company,
                    "Location": place,
                    "Source": company,
                    "Source type": "company site",
                    "Link": urljoin(base_url, link),
                })
    return rows
