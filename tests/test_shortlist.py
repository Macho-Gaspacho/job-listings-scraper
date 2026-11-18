"""The shortlist stage. No network."""

from openpyxl import load_workbook

from scrape import _run_search
from shortlist import (
    description_from_html,
    fetch_linkedin_description,
    load_rules,
    read_jobs,
    required_years,
    run_shortlist,
    score_row,
    title_drop_reason,
)


ENGLISH = (
    "We are looking for a product manager to own the roadmap, talk to customers, "
    "and work with engineers on a digital product for small businesses."
)
GERMAN = (
    "Wir suchen einen Produktmanager mit mehrjahriger Berufserfahrung in der "
    "Entwicklung digitaler Produkte fur unsere Kunden in Deutschland und der Schweiz."
)


def _row(**overrides):
    base = {
        "title": "Product Manager",
        "company": "ACME",
        "location": "Amsterdam, Netherlands",
        "date_posted": "2026-11-01",
        "source": "indeed",
        "url": "https://example.com/jobs/1",
        "description": ENGLISH,
        "role_searched": "Product Manager",
        "place_searched": "Amsterdam, Netherlands",
        "job_type": "Full-time",
    }
    base.update(overrides)
    return base


def test_required_years_ignores_company_history_and_reads_ranges():
    samples = {
        "8 years of experience in product": 8,
        "7 + years' experience deliver": 7,
        "al menos 3 años de experiencia": 3,
        "+10 ans d'expérience": 10,
        "2-3 years of experience": 2,
        "1-2 years of experience": 1,
        "family business for almost 65 jaar merken wereldwijd": None,
        "For over 20 years, we’ve been the backbone": None,
        "mindestens 3 Jahre Berufserfahrung": 3,
        "minimaal 2 jaar ervaring": 2,
        "almeno 10 anni di esperienza in ambito Digital Product Management": 10,
    }
    for text, expect in samples.items():
        assert required_years(text) == expect, text


def test_title_filter_drops_senior_and_intern_but_not_internal():
    rules = load_rules()
    assert title_drop_reason(_row(title="Senior Product Manager"), rules)
    assert title_drop_reason(_row(title="Staff Product Manager"), rules)
    assert title_drop_reason(_row(title="Intern PRODUCT MANAGER"), rules)
    assert title_drop_reason(_row(title="Lead Technology Product manager"), rules)
    assert title_drop_reason(_row(title="Stage Product Manager"), rules)
    assert title_drop_reason(_row(title="Product Manager", job_type="Internship"), rules) is not None
    assert title_drop_reason(_row(title="International Product Manager"), rules) is None
    assert title_drop_reason(_row(title="(Junior) Product Manager"), rules) is None
    assert title_drop_reason(_row(title="Product stage manager"), rules) is None


def test_searching_for_a_senior_role_keeps_senior_titles(tmp_path):
    rules = load_rules()
    result = run_shortlist(
        [_row(title="Senior Designer", role_searched="Senior Designer", description=ENGLISH)],
        rules,
        roles=["Senior Designer"],
        skip_fetch=True,
        pause_seconds=0,
        output_path=tmp_path / "shortlist.xlsx",
        funnel_json=tmp_path / "funnel.json",
        funnel_log=tmp_path / "funnel.log",
    )
    assert result["funnel"][1]["count"] == 1
    assert result["top"][0]["title"] == "Senior Designer"


def test_missing_years_are_not_described_as_junior():
    rules = load_rules()
    _score, reason = score_row(_row(description=ENGLISH + " We did not state a number."), rules)
    lowered = reason.casefold()
    assert "seniority not stated" in lowered
    assert "years requirement not stated" in lowered
    assert "junior" not in lowered
    assert "no 3" not in lowered
    junior_score, junior_reason = score_row(
        _row(title="Junior Product Manager", description=ENGLISH),
        rules,
    )
    plain_score, _plain_reason = score_row(_row(description=ENGLISH), rules)
    assert junior_score > plain_score
    assert "junior" in junior_reason.casefold()


def test_two_stated_years_count_as_evidence():
    rules = load_rules()
    _score, reason = score_row(
        _row(description=ENGLISH + " You have 2 years of experience in product management."),
        rules,
    )
    assert "asks for 2 years" in reason.casefold()
    assert "no 3" not in reason.casefold()


