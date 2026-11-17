"""Resolve a typed city or country to one real place.

A hand-written list of hub cities misses every city we did not think of,
and every spelling we did not write down. GeoNames cities15000 (CC BY 4.0)
has local and Cyrillic names. Filtered to population >= 50,000 it is small
enough to ship, so this works offline and the same way on every computer.
"Milan, Texas" is not in that file. See geodata/NOTICE.md.
"""

from __future__ import annotations

import gzip
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from regions import canonical_country, english_name


_DATA = Path(__file__).resolve().parent / "geodata" / "cities.tsv.gz"
_COUNTRIES = Path(__file__).resolve().parent / "geodata" / "countries.yaml"

# GeoNames uses the administrative name. The label people expect is shorter.
_CITY_NAMES = {"Frankfurt am Main": "Frankfurt"}

_REMOTE = (
    "remote",
    "remoto",
    "remote work",
    "удаленно",
    "удалённо",
    "удаленка",
    "удалёнка",
    "da remoto",
    "homeoffice",
    "home office",
    "telearbeit",
    "teletravail",
    "télétravail",
)


@dataclass(frozen=True)
class PlaceResult:
    """What one typed place resolved to.

    ``detail`` is ``city`` or ``country`` when status is ``unknown``, so the
    wizard can pick the message. ``choices`` is set only for ``choose``.
    """

    status: str
    city: str = ""
    country: str = ""
    label: str = ""
    choices: tuple[tuple[str, str, str], ...] = ()
    typed: str = ""
    detail: str = ""


@dataclass(frozen=True)
class _City:
    name: str
    asciiname: str
    country: str
    population: int
    aliases: tuple[str, ...]


def norm(value: object) -> str:
    """NFKC, casefold, drop accents, treat ё as е, and turn hyphens and dots into spaces."""
    text = unicodedata.normalize("NFKC", "" if value is None else str(value))
    text = text.casefold().replace("ё", "е")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("-", " ").replace(".", " ")
    return " ".join(text.split())


def _title_case(value: str) -> str:
    return " ".join(value.split()).title()


@lru_cache(maxsize=1)
def _iso_to_country() -> dict[str, str]:
    if not _COUNTRIES.is_file():
        return {}
    raw = yaml.safe_load(_COUNTRIES.read_text(encoding="utf-8")) or {}
    found = {}
    for key, entry in raw.items():
        if isinstance(entry, dict) and entry.get("iso2"):
            found[str(entry["iso2"]).upper()] = str(key)
    return found


def _country_of(text: str) -> str | None:
    """Canonical country key, from regions and then geodata/countries.yaml."""
    found = canonical_country(text)
    if found:
        return found
    if not text or not _COUNTRIES.is_file():
        return None
    raw = yaml.safe_load(_COUNTRIES.read_text(encoding="utf-8")) or {}
    wanted = norm(text)
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        for alias in entry.get("names") or []:
            if norm(alias) == wanted:
                return str(key)
    return None


def _display_city(name: str) -> str:
    return _CITY_NAMES.get(name, name)


def _label(city: str, country: str) -> str:
    return f"{city}, {english_name(country)}"


@lru_cache(maxsize=1)
def _indexes() -> tuple[dict[str, tuple[_City, ...]], dict[str, tuple[_City, ...]]]:
    if not _DATA.is_file():
        raise FileNotFoundError(
            f"Missing {_DATA}. Build it with tools/build_places.py."
        )
    iso = _iso_to_country()
    tier1: dict[str, list[_City]] = {}
    tier2: dict[str, list[_City]] = {}
    seen1: dict[str, set[int]] = {}
    seen2: dict[str, set[int]] = {}
    with gzip.open(_DATA, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue
            country = iso.get(parts[3].upper())
            if not country:
                continue
            city = _City(
                name=parts[1],
                asciiname=parts[2],
                country=country,
                population=int(parts[4]),
                aliases=tuple(alias for alias in parts[5].split("|") if alias),
            )
            for key in {norm(city.name), norm(city.asciiname)}:
                if not key:
                    continue
                bucket = seen1.setdefault(key, set())
                if line_number in bucket:
                    continue
                bucket.add(line_number)
                tier1.setdefault(key, []).append(city)
            for alias in city.aliases:
                key = norm(alias)
                if not key:
                    continue
                bucket = seen2.setdefault(key, set())
                if line_number in bucket:
                    continue
                bucket.add(line_number)
                tier2.setdefault(key, []).append(city)
    return (
        {key: tuple(cities) for key, cities in tier1.items()},
        {key: tuple(cities) for key, cities in tier2.items()},
    )


def _lookup(city_text: str, country: str) -> list[_City]:
    tier1, tier2 = _indexes()
    key = norm(city_text)
    found = list(tier1.get(key) or ())
    if not found:
        found = list(tier2.get(key) or ())
    if country:
        found = [city for city in found if city.country == country]
    best: dict[tuple[str, str], _City] = {}
    for city in found:
        pair = (city.name, city.country)
        current = best.get(pair)
        if current is None or city.population > current.population:
            best[pair] = city
    return list(best.values())


def _result(status: str, typed: str, city: _City | None = None, **overrides) -> PlaceResult:
    if city is None:
        return PlaceResult(status=status, typed=typed, **overrides)
    shown = _display_city(city.name)
    return PlaceResult(
        status=status,
        city=shown,
        country=city.country,
        label=_label(shown, city.country),
        typed=typed,
    )


def resolve_place(raw: str) -> PlaceResult:
    """One typed place: a city, a country, remote, or a short question."""
    typed = "" if raw is None else str(raw)
    if not norm(typed):
        return PlaceResult(status="empty", typed=typed)
    if norm(typed) in {norm(phrase) for phrase in _REMOTE}:
        return PlaceResult(status="remote", typed=typed)

    if "," in typed:
        city_part, country_part = typed.rsplit(",", 1)
        country = _country_of(country_part.strip())
        if country is None:
            return PlaceResult(status="unknown", typed=typed, detail="country")
        country_given = True
    else:
        country = _country_of(typed.strip())
        if country is not None:
            return PlaceResult(
                status="country_only",
                country=country,
                label=english_name(country),
                typed=typed,
            )
        city_part = typed
        country_given = False

    matches = _lookup(city_part, country if country_given else "")
    if not matches and country_given:
        shown = _title_case(city_part)
        return PlaceResult(
            status="ok",
            city=shown,
            country=country,
            label=_label(shown, country),
            typed=typed,
        )
    if not matches:
        return PlaceResult(status="unknown", typed=typed, detail="city")

    matches.sort(key=lambda city: city.population, reverse=True)
    if len(matches) >= 2 and matches[0].population < 10 * matches[1].population:
        choices = tuple(
            (_display_city(city.name), city.country, _label(_display_city(city.name), city.country))
            for city in matches[:5]
        )
        return PlaceResult(status="choose", choices=choices, typed=typed)
    winner = matches[0]
    return _result("ok" if country_given else "confirm", typed, winner)
