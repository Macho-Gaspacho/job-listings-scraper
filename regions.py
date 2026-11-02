"""Country names and the location rules built from a user's config.

Company pages and remote boards use these rules. They do not assume a city.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from matching import normalise


# Country names Indeed accepts. The setup wizard and config.py both use this list.
INDEED_COUNTRIES = frozenset(
    {
        "argentina",
        "australia",
        "austria",
        "bahrain",
        "belgium",
        "brazil",
        "canada",
        "chile",
        "china",
        "colombia",
        "costa rica",
        "czech republic",
        "denmark",
        "ecuador",
        "egypt",
        "finland",
        "france",
        "germany",
        "greece",
        "hong kong",
        "hungary",
        "india",
        "indonesia",
        "ireland",
        "israel",
        "italy",
        "japan",
        "kuwait",
        "luxembourg",
        "malaysia",
        "mexico",
        "morocco",
        "netherlands",
        "new zealand",
        "nigeria",
        "norway",
        "oman",
        "pakistan",
        "panama",
        "peru",
        "philippines",
        "poland",
        "portugal",
        "qatar",
        "romania",
        "saudi arabia",
        "singapore",
        "south africa",
        "south korea",
        "spain",
        "sweden",
        "switzerland",
        "taiwan",
        "thailand",
        "türkiye",
        "ukraine",
        "united arab emirates",
        "uk",
        "usa",
        "uruguay",
        "venezuela",
        "vietnam",
    }
)

# Countries LinkedIn can search that Indeed's country list does not include.
# The wizard still allows these and leaves Indeed off.
OTHER_COUNTRIES = frozenset(
    {
        "albania",
        "armenia",
        "azerbaijan",
        "bangladesh",
        "belarus",
        "bosnia and herzegovina",
        "bulgaria",
        "croatia",
        "cyprus",
        "estonia",
        "georgia",
        "ghana",
        "iceland",
        "jordan",
        "kazakhstan",
        "kenya",
        "latvia",
        "lebanon",
        "lithuania",
        "malta",
        "moldova",
        "montenegro",
        "nepal",
        "north macedonia",
        "serbia",
        "slovakia",
        "slovenia",
        "sri lanka",
        "tunisia",
    }
)

# A name a person might type, and the Indeed country it means.
COUNTRY_ALIASES = {
    "czechia": "czech republic",
    "turkey": "türkiye",
    "uae": "united arab emirates",
    "united kingdom": "uk",
    "u.k.": "uk",
    "great britain": "uk",
    "britain": "uk",
    "england": "uk",
    "scotland": "uk",
    "wales": "uk",
    "us": "usa",
    "u.s.": "usa",
    "u.s.a.": "usa",
    "united states": "usa",
    "united states of america": "usa",
    "america": "usa",
    "italia": "italy",
    "deutschland": "germany",
    "espana": "spain",
    "españa": "spain",
    "holland": "netherlands",
    "the netherlands": "netherlands",
    "bosnia": "bosnia and herzegovina",
    "macedonia": "north macedonia",
    "republic of serbia": "serbia",
    "republic of armenia": "armenia",
}

# A common native name, used when a remote advert writes the country that way.
NATIVE_NAMES = {
    "austria": "Österreich",
    "brazil": "Brasil",
    "czech republic": "Česko",
    "denmark": "Danmark",
    "finland": "Suomi",
    "germany": "Deutschland",
    "greece": "Elláda",
    "hungary": "Magyarország",
    "italy": "Italia",
    "japan": "Nihon",
    "mexico": "México",
    "netherlands": "Nederland",
    "norway": "Norge",
    "poland": "Polska",
    "spain": "España",
    "sweden": "Sverige",
    "switzerland": "Schweiz",
}

# Indeed codes that are in the EU or the EEA. Remote jobs for those countries
# also match Europe, EU, and EMEA. The UK is not in this set.
EU_EEA = frozenset(
    {
        "austria",
        "belgium",
        "czech republic",
        "denmark",
        "finland",
        "france",
        "germany",
        "greece",
        "hungary",
        "ireland",
        "italy",
        "luxembourg",
        "netherlands",
        "norway",
        "poland",
        "portugal",
        "romania",
        "spain",
        "sweden",
    }
)

_ENGLISH_NAMES = {
    "uk": "United Kingdom",
    "usa": "United States",
    "türkiye": "Türkiye",
}

# Region words that are not Indeed countries, but show up in remote adverts.
_EXTRA_REGIONS = (
    "eu",
    "eea",
    "europe",
    "european",
    "emea",
    "latam",
    "latin america",
    "apac",
    "asia",
    "worldwide",
    "anywhere",
    "global",
    "north america",
    "south america",
)

_REGION_FAMILY = {
    "eu": frozenset({"eu", "eea", "europe", "european"}),
    "eea": frozenset({"eu", "eea", "europe", "european"}),
    "europe": frozenset({"eu", "eea", "europe", "european"}),
    "european": frozenset({"eu", "eea", "europe", "european"}),
}

_SKIP_OFFICE_PHRASES = frozenset(
    {"remote", "work from home", "working from home", "hybrid", "on site", "onsite"}
)


@dataclass(frozen=True)
class LocationFilter:
    """The optional location_filter block. None means "work this out"."""

    offices: tuple[str, ...] | None = None
    remote_regions: tuple[str, ...] | None = None
    exclude_regions: tuple[str, ...] | None = None


@dataclass(frozen=True)
class LocationRules:
    """How one user's config decides which offices and remote jobs to keep."""

    country: str
    remote_regions: tuple[str, ...]
    exclude_regions: tuple[str, ...]
    offices: tuple[tuple[str, tuple[str, ...]], ...]