def test_twin_description_supplies_the_years_the_snippet_missed(tmp_path):
    rules = load_rules({"allowed_languages": ["en"]})
    snippet = "Localita: Rozzano. Humanitas is hiring a Digital Product Manager to join the digital team."
    full = (
        (ENGLISH + " ") * 3
        + "The candidate needs at least 10 years of experience in product management."
    )
    rows = [
        _row(
            title="Digital Product Manager",
            company="Humanitas",
            source="indeed",
            location="Rozzano, LOM, Italy",
            place_searched="Milan, Italy",
            description=snippet,
            url="https://it.indeed.com/viewjob?jk=1",
        ),
        _row(
            title="Digital Product Manager",
            company="Humanitas",
            source="linkedin",
            location="Assago, Lombardy, Italy",
            place_searched="Milan, Italy",
            description=full,
            url="https://www.linkedin.com/jobs/view/4490436420",
        ),
    ]
    result = run_shortlist(rows, rules, skip_fetch=True, pause_seconds=0, output_path=tmp_path / "out.xlsx")
    assert result["funnel"][0]["count"] == 2
    assert result["funnel"][3]["count"] == 0
    assert result["drop_reasons"]["experience"]
    reason = next(iter(result["drop_reasons"]["experience"]))
    assert "10" in reason
    assert "linkedin" in reason.casefold()


def test_short_snippet_without_a_twin_stays_and_does_not_claim_junior(tmp_path):
    rules = load_rules()
    result = run_shortlist(
        [_row(description="Insify is hiring a product manager for insurance.", source="indeed")],
        rules,
        skip_fetch=True,
        pause_seconds=0,
        output_path=tmp_path / "out.xlsx",
    )
    assert result["funnel"][-1]["count"] == 1
    reason = result["top"][0]["reason"].casefold()
    assert "short snippet" in reason
    assert "junior" not in reason
    assert "no 3" not in reason
    assert "seniority not stated" in reason


def test_language_filter_drops_german_and_can_be_left_off():
    german = _row(title="Product Manager", description=GERMAN, location="Berlin, Germany")
    limited = run_shortlist([german], load_rules({"allowed_languages": ["en", "it"]}), skip_fetch=True, pause_seconds=0)
    assert limited["funnel"][4]["count"] == 0
    assert any("german" in reason.casefold() for reason in limited["drop_reasons"]["language"])
    open_rules = run_shortlist([german], load_rules(), skip_fetch=True, pause_seconds=0)
    assert open_rules["funnel"][4]["count"] == 1


def test_top_n_workbook_has_the_three_sheets_and_a_reason(tmp_path):
    rules = load_rules({"top_n": 1})
    rows = [
        _row(title="Product Manager", company="One", url="https://example.com/1"),
        _row(title="Product Manager", company="Two", url="https://example.com/2", description=ENGLISH + " Associate product work."),
    ]
    workbook = tmp_path / "shortlist.xlsx"
    run_shortlist(
        rows,
        rules,
        output_path=workbook,
        funnel_json=tmp_path / "shortlist-funnel.json",
        funnel_log=tmp_path / "shortlist-funnel.log",
        skip_fetch=True,
        pause_seconds=0,
    )
    book = load_workbook(workbook)
    assert book.sheetnames == ["Funnel", "Ranked", "Top-N"]
    assert book.active.title == "Top-N"
    assert book["Top-N"].max_row == 2
    assert book["Ranked"].max_row == 3
    assert book["Top-N"]["C2"].value
    assert "Starting listings: 2" in (tmp_path / "shortlist-funnel.log").read_text(encoding="utf-8")
    saved = (tmp_path / "shortlist-funnel.json").read_text(encoding="utf-8")
    assert '"stage": "Top-N"' in saved


def test_cache_is_used_and_the_fetcher_is_not_called(tmp_path):
    rules = load_rules()
    cache = tmp_path / "cache.json"
    url = "https://www.linkedin.com/jobs/view/4490436420"
    cache.write_text(
        '{"%s": "%s"}' % (url, ENGLISH + " You need at least 8 years of experience."),
        encoding="utf-8",
    )

    def explode(_url):
        raise AssertionError("network")

    result = run_shortlist(
        [_row(source="linkedin", url=url, description="")],
        rules,
        cache_path=cache,
        get=explode,
        skip_fetch=False,
        pause_seconds=0,
    )
    assert result["funnel"][3]["count"] == 0
    assert result["meta"]["Descriptions fetched this run"] == 0


