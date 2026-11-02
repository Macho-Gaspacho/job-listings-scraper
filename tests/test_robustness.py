"""Failures a beginner can hit: offline runs, bad files, and spreadsheet formulas.

No test here talks to the network. Sites are replaced with functions that raise.
"""

import csv
import json
import os
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
from openpyxl import Workbook, load_workbook

import boards
import save_results
import scrape
import setup_wizard
from boards import http_get
from config import Place, Settings, load_config
from environment import certificate_hint
from save_results import load_seen, save_seen, write_daily_files, write_outputs
from scrape import _run_search, collect_listings


def _row(**overrides):
    base = {
        "is_new": "yes",
        "title": "Designer",
        "company": "ACME",
        "location": "Berlin",
        "date_posted": "2026-11-01",
        "source": "indeed",
        "source_type": "aggregator",
        "url": "https://example.com/jobs/1",
        "description": "Draw things.",
        "role_searched": "Designer",
        "place_searched": "Berlin, Germany",
    }
    base.update(overrides)
    return base


def _settings(**overrides):
    values = dict(
        roles=["Designer"],
        places=[
            Place(
                name="Berlin, Germany",
                indeed_location="Berlin, Germany",
                linkedin_location="Berlin, Germany",
            )
        ],
        sites=["indeed"],
        country="germany",
        results_per_search=1,
        posted_within_days=7,
        pause_seconds=0,
        fetch_descriptions=False,
        snippet_characters=80,
        output_dir=None,
        csv_path=None,
        excel_path=None,
        seen_file=None,
    )
    values.update(overrides)
    return Settings(**values)


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _search_config(tmp_path: Path, *, remote: bool) -> Path:
    remote_source = ""
    if remote:
        remote_source = """
  - id: remote_ok
    enabled: true
    kind: remote board
"""
    return _write_config(
        tmp_path,
        f"""
roles: [Designer]
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
sources:
  - id: indeed
    enabled: true
    kind: aggregator
{remote_source}country: germany
results_per_search: 5
posted_within_days: 7
pause_seconds: 1
output:
  directory: output
  csv: jobs.csv
  excel: jobs.xlsx
  seen_file: data/seen_jobs.json
""",
    )


def _offline(*_args, **_kwargs):
    raise URLError("proxy connection failed SECRET_OFFLINE_BLOB")


def _result_files(tmp_path: Path) -> dict[Path, bytes]:
    output = tmp_path / "output"
    data = tmp_path / "data"
    output.mkdir()
    data.mkdir()
    files = {
        output / "jobs.csv": b"OLD,CSV\nkeep-this-row\n",
        output / "jobs.xlsx": b"PK\x03\x04old-excel-bytes",
        output / "new_jobs.csv": b"OLD,NEW\n",
        output / "last_run.json": b"{}\n",
        data / "seen_jobs.json": b'{"seen_keys": ["abc"]}\n',
    }
    for path, payload in files.items():
        path.write_bytes(payload)
    return files


def _column(sheet, header: str) -> int:
    for cell in sheet[1]:
        if cell.value == header:
            return cell.column
    raise AssertionError(f"missing column {header}")


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self, _limit: int = -1) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> bool:
        return False


def _http_error(code: int, retry_after: str | None = None, msg: str = "no") -> HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError("https://example.com/jobs", code, msg, headers, None)


def test_offline_run_keeps_previous_results(tmp_path, capsys):
    config = _search_config(tmp_path, remote=True)
    files = _result_files(tmp_path)

    code = _run_search(config, False, fetch=_offline, getter=_offline)

    captured = capsys.readouterr()
    output_dir = tmp_path / "output"
    assert code == 1
    assert "Nothing was downloaded (no internet?)." in captured.out
    assert f"Your previous results in {output_dir} were kept." in captured.out
    assert "SECRET_OFFLINE_BLOB" not in captured.out
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert "Saved " not in captured.out
    for path, payload in files.items():
        assert path.read_bytes() == payload
    assert list(output_dir.glob("*.tmp")) == []
    assert list((tmp_path / "data").glob("*.tmp")) == []


