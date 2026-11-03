"""Interview, data-driven presets, and country format suggestions. No network."""

import re
from datetime import date
from pathlib import Path

import pytest
import yaml
from docx import Document
from docx.shared import Inches

from cv.cli import output_filename, run_cv
from cv.presets import list_presets, load_preset, section_title
from cv.profile import load_profile, profile_from_mapping, profile_text
from cv.render_docx import render_docx
from cv.render_text import render_markdown
from cv.suggest import suggest_format
from cv.tailor import tailor
from cv.wizard import INTERVIEW_MENU_LABEL, run_launcher_menu
from save_results import write_outputs
from scrape import main


ROOT = Path(__file__).resolve().parents[1]
PRESETS = (
    "us_resume",
    "uk_cv",
    "de_lebenslauf",
    "eu_europass",
    "it_cv",
    "fr_cv",
    "nl_cv",
    "es_cv",
    "pl_cv",
    "ca_resume",
)
_CAPITAL = re.compile(r"[^\W\d_]+", re.UNICODE)
_FIXED_LABELS = "CEFR\nLanguage\nOrt\nDatum\n"
_MONTH_NAMES = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
    "January",
    "February",
    "March",
    "April",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
PL_CONSENT = (
    "Wyrażam zgodę na przetwarzanie moich danych osobowych dla potrzeb niezbędnych "
    "do realizacji procesu rekrutacji zgodnie z Rozporządzeniem Parlamentu Europejskiego "
    "i Rady (UE) 2016/679"
)


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.delenv("CV_LLM_API_KEY", raising=False)
    monkeypatch.delenv("CV_LLM_BASE_URL", raising=False)


def _script(pairs):
    remaining = list(pairs)
    prompts = []

    def ask(prompt=""):
        if not remaining:
            raise AssertionError(f"No answer left for: {prompt}")
        needle, answer = remaining.pop(0)
        prompts.append(prompt)
        if needle.casefold() not in prompt.casefold():
            raise AssertionError(f"Expected {needle!r} in prompt, got {prompt!r}")
        return answer

    return ask, remaining, prompts


def _skip_pairs(name="Sam Lee"):
    return [
        ("name", ""),
        ("name", name),
        ("mail", ""),
        ("hone", ""),
        ("city", ""),
        ("summary", ""),
        ("paid", ""),
        ("volunteer", ""),
        ("project", ""),
        ("family", ""),
        ("university", ""),
        ("skill", ""),
        ("language", ""),
        ("certificate", ""),
        ("link", ""),
    ]


def _no_work_pairs():
    return [
        ("name", "Lucía Navarro"),
        ("mail", "lucia@example.com"),
        ("hone", ""),
        ("city", "Madrid"),
        ("summary", "Recent graduate who wants a first marketing role."),
        ("paid", "no work experience yet"),
        ("volunteer", ""),
        ("project", ""),
        ("family", ""),
        ("university", "Universidad Complutense"),
        ("qualification", "Grado"),
        ("subject", "Marketing"),
        ("start", "2021"),
        ("end", "2025"),
        ("university", ""),
        ("skill", "Canva"),
        ("where", "Designed three posters for a student fair."),
        ("skill", ""),
        ("language", "Spanish"),
        ("how well", "6"),
        ("language", "English"),
        ("how well", "comfortable at work"),
        ("language", ""),
        ("certificate", ""),
        ("link", ""),
    ]


