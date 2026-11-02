"""Library logs stay hidden unless a detailed run was asked for. No network."""

import io
import logging
import sys
from pathlib import Path

from config import Place, Settings
from jobspy.util import configure_logging as jobspy_configure
from jobspy.util import log_handler
from scrape import collect_listings, configure_logging
from sources import fetch_listings


def _settings() -> Settings:
    return Settings(
        roles=["Nurse"],
        places=[
            Place(
                name="Italy",
                indeed_location="Italy",
                linkedin_location="Italy",
            )
        ],
        sites=["indeed"],
        country="italy",
        results_per_search=20,
        posted_within_days=14,
        pause_seconds=0,
        fetch_descriptions=False,
        snippet_characters=80,
        output_dir=Path("output"),
        csv_path=Path("output/jobs.csv"),
        excel_path=Path("output/jobs.xlsx"),
        seen_file=Path("data/seen_jobs.json"),
    )


def _bind_library_handler() -> None:
    """Point the library handler at the stderr pytest is capturing."""
    log_handler.stream = sys.stderr


def test_jobspy_logger_is_silenced_by_default(capsys, monkeypatch):
    seen = {}

    def boom(**kwargs):
        seen["verbose"] = kwargs.get("verbose")
        jobspy_configure(None if kwargs.get("verbose") is None else kwargs["verbose"])
        logging.getLogger("jobspy.indeed").error(
            "HTTPSConnectionPool(host='it.indeed.com', port=443): Max retries exceeded"
        )
        logging.getLogger("urllib3.connectionpool").error(
            "HTTPSConnectionPool(host='it.indeed.com', port=443): Max retries exceeded"
        )
        raise OSError("offline")

    monkeypatch.setattr("sources.scrape_jobs", boom)
    _bind_library_handler()
    configure_logging(False)
    settings = _settings()
    rows, failures = collect_listings(
        settings,
        lambda role, place, site: fetch_listings(settings, role, place, site),
        pause=lambda _seconds: None,
    )
    captured = capsys.readouterr()
    combined = f"{captured.out}\n{captured.err}"
    assert seen["verbose"] is None
    assert failures == 1
    assert rows == []
    assert not logging.getLogger("jobspy.indeed").isEnabledFor(logging.ERROR)
    assert not logging.getLogger("urllib3").isEnabledFor(logging.ERROR)
    assert not any(line.startswith("ERROR:jobspy") for line in combined.splitlines())
    assert not any(line.startswith("ERROR:urllib3") for line in combined.splitlines())
    assert "Skipped" in captured.out


def test_verbose_shows_jobspy_errors_again():
    """--verbose turns the library logger back on, in the same format it usually prints."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    logger = logging.getLogger("jobspy")
    logger.addHandler(handler)
    try:
        configure_logging(True)
        jobspy_configure(2)
        logging.getLogger("jobspy.indeed").error("HTTPSConnectionPool(host='example')")
        assert "ERROR:jobspy.indeed:HTTPSConnectionPool(host='example')" in stream.getvalue()
    finally:
        logger.removeHandler(handler)
        configure_logging(False)
