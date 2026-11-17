"""Company-page fan-out. Fake getter, fake clock, no network."""

import json
import random
import threading
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import urlparse

from boards import Company, _company_jobs, collect_company_pages
from config import load_config


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.lock = threading.Lock()

    def time(self) -> float:
        with self.lock:
            return self.now

    def sleep(self, seconds: float) -> None:
        with self.lock:
            self.now += float(seconds)


def _quiet_clock() -> Clock:
    """A clock that advances on sleep, so a test never waits in real time."""
    return Clock()


def _settings(tmp_path, role: str = "Data Analyst"):
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
roles: [{role}]
require_title_match: false
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
country: germany
sources:
  - id: company_pages
    enabled: true
    kind: company site
companies: []
""",
        encoding="utf-8",
    )
    return load_config(path)


def _greenhouse(title: str, url: str) -> bytes:
    payload = {
        "jobs": [
            {
                "title": title,
                "location": {"name": "Berlin, Germany"},
                "absolute_url": url,
                "content": "A role.",
            }
        ]
    }
    return json.dumps(payload).encode("utf-8")


def _token(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if "boards" in parts:
        return parts[parts.index("boards") + 1]
    if "postings" in parts:
        return parts[parts.index("postings") + 1]
    return parts[-1] if parts else url


def test_one_host_is_not_called_twice_at_once(tmp_path):
    clock = Clock()
    in_flight = {"n": 0, "max": 0}
    per_host: dict[str, int] = {}
    max_host: dict[str, int] = {}
    calls: dict[str, list[float]] = {}
    guard = threading.Lock()

    def getter(url: str) -> bytes:
        host = urlparse(url).hostname or ""
        with guard:
            in_flight["n"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["n"])
            per_host[host] = per_host.get(host, 0) + 1
            max_host[host] = max(max_host.get(host, 0), per_host[host])
            calls.setdefault(host, []).append(clock.time())
        try:
            return b'{"jobs": []}'
        finally:
            with guard:
                in_flight["n"] -= 1
                per_host[host] -= 1

    companies = []
    for index in range(4):
        companies.append(Company(f"Green {index}", "greenhouse", f"green{index}"))
        companies.append(Company(f"Lever {index}", "lever", f"lever{index}"))
    collect_company_pages(
        companies,
        getter,
        _settings(tmp_path),
        sleep=clock.sleep,
        clock=clock.time,
        roles=["legal counsel"],
    )
    assert in_flight["max"] <= 4
    assert all(value <= 1 for value in max_host.values())
    for host, times in calls.items():
        ordered = sorted(times)
        gaps = [later - earlier for earlier, later in zip(ordered, ordered[1:])]
        assert gaps
        assert min(gaps) >= 0.5


def test_output_order_does_not_depend_on_which_thread_finishes(tmp_path):
    settings = _settings(tmp_path)
    clock = Clock()
    companies = [
        Company("Zed", "ashby", "zed"),
        Company("Ann", "greenhouse", "ann"),
        Company("Mia", "lever", "mia"),
    ]

    def getter(url: str) -> bytes:
        clock.sleep(random.random())
        token = _token(url)
        link = f"https://example.com/{token}"
        if "api.lever.co" in url:
            return json.dumps(
                [{"text": token, "categories": {"location": "Berlin, Germany"}, "hostedUrl": link}]
            ).encode("utf-8")
        if "ashbyhq" in url:
            return json.dumps(
                {"jobs": [{"title": token, "location": "Berlin, Germany", "jobUrl": link}]}
            ).encode("utf-8")
        return _greenhouse(token, link)

    seen = []
    for _ in range(5):
        rows, failures = collect_company_pages(
            companies,
            getter,
            settings,
            sleep=clock.sleep,
            clock=clock.time,
            roles=["legal counsel"],
        )
        assert failures == 0
        seen.append([(row["company"], row["title"], row["url"]) for row in rows])
    assert seen[0] == seen[1] == seen[2] == seen[3] == seen[4]
    assert [item[0] for item in seen[0]] == ["Ann", "Mia", "Zed"]


def test_blocked_and_missing_pages_are_named(tmp_path, capsys):
    settings = _settings(tmp_path)

    def getter(url: str) -> bytes:
        token = _token(url)
        if token == "missing":
            raise HTTPError(url, 404, "missing", Message(), None)
        if token == "limited":
            raise HTTPError(url, 429, "limited", Message(), None)
        return _greenhouse("Data Analyst", "https://example.com/kept")

    companies = [
        Company("Kept", "greenhouse", "kept"),
        Company("Missing", "greenhouse", "missing"),
        Company("Limited", "lever", "limited"),
    ]
    clock = _quiet_clock()
    rows, failures = collect_company_pages(
        companies,
        getter,
        settings,
        sleep=clock.sleep,
        clock=clock.time,
        roles=["legal counsel"],
    )
    text = capsys.readouterr().out
    assert failures == 2
    assert [row["company"] for row in rows] == ["Kept"]
    assert "blocked or not found" in text
    assert "Missing" in text
    assert "Limited" in text


def test_user_typed_company_is_queried_once(tmp_path):
    calls = []

    def getter(url: str) -> bytes:
        calls.append(url)
        return b'{"jobs": []}'

    user = Company("Adyen", "greenhouse", "adyen")
    curated = Company(
        "Adyen",
        "greenhouse",
        "adyen",
        curated=True,
        families=("data",),
        jobs_in_country=80,
    )
    clock = _quiet_clock()
    collect_company_pages(
        [curated, user],
        getter,
        _settings(tmp_path),
        sleep=clock.sleep,
        clock=clock.time,
        roles=["data analyst"],
    )
    assert len(calls) == 1


def test_curated_pages_follow_the_role_family(tmp_path):
    calls = []

    def getter(url: str) -> bytes:
        calls.append(_token(url))
        return b'{"jobs": []}'

    companies = [
        Company("Alpha", "greenhouse", "alpha", curated=True, families=("tech",), jobs_in_country=9),
        Company("Beta", "greenhouse", "beta", curated=True, families=("data",), jobs_in_country=8),
    ]
    clock = _quiet_clock()
    collect_company_pages(
        companies,
        getter,
        _settings(tmp_path),
        sleep=clock.sleep,
        clock=clock.time,
        roles=["data analyst"],
    )
    assert calls == ["beta"]


def test_other_family_queries_curated_employers(tmp_path):
    calls = []

    def getter(url: str) -> bytes:
        calls.append(_token(url))
        return b'{"jobs": []}'

    companies = [
        Company("Alpha", "greenhouse", "alpha", curated=True, families=("tech",), jobs_in_country=9),
        Company("Beta", "greenhouse", "beta", curated=True, families=("data",), jobs_in_country=8),
    ]
    clock = _quiet_clock()
    collect_company_pages(
        companies,
        getter,
        _settings(tmp_path),
        sleep=clock.sleep,
        clock=clock.time,
        roles=["legal counsel"],
    )
    assert set(calls) == {"alpha", "beta"}


def test_curated_cap_keeps_the_largest_boards(tmp_path):
    calls = []

    def getter(url: str) -> bytes:
        calls.append(_token(url))
        return b'{"jobs": []}'

    companies = [
        Company(
            f"Co {index:02d}",
            "greenhouse",
            f"c{index:02d}",
            curated=True,
            families=("tech",),
            jobs_in_country=index,
        )
        for index in range(1, 71)
    ]
    clock = _quiet_clock()
    collect_company_pages(
        companies,
        getter,
        _settings(tmp_path),
        sleep=clock.sleep,
        clock=clock.time,
        roles=["legal counsel"],
    )
    assert set(calls) == {f"c{index:02d}" for index in range(11, 71)}
    assert len(calls) == 60


def test_disabled_company_is_not_queried(tmp_path):
    calls = []

    def getter(url: str) -> bytes:
        calls.append(_token(url))
        return b'{"jobs": []}'

    companies = [
        Company("Off", "greenhouse", "off", enabled=False, curated=True, families=("data",)),
        Company("On", "greenhouse", "on", curated=True, families=("data",), jobs_in_country=3),
    ]
    clock = _quiet_clock()
    collect_company_pages(
        companies,
        getter,
        _settings(tmp_path),
        sleep=clock.sleep,
        clock=clock.time,
        roles=["data analyst"],
    )
    assert calls == ["on"]


def test_eu_lever_uses_the_eu_host():
    seen = []

    def getter(url: str) -> bytes:
        seen.append(url)
        return b"[]"

    _company_jobs(Company("Acme", "lever", "acme", region="eu"), getter)
    _company_jobs(Company("Acme", "lever", "acme"), getter)
    assert seen == [
        "https://api.eu.lever.co/v0/postings/acme?mode=json",
        "https://api.lever.co/v0/postings/acme?mode=json",
    ]