def _people():
    def person(contact, summary, experience, education, skills, languages, job):
        data = {
            "contact": contact,
            "summary": summary,
            "photo": {"path": "", "include": False},
            "personal": {
                "include": True,
                "date_of_birth": "1986",
                "nationality": "Narnian",
                "marital_status": "unmarried",
            },
            "signature": {"include": False, "place": ""},
            "gdpr_consent": False,
            "references_on_request": False,
            "document_language": "en",
            "experience": experience,
            "education": education,
            "skills": skills,
            "languages": languages,
            "certifications": [],
            "links": [],
        }
        return data, job

    nurse, nurse_job = person(
        {
            "full_name": "Sanne de Vries",
            "email": "sanne@example.com",
            "phone": "+31-6-0000-0000",
            "location": "Rotterdam",
        },
        "Ward nurse on a surgical unit.",
        [
            {
                "employer": "Erasmus MC",
                "title": "Verpleegkundige",
                "location": "Rotterdam",
                "start": "2018",
                "end": "2024",
                "bullets": ["Cared for 6 patients on a surgical ward."],
            }
        ],
        [
            {
                "institution": "Hogeschool Rotterdam",
                "degree": "HBO",
                "field": "Nursing",
                "start": "2014",
                "end": "2018",
            }
        ],
        [{"name": "Wound care", "evidence": "Dressed surgical wounds on the ward."}],
        [{"name": "Dutch", "level": "C1"}, {"name": "English", "level": "B2"}],
        {
            "title": "Nurse",
            "company": "Amsterdam UMC",
            "location": "Amsterdam, Netherlands",
            "description": "Ward nurse for surgical patients.",
            "languages": "Dutch",
        },
    )
    warehouse, warehouse_job = person(
        {
            "full_name": "Piotr Kowalski",
            "email": "piotr@example.com",
            "phone": "+48-600-000-000",
            "location": "Kraków",
        },
        "Warehouse worker who picks orders.",
        [
            {
                "employer": "Magazyn Wisła",
                "title": "Magazynier",
                "location": "Kraków",
                "start": "2019",
                "end": "2024",
                "bullets": ["Picked 120 orders in a shift."],
            }
        ],
        [
            {
                "institution": "Zespół Szkół Zawodowych",
                "degree": "Dyplom",
                "field": "Logistyka",
                "start": "2015",
                "end": "2019",
            }
        ],
        [{"name": "Order picking", "evidence": "Picked 120 orders in a shift at Magazyn Wisła."}],
        [{"name": "Polish", "level": "C2"}],
        {
            "title": "Warehouse worker",
            "company": "Logistyka Południe",
            "location": "Kraków, Poland",
            "description": "Pick orders in a warehouse shift.",
            "languages": "Polish",
        },
    )
    graduate, graduate_job = person(
        {
            "full_name": "Lucía Navarro",
            "email": "lucia@example.com",
            "phone": "",
            "location": "Madrid",
        },
        "Recent marketing graduate.",
        [],
        [
            {
                "institution": "Universidad Complutense",
                "degree": "Grado",
                "field": "Marketing",
                "start": "2021",
                "end": "2025",
            }
        ],
        [{"name": "Canva", "evidence": "Designed three posters for a student fair."}],
        [{"name": "Spanish", "level": "C2"}, {"name": "English", "level": "B1"}],
        {
            "title": "Marketing assistant",
            "company": "Feria Norte",
            "location": "Madrid, Spain",
            "description": "Marketing graduate programme in Madrid.",
            "languages": "Spanish",
        },
    )
    engineer, engineer_job = person(
        {
            "full_name": "Jordan Lee",
            "email": "jordan@example.com",
            "phone": "+1-555-0100",
            "location": "Austin",
        },
        "Software engineer who builds Python services.",
        [
            {
                "employer": "Northwind Labs",
                "title": "Software Engineer",
                "location": "Austin",
                "start": "2020",
                "end": "2024",
                "bullets": ["Built a Python service used by 3 teams."],
            }
        ],
        [
            {
                "institution": "State University",
                "degree": "BSc",
                "field": "Computer Science",
                "start": "2016",
                "end": "2020",
            }
        ],
        [{"name": "Python", "evidence": "Built a Python service used by 3 teams."}],
        [{"name": "English", "level": "C2"}],
        {
            "title": "Software Engineer",
            "company": "Northwind Labs",
            "location": "Austin, USA",
            "description": "Python service for a product team.",
            "languages": "English",
        },
    )
    accountant, accountant_job = person(
        {
            "full_name": "Amélie Tremblay",
            "email": "amelie@example.com",
            "phone": "+1-416-555-0100",
            "location": "Toronto",
        },
        "Accountant who reconciles invoices.",
        [
            {
                "employer": "Laurentian Books",
                "title": "Accountant",
                "location": "Toronto",
                "start": "2017",
                "end": "2024",
                "bullets": ["Reconciled 40 invoices each month."],
            }
        ],
        [
            {
                "institution": "University of Toronto",
                "degree": "BCom",
                "field": "Accounting",
                "start": "2013",
                "end": "2017",
            }
        ],
        [{"name": "Excel", "evidence": "Reconciled 40 invoices in Excel each month."}],
        [{"name": "French", "level": "C2"}, {"name": "English", "level": "C1"}],
        {
            "title": "Accountant",
            "company": "Laurentian Books",
            "location": "Toronto, Canada",
            "description": "Reconcile invoices for a Toronto team.",
            "languages": "English",
        },
    )
    cyrillic, cyrillic_job = person(
        {
            "full_name": "Мария Иванова",
            "email": "maria@example.com",
            "phone": "",
            "location": "Афины",
        },
        "Медсестра в городской больнице.",
        [
            {
                "employer": "Больница Надежда",
                "title": "Медсестра",
                "location": "Афины",
                "start": "2018",
                "end": "2024",
                "bullets": ["Вела 4 пациента в смену."],
            }
        ],
        [
            {
                "institution": "Медицинский колледж",
                "degree": "Диплом",
                "field": "Сестринское дело",
                "start": "2014",
                "end": "2018",
            }
        ],
        [{"name": "Перевязка", "evidence": "Делала перевязку в отделении."}],
        [{"name": "Русский", "level": "C2"}],
        {
            "title": "Инженер",
            "company": "Яндекс",
            "location": "Athens, Greece",
            "description": "Инженер в команде поддержки.",
            "languages": "",
        },
    )
    return {
        "nurse_nl": (nurse, nurse_job),
        "warehouse_pl": (warehouse, warehouse_job),
        "graduate_es": (graduate, graduate_job),
        "engineer_us": (engineer, engineer_job),
        "accountant_ca": (accountant, accountant_job),
        "cyrillic": (cyrillic, cyrillic_job),
    }


