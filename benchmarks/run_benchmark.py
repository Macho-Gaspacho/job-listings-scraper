"""Run the fixed benchmark and write a summary.

The search is the same path as ``scrape.py`` without the wizard. Place text
goes through the wizard's own parsers. A place the wizard would reject, or a
place with several matches, is recorded and the run continues. One confirmed
match is accepted, because the wizard's default for that question is Yes.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import traceback
import unicodedata
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

import scrape  # noqa: E402
import setup_wizard  # noqa: E402
from config import load_config  # noqa: E402
from listings import OUTPUT_FIELDS  # noqa: E402
from sources import fetch_listings  # noqa: E402
from regions import (  # noqa: E402
    COUNTRY_ALIASES,
    EU_EEA,
    INDEED_COUNTRIES,
    NATIVE_NAMES,
    _country_in_text,
    contains_phrase,
    english_name,
    fold_text,
)
from source_map import chosen_sources  # noqa: E402
from synonyms import suggestions_for  # noqa: E402


QUERIES_PATH = Path(__file__).resolve().parent / "queries.yaml"
RESULTS_ROOT = Path(__file__).resolve().parent / "results"

# Home country used when the remote area is not itself a country (Europe).
# The wizard would ask. Indeed is not searched for that area, so the choice
# does not change the request. Italy is the example in that question.
_REMOTE_HOME_COUNTRY = "italy"

_COLUMNS = (
    "query",
    "status",
    "total",
    "relevant_in_sample",
    "wrong_country",
    "company_pages_%",
    "aggregators_%",
    "per_source",
    "blocked",
    "errors",
    "seconds",
)

# ISO alpha-2 for every country regions.py knows. A trailing ", XX" counts as
# a US state unless XX is the expected country's own code (DE is Germany and
# Delaware; TN is Tunisia and Tennessee).
ISO2 = {
    "argentina": "AR",
    "australia": "AU",
    "austria": "AT",
    "bahrain": "BH",
    "belgium": "BE",
    "brazil": "BR",
    "canada": "CA",
    "chile": "CL",
    "china": "CN",
    "colombia": "CO",
    "costa rica": "CR",
    "czech republic": "CZ",
    "denmark": "DK",
    "ecuador": "EC",
    "egypt": "EG",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "greece": "GR",
    "hong kong": "HK",
    "hungary": "HU",
    "india": "IN",
    "indonesia": "ID",
    "ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "japan": "JP",
    "kuwait": "KW",
    "luxembourg": "LU",
    "malaysia": "MY",
    "mexico": "MX",
    "morocco": "MA",
    "netherlands": "NL",
    "new zealand": "NZ",
    "nigeria": "NG",
    "norway": "NO",
    "oman": "OM",
    "pakistan": "PK",
    "panama": "PA",
    "peru": "PE",
    "philippines": "PH",
    "poland": "PL",
    "portugal": "PT",
    "qatar": "QA",
    "romania": "RO",
    "saudi arabia": "SA",
    "singapore": "SG",
    "south africa": "ZA",
    "south korea": "KR",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "taiwan": "TW",
    "thailand": "TH",
    "türkiye": "TR",
    "ukraine": "UA",
    "united arab emirates": "AE",
    "uk": "GB",
    "usa": "US",
    "uruguay": "UY",
    "venezuela": "VE",
    "vietnam": "VN",
    "albania": "AL",
    "armenia": "AM",
    "azerbaijan": "AZ",
    "bangladesh": "BD",
    "belarus": "BY",
    "bosnia and herzegovina": "BA",
    "bulgaria": "BG",
    "croatia": "HR",
    "cyprus": "CY",
    "estonia": "EE",
    "georgia": "GE",
    "ghana": "GH",
    "iceland": "IS",
    "jordan": "JO",
    "kazakhstan": "KZ",
    "kenya": "KE",
    "latvia": "LV",
    "lebanon": "LB",
    "lithuania": "LT",
    "malta": "MT",
    "moldova": "MD",
    "montenegro": "ME",
    "nepal": "NP",
    "north macedonia": "MK",
    "serbia": "RS",
    "slovakia": "SK",
    "slovenia": "SI",
    "sri lanka": "LK",
    "tunisia": "TN",
}

US_STATE_CODES = frozenset(
    """
    AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD
    MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC
    SD TN TX UT VT VA WA WV WI WY
    """.split()
)

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_STATE_SUFFIX = re.compile(r",\s*([A-Za-z]{2})\s*$")
_GENERIC_REMOTE = frozenset(
    {
        "",
        "remote",
        "remoto",
        "remote work",
        "work from home",
        "working from home",
        "home office",
        "homeoffice",
        "da remoto",
        "worldwide",
        "anywhere",
        "global",
    }
)
_REMOTE_EU_WORDS = frozenset({"eu", "eea", "emea", "europe", "european"})
_HEADER_TO_KEY = {label: key for key, label in OUTPUT_FIELDS}


def load_spec(path: Path | None = None) -> dict:
    """The fixed queries file."""
    raw = yaml.safe_load((path or QUERIES_PATH).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or not isinstance(raw.get("queries"), list):
        raise ValueError("benchmarks/queries.yaml needs a queries list.")
    return raw


def _tokens(text: object) -> list[str]:
    decomposed = unicodedata.normalize("NFKD", "" if text is None else str(text))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _WORD.findall(stripped.casefold())


def _phrase_in_title(title: object, phrase: object) -> bool:
    haystack = _tokens(title)
    needle = _tokens(phrase)
    if not needle or len(needle) > len(haystack):
        return False
    size = len(needle)
    return any(haystack[index : index + size] == needle for index in range(len(haystack) - size + 1))


def _country_labels(country: str) -> list[str]:
    labels = [country, english_name(country)]
    native = NATIVE_NAMES.get(country, "")
    if native:
        labels.append(native)
    for alias, target in COUNTRY_ALIASES.items():
        if target == country:
            labels.append(alias)
    return [label for label in labels if label]


def _mentions_country(location: str, country: str) -> bool:
    if any(contains_phrase(label, location) for label in _country_labels(country)):
        return True
    iso = ISO2.get(country, "")
    return bool(iso) and iso.casefold() in _tokens(location)


def _mentions_city(location: str, city_names: list[str]) -> bool:
    return any(contains_phrase(name, location) for name in city_names if name)


def _foreign_state_suffix(location: str, expected: list[str]) -> bool:
    """True when the location ends with a US state code for a non-US search.

    A code that is the expected country's ISO alpha-2 is the country itself.
    """
    if "usa" in expected:
        return False
    match = _STATE_SUFFIX.search(str(location or "").strip())
    if match is None:
        return False
    code = match.group(1).upper()
    if code not in US_STATE_CODES:
        return False
    own = {ISO2.get(country, "") for country in expected if country != "remote_eu"}
    return code not in own


def _wrong_country(location: str, expected: list[str]) -> bool:
    if _foreign_state_suffix(location, expected):
        return True
    if "remote_eu" in expected:
        found = _country_in_text(location)
        return bool(found) and found not in EU_EEA
    found = _country_in_text(location)
    return bool(found) and found not in expected


def _remote_eu(location: str) -> bool:
    folded = fold_text(location)
    if folded in _GENERIC_REMOTE:
        return True
    words = set(_tokens(location))
    if words & _REMOTE_EU_WORDS:
        return True
    return any(_mentions_country(location, country) for country in EU_EEA)


def _location_passes(location: str, expected: list[str], city_names: list[str]) -> bool:
    if "remote_eu" in expected:
        return _remote_eu(location)
    if not str(location or "").strip():
        return True
    # A US state suffix or another country's name is not "the place we searched",
    # even when the city spelling matches (Milano, TX).
    if _wrong_country(location, expected):
        return False
    if any(_mentions_country(location, country) for country in expected):
        return True
    return _mentions_city(location, city_names)


def _percent(count: int, total: int) -> int:
    if total <= 0:
        return 0
    return int(round(100 * count / total))


def _per_source(rows: list[dict]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        for part in str(row.get("source") or "").split(", "):
            name = part.strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{name}:{counts[name]}" for name in sorted(counts))


def measure(rows: list[dict], query: dict, sample_size: int, city_names: list[str] | None = None) -> dict:
    """Counts for one saved result file. ``rows`` are already filtered and deduped."""
    expected = [str(item) for item in query.get("expected_countries") or []]
    phrases = [str(item) for item in query.get("relevant_title_phrases") or []]
    names = list(city_names) if city_names is not None else _city_names(query, None)
    total = len(rows)
    sample = rows[:sample_size]
    relevant = 0
    for row in sample:
        title_ok = any(_phrase_in_title(row.get("title", ""), phrase) for phrase in phrases)
        place_ok = _location_passes(str(row.get("location") or ""), expected, names)
        if title_ok and place_ok:
            relevant += 1
    wrong = sum(1 for row in rows if _wrong_country(str(row.get("location") or ""), expected))
    company = sum(1 for row in rows if str(row.get("source_type") or "") == "company site")
    aggregators = sum(1 for row in rows if str(row.get("source_type") or "") == "aggregator")
    shown = min(sample_size, total)
    return {
        "total": total,
        "relevant_in_sample": f"{relevant}/{shown}",
        "wrong_country": wrong,
        "company_pages_%": _percent(company, total),
        "aggregators_%": _percent(aggregators, total),
        "per_source": _per_source(rows),
    }


def _city_names(query: dict, parsed: dict | None) -> list[str]:
    names: list[str] = []
    place = str(query.get("place") or "")
    typed = place.split(",", 1)[0].strip() if place else ""
    if typed and fold_text(typed) != "remote":
        names.append(typed)
    if parsed and parsed.get("kind") == "city":
        label = str(parsed.get("name") or "")
        city = label.split(",", 1)[0].strip()
        if city and city not in names:
            names.append(city)
    return names


def _accept_place(raw: str) -> tuple[dict | None, str | None]:
    """The wizard's place, or an error kind.

    ``confirm`` has a single match and the wizard defaults to Yes, so a
    benchmark accepts it. ``choose`` has no default and is rejected.
    """
    parsed, problem = setup_wizard.parse_place(raw)
    if parsed is not None:
        return parsed, None
    if problem == "confirm":
        fuller = getattr(setup_wizard, "parse_place_full", None)
        convert = getattr(setup_wizard, "accepted_place", None)
        if fuller is not None and convert is not None:
            return convert(fuller(raw)), None
    return None, problem or "unknown"


def _remote_block(raw: str) -> tuple[dict | None, str | None]:
    resolved = setup_wizard.resolve_remote_area(raw)
    if resolved is None:
        return None, "remote_area"
    label, code, on_indeed = resolved
    return {"label": label, "indeed": on_indeed, "country": code}, None


class _SilentIO:
    """Collects nothing. The benchmark does not print the wizard's source notes."""

    def say(self, _text: str) -> None:
        return None