def test_a_single_successful_source_still_saves(tmp_path, capsys):
    config = _search_config(tmp_path, remote=True)

    def fetch(_role, _place, _site):
        return [_row(title="Kept role", url="https://example.com/kept")]

    code = _run_search(config, False, fetch=fetch, getter=_offline)

    captured = capsys.readouterr()
    assert code == 0
    assert "Nothing was downloaded" not in captured.out
    assert "SECRET_OFFLINE_BLOB" not in captured.out
    csv_text = (tmp_path / "output" / "jobs.csv").read_text(encoding="utf-8-sig")
    assert "Kept role" in csv_text
    assert (tmp_path / "output" / "jobs.xlsx").is_file()
    assert (tmp_path / "output" / "new_jobs.csv").is_file()
    assert (tmp_path / "output" / "last_run.json").is_file()
    seen = json.loads((tmp_path / "data" / "seen_jobs.json").read_text(encoding="utf-8"))
    assert seen["seen_keys"]


def test_result_files_are_written_by_replacing_a_temp_file(tmp_path, monkeypatch):
    calls = []
    real_replace = os.replace

    def spy(src, dst):
        calls.append((Path(src).name, Path(dst).name))
        return real_replace(src, dst)

    monkeypatch.setattr(save_results.os, "replace", spy)
    when = __import__("datetime").datetime(2026, 11, 2, 12, 0)
    write_outputs([_row()], tmp_path / "jobs.csv", tmp_path / "jobs.xlsx")
    save_seen(tmp_path / "seen_jobs.json", {"url:https://example.com/jobs/1"})
    write_daily_files([_row()], tmp_path / "new_jobs.csv", tmp_path / "last_run.json", when)

    replaced = dict(calls)
    for name in ("jobs.csv", "jobs.xlsx", "seen_jobs.json", "new_jobs.csv", "last_run.json"):
        assert replaced.get(name + ".tmp") == name
        assert not (tmp_path / (name + ".tmp")).exists()


def test_open_excel_file_is_saved_under_a_new_name(tmp_path, monkeypatch, capsys):
    excel = tmp_path / "jobs.xlsx"
    original = b"PK\x03\x04already-open-in-excel"
    excel.write_bytes(original)
    real_save = Workbook.save

    def save(self, filename, *args, **kwargs):
        if Path(filename).name.startswith("jobs.xlsx"):
            raise PermissionError("locked by Excel")
        return real_save(self, filename)

    monkeypatch.setattr(Workbook, "save", save)
    write_outputs([_row(title="Still here")], tmp_path / "jobs.csv", excel)

    captured = capsys.readouterr()
    copies = sorted(tmp_path.glob("jobs-*.xlsx"))
    assert excel.read_bytes() == original
    assert len(copies) == 1
    assert copies[0].name.startswith("jobs-")
    assert len(copies[0].name.removesuffix(".xlsx").split("-")[-1]) == 4
    assert "jobs.xlsx is open in Excel; saved as" in captured.out
    assert copies[0].name in captured.out
    assert "instead" in captured.out
    assert "Traceback" not in captured.out
    workbook = load_workbook(copies[0])
    assert workbook["Jobs"]["B2"].value == "Still here"
    assert list(tmp_path.glob("*.tmp")) == []


def test_safe_cell_prefixes_formula_characters():
    from save_results import safe_cell

    assert safe_cell("=1+1") == "'=1+1"
    assert safe_cell("  =1+1") == "'  =1+1"
    assert safe_cell("+1") == "'+1"
    assert safe_cell("-1") == "'-1"
    assert safe_cell("@cmd") == "'@cmd"
    assert safe_cell("\tcmd") == "'\tcmd"
    assert safe_cell("\rcmd") == "'\rcmd"
    assert safe_cell("hello") == "hello"
    assert safe_cell("  hello") == "  hello"
    assert safe_cell(3) == 3