def _capitalised(text: str) -> set[str]:
    found = set()
    for word in _CAPITAL.findall(text):
        if word[:1].isupper():
            found.add(word.casefold())
    return found


def _preset_text(preset) -> str:
    parts = [preset.present_label, preset.references_line, preset.consent_line, _FIXED_LABELS]
    for titles in preset.section_titles.values():
        parts.extend(str(value) for value in titles.values())
    for labels in preset.field_labels.values():
        parts.extend(str(value) for value in labels.values())
    return "\n".join(part for part in parts if part)


def _skill_names(markdown: str, preset) -> set[str]:
    title = section_title(preset, "skills")
    names = set()
    in_section = False
    for line in markdown.splitlines():
        if line.startswith("## "):
            in_section = line[3:].strip() == title
            continue
        if in_section and line.startswith("- "):
            names.add(line[2:].split(" — ")[0].strip().casefold())
    return names


def _assert_no_invention(markdown: str, profile, job: dict, preset) -> None:
    corpus = "\n".join(
        [
            profile_text(profile),
            "\n".join(str(value) for value in job.values()),
            _preset_text(preset),
        ]
    )
    invented_numbers = set(re.findall(r"\d+", markdown)) - set(re.findall(r"\d+", corpus))
    assert invented_numbers == set()
    allowed = _capitalised(corpus)
    for word in _capitalised(markdown):
        assert word in allowed, word
    for month in _MONTH_NAMES:
        if re.search(rf"\b{month}\b", markdown):
            assert re.search(rf"\b{month}\b", corpus)
    profile_skills = {item.name.casefold() for item in profile.skills}
    assert _skill_names(markdown, preset) <= profile_skills
    assert profile.full_name in markdown


def _write_jobs(tmp_path: Path, job: dict) -> Path:
    row = {
        "title": job["title"],
        "company": job["company"],
        "location": job["location"],
        "description": job.get("description", ""),
        "languages": job.get("languages", ""),
        "url": "https://example.com/jobs/one",
        "is_remote": job.get("is_remote", "No"),
        "place_searched": job.get("place_searched", ""),
    }
    path = tmp_path / "jobs.csv"
    write_outputs([row], path, tmp_path / "jobs.xlsx")
    return path