def test_description_fetch_retries_429_and_stops_on_403():
    html = (
        '<div class="show-more-less-html__markup">'
        "<p>At least 4 years of experience in product management.</p></div>"
    )
    calls = {"n": 0}
    sleeps = []

    def get(_url):
        calls["n"] += 1
        if calls["n"] == 1:
            return 429, ""
        return 200, html

    text = fetch_linkedin_description(
        "https://www.linkedin.com/jobs/view/123",
        get,
        sleeps.append,
        attempts=3,
        pause=2,
    )
    assert "4 years" in text
    assert calls["n"] == 2
    assert sleeps == [2]

    blocked = {"n": 0}

    def refuse(_url):
        blocked["n"] += 1
        return 403, ""

    assert fetch_linkedin_description("https://www.linkedin.com/jobs/view/9", refuse, sleeps.append) == ""
    assert blocked["n"] == 1


def test_html_parser_reads_the_public_description_block():
    html = (
        '<div class="show-more-less-html__markup">'
        "<p>At least 5 years of experience.</p></div>"
    )
    assert "5 years" in description_from_html(html)


def test_excluded_company_and_country_are_removed():
    rules = load_rules({"exclude_companies": ["Contoso"], "exclude_countries": ["russia"]})
    result = run_shortlist(
        [
            _row(company="Contoso BV", url="https://example.com/a"),
            _row(location="Moscow, Russia", place_searched="Moscow", url="https://example.com/b"),
            _row(url="https://example.com/c"),
        ],
        rules,
        skip_fetch=True,
        pause_seconds=0,
    )
    assert result["funnel"][-1]["count"] == 1
    assert result["top"][0]["url"] == "https://example.com/c"


def test_defaults_are_on_without_a_config_block(tmp_path):
    rules = load_rules()
    assert rules.enabled is True
    assert rules.top_n == 40
    assert rules.max_required_years == 3
    assert rules.allowed_languages == ()
    assert "senior" in rules.title_exclude
    tuned = load_rules({"top_n": 10, "enabled": False})
    assert tuned.top_n == 10
    assert tuned.enabled is False
    assert "senior" in tuned.title_exclude
    path = tmp_path / "jobs.csv"
    path.write_text(
        "Title,Company,Location,Date posted,Source,URL,Description,Role searched,Place searched\n"
        "Product Manager,ACME,\"Amsterdam, Netherlands\",2026-11-01,indeed,https://example.com/j,"
        "\"A product manager role with customers and a roadmap.\",Product Manager,\"Amsterdam, Netherlands\"\n",
        encoding="utf-8",
    )
    rows = read_jobs(path)
    assert rows[0]["title"] == "Product Manager"
    assert rows[0]["company"] == "ACME"


def test_same_city_with_two_spellings_is_one_row():
    rules = load_rules()
    short = "Zucchetti is hiring a project manager in Rome for a digital team."
    full = (ENGLISH + " ") * 3 + "This project manager role is based in Rome."
    result = run_shortlist(
        [
            _row(
                title="Project Manager",
                company="Zucchetti",
                source="indeed",
                location="Roma, LAZ, Italy",
                place_searched="Rome, Italy",
                description=short,
                url="https://example.com/indeed",
                role_searched="Project Manager",
            ),
            _row(
                title="Project Manager",
                company="Zucchetti",
                source="linkedin",
                location="Rome, Latium, Italy",
                place_searched="Rome, Italy",
                description=full,
                url="https://www.linkedin.com/jobs/view/1",
                role_searched="Project Manager",
            ),
        ],
        rules,
        skip_fetch=True,
        pause_seconds=0,
    )
    assert result["meta"]["Duplicate rows combined"] == 1
    assert result["funnel"][-1]["count"] == 1
    assert result["top"][0]["url"].endswith("/1")
    assert result["top"][0]["location"] == "Rome, Latium, Italy"


def test_milan_and_milano_collapse_but_rome_and_milan_do_not():
    rules = load_rules()
    text = ENGLISH
    result = run_shortlist(
        [
            _row(title="Product Manager", company="ACME", location="Milano, Lombardy, Italy", url="https://example.com/a", description=text),
            _row(title="Product Manager", company="ACME", location="Milan, Italy", url="https://example.com/b", description=text + " Extra detail about the team."),
            _row(title="Product Manager", company="ACME", location="Rome, Italy", url="https://example.com/c", description=text),
        ],
        rules,
        skip_fetch=True,
        pause_seconds=0,
    )
    urls = {item["url"] for item in result["top"]}
    assert "https://example.com/c" in urls
    assert len(result["top"]) == 2
    assert result["meta"]["Duplicate rows combined"] == 1


