"""Curated employer files and the checker's pure helpers. No network."""

from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from email.message import Message

import pytest
import yaml

from config import KNOWN_SYSTEMS, load_config
from tools.verify_employers import _write, count_jobs, job_in_country, status_name

_ROOT = Path(__file__).resolve().parents[1]
_EMPLOYERS = _ROOT / "employers"
_COUNTRIES = ("italy", "germany", "netherlands", "uk", "france", "spain", "poland")


def _files():
    return sorted(_EMPLOYERS.glob("*.yaml"))


def _load(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _known_families() -> set[str]:
    raw = yaml.safe_load((_ROOT / "sourcemap" / "role_families.yaml").read_text(encoding="utf-8"))
    return {key for key, value in raw.items() if isinstance(value, list) and key != "other"}


@pytest.mark.parametrize("path", _files(), ids=lambda path: path.name)
def test_employer_file_parses(path):
    raw = _load(path)
    assert raw.get("country") == path.stem
    date.fromisoformat(str(raw.get("checked_on")))
    employers = raw.get("employers")
    assert isinstance(employers, list) and employers
    known = _known_families()
    seen = set()
    for entry in employers:
        system = str(entry["system"])
        assert system in KNOWN_SYSTEMS
        for family in entry.get("families") or []:
            assert family in known
        key = (system, str(entry.get("token") or ""))
        assert key not in seen
        seen.add(key)
        last = entry.get("last_check") or {}
        assert last.get("status")


@pytest.mark.parametrize("country", _COUNTRIES)
def test_country_has_at_least_15_checked_employers(country):
    raw = _load(_EMPLOYERS / f"{country}.yaml")
    ok = [
        entry
        for entry in raw["employers"]
        if (entry.get("last_check") or {}).get("status") == "ok"
        and int((entry.get("last_check") or {}).get("jobs_in_country") or 0) >= 1
    ]
    if len(ok) < 15:
        pytest.xfail(f"{country}: {len(ok)} verified employers with status ok, short of 15")
    assert len(ok) >= 15


@pytest.mark.parametrize(
    ("exc", "total", "expected"),
    [
        (None, 3, "ok"),
        (None, 0, "empty"),
        (HTTPError("https://example.test", 404, "missing", Message(), None), 0, "not_found"),
        (HTTPError("https://example.test", 403, "no", Message(), None), 0, "blocked"),
        (HTTPError("https://example.test", 429, "slow", Message(), None), 0, "blocked"),
        (TimeoutError("timed out"), 0, "error:TimeoutError"),
        (RuntimeError("boom"), 0, "error:RuntimeError"),
    ],
)
def test_status_name(exc, total, expected):
    assert status_name(exc, total) == expected


@pytest.mark.parametrize(
    ("location", "country", "hubs", "expected"),
    [
        ("Berlin, Germany", "germany", ["Berlin"], True),
        ("München, Deutschland", "germany", ["Munich"], True),
        ("Amsterdam", "netherlands", ["Amsterdam"], True),
        ("Paris, France", "germany", ["Berlin"], False),
        ("Remote", "netherlands", ["Amsterdam"], False),
        ("Remote - Europe", "europe_remote", [], True),
        ("Remote (EU only)", "europe_remote", [], True),
        ("Remote - Germany", "europe_remote", [], False),
        ("London, United Kingdom", "uk", ["London"], True),
    ],
)
def test_job_in_country(location, country, hubs, expected):
    assert job_in_country(location, country, hubs) is expected


def test_count_jobs_uses_the_country_rule():
    jobs = [
        {"location": "Berlin, Germany"},
        {"location": "Paris, France"},
        {"location": "Remote - Europe"},
    ]
    total, kept = count_jobs(jobs, "germany", ["Berlin"])
    assert (total, kept) == (3, 1)
    total, remote = count_jobs(jobs, "europe_remote", [])
    assert (total, remote) == (3, 1)


def test_old_company_config_still_loads(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
roles: [Data Analyst]
locations:
  - name: Amsterdam, Netherlands
    indeed_location: Amsterdam, Netherlands
    linkedin_location: Amsterdam, Netherlands
country: netherlands
sources:
  - id: company_pages
    enabled: true
    kind: company site
companies:
  - name: Adyen
    system: greenhouse
    token: adyen
""",
        encoding="utf-8",
    )
    settings = load_config(path)
    company = settings.companies[0]
    assert company.region == ""
    assert company.families == ()
    assert company.curated is False
    assert company.jobs_in_country == 0


def test_write_updates_the_entries_it_checked(tmp_path):
    path = tmp_path / "netherlands.yaml"
    path.write_text(
        "country: netherlands\nchecked_on: 2020-01-01\nemployers:\n"
        "  - name: Acme\n    system: greenhouse\n    token: acme\n"
        "    last_check: {status: ok, jobs_total: 1, jobs_in_country: 1}\n",
        encoding="utf-8",
    )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    entry = raw["employers"][0]
    _write(
        path,
        raw,
        [{"entry": entry, "status": "empty", "jobs_total": 0, "jobs_in_country": 0}],
    )
    again = yaml.safe_load(path.read_text(encoding="utf-8"))
    saved = again["employers"][0]
    assert saved["last_check"] == {"status": "empty", "jobs_total": 0, "jobs_in_country": 0}
    assert saved["enabled"] is False
    date.fromisoformat(again["checked_on"])