def _config_for(query: dict, spec: dict, folder: Path) -> tuple[dict | None, str | None]:
    parsed, problem = _accept_place(str(query.get("place") or ""))
    if parsed is None:
        return None, problem or "unknown"
    remote = None
    area = query.get("remote_area")
    if area:
        remote, remote_problem = _remote_block(str(area))
        if remote is None:
            return None, remote_problem or "remote_area"
    if parsed["kind"] in {"city", "country"}:
        country = parsed["country"]
    elif remote and remote.get("country"):
        country = remote["country"]
    else:
        country = _REMOTE_HOME_COUNTRY
    role = str(query["role"])
    suggestions = suggestions_for([role], country)
    places = setup_wizard.places_from(parsed, remote)
    choice = setup_wizard.parse_sources("")
    if choice is None:
        return None, "sources"
    enabled, link_ids = chosen_sources(choice, country, places, [role], [])
    enabled = setup_wizard._finish_sources(_SilentIO(), enabled, country in INDEED_COUNTRIES, places)
    data = setup_wizard.build_config(
        [role],
        places,
        country,
        [],
        suggestions,
        [],
        enabled,
        [],
        require_title_match=bool(suggestions),
        results_per_search=int(spec["results_per_search"]),
        posted_within_days=int(spec["posted_within_days"]),
        source_choice="auto" if choice == "auto" else None,
        link_outs=link_ids if choice == "auto" else None,
    )
    data["output"] = {
        "directory": ".",
        "csv": "jobs.csv",
        "excel": "jobs.xlsx",
        "seen_file": "seen_jobs.json",
    }
    folder.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    (folder / "config.yaml").write_text(body, encoding="utf-8")
    return parsed, None