def test_spreadsheet_text_cannot_become_a_formula_or_a_script_link(tmp_path):
    csv_path = tmp_path / "jobs.csv"
    excel_path = tmp_path / "jobs.xlsx"
    write_outputs(
        [
            _row(
                title='=HYPERLINK("http://x","y")',
                company="+cmd",
                description="-note",
                url="javascript:alert(1)",
            ),
            _row(title="=1+1", url="https://example.com/ok", company="ACME"),
            _row(title="Normal", url="http://example.com/also", company="ACME"),
        ],
        csv_path,
        excel_path,
    )

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.reader(handle))
    assert csv_rows[1][1] == '\'=HYPERLINK("http://x","y")'
    assert csv_rows[2][1] == "'=1+1"
    assert "'+cmd" in csv_rows[1]
    assert "'-note" in csv_rows[1]

    sheet = load_workbook(excel_path)["Jobs"]
    title = _column(sheet, "Title")
    url = _column(sheet, "URL")
    company = _column(sheet, "Company")
    dangerous = sheet.cell(2, title)
    assert dangerous.data_type == "s"
    assert dangerous.data_type != "f"
    assert dangerous.value == '\'=HYPERLINK("http://x","y")'
    assert sheet.cell(2, url).hyperlink is None
    assert sheet.cell(2, company).value == "'+cmd"
    formula = sheet.cell(3, title)
    assert formula.data_type == "s"
    assert formula.value == "'=1+1"
    assert sheet.cell(3, url).hyperlink.target == "https://example.com/ok"
    assert sheet.cell(4, url).hyperlink.target == "http://example.com/also"
    ftp = _row(title="FTP", url="ftp://example.com/secret")
    write_outputs([ftp], tmp_path / "ftp.csv", tmp_path / "ftp.xlsx")
    ftp_sheet = load_workbook(tmp_path / "ftp.xlsx")["Jobs"]
    assert ftp_sheet.cell(2, _column(ftp_sheet, "URL")).hyperlink is None


@pytest.mark.parametrize(
    "body",
    ["{not json", "[]", '{"seen_keys": "abc"}', '{"seen_keys": [1]}'],
)
def test_unreadable_seen_file_is_renamed(tmp_path, capsys, body):
    path = tmp_path / "seen_jobs.json"
    path.write_text(body, encoding="utf-8")

    assert load_seen(path) == set()

    captured = capsys.readouterr()
    renamed = list(tmp_path.glob("seen_jobs.corrupt-*.json"))
    assert not path.exists()
    assert len(renamed) == 1
    assert renamed[0].read_text(encoding="utf-8") == body
    assert renamed[0].name in captured.out
    assert captured.out.count(renamed[0].name) == 1
    assert "Traceback" not in captured.out
    assert "JSONDecodeError" not in captured.out
    assert "Traceback" not in captured.err