def fold_text(value: object) -> str:
    """Lowercase text with accents removed, so München and Munchen compare equal."""
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("-", " ").replace("–", " ").replace("—", " ")
    return " ".join(text.casefold().split())


def contains_phrase(phrase: str, text: str) -> bool:
    """True when phrase is a whole word or a whole sequence of words in text.

    Words are split the same way as job titles, so a hyphen is a gap and
    "us" does not match inside "user".
    """
    needle = [token[:-1] if token.endswith("*") else token for token in normalise(phrase)]
    needle = [token for token in needle if token]
    haystack = [token[:-1] if token.endswith("*") else token for token in normalise(text)]
    haystack = [token for token in haystack if token]
    if not needle or not haystack or len(needle) > len(haystack):
        return False
    size = len(needle)
    return any(haystack[index : index + size] == needle for index in range(len(haystack) - size + 1))


@lru_cache(maxsize=1)
def _canonical_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for code in INDEED_COUNTRIES | OTHER_COUNTRIES:
        index[fold_text(code)] = code
    for alias, code in COUNTRY_ALIASES.items():
        index[fold_text(alias)] = code
    return index


def canonical_country(name: str) -> str | None:
    """An Indeed country code, or None when the name is not a country."""
    text = fold_text(name)
    if not text:
        return None
    return _canonical_index().get(text)


def english_name(country: str) -> str:
    """The English name for a country code."""
    if country in _ENGLISH_NAMES:
        return _ENGLISH_NAMES[country]
    small = {"and", "of", "the"}
    words = []
    for index, part in enumerate(country.split()):
        if index and part in small:
            words.append(part)
        else:
            words.append(part.capitalize())
    return " ".join(words)


def country_from_places(places) -> str | None:
    """The country named by the first office, such as Berlin, Germany -> germany."""
    for place in places:
        if getattr(place, "remote", False):
            continue
        for text in (
            getattr(place, "name", ""),
            getattr(place, "indeed_location", ""),
            getattr(place, "linkedin_location", ""),
        ):
            code = _country_in_text(str(text or ""))
            if code:
                return code
    return None


def _country_in_text(text: str) -> str | None:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    candidates = []
    if parts:
        candidates.append(parts[-1])
    candidates.extend(reversed(parts))
    candidates.append(text)
    for candidate in candidates:
        code = canonical_country(candidate)
        if code:
            return code
        for inner in re.findall(r"\(([^)]*)\)", candidate):
            code = canonical_country(inner)
            if code:
                return code
    return None


def default_remote_regions(country: str) -> tuple[str, ...]:
    """Country name, native name, and worldwide. Europe only for an EU/EEA country."""
    names = [english_name(country)]
    native = NATIVE_NAMES.get(country)
    if native and fold_text(native) != fold_text(names[0]):
        names.append(native)
    names.extend(("Worldwide", "Anywhere", "Global"))
    if country in EU_EEA:
        names.extend(("Europe", "EU", "EMEA"))
    result: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = fold_text(name)
        if key and key not in seen:
            seen.add(key)
            result.append(name)
    return tuple(result)