def _nz_yaml() -> str:
    return """
id: nz_cv
page_size: a4
max_pages: 2
photo: optional
countries:
  - new zealand
date_format: yyyy-mm
present_label: Present
chronology: reverse
language: mi
section_order:
  - contact
  - summary
  - experience
  - education
  - skills
section_titles:
  mi:
    contact: Contact
    summary: Summary
    experience: Kupu
    education: Education
  en:
    contact: Contact
    summary: Summary
    experience: Experience
    education: Education
    skills: Skills
field_labels:
  en:
    date_of_birth: Date of birth
review_notes:
  - "Double-check: this fixture preset exists only to prove a new file is discovered."
"""


@pytest.mark.parametrize("fmt", PRESETS)
@pytest.mark.parametrize("who", list(_people()))
def test_every_preset_and_profile_stays_inside_the_facts(tmp_path, fmt, who):
    raw, job = _people()[who]
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    profile = load_profile(path)
    preset = load_preset(fmt)
    markdown = render_markdown(tailor(profile, job, preset))
    _assert_no_invention(markdown, profile, job, preset)
    if who == "graduate_es":
        assert profile.experience == ()
        assert "Universidad Complutense" in markdown


def test_new_presets_follow_local_conventions():
    nl = load_preset("nl_cv")
    es = load_preset("es_cv")
    pl = load_preset("pl_cv")
    ca = load_preset("ca_resume")
    assert nl.page_size == "a4"
    assert nl.photo == "optional"
    assert es.page_size == "a4"
    assert es.photo == "customary"
    assert pl.page_size == "a4"
    assert pl.photo == "optional"
    assert pl.consent_line == PL_CONSENT
    assert "consent" in pl.section_order
    assert ca.page_size == "letter"
    assert ca.photo == "forbidden"
    assert ca.personal_fields == ()
    assert section_title(nl, "experience") == "Werkervaring"
    assert section_title(es, "experience") == "Experiencia profesional"
    assert section_title(pl, "experience") == "Doświadczenie zawodowe"
    assert section_title(ca, "experience") == "Experience"
    for preset in (nl, es, pl, ca):
        assert "experience" in preset.section_titles["en"]


def test_ca_resume_drops_photo_and_date_of_birth(tmp_path):
    photo = tmp_path / "face.png"
    photo.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?"
        b"\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    raw, job = _people()["accountant_ca"]
    raw["photo"] = {"path": str(photo), "include": True}
    raw["personal"]["date_of_birth"] = "1986-02-02"
    raw["personal"]["nationality"] = "Canadian"
    raw["personal"]["marital_status"] = "married"
    profile = profile_from_mapping(raw)
    preset = load_preset("ca_resume")
    document = tailor(profile, job, preset)
    markdown = render_markdown(document)
    docx = Document(render_docx(document, tmp_path / "ca.docx"))
    assert "1986" not in markdown
    assert "Feb" not in markdown
    assert "Canadian" not in markdown
    assert "married" not in markdown
    assert "face.png" not in markdown
    assert len(docx.inline_shapes) == 0
    assert docx.sections[0].page_width == Inches(8.5)


def test_pl_cv_consent_line_is_opt_in_only(tmp_path):
    raw, job = _people()["warehouse_pl"]
    opted_out = profile_from_mapping(raw)
    hidden = render_markdown(tailor(opted_out, job, load_preset("pl_cv")))
    assert PL_CONSENT not in hidden
    assert "2016/679" not in hidden
    raw["gdpr_consent"] = True
    shown = render_markdown(tailor(profile_from_mapping(raw), job, load_preset("pl_cv")))
    assert PL_CONSENT in shown
    us = render_markdown(tailor(profile_from_mapping(raw), job, load_preset("us_resume")))
    assert PL_CONSENT not in us


def test_non_latin_filenames_are_valid_and_readable(tmp_path):
    cases = (
        ("Яндекс", "Инженер"),
        ("Εταιρεία Βήτα", "Λογιστής"),
    )
    for company, role in cases:
        stem = output_filename(company, role, date(2026, 11, 3))
        assert stem.startswith("CV_")
        assert stem.endswith("_2026-11-03")
        assert "/" not in stem and "\\" not in stem and "\0" not in stem
        assert company.split()[0] in stem
        assert role.split()[0] in stem
        path = tmp_path / f"{stem}.md"
        path.write_text("ok\n", encoding="utf-8")
        assert path.read_text(encoding="utf-8") == "ok\n"

    raw, job = _people()["cyrillic"]
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    jobs = _write_jobs(tmp_path, job)
    out = tmp_path / "cv"
    code = run_cv("1", "eu_europass", jobs, profile_path, out, today=date(2026, 11, 3))
    assert code == 0
    written = list(out.glob("CV_*_2026-11-03.md"))
    assert len(written) == 1
    assert "Яндекс" in written[0].name
    assert "Инженер" in written[0].name
    assert "Мария Иванова" in written[0].read_text(encoding="utf-8")


