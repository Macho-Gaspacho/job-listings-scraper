"""Read one row from the jobs spreadsheet the scraper already writes."""

from __future__ import annotations

import csv
from pathlib import Path

from listings import OUTPUT_FIELDS


def load_job_rows(path: str | Path) -> list[dict]:
    """Rows are numbered from 1. Row 1 is the first job under the header."""
    label_to_key = {label: key for key, label in OUTPUT_FIELDS}
    rows = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, raw in enumerate(reader, start=1):
            row = {"row_number": str(index)}
            for header, value in raw.items():
                if header is None:
                    continue
                key = label_to_key.get(header, header)
                row[key] = "" if value is None else str(value)
            row["row_number"] = index
            rows.append(row)
    return rows


def select_job(rows: list[dict], row_or_url: str) -> dict:
    text = str(row_or_url).strip()
    if text.isdigit():
        number = int(text)
        for row in rows:
            if row["row_number"] == number:
                return row
        raise LookupError(f"No job at row {number}.")
    for row in rows:
        if row.get("url", "").strip() == text:
            return row
    raise LookupError(f"No job with that URL: {text}")