def test_unlisted_language_lowers_the_score_without_dropping_the_row():
    rules = load_rules()
    german = _row(title="Product Manager", company="Caya", location="Berlin, Germany", description=GERMAN, url="https://example.com/de")
    english = _row(description=ENGLISH, url="https://example.com/en")
    plain = run_shortlist([german, english], rules, skip_fetch=True, pause_seconds=0)
    marked = run_shortlist(
        [german, english],
        rules,
        spoken_languages=("English",),
        skip_fetch=True,
        pause_seconds=0,
    )
    assert plain["funnel"][4]["count"] == 2
    assert marked["funnel"][4]["count"] == 2
    german_row = next(item for item in marked["top"] if item["url"].endswith("/de"))
    english_row = next(item for item in marked["top"] if item["url"].endswith("/en"))
    assert german_row["score"] < english_row["score"]
    assert "did not list" in german_row["reason"].casefold()
    assert "german" in german_row["reason"].casefold()
    assert "did not list" not in english_row["reason"].casefold()


def test_skipped_language_question_matches_a_run_with_no_languages():
    rules = load_rules()
    row = _row(description=GERMAN, location="Berlin, Germany", company="Caya")
    alone = score_row(dict(row), rules)
    answered = run_shortlist([row], rules, spoken_languages=None, skip_fetch=True, pause_seconds=0)
    assert answered["top"][0]["score"] == alone[0]
    assert "did not list" not in answered["top"][0]["reason"].casefold()


def test_strict_mode_drops_a_language_the_person_did_not_list():
    rules = load_rules()
    result = run_shortlist(
        [
            _row(description=GERMAN, location="Berlin, Germany", company="Caya", url="https://example.com/de"),
            _row(description=ENGLISH, url="https://example.com/en"),
        ],
        rules,
        spoken_languages=("English", "Italian"),
        strict_fit=True,
        skip_fetch=True,
        pause_seconds=0,
    )
    assert result["funnel"][4]["count"] == 1
    assert result["top"][0]["url"].endswith("/en")
    assert any("did not list" in reason.casefold() for reason in result["drop_reasons"]["language"])


def test_equal_scores_put_a_fuller_newer_posting_first():
    rules = load_rules({"top_n": 2})
    older = _row(
        title="Designer",
        company="Older",
        role_searched="Designer",
        description=(ENGLISH + " ") * 3,
        date_posted="2026-11-01",
        url="https://example.com/old",
        source="indeed",
    )
    newer = _row(
        title="Designer",
        company="Newer",
        role_searched="Designer",
        description="Draw things.",
        date_posted="2026-11-18",
        url="https://example.com/new",
        source="indeed",
    )
    # The short text is a snippet, so the fuller posting ranks first even though it is older.
    result = run_shortlist([newer, older], rules, skip_fetch=True, pause_seconds=0)
    assert result["top"][0]["score"] == result["top"][1]["score"]
    assert result["top"][0]["url"].endswith("/old")
    same_day = run_shortlist(
        [
            _row(title="Designer", company="A", role_searched="Designer", description=ENGLISH, date_posted="2026-11-02", url="https://example.com/a"),
            _row(title="Designer", company="B", role_searched="Designer", description=ENGLISH + " More about the team and the work.", date_posted="2026-11-02", url="https://example.com/b"),
        ],
        rules,
        skip_fetch=True,
        pause_seconds=0,
    )
    assert same_day["top"][0]["url"].endswith("/b")


def test_search_writes_the_shortlist_without_a_network_call(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
roles: [Designer]
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
sources:
  - id: indeed
    enabled: true
    kind: aggregator
country: germany
""",
        encoding="utf-8",
    )

    def explode(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("shortlist.default_get", explode)

    def fetch(_role, _place, _site):
        return [
            _row(
                title="Designer",
                role_searched="Designer",
                description="Draw things for a team.",
                source="indeed",
                location="Berlin, Germany",
                place_searched="Berlin, Germany",
            )
        ]

    code = _run_search(config, fetch=fetch, getter=fetch)
    assert code == 0
    workbook = load_workbook(tmp_path / "output" / "shortlist.xlsx")
    assert "Top-N" in workbook.sheetnames
    assert workbook["Top-N"]["C2"].value
