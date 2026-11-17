"""Curated employers use the whole-board role rule. User-typed companies do not.

No network. Rows come from tests/fixtures/curated_role_match.json.
"""

import json
from pathlib import Path

import pytest
import yaml

from boards import Company, collect_company_pages, filter_board_jobs
from config import load_config


_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "curated_role_match.json"
_CASES = json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]


def _settings(tmp_path, role: str, keywords: list[str] | None):
    data = {
        "roles": [role],
        "require_title_match": False,
        "locations": [
            {
                "name": "Frankfurt, Germany",
                "indeed_location": "Frankfurt, Germany",
                "linkedin_location": "Frankfurt, Germany",
                "remote": False,
            }
        ],
        "country": "germany",
        "sources": [{"id": "arbeitnow", "enabled": True, "kind": "job board"}],
    }
    if keywords:
        data["title_keywords"] = {role: keywords}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return load_config(path)


def _case_id(case: dict) -> str:
    kind = "curated" if case["curated"] else "user"
    return f"{case['role']}-{kind}-{case['title']}"


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_curated_employers_follow_the_whole_board_role_rule(tmp_path, case):
    settings = _settings(tmp_path, case["role"], case.get("keywords"))
    job = {
        "title": case["title"],
        "company": "Example",
        "location": "Frankfurt am Main",
        "is_remote": False,
        "url": "https://example.com/job",
        "description": "A posting.",
        "source": "Example careers",
    }
    kept = filter_board_jobs([job], settings, "company site", curated=case["curated"])
    assert bool(kept) is case["kept"]


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += float(seconds)


def _page(titles: list[str]) -> bytes:
    payload = {
        "jobs": [
            {
                "title": title,
                "location": {"name": "Frankfurt am Main"},
                "absolute_url": f"https://example.com/{index}",
                "content": "A posting.",
            }
            for index, title in enumerate(titles)
        ]
    }
    return json.dumps(payload).encode("utf-8")


def test_collecting_a_curated_page_drops_titles_outside_the_role(tmp_path):
    settings = _settings(tmp_path, "risk manager", None)
    clock = _Clock()
    curated = Company("Acme", "greenhouse", "acme", curated=True, families=("finance",))
    user = Company("Typed", "greenhouse", "typed")
    titles = ["Account Manager", "Senior Risk Manager"]

    def getter(url: str) -> bytes:
        assert "boards-api.greenhouse.io" in url
        return _page(titles)

    rows, failures = collect_company_pages(
        [curated, user],
        getter,
        settings,
        sleep=clock.sleep,
        clock=clock.time,
        roles=["risk manager"],
    )
    assert failures == 0
    by_company: dict[str, list[str]] = {}
    for row in rows:
        by_company.setdefault(row["company"], []).append(row["title"])
    assert by_company["Acme"] == ["Senior Risk Manager"]
    assert by_company["Typed"] == ["Account Manager", "Senior Risk Manager"]