def test_interview_with_no_work_experience_writes_only_typed_facts(tmp_path):
    from cv.interview import run_interview

    path = tmp_path / "cv_profile.yaml"
    ask, remaining, prompts = _script(_no_work_pairs())
    lines = []
    code = run_interview(ask, lines.append, path)
    assert code == 0
    assert remaining == []
    blob = "\n".join(prompts + lines)
    for banned in ("Mina", "Harbor", "Ada Lovelace", "e.g.", "for example"):
        assert banned.casefold() not in blob.casefold()
    text = path.read_text(encoding="utf-8")
    assert "no work experience yet" not in text.casefold()
    assert "Harbor" not in text
    profile = load_profile(path)
    assert profile.full_name == "Lucía Navarro"
    assert profile.email == "lucia@example.com"
    assert profile.location == "Madrid"
    assert profile.summary == "Recent graduate who wants a first marketing role."
    assert profile.experience == ()
    assert profile.education[0].institution == "Universidad Complutense"
    assert profile.education[0].degree == "Grado"
    assert profile.education[0].field == "Marketing"
    assert profile.education[0].start == "2021"
    assert profile.education[0].end == "2025"
    assert profile.skills[0].name == "Canva"
    assert profile.skills[0].evidence == "Designed three posters for a student fair."
    levels = {item.name: item.level for item in profile.languages}
    assert levels == {"Spanish": "C2", "English": "B2"}
    assert profile.personal.date_of_birth == ""
    assert profile.personal.include is False
    assert profile.photo_opt_in is False
    assert profile.gdpr_consent is False
    job = {
        "title": "Marketing assistant",
        "company": "Feria Norte",
        "location": "Madrid, Spain",
        "description": "Marketing graduate programme.",
        "languages": "Spanish",
        "is_remote": "No",
    }
    jobs = _write_jobs(tmp_path, job)
    out = tmp_path / "cv"
    assert run_cv("1", "es_cv", jobs, path, out, today=date(2026, 11, 3)) == 0
    markdown = (out / "CV_Feria_Norte_Marketing_assistant_2026-11-03.md").read_text(encoding="utf-8")
    assert "Lucía Navarro" in markdown
    assert "Universidad Complutense" in markdown
    assert "Canva" in markdown
    assert "no work experience" not in markdown.casefold()


def test_interview_skip_all_optional_sections_still_makes_a_cv(tmp_path):
    from cv.interview import run_interview

    path = tmp_path / "cv_profile.yaml"
    ask, remaining, prompts = _script(_skip_pairs())
    code = run_interview(ask, lambda _line: None, path)
    assert code == 0
    assert remaining == []
    assert "skip" not in prompts[0].casefold()
    assert "skip" not in prompts[1].casefold()
    assert all("skip" in prompt.casefold() for prompt in prompts[2:])
    profile = load_profile(path)
    assert profile.full_name == "Sam Lee"
    assert profile.summary == ""
    assert profile.experience == ()
    assert profile.education == ()
    assert profile.skills == ()
    assert profile.languages == ()
    assert profile.certifications == ()
    assert profile.links == ()
    job = {
        "title": "Assistant",
        "company": "Northwind",
        "location": "Austin, USA",
        "description": "General assistant.",
        "languages": "",
    }
    out = tmp_path / "cv"
    assert (
        run_cv(
            "1",
            "us_resume",
            _write_jobs(tmp_path, job),
            path,
            out,
            today=date(2026, 11, 3),
        )
        == 0
    )
    markdown = (out / "CV_Northwind_Assistant_2026-11-03.md").read_text(encoding="utf-8")
    assert "Sam Lee" in markdown
    assert "Experience" not in markdown


