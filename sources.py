"""Source definitions and helpers for the job scraper.

Each source knows how to fetch listings from its site or board.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Source(Protocol):
    name: str
    kind: str

    def fetch(self, config: dict) -> list[dict]: ...


@dataclass
class CompanySource:
    name: str
    kind: str = "company site"
    token: str = ""
    system: str = ""

    def fetch(self, config: dict) -> list[dict]:
        # placeholder - real implementation in boards.py
        return []


@dataclass
class BoardSource:
    name: str
    kind: str = "remote board"

    def fetch(self, config: dict) -> list[dict]:
        return []
