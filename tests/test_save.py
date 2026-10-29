"""Tests for the CSV, Excel file, and the memory of listings already seen."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from listings import listing_key
from save_results import load_seen, save_seen, write_daily_files, write_outputs


def _row(**overrides):
    base = {
        "is_new": "yes",
        "title": "Market Research Analyst",
        "company": "Ipsos",
        "location": "Milano, LOM, Italy",
        "date_posted": "2026-10-19",
        "source": "indeed",
        "source_type": "aggregator",
        "url": "https://it.indeed.com/viewjob?jk=sample",
        "description": "Study how people shop.",
        "role_searched": "Market Research Analyst",
        "place_searched": "Milan, Italy",
    }
    base.update(overrides)
    return base


def test_write_outputs_creates_csv_and_excel_with_friendly_headers(tmp_path):
    csv_path = tmp_path / "output" / "jobs.csv"
    excel_path = tmp_path / "output" / "jobs.xlsx"
    write_outputs([_row()], csv_path, excel_path)

    csv_text = csv_path.read_text(encoding="utf-8-sig")
    assert csv_text.splitlines()[0].startswith("New since last run,Title,Company")
    assert "Ipsos" in csv_text
    assert "Study how people shop." in csv_text

    workbook = load_workbook(excel_path)
    sheet = workbook["Jobs"]
    headers = [cell.value for cell in sheet[1]]
    assert headers[:9] == [
        "New since last run",
        "Title",
        "Company",
        "Location",
        "Date posted",
        "Source",
        "Source type",
        "URL",
        "Description",
    ]
    assert sheet["A2"].value == "yes"
    assert sheet["G2"].value == "aggregator"
    assert sheet["H2"].value == "https://it.indeed.com/viewjob?jk=sample"
    assert sheet["H2"].hyperlink.target == "https://it.indeed.com/viewjob?jk=sample"
    assert sheet.auto_filter.ref is not None
    assert sheet.freeze_panes == "A2"
    assert "how to read" in workbook["About this file"]["A1"].value.lower()


def test_write_daily_files_keeps_only_new_rows_and_counts_each_source(tmp_path):
    rows = [
        _row(is_new="yes", title="New role", source="indeed", source_type="aggregator"),
        _row(
            is_new="no",
            title="Already seen",
            source="Satispay careers, linkedin",
            source_type="company site",
            url="https://jobs.ashbyhq.com/satispay/1",
        ),
    ]
    when = datetime(2026, 10, 22, 16, 5, tzinfo=ZoneInfo("Europe/Rome"))
    summary = write_daily_files(
        rows,
        tmp_path / "output" / "new_jobs.csv",
        tmp_path / "output" / "last_run.json",
        when,
    )

    csv_lines = (tmp_path / "output" / "new_jobs.csv").read_text(encoding="utf-8-sig").splitlines()
    assert csv_lines[0].startswith("New since last run,Title,Company")
    assert len(csv_lines) == 2
    assert "New role" in csv_lines[1]
    assert "Already seen" not in "\n".join(csv_lines)

    saved = json.loads((tmp_path / "output" / "last_run.json").read_text(encoding="utf-8"))
    assert saved["run_at"] == "2026-10-22T16:05:00+02:00"
    assert saved["timezone"] == "Europe/Rome"
    assert saved["total_listings"] == 2
    assert saved["new_listings"] == 1
    assert saved["by_source"]["indeed"] == {"total": 1, "new": 1}
    assert saved["by_source"]["Satispay careers"] == {"total": 1, "new": 0}
    assert saved["by_source"]["linkedin"] == {"total": 1, "new": 0}
    assert saved["by_source_type"]["company site"] == {"total": 1, "new": 0}
    assert summary["new_listings"] == 1


def test_write_daily_files_writes_a_header_when_nothing_is_new(tmp_path):
    when = datetime(2026, 10, 23, 8, 0, tzinfo=ZoneInfo("Europe/Rome"))
    write_daily_files(
        [_row(is_new="no")],
        tmp_path / "output" / "new_jobs.csv",
        tmp_path / "output" / "last_run.json",
        when,
    )
    csv_lines = (tmp_path / "output" / "new_jobs.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(csv_lines) == 1
    assert csv_lines[0].startswith("New since last run,Title,Company")
    saved = json.loads((tmp_path / "output" / "last_run.json").read_text(encoding="utf-8"))
    assert saved["total_listings"] == 1
    assert saved["new_listings"] == 0


def test_seen_file_round_trip(tmp_path):
    path = tmp_path / "data" / "seen_jobs.json"
    row = _row()
    save_seen(path, {listing_key(row)})
    assert load_seen(path) == {listing_key(row)}
    assert load_seen(tmp_path / "missing.json") == set()
