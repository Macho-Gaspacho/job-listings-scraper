"""CV generator tests. No network and no invented facts."""

import json
import re
import zlib
import struct
from datetime import date
from pathlib import Path

import pytest
import yaml
from docx import Document
from docx.shared import Inches

from cv.cli import output_filename, run_cv
from cv.jobs import load_job_rows, select_job
from cv.llm import rephrase_bullets
from cv.presets import include_photo, load_preset, page_limit, personal_fields_for
from cv.profile import ProfileError, load_profile, profile_text
from cv.render_docx import libreoffice_pdf, render_docx
from cv.render_text import (
    estimate_pages,
    render_cover_letter,
    render_html,
    render_markdown,
    render_match_report,
)
from cv.tailor import tailor
from cv.wizard import CV_MENU_LABEL, run_launcher_menu
from matching import normalise
from save_results import write_outputs
from scrape import main


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "profile" / "cv_profile.example.yaml"


@pytest.fixture(autouse=True)
def _cv_tests_do_not_call_an_llm(monkeypatch):
    """A key in the environment must not turn the suite into a network test."""
    monkeypatch.delenv("CV_LLM_API_KEY", raising=False)
    monkeypatch.delenv("CV_LLM_BASE_URL", raising=False)


def _png(path: Path) -> None:
    """A 1x1 PNG so python-docx has a real picture to embed. No image library."""
    raw = b"\x00\xff\xff\xff"

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _profile_dict(photo: str = "", **overrides) -> dict:
    data = {
        "contact": {
            "full_name": "Ada Lovelace",
            "email": "ada.secret@example.com",
            "phone": "+1-555-0148",
            "location": "Berlin",
        },
        "summary": "Ward nurse who writes Python handover notes.",
        "photo": {"path": photo, "include": True},
        "personal": {
            "include": True,
            "date_of_birth": "1984-07-09",
            "nationality": "Narnian",
            "marital_status": "unmarried",
        },
        "signature": {"include": True, "place": "Berlin"},
        "gdpr_consent": True,
        "references_on_request": True,
        "document_language": "en",
        "experience": [
            {
                "employer": "Harbor Clinic",
                "title": "Nurse",
                "location": "Berlin",
                "start": "2020",
                "end": "2024",
                "bullets": [
                    "Taught Python to 8 new nurses.",
                    "Wrote Python handover notes.",
                ],
            },
            {
                "employer": "City Hospital",
                "title": "Nurse",
                "location": "Berlin",
                "start": "2010",
                "end": "2016",
                "bullets": ["Cared for 8 patients on a medical ward."],
            },
        ],
        "education": [
            {
                "institution": "City Hospital School",
                "degree": "Diploma",
                "field": "Nursing",
                "start": "2006",
                "end": "2010",
            }
        ],
        "skills": [
            {"name": "Python", "evidence": "Wrote Python handover notes on the ward."},
            {"name": "Excel", "evidence": "Kept a supply rota in Excel."},
        ],
        "languages": [
            {"name": "English", "level": "C1"},
            {"name": "German", "level": "B2"},
        ],
        "certifications": [{"name": "Ward Mentor", "issuer": "Harbor Clinic", "date": "2021"}],
        "links": [{"label": "Portfolio", "url": "https://example.com/ada"}],
    }
    data.update(overrides)
    return data


