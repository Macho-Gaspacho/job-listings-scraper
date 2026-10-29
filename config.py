"""Load config.yaml into a Settings object."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Settings:
    roles: list[str]
    places: list[str]
    pause_seconds: float
    companies: list[dict]
    boards: list[dict]


def load_config(path: Path) -> Settings:
    """Read config.yaml and return a Settings object."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Settings(
        roles=list(raw.get("roles") or []),
        places=list(raw.get("places") or []),
        pause_seconds=float(raw.get("pause_seconds") or 1.0),
        companies=list(raw.get("companies") or []),
        boards=list(raw.get("boards") or []),
    )
