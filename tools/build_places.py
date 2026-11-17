"""Download GeoNames cities15000 and write geodata/cities.tsv.gz.

Maintainers run this. The job search never does. The same zip always
produces the same gzip (mtime is 0).
"""

from __future__ import annotations

import gzip
import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
CITIES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
OUTPUT = ROOT / "geodata" / "cities.tsv.gz"
COUNTRIES = ROOT / "geodata" / "countries.yaml"
MIN_POPULATION = 50000
USER_AGENT = (
    "job-listings-scraper/1.0 "
    "(+https://github.com/Macho-Gaspacho/job-listings-scraper)"
)
# Latin (including extensions) and Cyrillic, plus space, apostrophe, dot, hyphen.
_ALIAS = re.compile(r"^[A-Za-zÀ-ɏЀ-ӿ .'\-]+$")


def _known_codes() -> set[str]:
    raw = yaml.safe_load(COUNTRIES.read_text(encoding="utf-8")) or {}
    return {str(entry.get("iso2") or "").upper() for entry in raw.values() if isinstance(entry, dict)}


def _aliases(field: str) -> str:
    found: set[str] = set()
    for part in field.split(","):
        name = part.strip()
        if name and _ALIAS.fullmatch(name):
            found.add(name)
    return "|".join(sorted(found))


def _rows(text: str) -> tuple[list[str], int, list[str]]:
    known = _known_codes()
    lines: list[tuple[int, str]] = []
    unknown_codes: set[str] = set()
    unknown_cities = 0
    for raw in text.splitlines():
        if not raw or raw.startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) < 15:
            continue
        try:
            population = int(parts[14])
        except ValueError:
            continue
        if population < MIN_POPULATION:
            continue
        code = parts[8].strip().upper()
        if code not in known:
            unknown_codes.add(code)
            unknown_cities += 1
        geonameid = int(parts[0])
        line = "\t".join(
            (
                parts[0].strip(),
                parts[1].strip(),
                parts[2].strip(),
                code,
                str(population),
                _aliases(parts[3] if len(parts) > 3 else ""),
            )
        )
        lines.append((geonameid, line))
    lines.sort(key=lambda item: item[0])
    return [line for _geonameid, line in lines], unknown_cities, sorted(unknown_codes)


def _gzip(payload: bytes) -> bytes:
    """gzip with mtime 0 so one input has one output on every OS."""
    return gzip.compress(payload, mtime=0)


def build(zip_bytes: bytes) -> tuple[int, int, list[str]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        name = next(item for item in archive.namelist() if item.endswith(".txt"))
        text = archive.read(name).decode("utf-8")
    lines, unknown_cities, unknown_codes = _rows(text)
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(_gzip(payload))
    return len(lines), unknown_cities, unknown_codes


def download() -> bytes:
    request = urllib.request.Request(CITIES_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def main() -> int:
    count, unknown_cities, unknown_codes = build(download())
    print(f"{count} cities")
    codes = ", ".join(unknown_codes) if unknown_codes else "none"
    print(f"{unknown_cities} cities have no entry in geodata/countries.yaml: {codes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