def _write_profile(path: Path, **overrides) -> Path:
    payload = _profile_dict(**overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _jobs(tmp_path: Path) -> Path:
    rows = [
        {
            "is_new": "yes",
            "title": "Nurse",
            "company": "Harbor Clinic",
            "location": "Berlin, Germany",
            "date_posted": "2026-10-01",
            "source": "indeed",
            "source_type": "aggregator",
            "url": "https://example.com/jobs/nurse",
            "description": "Ward nursing. Python handover notes. Terraform and Epic. 12 years required.",
            "role_searched": "Nurse",
            "place_searched": "Berlin",
            "languages": "German",
            "job_type": "Full-time",
            "is_remote": "No",
        },
        {
            "is_new": "no",
            "title": "Analyst",
            "company": "Ipsos",
            "location": "Milan, Italy",
            "date_posted": "2026-10-02",
            "source": "indeed",
            "source_type": "aggregator",
            "url": "https://example.com/jobs/analyst",
            "description": "Study how people shop.",
            "role_searched": "Analyst",
            "place_searched": "Milan",
        },
    ]
    csv_path = tmp_path / "jobs.csv"
    write_outputs(rows, csv_path, tmp_path / "jobs.xlsx")
    return csv_path


def _chrome(preset) -> set[str]:
    words = set()
    for titles in preset.section_titles.values():
        for title in titles.values():
            words.update(normalise(title))
            words.update(token.casefold() for token in re.findall(r"[A-Za-z0-9+#.-]+", title))
    for label_map in preset.field_labels.values():
        for label in label_map.values():
            words.update(token.casefold() for token in re.findall(r"[A-Za-z0-9+#.-]+", label))
    for extra in (preset.present_label, preset.references_line, preset.consent_line, "CEFR"):
        words.update(token.casefold() for token in re.findall(r"[A-Za-z0-9+#.-]+", extra or ""))
    return words


def _assert_grounded(text: str, profile, preset, extra: str = "") -> None:
    """Numbers and proper nouns in the CV must come from the profile or preset chrome."""
    corpus = profile_text(profile)
    allowed_numbers = set(re.findall(r"\d+", corpus))
    found_numbers = set(re.findall(r"\d+", text))
    invented_numbers = found_numbers - allowed_numbers
    assert invented_numbers == set()
    allowed_words = {token.casefold() for token in re.findall(r"[A-Za-z0-9+#.-]+", corpus)}
    allowed_words |= _chrome(preset)
    allowed_words |= {token.casefold() for token in re.findall(r"[A-Za-z0-9+#.-]+", extra)}
    for word in re.findall(r"\b[A-Z][A-Za-z0-9+#]*", text):
        assert word.casefold() in allowed_words, word


def _tailored(tmp_path: Path, fmt: str = "us_resume", **profile_overrides):
    photo = profile_overrides.pop("photo", "")
    profile_path = _write_profile(tmp_path / "cv_profile.yaml", photo=photo, **profile_overrides)
    profile = load_profile(profile_path)
    job = select_job(load_job_rows(_jobs(tmp_path)), "1")
    preset = load_preset(fmt)
    document = tailor(profile, job, preset)
    return profile, job, preset, document


def test_example_profile_loads_and_personal_fields_are_opt_in():
    profile = load_profile(EXAMPLE)
    assert profile.full_name
    assert profile.experience
    assert profile.photo_opt_in is False
    assert profile.personal.include is False
    assert profile.gdpr_consent is False


def test_invalid_language_level_is_rejected(tmp_path):
    path = _write_profile(tmp_path / "cv_profile.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["languages"][0]["level"] = "fluent"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ProfileError, match="CEFR"):
        load_profile(path)


def test_profile_requires_a_name(tmp_path):
    path = tmp_path / "cv_profile.yaml"
    path.write_text("summary: Hello\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="full_name"):
        load_profile(path)


@pytest.mark.parametrize(
    "name",
    ["us_resume", "uk_cv", "de_lebenslauf", "eu_europass", "it_cv", "fr_cv"],
)
def test_presets_declare_layout_photo_and_personal_rules(name):
    preset = load_preset(name)
    assert preset.page_size in {"letter", "a4"}
    assert preset.photo in {"forbidden", "optional", "customary"}
    assert preset.max_pages >= 1
    assert preset.section_order
    assert preset.language in preset.section_titles
    assert "experience" in preset.section_titles[preset.language]
    assert preset.review_notes


def test_us_preset_drops_photo_and_date_of_birth(tmp_path):
    photo = tmp_path / "photo.png"
    _png(photo)
    profile, _job, preset, document = _tailored(tmp_path, "us_resume", photo=str(photo))
    assert include_photo(preset, profile) is False
    assert personal_fields_for(preset, profile) == {}
    markdown = render_markdown(document)
    html = render_html(document)
    docx_path = render_docx(document, tmp_path / "us.docx")
    docx = Document(docx_path)
    text = "\n".join(paragraph.text for paragraph in docx.paragraphs)
    for body in (markdown, html, text):
        assert "1984-07-09" not in body
        assert "Narnian" not in body
        assert "unmarried" not in body
        assert "photo.png" not in body
        _assert_grounded(body, profile, preset)
    assert len(docx.inline_shapes) == 0
    assert docx.sections[0].page_width == Inches(8.5)


def test_de_photo_only_when_provided_and_opted_in(tmp_path):
    photo = tmp_path / "photo.png"
    _png(photo)
    preset = load_preset("de_lebenslauf")

    opted_out_path = _write_profile(tmp_path / "out.yaml", photo=str(photo))
    opted_out_data = yaml.safe_load(opted_out_path.read_text(encoding="utf-8"))
    opted_out_data["photo"]["include"] = False
    opted_out_path.write_text(yaml.safe_dump(opted_out_data), encoding="utf-8")
    opted_out = load_profile(opted_out_path)
    assert include_photo(preset, opted_out) is False

    missing = load_profile(
        _write_profile(tmp_path / "missing.yaml", photo=str(tmp_path / "absent.png"))
    )
    missing_data_path = tmp_path / "missing.yaml"
    missing_data = yaml.safe_load(missing_data_path.read_text(encoding="utf-8"))
    missing_data["photo"]["include"] = True
    missing_data["photo"]["path"] = str(tmp_path / "absent.png")
    missing_data_path.write_text(yaml.safe_dump(missing_data), encoding="utf-8")
    missing = load_profile(missing_data_path)
    assert include_photo(preset, missing) is False

    profile, _job, preset, document = _tailored(tmp_path, "de_lebenslauf", photo=str(photo))
    data = yaml.safe_load((tmp_path / "cv_profile.yaml").read_text(encoding="utf-8"))
    data["photo"]["include"] = True
    (tmp_path / "cv_profile.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    profile = load_profile(tmp_path / "cv_profile.yaml")
    document = tailor(profile, select_job(load_job_rows(_jobs(tmp_path)), "1"), preset)
    assert include_photo(preset, profile) is True
    markdown = render_markdown(document)
    docx_path = render_docx(document, tmp_path / "de.docx")
    docx = Document(docx_path)
    text = "\n".join(paragraph.text for paragraph in docx.paragraphs)
    assert "Berufserfahrung" in markdown
    assert "Ausbildung" in markdown
    assert "Kenntnisse" in markdown
    assert "photo.png" in markdown
    assert len(docx.inline_shapes) == 1
    assert "Berufserfahrung" in text
    # OOXML stores A4 as 11906 twips. Mm(210) does not survive that round trip.
    assert docx.sections[0].page_width.twips == 11906


def test_match_report_lists_missing_keywords_without_adding_them(tmp_path):
    profile, _job, preset, document = _tailored(tmp_path, "us_resume")
    report = document.report
    assert "terraform" in report.missing
    assert "epic" in report.missing
    assert "12" in report.missing
    assert "python" in report.covered
    markdown = render_markdown(document)
    html = render_html(document)
    report_text = render_match_report(document)
    for gap in report.missing:
        assert gap not in markdown.casefold()
        assert gap not in html.casefold()
    assert "terraform" in report_text.casefold()
    assert "not added" in report_text.casefold()
    assert "handover" in markdown.casefold()
    assert "excel" not in markdown.casefold()
    assert markdown.index("handover") < markdown.index("Taught")
    assert markdown.index("2020") < markdown.index("2010")
    _assert_grounded(markdown, profile, preset)
    _assert_grounded(html, profile, preset)


def test_page_count_heuristic_and_us_limit_after_ten_years(tmp_path):
    assert estimate_pages("one two three") == 1
    assert estimate_pages(" ".join(["word"] * 401)) == 2
    short, _job, short_preset, _doc = _tailored(tmp_path / "short", "us_resume")
    assert page_limit(short_preset, short) == 2  # 2010-2024 spans more than 10 years
    recent = _profile_dict()
    recent["experience"] = [recent["experience"][0]]
    path = tmp_path / "recent.yaml"
    path.write_text(yaml.safe_dump(recent), encoding="utf-8")
    recent_profile = load_profile(path)
    assert page_limit(load_preset("us_resume"), recent_profile) == 1

    long_bullet = " ".join(["nursing"] * 500)
    data = _profile_dict()
    data["experience"][0]["bullets"] = [long_bullet]
    data["experience"] = [data["experience"][0]]
    data["skills"] = [data["skills"][0]]
    path = tmp_path / "long.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    profile = load_profile(path)
    job = {
        "title": "Nurse",
        "company": "Harbor Clinic",
        "description": "Ward nursing. Terraform.",
        "location": "Berlin",
        "languages": "",
        "url": "https://example.com/jobs/nurse",
    }
    document = tailor(profile, job, load_preset("us_resume"))
    markdown = render_markdown(document)
    assert estimate_pages(markdown) > page_limit(document.preset, profile)
    assert any("page" in warning.casefold() for warning in document.report.warnings)
    assert "terraform" not in markdown.casefold()


def test_italian_consent_line_is_opt_in_only(tmp_path):
    profile, _job, preset, document = _tailored(tmp_path, "it_cv")
    assert "2016/679" in render_markdown(document)
    data = yaml.safe_load((tmp_path / "cv_profile.yaml").read_text(encoding="utf-8"))
    data["gdpr_consent"] = False
    (tmp_path / "cv_profile.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    profile = load_profile(tmp_path / "cv_profile.yaml")
    document = tailor(profile, select_job(load_job_rows(_jobs(tmp_path)), "1"), preset)
    assert "2016/679" not in render_markdown(document)
    _us = tailor(profile, select_job(load_job_rows(_jobs(tmp_path)), "1"), load_preset("us_resume"))
    assert "2016/679" not in render_markdown(_us)


def test_cover_letter_uses_job_vacancy_and_profile_facts_only(tmp_path):
    profile, job, preset, document = _tailored(tmp_path, "uk_cv")
    letter = render_cover_letter(document)
    assert "Harbor Clinic" in letter
    assert "Nurse" in letter
    assert "terraform" not in letter.casefold()
    assert "12" not in re.findall(r"\d+", letter)
    _assert_grounded(
        letter, profile, preset, extra=f"{job['title']} {job['company']} {job['location']} Applying"
    )
    assert "References available on request" in render_markdown(document)


def test_llm_mode_is_disabled_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("CV_LLM_API_KEY", raising=False)
    monkeypatch.delenv("CV_LLM_BASE_URL", raising=False)

    def boom(*_args, **_kwargs):
        raise AssertionError("LLM mode must not call the network when no key is set")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    profile = load_profile(_write_profile(tmp_path / "cv_profile.yaml"))
    result = rephrase_bullets(
        ["Wrote Python handover notes."],
        "Nurse",
        profile,
    )
    assert result.used_llm is False
    assert result.bullets == ("Wrote Python handover notes.",)
    assert result.warnings == ()


def test_llm_postcheck_rejects_an_injected_fake_employer(monkeypatch, tmp_path):
    monkeypatch.setenv("CV_LLM_API_KEY", "test-key")
    monkeypatch.setenv("CV_LLM_BASE_URL", "https://llm.example/v1")
    profile = load_profile(_write_profile(tmp_path / "cv_profile.yaml"))
    seen = {}

    def opener(request, timeout=30):
        seen["timeout"] = timeout
        seen["body"] = request.data.decode()
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [
                                "At Harbor Clinic, cared for 8 patients.",
                                "Invented a platform at Initech and cut infections by 40.",
                            ]
                        )
                    }
                }
            ]
        }

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(payload).encode()

        return Response()

    result = rephrase_bullets(
        [
            "Cared for 8 patients on a medical ward.",
            "Wrote Python handover notes.",
        ],
        "Nurse",
        profile,
        opener=opener,
    )
    assert result.used_llm is True
    assert "use only the facts provided" in seen["body"]
    assert "ada.secret@example.com" not in seen["body"]
    assert "555-0148" not in seen["body"]
    assert "1984-07-09" not in seen["body"]
    assert "Narnian" not in seen["body"]
    assert "unmarried" not in seen["body"]
    assert "photo" not in seen["body"].casefold()
    assert result.bullets[0] == "At Harbor Clinic, cared for 8 patients."
    assert result.bullets[1] == "Wrote Python handover notes."
    assert "Initech" in " ".join(result.warnings)


