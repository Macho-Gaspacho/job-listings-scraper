"""Write the listings to a CSV and an Excel file, and keep the memory of seen jobs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

COLUMNS = [
    "Title",
    "Company",
    "Location",
    "Source",
    "Source type",
    "Link",
    "Status",
    "Date found",
]


def write_outputs(rows: list[dict], output_dir: Path) -> None:
    """Write jobs.csv and jobs.xlsx."""
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, output_dir / "jobs.csv")
    write_xlsx(rows, output_dir / "jobs.xlsx")


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in COLUMNS})


def write_xlsx(rows: list[dict], path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Jobs"
    sheet.append(COLUMNS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([row.get(key, "") for key in COLUMNS])
    for column in sheet.columns:
        length = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(length + 2, 60)
    workbook.save(path)


def load_seen(path: Path) -> set[tuple[str, str]]:
    """Load the memory of company+title pairs already seen."""
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(item["company"], item["title"]) for item in data}


def save_seen(path: Path, rows: list[dict]) -> None:
    """Update the memory file with every row from this run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    known = {(item["company"], item["title"]) for item in existing}
    for row in rows:
        key = (row.get("Company", "").casefold(), row.get("Title", "").casefold())
        if key not in known:
            existing.append({"company": key[0], "title": key[1]})
            known.add(key)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def write_daily_files(rows: list[dict], output_dir: Path, seen_path: Path) -> None:
    """Write the three files the daily commit expects."""
    output_dir.mkdir(parents=True, exist_ok=True)
    new_rows = [row for row in rows if row.get("Status") == "New"]
    write_csv(new_rows, output_dir / "new_jobs.csv")
    last_run = {
        "when": rows[0].get("Date found") if rows else "",
        "found": len(rows),
        "new": len(new_rows),
    }
    (output_dir / "last_run.json").write_text(json.dumps(last_run, indent=2), encoding="utf-8")
    save_seen(seen_path, rows)