def _is_blocked(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if code is None:
        code = getattr(exc, "status_code", None)
    if code in {403, 429}:
        return True
    if isinstance(exc, HTTPError) and exc.code in {403, 429}:
        return True
    text = str(exc).casefold()
    if "captcha" in text or "authenticating" in text:
        return True
    if re.search(r"\bhttp\s*40[39]\b|\b(?:status(?:\s*code)?\s*[:=]?\s*)40[39]\b", text):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError, URLError)):
        return True
    if "proxy" in text or "timed out" in text or "timeout" in text:
        return True
    if "connection" in text and any(
        word in text for word in ("refused", "reset", "aborted", "failed", "error")
    ):
        return True
    name = type(exc).__name__.casefold()
    return "timeout" in name or "proxy" in name or "connection" in name


def _remember(found: list[str], item: str) -> None:
    if item not in found:
        found.append(item)


class _BlockedFetch:
    def __init__(self, fetch) -> None:
        self.fetch = fetch
        self.blocked: list[str] = []
        self.errors: list[str] = []

    def __call__(self, role, place, site):
        try:
            rows = self.fetch(role, place, site)
        except Exception as exc:
            if _is_blocked(exc):
                _remember(self.blocked, str(site))
            else:
                _remember(self.errors, f"{site}:{type(exc).__name__}")
            return []
        if isinstance(rows, (bytes, str)):
            text = rows.decode("utf-8", "replace") if isinstance(rows, bytes) else rows
            folded = text.casefold()
            if "captcha" in folded or "authenticating" in folded:
                _remember(self.blocked, str(site))
                return []
        return rows or []


