"""The made-up sample spreadsheet. No network."""

import importlib.util
from pathlib import Path


def _sample_module():
    path = Path(__file__).resolve().parents[1] / "tools" / "make_sample.py"
    spec = importlib.util.spec_from_file_location("make_sample", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sample_rows_do_not_label_an_office_job_as_remote():
    rows = _sample_module().sample_rows()
    assert rows
    places = {row["place_searched"] for row in rows}
    assert "Remote" in places
    assert any(row["is_remote"] == "No" for row in rows)
    blob = " ".join(
        f"{row['title']} {row['location']} {row['place_searched']}" for row in rows
    ).casefold()
    assert "milan" not in blob
    for city in ("amsterdam", "warsaw", "madrid", "toronto", "berlin"):
        assert city in blob
    for row in rows:
        assert row["salary"] != "" or row["title"]
        for key in ("salary", "job_type", "is_remote", "level", "languages", "visa"):
            assert key in row
        if row["is_remote"] == "No":
            assert row["place_searched"] != "Remote"
        if row["place_searched"] == "Remote":
            assert row["is_remote"] == "Yes"


def test_checked_in_sample_matches_the_fixture():
    module = _sample_module()
    csv_path = Path(__file__).resolve().parents[1] / "sample" / "jobs.csv"
    text = csv_path.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0]
    for label in ("Salary", "Job type", "Remote", "Level", "Languages", "Visa"):
        assert label in header
    assert "milan" not in text.casefold()
    for row in module.sample_rows():
        assert row["title"] in text
