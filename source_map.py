"""Decide which job sources to use. No network.

The map lives in sourcemap/sources.yaml. Role families live in
sourcemap/role_families.yaml. Link-out sites are named here and written
to a file later. This module never downloads them.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from config import KNOWN_SYSTEMS, Company
from places import norm
from regions import INDEED_COUNTRIES, canonical_country, english_name


_ROOT = Path(__file__).resolve().parent
_SOURCES_PATH = _ROOT / "sourcemap" / "sources.yaml"
_FAMILIES_PATH = _ROOT / "sourcemap" / "role_families.yaml"
_EMPLOYER_DIR = _ROOT / "employers"

_EMPLOYER_LINK_FAMILIES = {"consulting", "finance", "data", "product_project"}

_FAMILY_ORDER = (
    "tech",
    "data",
    "product_project",
    "consulting",
    "finance",
    "marketing",
    "medicine",
)

_FAMILY_LABEL = {
    "tech": "tech",
    "data": "data",
    "product_project": "product or project",
    "consulting": "consulting",
    "finance": "finance",
    "marketing": "marketing",
    "medicine": "medicine",
    "other": "other",
}

_SOURCE_LABEL = {
    "arbeitnow": "Arbeitnow",
    "remotive": "Remotive",
    "we_work_remotely": "We Work Remotely",
    "remote_ok": "Remote OK",
    "working_nomads": "Working Nomads",
    "indeed": "Indeed",
    "linkedin": "LinkedIn",
}

_NARROW_REMOTE = ("remotive", "we_work_remotely", "remote_ok")
_BROAD_AREAS = {"europe", "worldwide", "world", "anywhere", "global"}


@dataclass(frozen=True)
class Recommendation:
    """Sources in tier order, link-out ids, and the lines to print."""

    sources: tuple[str, ...]
    link_outs: tuple[str, ...]
    explanation: tuple[str, ...]
    family: str = "other"
    graduate: bool = False


def _read_yaml(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} should be a mapping.")
    return raw


@lru_cache(maxsize=1)
def _sources() -> dict:
    return _read_yaml(_SOURCES_PATH)


@lru_cache(maxsize=1)
def _families() -> dict:
    return _read_yaml(_FAMILIES_PATH)


def _phrase_list(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(norm(item) for item in values if norm(item))


def _has_phrase(text: str, phrase: str) -> bool:
    """True when phrase is a run of whole words inside text. Both are already normed."""
    words = text.split()
    parts = phrase.split()
    size = len(parts)
    if not size or len(words) < size:
        return False
    return any(words[index : index + size] == parts for index in range(len(words) - size + 1))


def role_family(role: str) -> tuple[str, bool]:
    """(family, graduate flag). The first listed family wins. Graduate is extra."""
    text = norm(role)
    table = _families()
    graduate = any(_has_phrase(text, phrase) for phrase in _phrase_list(table.get("graduate")))
    for name in _FAMILY_ORDER:
        if any(_has_phrase(text, phrase) for phrase in _phrase_list(table.get(name))):
            return name, graduate
    return "other", graduate


def auto_words() -> frozenset[str]:
    """Phrases that mean 'pick for me', already normalised."""
    return frozenset(_phrase_list(_sources().get("auto_words")))


def _country_key(country: str) -> str:
    text = str(country or "").strip()
    code = canonical_country(text) if text else None
    if code:
        return code
    return norm(text)


def _field(place: object, key: str, default=None):
    if isinstance(place, dict):
        return place.get(key, default)
    return getattr(place, key, default)


def _area(place: object) -> str:
    for key in ("indeed_location", "linkedin_location", "name"):
        text = str(_field(place, key) or "").strip()
        if text:
            return norm(text)
    return ""


def _any_remote(places: list) -> bool:
    return any(bool(_field(place, "remote", False)) for place in places)


def _broad_remote_only(places: list) -> bool:
    """The only places are remote, and each area is Europe or worldwide."""
    if not places or not all(bool(_field(place, "remote", False)) for place in places):
        return False
    return all(_area(place) in _BROAD_AREAS for place in places)


def _indeed_allowed(country_key: str, places: list) -> bool:
    """Indeed stays off for countries it does not cover, and for Europe or Worldwide alone."""
    if country_key not in INDEED_COUNTRIES:
        return False
    if not places:
        return True
    return any(_field(place, "search_indeed", True) is not False for place in places)


def _country_block(country_key: str) -> dict:
    data = _sources()
    defaults = data.get("defaults") or {}
    countries = data.get("countries") or {}
    block = countries.get(country_key) if isinstance(countries, dict) else None
    if not isinstance(block, dict):
        block = {}
        use_default = True
    else:
        use_default = False

    def pick(key: str) -> list:
        if key in block:
            value = block.get(key) or []
        elif use_default:
            value = defaults.get(key) or []
        else:
            value = block.get(key) or []
        return [str(item) for item in value]

    if use_default:
        return {
            "board": [str(item) for item in (defaults.get("board") or [])],
            "link_out": [str(item) for item in (defaults.get("link_out") or [])],
            "aggregator": [str(item) for item in (defaults.get("aggregator") or [])],
        }
    return {"board": pick("board"), "link_out": pick("link_out"), "aggregator": pick("aggregator")}


def _link_catalog() -> dict:
    raw = _sources().get("link_outs") or {}
    return raw if isinstance(raw, dict) else {}


def link_spec(link_id: str) -> dict | None:
    """Label and URL template for one link-out, or None when it was left out of the map."""
    entry = _link_catalog().get(link_id)
    if not isinstance(entry, dict):
        return None
    url = str(entry.get("url") or "").strip()
    label = str(entry.get("label") or link_id).strip()
    if not url or not label:
        return None
    return {"label": label, "url": url}


def remote_source_ids(places: list) -> list[str]:
    """Remote boards for this search. Empty when the user did not ask for remote work."""
    if not _any_remote(places):
        return []
    catalog = []
    remote = _sources().get("remote") or {}
    if isinstance(remote, dict):
        catalog = [str(item) for item in (remote.get("remote") or [])]
    if _broad_remote_only(places):
        return catalog
    return [item for item in catalog if item in _NARROW_REMOTE]


def _unique(items: list[str]) -> list[str]:
    found: list[str] = []
    for item in items:
        if item and item not in found:
            found.append(item)
    return found


def _labels(ids: list[str]) -> str:
    names = []
    catalog = _link_catalog()
    for source_id in ids:
        if source_id in _SOURCE_LABEL:
            names.append(_SOURCE_LABEL[source_id])
            continue
        entry = catalog.get(source_id)
        if isinstance(entry, dict) and entry.get("label"):
            names.append(str(entry["label"]))
        else:
            names.append(source_id.replace("_", " "))
    return ", ".join(names)


def _family_of(roles: list[str]) -> tuple[str, bool]:
    if not roles:
        return "other", False
    family, graduate = role_family(roles[0])
    if any(role_family(role)[1] for role in roles[1:]):
        graduate = True
    return family, graduate


def _employer_companies(path: Path) -> list[Company]:
    """Enabled employers whose last check succeeded. Missing files are empty."""
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return []
    found: list[Company] = []
    for entry in raw.get("employers") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("enabled", True) is False:
            continue
        last = entry.get("last_check") or {}
        status = str(last.get("status") or "ok") if isinstance(last, dict) else "ok"
        if status != "ok":
            continue
        system = str(entry.get("system") or "").strip().casefold()
        name = str(entry.get("name") or "").strip()
        if not name or system not in KNOWN_SYSTEMS:
            continue
        families = entry.get("families") or []
        if isinstance(families, str):
            families = [families]
        jobs = 0
        if isinstance(last, dict):
            try:
                jobs = int(last.get("jobs_in_country") or 0)
            except (TypeError, ValueError):
                jobs = 0
        found.append(
            Company(
                name=name,
                system=system,
                token=str(entry.get("token") or "").strip(),
                enabled=True,
                region=str(entry.get("region") or "").strip().casefold(),
                families=tuple(str(item).strip() for item in families if str(item).strip()),
                curated=True,
                jobs_in_country=jobs,
            )
        )
    return found


def curated_employers(country: str, places: list, roles: list[str]) -> list[Company]:
    """Curated career pages for this country and role, capped at 60.

    A remote place also adds employers from employers/europe_remote.yaml.
    """
    from boards import select_companies

    places = list(places or [])
    country_key = _country_key(country)
    found: list[Company] = []
    seen: set[tuple[str, str]] = set()
    paths = []
    if country_key:
        paths.append(_EMPLOYER_DIR / f"{country_key}.yaml")
    if _any_remote(places):
        paths.append(_EMPLOYER_DIR / "europe_remote.yaml")
    for path in paths:
        for company in _employer_companies(path):
            key = (company.system, company.token.casefold())
            if key in seen:
                continue
            seen.add(key)
            found.append(company)
    return select_companies(found, roles)


def recommend(country: str, places: list, roles: list[str]) -> Recommendation:
    """Ordered source ids, link-out ids, and the plain-language explanation."""
    places = list(places or [])
    roles = [str(role) for role in (roles or [])]
    country_key = _country_key(country)
    block = _country_block(country_key)
    family, graduate = _family_of(roles)
    boards = _unique(block["board"])
    remote_ids = remote_source_ids(places)
    aggregators = []
    for source_id in block["aggregator"]:
        if source_id == "indeed" and not _indeed_allowed(country_key, places):
            continue
        aggregators.append(source_id)
    aggregators = _unique(aggregators)
    link_ids = _unique(block["link_out"])
    if graduate:
        extra = _sources().get("graduate_link_outs") or []
        link_ids = _unique(link_ids + [str(item) for item in extra])
    if family in _EMPLOYER_LINK_FAMILIES:
        mapping = _sources().get("employer_link_outs") or {}
        if isinstance(mapping, dict):
            extra = mapping.get(country_key) or []
            link_ids = _unique(link_ids + [str(item) for item in extra])
    link_ids = [item for item in link_ids if link_spec(item)]
    sources = tuple(_unique(boards + remote_ids + aggregators))
    label = _FAMILY_LABEL.get(family, family.replace("_", " "))
    country_name = english_name(country_key) if country_key else str(country or "").strip()
    curated = curated_employers(country_key, places, roles)
    lines = [f"Recommended for a {label} job in {country_name}:"]
    lines.append(
        "  First: company career pages "
        f"({len(curated)} employers that hire {label} people in {country_name}, "
        "plus any you add)."
    )
    if boards:
        lines.append(f"  Then: {_labels(boards)}.")
    if remote_ids:
        lines.append(f"  Remote boards: {_labels(remote_ids)}.")
    if link_ids:
        lines.append(
            "  Links to open yourself (we do not read these sites): "
            f"{_labels(link_ids)}. They will be in output/links.md."
        )
    if aggregators == ["indeed", "linkedin"]:
        lines.append("  Last: Indeed, LinkedIn (most applicants per job).")
    elif aggregators == ["linkedin"]:
        lines.append("  Last: LinkedIn (most applicants per job).")
    elif aggregators == ["indeed"]:
        lines.append("  Last: Indeed (most applicants per job).")
    elif aggregators:
        lines.append(f"  Last: {_labels(aggregators)} (most applicants per job).")
    return Recommendation(
        sources=sources,
        link_outs=tuple(link_ids),
        explanation=tuple(lines),
        family=family,
        graduate=graduate,
    )


def chosen_sources(
    choice: str | set[str],
    country: str,
    places: list,
    roles: list[str],
    companies: list,
) -> tuple[set[str], list[str]]:
    """Enabled source ids, and link-out ids (link-outs only in auto mode)."""
    places = list(places or [])
    roles = list(roles or [])
    companies = list(companies or [])
    if choice == "auto":
        recommendation = recommend(country, places, roles)
        enabled = set(recommendation.sources)
        if companies:
            enabled.add("company_pages")
        return enabled, list(recommendation.link_outs)
    groups = set(choice or [])
    enabled: set[str] = set()
    if "company" in groups and companies:
        enabled.add("company_pages")
    if "board" in groups:
        enabled.update(_country_block(_country_key(country))["board"])
    for item in groups:
        if str(item).startswith("board:"):
            enabled.add(str(item).split(":", 1)[1])
    if "remote" in groups:
        enabled.update(remote_source_ids(places))
    country_key = _country_key(country)
    if "indeed" in groups and _indeed_allowed(country_key, places):
        enabled.add("indeed")
    if "linkedin" in groups:
        enabled.add("linkedin")
    return enabled, []