def _raise_fixture(payload: dict) -> None:
    kind = str(payload.get("raise") or "Exception")
    if kind == "HTTPError":
        code = int(payload.get("code") or 429)
        raise HTTPError("https://example.test/jobs", code, "blocked", Message(), None)
    if kind == "ValueError":
        raise ValueError(str(payload.get("message") or "bad"))
    if kind == "URLError":
        raise URLError(str(payload.get("message") or "proxy connection failed"))
    raise RuntimeError(kind)


def _fixture_fetch(folder: Path, query_id: str):
    def fetch(_role, _place, site):
        for path in (folder / query_id / f"{site}.json", folder / f"{site}.json"):
            if not path.is_file():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and "raise" in payload:
                _raise_fixture(payload)
            if isinstance(payload, list):
                return payload
            raise ValueError(f"{path} should be a list of rows or a raise object.")
        return []

    return fetch


def _read_rows(csv_path: Path) -> list[dict]:
    if not csv_path.is_file():
        return []
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            row = {}
            for header, value in raw.items():
                key = _HEADER_TO_KEY.get(header or "", header or "")
                row[key] = value or ""
            rows.append(row)
        return rows


def _empty_row(query_id: str, status: str, seconds: float) -> dict:
    return {
        "query": query_id,
        "status": status,
        "total": 0,
        "relevant_in_sample": "0/0",
        "wrong_country": 0,
        "company_pages_%": 0,
        "aggregators_%": 0,
        "per_source": "",
        "blocked": "",
        "errors": "",
        "seconds": round(seconds, 1),
    }