def test_pdf_is_skipped_when_libreoffice_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("cv.render_docx.shutil.which", lambda _name: None)
    assert libreoffice_pdf(tmp_path / "cv.docx") is None


def test_filename_uses_company_role_and_date():
    assert (
        output_filename("Harbor Clinic", "Nurse", date(2026, 11, 3))
        == "CV_Harbor_Clinic_Nurse_2026-11-03"
    )


def test_cli_writes_docx_markdown_and_selects_by_url(tmp_path):
    photo = tmp_path / "photo.png"
    _png(photo)
    profile_path = _write_profile(tmp_path / "cv_profile.yaml", photo=str(photo))
    jobs = _jobs(tmp_path)
    out = tmp_path / "cv"
    code = run_cv(
        "https://example.com/jobs/analyst",
        "eu_europass",
        jobs,
        profile_path,
        out,
        cover=True,
        today=date(2026, 11, 3),
    )
    assert code == 0
    docx = out / "CV_Ipsos_Analyst_2026-11-03.docx"
    assert docx.is_file()
    assert (out / "CV_Ipsos_Analyst_2026-11-03.md").is_file()
    assert (out / "CV_Ipsos_Analyst_2026-11-03.html").is_file()
    assert (out / "CV_Ipsos_Analyst_2026-11-03_match.md").is_file()
    letter = (out / "Cover_Ipsos_Analyst_2026-11-03.md").read_text(encoding="utf-8")
    assert "Ipsos" in letter
    assert "terraform" not in letter.casefold()
    body = (out / "CV_Ipsos_Analyst_2026-11-03.md").read_text(encoding="utf-8")
    assert "CEFR" in body
    assert "1984-07-09" not in body or "date_of_birth" in load_preset("eu_europass").personal_fields