def _keep_office_phrase(phrase: str) -> bool:
    folded = fold_text(phrase)
    if not folded or folded in _SKIP_OFFICE_PHRASES:
        return False
    letters = re.sub(r"[^a-z0-9]", "", folded)
    if len(letters) < 3 and canonical_country(phrase) is None:
        return False
    return True


def _push_phrase(found: list[str], seen: set[str], phrase: str) -> None:
    cleaned = " ".join(phrase.split())
    if not _keep_office_phrase(cleaned):
        return
    key = fold_text(cleaned)
    if key in seen:
        return
    seen.add(key)
    found.append(cleaned)


def phrases_from_place(place) -> tuple[str, ...]:
    """City and country words from a place name and its search locations."""
    found: list[str] = []
    seen: set[str] = set()
    for text in (
        getattr(place, "name", ""),
        getattr(place, "indeed_location", ""),
        getattr(place, "linkedin_location", ""),
    ):
        for segment in re.split(r"[,;/|]", str(text or "")):
            bare = re.sub(r"\([^)]*\)", " ", segment)
            _push_phrase(found, seen, bare)
            for inner in re.findall(r"\(([^)]*)\)", segment):
                _push_phrase(found, seen, inner)
    return tuple(found)


def _place_blob(place) -> str:
    return " ".join(
        str(part or "")
        for part in (
            getattr(place, "name", ""),
            getattr(place, "indeed_location", ""),
            getattr(place, "linkedin_location", ""),
        )
    )


def _office_map(places, explicit: tuple[str, ...] | None) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Pair each office with the words that mean that office.

    One city and an explicit list: every word belongs to that city, including
    a local spelling that is not in the place name. Several cities: a word is
    given to the city it appears in, and a shared word such as the country
    is given to each of them.
    """
    offices = [place for place in places if not getattr(place, "remote", False)]
    if explicit is None:
        return tuple((place.name, phrases_from_place(place)) for place in offices)
    if len(offices) == 1:
        return ((offices[0].name, tuple(explicit)),)
    assigned = {place.name: [] for place in offices}
    blobs = {place.name: _place_blob(place) for place in offices}
    for phrase in explicit:
        owners = [name for name, blob in blobs.items() if contains_phrase(phrase, blob)]
        for name in owners or list(assigned):
            assigned[name].append(phrase)
    return tuple((name, tuple(phrases)) for name, phrases in assigned.items())


def build_location_rules(places, country: str, explicit: LocationFilter | None = None) -> LocationRules:
    """Rules for company pages and remote boards. Missing lists are filled in."""
    offices = None if explicit is None else explicit.offices
    regions = None if explicit is None else explicit.remote_regions
    excluded = None if explicit is None else explicit.exclude_regions
    return LocationRules(
        country=country,
        remote_regions=(
            default_remote_regions(country) if regions is None else tuple(regions)
        ),
        exclude_regions=() if excluded is None else tuple(excluded),
        offices=_office_map(places, offices),
    )


def _terms_for(labels: tuple[str, ...]) -> frozenset[str]:
    terms: set[str] = set()
    for label in labels:
        folded = fold_text(label)
        if folded:
            terms.add(folded)
        code = canonical_country(label)
        if code is None:
            continue
        for extra in (
            code,
            english_name(code),
            NATIVE_NAMES.get(code, ""),
        ):
            folded_extra = fold_text(extra)
            if folded_extra:
                terms.add(folded_extra)
        for alias, target in COUNTRY_ALIASES.items():
            if target == code:
                terms.add(fold_text(alias))
    return frozenset(term for term in terms if re.sub(r"[^a-z0-9]", "", term))


def remote_terms(rules: LocationRules) -> frozenset[str]:
    """Words that mean a remote job is open where this user asked to look."""
    terms = set(_terms_for(rules.remote_regions))
    if {"eu", "europe", "eea"} & terms:
        terms.add("european")
    return frozenset(terms)


def home_terms(rules: LocationRules) -> frozenset[str]:
    """The user's country plus the remote regions. Used to spot "somewhere else only"."""
    return remote_terms(rules) | _terms_for((english_name(rules.country), rules.country))


