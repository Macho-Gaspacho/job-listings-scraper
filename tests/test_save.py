from pathlib import Path
from save_results import write_csv, load_seen, save_seen


def test_write_and_load_seen(tmp_path):
    path = tmp_path / "seen.json"
    rows = [{"Company": "Acme", "Title": "PM", "Status": "New"}]
    save_seen(path, rows)
    assert ("acme", "pm") in load_seen(path)


def test_write_csv(tmp_path):
    path = tmp_path / "out.csv"
    rows = [{"Title": "PM", "Company": "A", "Location": "Milan", "Source": "x", "Source type": "company site", "Link": "http://x", "Status": "New", "Date found": "2026-10-22"}]
    write_csv(rows, path)
    assert path.read_text().startswith("Title,Company")