def test_interview_does_not_overwrite_without_confirmation(tmp_path):
    from cv.interview import run_interview

    path = tmp_path / "cv_profile.yaml"
    original = "contact:\n  full_name: Keep Me\n"
    path.write_text(original, encoding="utf-8")
    ask, remaining, _prompts = _script([("overwrite", "n")])
    code = run_interview(ask, lambda _line: None, path)
    assert code == 0
    assert remaining == []
    assert path.read_text(encoding="utf-8") == original

    ask, remaining, _prompts = _script([("overwrite", "")])
    run_interview(ask, lambda _line: None, path)
    assert remaining == []
    assert path.read_text(encoding="utf-8") == original

    ask, remaining, _prompts = _script([("overwrite", "y"), *_skip_pairs("New Person")])
    assert run_interview(ask, lambda _line: None, path) == 0
    assert remaining == []
    assert load_profile(path).full_name == "New Person"


def test_cv_interview_flag_writes_the_profile(tmp_path, monkeypatch):
    path = tmp_path / "cv_profile.yaml"
    answers = iter(answer for _needle, answer in _skip_pairs("Sam Lee"))
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    code = main(["--cv-interview", "--profile", str(path)])
    assert code == 0
    assert load_profile(path).full_name == "Sam Lee"


def test_menu_offers_the_interview_and_launchers_name_it(tmp_path):
    phrase = "I don't have a CV yet - help me make one"
    assert INTERVIEW_MENU_LABEL == phrase
    for name in ("start.sh", "start.bat", "start.command"):
        assert phrase in (ROOT / name).read_text(encoding="utf-8")

    missing = tmp_path / "missing.yaml"
    lines = []
    ask, remaining, _prompts = _script([(">", "2"), ("question", "n")])
    code = run_launcher_menu(
        ask,
        lines.append,
        tmp_path / "jobs.csv",
        missing,
        tmp_path / "cv",
        lambda: 0,
    )
    assert code == 1
    assert remaining == []
    assert phrase in "\n".join(lines)
    assert not missing.exists()

    ask, remaining, _prompts = _script([(">", "3"), *_skip_pairs("Menu Person")])
    code = run_launcher_menu(
        ask,
        lines.append,
        tmp_path / "jobs.csv",
        missing,
        tmp_path / "cv",
        lambda: 0,
    )
    assert code == 0
    assert remaining == []
    assert load_profile(missing).full_name == "Menu Person"


def test_make_a_cv_without_a_profile_offers_the_interview_then_continues(tmp_path):
    path = tmp_path / "cv_profile.yaml"
    lines = []
    ask, remaining, _prompts = _script(
        [(">", "2"), ("question", ""), *_skip_pairs("First CV")]
    )
    code = run_launcher_menu(
        ask,
        lines.append,
        tmp_path / "no-jobs.csv",
        path,
        tmp_path / "cv",
        lambda: 0,
    )
    assert code == 1
    assert remaining == []
    assert load_profile(path).full_name == "First CV"
    assert "jobs" in "\n".join(lines).casefold()