def _markdown(rows: list[dict]) -> str:
    header = "| " + " | ".join(_COLUMNS) + " |"
    line = "| " + " | ".join("---" for _ in _COLUMNS) + " |"
    body = []
    for row in rows:
        cells = [str(row.get(column, "")).replace("|", "/") for column in _COLUMNS]
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, line, *body]) + "\n"


def run(
    label: str,
    only: str = "",
    offline: str = "",
    results_root: Path | None = None,
    fetch=None,
) -> list[dict]:
    """Run the queries and write summary.md and summary.json. Returns the rows."""
    spec = load_spec()
    wanted = {item.strip() for item in only.split(",") if item.strip()}
    queries = [item for item in spec["queries"] if not wanted or item["id"] in wanted]
    root = Path(results_root) if results_root is not None else RESULTS_ROOT
    label_dir = root / label
    sample_size = int(spec["sample_size"])
    offline_dir = Path(offline) if offline else None
    live = fetch is None and offline_dir is None
    summaries = []
    for query in queries:
        started = time.perf_counter()
        query_id = str(query["id"])
        folder = label_dir / "raw" / query_id
        parsed, problem = _config_for(query, spec, folder)
        if parsed is None:
            summaries.append(_empty_row(query_id, f"place_rejected:{problem}", time.perf_counter() - started))
            print(f"{query_id}: place_rejected:{problem}", flush=True)
            continue
        if fetch is not None:
            search = fetch
        elif offline_dir is not None:
            search = _fixture_fetch(offline_dir, query_id)
        else:
            settings = load_config(folder / "config.yaml")

            def search(role, place, site, _settings=settings):
                return fetch_listings(_settings, role, place, site, verbose=False)

        wrapped = _BlockedFetch(search)

        def run_fetch(role, place, site, _wrapped=wrapped):
            return _wrapped(role, place, site)

        try:
            scrape._run_search(
                folder / "config.yaml",
                fetch=run_fetch,
                getter=None if live else (lambda _url: b""),
                verbose=False,
            )
        except Exception as exc:
            _remember(wrapped.errors, f"runner:{type(exc).__name__}")
        rows = _read_rows(folder / "jobs.csv")
        stats = measure(rows, query, sample_size, _city_names(query, parsed))
        seconds = round(time.perf_counter() - started, 1)
        record = {
            "query": query_id,
            "status": "ok",
            "total": stats["total"],
            "relevant_in_sample": stats["relevant_in_sample"],
            "wrong_country": stats["wrong_country"],
            "company_pages_%": stats["company_pages_%"],
            "aggregators_%": stats["aggregators_%"],
            "per_source": stats["per_source"],
            "blocked": ", ".join(wrapped.blocked) if wrapped else "",
            "errors": ", ".join(wrapped.errors) if wrapped else "",
            "seconds": seconds,
        }
        summaries.append(record)
        print(f"{query_id}: {record['total']} rows, wrong_country={record['wrong_country']}", flush=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    text = _markdown(summaries)
    (label_dir / "summary.md").write_text(text, encoding="utf-8")
    (label_dir / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(text, flush=True)
    return summaries


def main(argv: list[str] | None = None, results_root: Path | None = None, fetch=None) -> int:
    """CLI entry. Returns 0, or 2 when the runner itself crashes."""
    try:
        parser = argparse.ArgumentParser(description="Run the fixed job-search benchmark.")
        parser.add_argument("--label", required=True)
        parser.add_argument("--only", default="")
        parser.add_argument("--offline", default="")
        args = parser.parse_args(argv)
        run(args.label, only=args.only, offline=args.offline, results_root=results_root, fetch=fetch)
        return 0
    except Exception:
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