def matches_remote_region(location: str, rules: LocationRules) -> bool:
    """True when the location names one of the user's remote regions."""
    return any(contains_phrase(term, location) for term in remote_terms(rules))


def is_home_region(label: str, rules: LocationRules) -> bool:
    """True when this region word means the user's own country or remote region."""
    folded = fold_text(label)
    terms = home_terms(rules)
    if folded in terms:
        return True
    family = _REGION_FAMILY.get(folded, frozenset())
    return bool(family & terms)


@lru_cache(maxsize=1)
def exclusion_labels() -> tuple[str, ...]:
    """Country and region names, longest first, for "X only" checks."""
    found: list[str] = []
    seen: set[str] = set()
    for label in (*INDEED_COUNTRIES, *COUNTRY_ALIASES, *_EXTRA_REGIONS):
        folded = fold_text(label)
        letters = re.sub(r"[^a-z0-9]", "", folded)
        if len(letters) < 2 or folded in seen:
            continue
        seen.add(folded)
        found.append(label)
    found.sort(key=lambda item: len(fold_text(item)), reverse=True)
    return tuple(found)


def excluded_region(text: str, rules: LocationRules) -> bool:
    """True when the text says the role is limited to somewhere else.

    "Bonus only" and "remote user research" are not region limits.
    "US only" is, unless the user's own country is the US.
    """
    folded = fold_text(text)
    if not folded:
        return False
    for phrase in rules.exclude_regions:
        if contains_phrase(phrase, folded):
            return True
    if " only" not in folded and "remote" not in folded:
        return False
    for label in exclusion_labels():
        if is_home_region(label, rules):
            continue
        if " only" in folded and (
            contains_phrase(f"{label} only", folded)
            or contains_phrase(f"based in {label} only", folded)
            or contains_phrase(f"based in the {label} only", folded)
        ):
            return True
        if "remote" in folded and (
            contains_phrase(f"remote {label}", folded)
            or contains_phrase(f"remote, {label}", folded)
        ):
            return True
    return False


def matching_office(location: str, rules: LocationRules) -> str | None:
    """The configured place name whose city or country words appear in the location."""
    best_name = None
    best_score = 0
    for name, phrases in rules.offices:
        score = 0
        for phrase in phrases:
            if contains_phrase(phrase, location):
                score += len(fold_text(phrase))
        if score > best_score:
            best_score = score
            best_name = name
    return best_name


_REMOTE_HINTS = (
    "remote",
    "work from home",
    "working from home",
    "da remoto",
    "lavoro da casa",
    "anywhere",
    "worldwide",
)
_GENERIC_REMOTE = frozenset(
    {"remote", "worldwide", "anywhere", "global", "work from home"}
)


def looks_remote(location: str, is_remote: bool) -> bool:
    """True when the posting says it can be done from home, or the site flagged it."""
    if is_remote:
        return True
    return any(contains_phrase(hint, location) for hint in _REMOTE_HINTS)


def _generic_remote(location: str, is_remote: bool) -> bool:
    folded = fold_text(location)
    if is_remote and not folded:
        return True
    return folded in _GENERIC_REMOTE


def classify_place(location: str, is_remote: bool = False, rules: LocationRules | None = None) -> str | None:
    """Return the matching place name, "Remote", or None when the job is somewhere else."""
    if rules is None:
        raise ValueError("Location rules are required. They are built from config.yaml.")
    if excluded_region(location, rules):
        return None
    if looks_remote(location, is_remote):
        allowed = (
            matches_remote_region(location, rules)
            or matching_office(location, rules) is not None
            or _generic_remote(location, is_remote)
        )
        return "Remote" if allowed else None
    return matching_office(location, rules)


def system_timezone_name() -> str:
    """The computer's timezone, as an IANA name when Python knows one."""
    current = datetime.now().astimezone()
    key = getattr(current.tzinfo, "key", None)
    if isinstance(key, str) and key:
        return key
    try:
        name = current.tzname()
    except Exception:
        name = None
    return name or "UTC"


def validate_timezone(name: str) -> str:
    """An IANA timezone name, or a clear error when the name is not real."""
    cleaned = " ".join(str(name).split())
    try:
        ZoneInfo(cleaned)
    except Exception as exc:
        raise ValueError(
            f"timezone '{cleaned}' is not a recognised timezone. "
            "Use a name such as America/Chicago or Europe/Berlin."
        ) from exc
    return cleaned