def test_format_help_and_errors_list_presets_from_disk(tmp_path, capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    for name in PRESETS:
        assert name in help_text
    assert "choices=" not in (ROOT / "scrape.py").read_text(encoding="utf-8")

    profile = tmp_path / "profile.yaml"
    raw, job = _people()["nurse_nl"]
    profile.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    jobs = _write_jobs(tmp_path, job)
    code = main(
        [
            "--cv",
            "1",
            "--format",
            "not_a_real_format",
            "--jobs",
            str(jobs),
            "--profile",
            str(profile),
            "--cv-dir",
            str(tmp_path / "cv"),
        ]
    )
    assert code == 1
    message = capsys.readouterr().out
    assert "not_a_real_format" in message
    for name in list_presets():
        assert name in message


def test_dropped_preset_yaml_is_discovered_without_code_changes(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "presets"
    folder.mkdir()
    (folder / "nz_cv.yaml").write_text(_nz_yaml(), encoding="utf-8")
    monkeypatch.setattr("cv.presets.presets_dir", lambda: folder)
    assert list_presets() == ["nz_cv"]
    preset = load_preset("nz_cv")
    assert preset.id == "nz_cv"
    assert section_title(preset, "experience") == "Kupu"
    assert section_title(preset, "skills") == "Skills"
    raw, job = _people()["engineer_us"]
    job = dict(job)
    job["location"] = "Wellington, New Zealand"
    profile = profile_from_mapping(raw)
    markdown = render_markdown(tailor(profile, job, preset))
    assert "Kupu" in markdown
    assert "Python" in markdown
    assert suggest_format(job) == "nz_cv"
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0
    assert "nz_cv" in capsys.readouterr().out
    try:
        load_preset("missing")
    except ValueError as exc:
        assert "nz_cv" in str(exc)
    else:
        raise AssertionError("missing preset should fail")


@pytest.mark.parametrize(
    ("location", "place", "remote", "expected"),
    [
        ("Amsterdam, Netherlands", "", "No", "nl_cv"),
        ("Rotterdam, Holland", "", "No", "nl_cv"),
        ("Amsterdam, The Netherlands", "", "No", "nl_cv"),
        ("Kraków, Poland", "", "No", "pl_cv"),
        ("Madrid, Spain", "", "No", "es_cv"),
        ("Madrid, España", "", "No", "es_cv"),
        ("Austin, USA", "", "No", "us_resume"),
        ("Austin, United States", "", "No", "us_resume"),
        ("Toronto, Canada", "", "No", "ca_resume"),
        ("Berlin, Germany", "", "No", "de_lebenslauf"),
        ("London, United Kingdom", "", "No", "uk_cv"),
        ("Milan, Italy", "", "No", "it_cv"),
        ("Lyon, France", "", "No", "fr_cv"),
        ("Remote, Europe", "", "Yes", "eu_europass"),
        ("Remote, EU", "", "Yes", "eu_europass"),
        ("Remote - North America", "", "Yes", "us_resume"),
        ("Vienna, Austria", "", "No", "eu_europass"),
        ("Tokyo, Japan", "", "No", "us_resume"),
        ("Mexico City, Mexico", "", "No", "us_resume"),
        ("Remote", "Worldwide", "Yes", "us_resume"),
        ("Remote", "Berlin, Germany", "Yes", "de_lebenslauf"),
        ("Atlantis", "", "No", "us_resume"),
    ],
)
def test_auto_suggest_uses_the_job_country(location, place, remote, expected):
    assert (
        suggest_format(
            {
                "location": location,
                "place_searched": place,
                "is_remote": remote,
            }
        )
        == expected
    )


def test_format_flag_overrides_suggestion_and_enter_accepts_it(tmp_path):
    raw, job = _people()["nurse_nl"]
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    jobs = _write_jobs(tmp_path, job)
    out = tmp_path / "forced"
    code = main(
        [
            "--cv",
            "1",
            "--format",
            "us_resume",
            "--jobs",
            str(jobs),
            "--profile",
            str(profile),
            "--cv-dir",
            str(out),
            "--cv-date",
            "2026-11-03",
        ]
    )
    assert code == 0
    forced = (out / "CV_Amsterdam_UMC_Nurse_2026-11-03.md").read_text(encoding="utf-8")
    assert "## Experience" in forced
    assert "Werkervaring" not in forced

    suggested = tmp_path / "suggested"
    code = main(
        [
            "--cv",
            "1",
            "--jobs",
            str(jobs),
            "--profile",
            str(profile),
            "--cv-dir",
            str(suggested),
            "--cv-date",
            "2026-11-03",
        ]
    )
    assert code == 0
    body = (suggested / "CV_Amsterdam_UMC_Nurse_2026-11-03.md").read_text(encoding="utf-8")
    assert "Werkervaring" in body

    lines = []
    ask, remaining, _prompts = _script([(">", "2"), ("row", "1"), ("format", "")])
    code = run_launcher_menu(
        ask,
        lines.append,
        jobs,
        profile,
        tmp_path / "menu-cv",
        lambda: 0,
        today=date(2026, 11, 3),
    )
    assert code == 0
    assert remaining == []
    shown = "\n".join(lines)
    assert "nl_cv" in shown
    menu_body = (tmp_path / "menu-cv" / "CV_Amsterdam_UMC_Nurse_2026-11-03.md").read_text(
        encoding="utf-8"
    )
    assert "Werkervaring" in menu_body
