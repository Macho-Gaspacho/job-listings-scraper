"""Load and validate config.yaml.
"""

from __future__ import annotations

import yaml
from pathlib import Path


def load_config(path: str = "config.yaml") -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with p.open() as f:
        data = yaml.safe_load(f) or {}
    return data