def test_ctrl_c_during_setup_prints_a_plain_message(tmp_path, monkeypatch, capsys):
    def boom(_prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", boom)
    config = tmp_path / "config.yaml"

    code = setup_wizard.main(["--config", str(config)])

    captured = capsys.readouterr()
    assert code == 130
    assert "Stopped. Nothing was changed." in captured.out
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert not config.exists()


def test_ctrl_c_during_search_does_not_save(tmp_path, monkeypatch, capsys):
    config = _search_config(tmp_path, remote=False)
    files = _result_files(tmp_path)

    def boom(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(scrape, "fetch_listings", boom)
    code = scrape.main(["--config", str(config)])

    captured = capsys.readouterr()
    assert code == 130
    assert "Stopped. Results collected so far were not saved." in captured.out
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    for path, payload in files.items():
        assert path.read_bytes() == payload


def test_launchers_skip_pip_when_the_requirements_stamp_matches():
    root = Path(__file__).resolve().parents[1]
    for name in ("start.sh", "start.bat"):
        text = (root / name).read_text(encoding="utf-8")
        assert ".requirements.sha256" in text
        assert "sha256" in text
        assert "Could not update the tools (no internet?). Continuing with the ones already installed." in text
        assert "Could not install the tools. Check your internet connection and try again." in text
        assert "Installing the tools this program needs. The first time can take a few minutes..." in text
    bat = (root / "start.bat").read_text(encoding="utf-8")
    assert bat.rfind("pause") > bat.rfind("scrape.py")


def _base_config(extra: str = "", distance: str = "") -> str:
    distance_line = f"    distance_miles: {distance}\n" if distance != "" else ""
    return f"""
roles: [Designer]
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
{distance_line}sources:
  - id: indeed
    enabled: true
    kind: aggregator
country: germany
{extra}
"""


@pytest.mark.parametrize(
    ("key", "value", "low", "high"),
    [
        ("results_per_search", 0, 1, 200),
        ("results_per_search", 201, 1, 200),
        ("results_per_search", "ten", 1, 200),
        ("posted_within_days", 0, 1, 365),
        ("posted_within_days", 366, 1, 365),
        ("posted_within_days", "soon", 1, 365),
    ],
)
def test_search_limits_must_be_whole_numbers_in_range(tmp_path, key, value, low, high):
    path = _write_config(tmp_path, _base_config(f"{key}: {value}\n"))
    with pytest.raises(ValueError) as caught:
        load_config(path)
    message = str(caught.value)
    assert key in message
    assert str(low) in message
    assert str(high) in message
    assert "invalid literal" not in message


@pytest.mark.parametrize("value", [0, 0.5, "slow"])
def test_pause_seconds_must_be_at_least_one(tmp_path, value):
    path = _write_config(tmp_path, _base_config(f"pause_seconds: {value}\n"))
    with pytest.raises(ValueError) as caught:
        load_config(path)
    message = str(caught.value)
    assert "pause_seconds" in message
    assert "1" in message
    assert "invalid literal" not in message


@pytest.mark.parametrize("miles", [-1, 201, "far"])
def test_distance_miles_must_be_from_0_to_200(tmp_path, miles):
    path = _write_config(tmp_path, _base_config(distance=str(miles)))
    with pytest.raises(ValueError) as caught:
        load_config(path)
    message = str(caught.value)
    assert "distance_miles" in message
    assert "0" in message and "200" in message
    assert "invalid literal" not in message


def test_missing_limits_use_safe_defaults_and_edges_are_accepted(tmp_path):
    omitted = load_config(_write_config(tmp_path, _base_config()))
    assert omitted.results_per_search == 10
    assert omitted.posted_within_days == 30
    assert omitted.pause_seconds == 2
    assert omitted.places[0].distance_miles is None

    edges = load_config(
        _write_config(
            tmp_path,
            _base_config(
                "results_per_search: 200\nposted_within_days: 365\npause_seconds: 1\n",
                distance="0",
            ),
        )
    )
    assert edges.results_per_search == 200
    assert edges.posted_within_days == 365
    assert edges.pause_seconds == 1
    assert edges.places[0].distance_miles == 0

    upper = load_config(
        _write_config(
            tmp_path,
            _base_config(
                "results_per_search: 1\nposted_within_days: 1\npause_seconds: 1.5\n",
                distance="200",
            ),
        )
    )
    assert upper.results_per_search == 1
    assert upper.posted_within_days == 1
    assert upper.pause_seconds == 1.5
    assert upper.places[0].distance_miles == 200


@pytest.mark.parametrize(
    ("exc", "needle", "blob"),
    [
        (URLError("Tunnel connection failed via proxy SECRET_PROXY_BLOB"), "proxy", "SECRET_PROXY_BLOB"),
        (URLError(TimeoutError("timed out SECRET_TIMEOUT_BLOB")), "too long", "SECRET_TIMEOUT_BLOB"),
        (TimeoutError("timed out SECRET_TIMEOUT_BLOB"), "too long", "SECRET_TIMEOUT_BLOB"),
        (_http_error(403, msg="SECRET_403_BLOB"), "403", "SECRET_403_BLOB"),
        (_http_error(429, msg="SECRET_429_BLOB"), "429", "SECRET_429_BLOB"),
        (_http_error(503, msg="SECRET_503_BLOB"), "503", "SECRET_503_BLOB"),
        (
            OSError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed SECRET_SSL_BLOB"),
            "certificate",
            "SECRET_SSL_BLOB",
        ),
        (URLError("[Errno 61] Connection refused SECRET_NET_BLOB"), "internet", "SECRET_NET_BLOB"),
    ],
)
def test_network_failures_are_explained_in_plain_english(capsys, exc, needle, blob):
    certificate_hint.shown = False
    certificate_hint.platform = "darwin"
    certificate_hint.version = (3, 12, 0)
    try:
        def fetch(_role, _place, _site):
            raise exc

        _rows, failures = collect_listings(_settings(), fetch, pause=lambda _seconds: None)
        assert failures == 1
        captured = capsys.readouterr()
        assert needle in captured.out.lower()
        assert blob not in captured.out
        assert "Traceback" not in captured.out
        assert "Errno" not in captured.out
        assert "<urlopen" not in captured.out
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            assert "Install Certificates.command" in captured.out
    finally:
        certificate_hint.platform = None
        certificate_hint.version = None
        certificate_hint.shown = False


def test_ordinary_search_errors_keep_their_short_reason(capsys):
    def fetch(_role, _place, _site):
        raise RuntimeError("location not found")

    _rows, failures = collect_listings(_settings(), fetch, pause=lambda _seconds: None)
    assert failures == 1
    assert "location not found" in capsys.readouterr().out


def _patch_urlopen(monkeypatch, handler):
    def fail_sleep(_seconds):
        raise AssertionError("http_get slept with time.sleep; pass the injected sleep")

    monkeypatch.setattr(boards.time, "sleep", fail_sleep)
    monkeypatch.setattr(boards.urllib.request, "urlopen", handler)


def test_http_get_retries_429_and_honours_numeric_retry_after(monkeypatch):
    calls = {"n": 0}

    def urlopen(_request, timeout=45):
        calls["n"] += 1
        raise _http_error(429, retry_after="4")

    _patch_urlopen(monkeypatch, urlopen)
    sleeps = []
    with pytest.raises(RuntimeError):
        http_get("https://example.com/jobs", sleep=sleeps.append)
    assert calls["n"] == 3
    assert sleeps == [4, 4]


def test_http_get_caps_retry_after_at_30_seconds(monkeypatch):
    def urlopen(_request, timeout=45):
        raise _http_error(429, retry_after="90")

    _patch_urlopen(monkeypatch, urlopen)
    sleeps = []
    with pytest.raises(RuntimeError):
        http_get("https://example.com/jobs", sleep=sleeps.append)
    assert sleeps == [30, 30]


def test_http_get_uses_backoff_when_retry_after_is_not_numeric(monkeypatch):
    calls = {"n": 0}

    def urlopen(_request, timeout=45):
        calls["n"] += 1
        raise _http_error(503, retry_after="Wed, 21 Oct 2015 07:28:00 GMT")

    _patch_urlopen(monkeypatch, urlopen)
    sleeps = []
    with pytest.raises(RuntimeError):
        http_get("https://example.com/jobs", sleep=sleeps.append)
    assert calls["n"] == 3
    assert sleeps == [2, 5]


def test_http_get_retries_timeouts_then_returns_the_body(monkeypatch):
    calls = {"n": 0}

    def urlopen(_request, timeout=45):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("timed out")
        return _Response(b"ok")

    _patch_urlopen(monkeypatch, urlopen)
    sleeps = []
    assert http_get("https://example.com/jobs", sleep=sleeps.append) == b"ok"
    assert calls["n"] == 3
    assert sleeps == [2, 5]


@pytest.mark.parametrize(
    "exc",
    [_http_error(404), URLError("Connection refused")],
)
def test_http_get_does_not_retry_ordinary_client_or_connection_errors(monkeypatch, exc):
    calls = {"n": 0}

    def urlopen(_request, timeout=45):
        calls["n"] += 1
        raise exc

    _patch_urlopen(monkeypatch, urlopen)
    sleeps = []
    with pytest.raises(RuntimeError):
        http_get("https://example.com/jobs", sleep=sleeps.append)
    assert calls["n"] == 1
    assert sleeps == []