def test_scrape_cv_flag(tmp_path, capsys):
    profile_path = _write_profile(tmp_path / "cv_profile.yaml")
    jobs = _jobs(tmp_path)
    out = tmp_path / "cv"
    code = main(
        [
            "--cv",
            "1",
            "--format",
            "us_resume",
            "--jobs",
            str(jobs),
            "--profile",
            str(profile_path),
            "--cv-dir",
            str(out),
            "--cv-date",
            "2026-11-03",
        ]
    )
    assert code == 0
    assert (out / "CV_Harbor_Clinic_Nurse_2026-11-03.docx").is_file()
    message = capsys.readouterr().out
    assert "CV_Harbor_Clinic_Nurse_2026-11-03.docx" in message


def test_missing_profile_explains_how_to_start(tmp_path, capsys):
    jobs = _jobs(tmp_path)
    code = main(
        [
            "--cv",
            "1",
            "--format",
            "uk_cv",
            "--jobs",
            str(jobs),
            "--profile",
            str(tmp_path / "missing.yaml"),
            "--cv-dir",
            str(tmp_path / "cv"),
        ]
    )
    assert code == 1
    assert "cv_profile.example.yaml" in capsys.readouterr().out


def test_launcher_menu_can_make_a_cv(tmp_path, monkeypatch, capsys):
    profile_path = _write_profile(tmp_path / "cv_profile.yaml")
    jobs = _jobs(tmp_path)
    out = tmp_path / "cv"
    answers = iter(["2", "1", "de_lebenslauf"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    code = main(
        [
            "--menu",
            "--jobs",
            str(jobs),
            "--profile",
            str(profile_path),
            "--cv-dir",
            str(out),
            "--cv-date",
            "2026-11-03",
        ]
    )
    assert code == 0
    assert CV_MENU_LABEL == "Make a CV for one of these jobs"
    assert CV_MENU_LABEL in capsys.readouterr().out
    assert (out / "CV_Harbor_Clinic_Nurse_2026-11-03.docx").is_file()
    text = (out / "CV_Harbor_Clinic_Nurse_2026-11-03.md").read_text(encoding="utf-8")
    assert "Berufserfahrung" in text


def test_launcher_menu_search_choice_does_not_build_a_cv(tmp_path):
    seen = {}

    def run_search():
        seen["called"] = True
        return 0

    class Script:
        def __init__(self):
            self.answers = iter(["1"])
            self.lines = []

        def ask(self, prompt=""):
            self.lines.append(prompt)
            return next(self.answers)

        def say(self, text):
            self.lines.append(text)

    script = Script()
    code = run_launcher_menu(
        script.ask,
        script.say,
        tmp_path / "jobs.csv",
        tmp_path / "missing.yaml",
        tmp_path / "cv",
        run_search,
    )
    assert code == 0
    assert seen["called"] is True
    assert CV_MENU_LABEL in "\n".join(script.lines)


def test_profile_files_are_gitignored():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "profile/cv_profile.yaml" in text
    assert "profile/photo.*" in text
    assert "profile/cv_profile.example.yaml" not in text.splitlines()


def test_select_job_by_row_number_and_url(tmp_path):
    rows = load_job_rows(_jobs(tmp_path))
    assert select_job(rows, "2")["company"] == "Ipsos"
    assert select_job(rows, "https://example.com/jobs/nurse")["title"] == "Nurse"
    with pytest.raises(LookupError):
        select_job(rows, "99")
