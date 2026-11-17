"""Whole-board titles must match the role. Arbeitnow cities must match the place.

No network. Rows come from tests/fixtures/board_role_match.json.
"""

import json
import ssl
from pathlib import Path

import certifi
import pytest

import boards
from boards import _read_url, filter_board_jobs
from config import load_config


_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "board_role_match.json"
_CASES = json.loads(_FIXTURE.read_text(encoding="utf-8"))

_SOURCE_TYPE = {
    "arbeitnow": "job board",
    "remotive": "remote board",
    "company": "company site",
}


def _settings(tmp_path, role: str, keywords: list[str] | None = None):
    keyword_block = ""
    if keywords:
        lines = "\n".join(f"    - {phrase}" for phrase in keywords)
        keyword_block = f"title_keywords:\n  {role}:\n{lines}\n"
    body = f"""
roles: [{role}]
require_title_match: false
{keyword_block}locations:
  - name: Frankfurt, Germany
    indeed_location: Frankfurt, Germany
    linkedin_location: Frankfurt, Germany
    remote: false
country: germany
sources:
  - id: arbeitnow
    enabled: true
    kind: job board
"""
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return load_config(path)


def _row(source: str, title: str, location: str, is_remote: bool) -> tuple[dict, str]:
    remote_board = source in {"remotive", "we work remotely", "remote ok", "working nomads"}
    return (
        {
            "title": title,
            "company": "Example",
            "location": location,
            "is_remote": is_remote,
            "url": "https://example.com/job",
            "description": "A posting.",
            "source": "Example careers" if source == "company" else source,
        },
        _SOURCE_TYPE.get(source, "remote board" if remote_board else "job board"),
    )


@pytest.mark.parametrize("case", _CASES["titles"], ids=lambda case: case["title"])
def test_whole_board_titles_match_the_typed_role(tmp_path, case):
    settings = _settings(tmp_path, case["role"])
    remote = case["source"] != "arbeitnow" and case["source"] != "company"
    location = "Worldwide" if remote else "Frankfurt am Main"
    job, source_type = _row(case["source"], case["title"], location, remote)
    kept = filter_board_jobs([job], settings, source_type)
    assert bool(kept) is case["kept"]


def test_an_accepted_synonym_keeps_a_whole_board_title(tmp_path):
    settings = _settings(tmp_path, "software engineer", ["softwareentwickler"])
    job, source_type = _row("arbeitnow", "Softwareentwickler", "Frankfurt am Main", False)
    kept = filter_board_jobs([job], settings, source_type)
    assert [row["title"] for row in kept] == ["Softwareentwickler"]


def test_short_words_in_the_role_are_ignored(tmp_path):
    settings = _settings(tmp_path, "IT risk manager")
    yes, yes_type = _row("arbeitnow", "Risk und BCM Manager", "Frankfurt am Main", False)
    no, no_type = _row("arbeitnow", "IT Manager", "Frankfurt am Main", False)
    assert filter_board_jobs([yes], settings, yes_type)
    assert filter_board_jobs([no], settings, no_type) == []


@pytest.mark.parametrize("case", _CASES["places"], ids=lambda case: case["location"])
def test_arbeitnow_keeps_the_searched_city_or_the_country_alone(tmp_path, case):
    settings = _settings(tmp_path, "risk manager")
    job, source_type = _row(
        "arbeitnow",
        "Senior Risk Manager",
        case["location"],
        case["is_remote"],
    )
    kept = filter_board_jobs([job], settings, source_type)
    assert bool(kept) is case["kept"]


def test_company_pages_still_keep_another_city_in_the_country(tmp_path):
    settings = _settings(tmp_path, "risk manager")
    job, source_type = _row(
        "company",
        "HR Manager",
        "Cologne, North Rhine-Westphalia, Germany",
        False,
    )
    kept = filter_board_jobs([job], settings, source_type)
    assert [row["location"] for row in kept] == ["Cologne, North Rhine-Westphalia, Germany"]


class _Body:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self, _limit: int = -1) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> bool:
        return False


def test_read_url_builds_its_ssl_context_from_certifi(monkeypatch):
    seen = {}

    def urlopen(_request, timeout=45, context=None):
        seen["context"] = context
        seen["timeout"] = timeout
        return _Body(b"ok")

    def create_default_context(cafile=None, capath=None, cadata=None):
        seen["cafile"] = cafile
        return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    monkeypatch.setattr(boards.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(ssl, "create_default_context", create_default_context)
    assert _read_url("https://example.com/jobs") == b"ok"
    assert seen["cafile"] == certifi.where()
    assert seen["context"] is not None


def test_read_url_falls_back_when_certifi_cannot_be_imported(monkeypatch):
    import sys

    seen = {}
    real_import = __import__
    monkeypatch.delitem(sys.modules, "certifi", raising=False)

    def urlopen(_request, timeout=45, context=None):
        seen["context"] = context
        return _Body(b"ok")

    def create_default_context(cafile=None, capath=None, cadata=None):
        seen.setdefault("calls", []).append(cafile)
        return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    def fake_import(name, *args, **kwargs):
        if name == "certifi":
            raise ImportError("certifi is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(boards.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(ssl, "create_default_context", create_default_context)
    monkeypatch.setattr("builtins.__import__", fake_import)
    assert _read_url("https://example.com/jobs") == b"ok"
    assert seen["calls"] == [None]
    assert seen["context"] is not None
