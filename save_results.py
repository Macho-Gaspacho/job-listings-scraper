"""Save the spreadsheet and remember which links we have already seen."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from listings import OUTPUT_FIELDS


# A quiet green so the "yes" cells are easy to spot in Excel.
NEW_FILL = PatternFill("solid", fgColor="CDE9D6")
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(bold=True, color="FFFFFF")
NEW_FONT = Font(bold=True, color="1B7A3A")
LINK_FONT = Font(color="0563C1", underline="single")

COLUMN_WIDTHS = {
    "A": 22,
    "B": 42,
    "C": 28,
    "D": 34,
    "E": 16,
    "F": 28,
    "G": 16,
    "H": 48,
    "I": 72,
    "J": 36,
    "K": 24,
}


def load_seen(path: str | Path) -> set[str]:
    """Links saved by earlier runs. A missing file means \"nothing yet\"."""
    file_path = Path(path)
    if not file_path.exists():
        return set()
    data = json.loads(file_path.read_text(encoding="utf-8"))
    return set(data.get("seen_keys") or [])


def save_seen(path: str | Path, keys: set[str]) -> None:
    """Write the memory file. Sorted keys keep the file stable between runs."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen_keys": sorted(keys)}
    file_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _bump(counts: dict[str, dict[str, int]], name: str, is_new: bool) -> None:
    bucket = counts.setdefault(name, {"total": 0, "new": 0})
    bucket["total"] += 1
    if is_new:
        bucket["new"] += 1


def run_summary(rows: list[dict], run_at) -> dict:
    """Totals for one run. A job found on two sites is counted under each name.

    total_listings is the number of rows, so it can be smaller than the sum
    of by_source when one row names more than one site.
    """
    by_source: dict[str, dict[str, int]] = {}
    by_source_type: dict[str, dict[str, int]] = {}
    for row in rows:
        is_new = row.get("is_new") == "yes"
        source_type = (row.get("source_type") or "aggregator").strip() or "aggregator"
        _bump(by_source_type, source_type, is_new)
        names = [part.strip() for part in (row.get("source") or "").split(",") if part.strip()]
        for name in names or ["unknown"]:
            _bump(by_source, name, is_new)
    return {
        "run_at": run_at.isoformat(timespec="seconds"),
        "timezone": "Europe/Rome",
        "total_listings": len(rows),
        "new_listings": sum(1 for row in rows if row.get("is_new") == "yes"),
        "by_source": dict(sorted(by_source.items())),
        "by_source_type": dict(sorted(by_source_type.items())),
    }


def write_daily_files(rows: list[dict], new_csv_path: str | Path, last_run_path: str | Path, run_at) -> dict:
    """Write the new-only spreadsheet and the small JSON summary of this run.

    When nothing is new, the CSV still gets the header row.
    """
    summary = run_summary(rows, run_at)
    new_rows = [row for row in rows if row.get("is_new") == "yes"]
    csv_file = Path(new_csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(new_rows, csv_file)
    last_run = Path(last_run_path)
    last_run.parent.mkdir(parents=True, exist_ok=True)
    last_run.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def write_outputs(rows: list[dict], csv_path: str | Path, excel_path: str | Path) -> None:
    """Write both spreadsheets. CSV opens anywhere. Excel has filters and links."""
    csv_file = Path(csv_path)
    excel_file = Path(excel_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    excel_file.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(rows, csv_file)
    _write_excel(rows, excel_file)


def _write_csv(rows: list[dict], path: Path) -> None:
    # utf-8-sig adds a marker so Excel on Windows shows accents (è, à) correctly.
    headers = [label for _, label in OUTPUT_FIELDS]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row.get(key, "") for key, _ in OUTPUT_FIELDS])


def _write_excel(rows: list[dict], path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Jobs"
    headers = [label for _, label in OUTPUT_FIELDS]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")

    url_column = next(index for index, (key, _) in enumerate(OUTPUT_FIELDS, start=1) if key == "url")
    description_column = next(
        index for index, (key, _) in enumerate(OUTPUT_FIELDS, start=1) if key == "description"
    )
    for row in rows:
        values = [row.get(key, "") for key, _ in OUTPUT_FIELDS]
        sheet.append(values)
        row_number = sheet.max_row
        if row.get("is_new") == "yes":
            first = sheet.cell(row_number, 1)
            first.fill = NEW_FILL
            first.font = NEW_FONT
        url = row.get("url") or ""
        if url:
            link = sheet.cell(row_number, url_column)
            link.hyperlink = url
            link.font = LINK_FONT
        sheet.cell(row_number, description_column).alignment = Alignment(
            wrap_text=True, vertical="top"
        )
        sheet.row_dimensions[row_number].height = 32

    last_row = max(sheet.max_row, 1)
    last_column = get_column_letter(len(headers))
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"
    sheet.freeze_panes = "A2"
    sheet.row_dimensions[1].height = 22
    for letter, width in COLUMN_WIDTHS.items():
        sheet.column_dimensions[letter].width = width
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True

    about = workbook.create_sheet("About this file")
    about["A1"] = "How to read this file"
    about["A1"].font = Font(bold=True, size=16, color="1F4E79")
    lines = [
        "Each row on the Jobs sheet is one job posting collected by scrape.py.",
        "New since last run is yes when that link was not in data/seen_jobs.json before this run.",
        "On a first run, every row says yes. Later runs say yes only for postings that were not saved before.",
        "Use the dropdown arrows in the header row to filter. Choose yes to see only the new listings.",
        "Role searched is the phrase from config.yaml that found the posting. Place searched is Milan or Remote.",
        "Description is a short snippet, not the full advert. Open the URL for the full posting.",
        "Source type is company site, remote board, or aggregator. Sort or filter that column to see the less crowded sources first. Company site means the company's own careers page.",
        "The same title at the same company is kept once. The company site link is kept when a job board lists it too.",
        "Delete data/seen_jobs.json if you want the next run to treat every listing as new again.",
    ]
    for offset, line in enumerate(lines, start=3):
        about.cell(offset, 1, line)
    about.column_dimensions["A"].width = 120
    workbook.save(path)
