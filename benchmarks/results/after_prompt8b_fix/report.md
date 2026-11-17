# Prompt 8b-fix

Curated employers now follow the same title rule as the whole-board feeds. A company the user typed is unchanged. On those strict sources, a synonym counts only when it has at least two words longer than two letters.

`financial analyst` is not a synonym of `investment banking analyst`. That title is dropped on a curated page. It is kept only when the keyword list itself contains the two-word phrase `financial analyst`.

The 356 Paris rows were not limited to titles containing "analyst". This role is not in `synonyms/roles.yaml`, so `require_title_match` stays off and curated pages were keeping every title. The role rule removes them. A one-word synonym such as `analyst` is also ignored if it is added later.

## Single-word synonyms ignored for the nine roles

These catalog phrases have fewer than two words longer than two letters. The rule ignores them on curated pages and on whole-board feeds. Indeed, LinkedIn, and a company the user typed still use them.

| role | ignored synonyms |
| --- | --- |
| data analyst | datenanalyst (de) |
| software engineer | sviluppatore (it), softwareentwickler (de), développeur (fr), softwareontwikkelaar (nl), programista (pl) |
| product manager | produktmanager (de), productmanager (nl) |
| risk manager | none (no catalog entry) |
| strategy consultant | none (no catalog entry) |
| investment banking analyst | none (no catalog entry) |
| data scientist | datenwissenschaftler (de) |
| project manager | projektmanager (de), projectmanager (nl) |
| менеджер проектов | none (no catalog entry) |

Of the nine benchmark configs, only the Berlin software-engineer search attaches one of these: `softwareentwickler`. The others load a different language, or no list.

## Before (`after_prompt8b`) vs after (`after_prompt8b_fix`)

| query | before total | after total | before relevant | after relevant | before wrong_country | after wrong_country | before company % | after company % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q1_data_analyst_amsterdam | 30 | 29 | 14/20 | 14/20 | 0 | 0 | 0 | 0 |
| q2_software_engineer_berlin | 52 | 52 | 16/20 | 16/20 | 2 | 2 | 52 | 52 |
| q3_product_manager_milano_italia | 36 | 36 | 17/20 | 17/20 | 1 | 1 | 28 | 28 |
| q4_risk_manager_frankfurt | 215 | 39 | 0/20 | 7/20 | 5 | 0 | 82 | 3 |
| q5_strategy_consultant_london | 103 | 39 | 8/20 | 17/20 | 0 | 0 | 61 | 3 |
| q6_investment_banking_analyst_paris | 356 | 40 | 0/20 | 14/20 | 20 | 0 | 89 | 0 |
| q7_data_scientist_remote_eu | 19 | 19 | 11/19 | 12/19 | 8 | 7 | 0 | 0 |
| q8_project_manager_milan | 37 | 39 | 19/20 | 19/20 | 0 | 0 | 0 | 0 |
| q9_awkward_russian_title_city_only | 223 | 20 | 0/20 | 20/20 | 4 | 0 | 91 | 0 |

q4, q6, and q9 were the curated-page floods. Those pages now have to contain the typed role. q4 relevance is back to 7/20. q6 is 14/20, all Indeed and LinkedIn. q9 is the LinkedIn sample again, 20/20.

## q4, first 10 titles

1. (Senior) Credit Risk Manager (m/f/d) — Raisin careers — Berlin, Berlin, Germany; Frankfurt a. M.; Hamburg; Munich
2. Manager IT-Quality, Risk und BCM (w/m/d) — indeed — Frankfurt am Main, HE, Germany
3. Senior Credit Analyst m/w/d — indeed — Frankfurt am Main, HE, Germany
4. Manager Risikomanagement Banken (w/m/d) — linkedin — Frankfurt, Hesse, Germany
5. Manager Business Continuity & Resilience Management (w/m/d) — linkedin — Frankfurt, Hesse, Germany
6. Manager IT-Quality, Risk und BCM (w/m/d) — linkedin — Frankfurt am Main, Hesse, Germany
7. (Senior) Principal - Rewards Consulting (m/w/d) — indeed — Frankfurt am Main, HE, Germany
8. Manager Group Customer Collaboration (m/f/d) — indeed — Darmstadt, HE, Germany
9. IT-Service Continuity Manager (m/w/d) — linkedin — Eschborn, Hesse, Germany
10. Senior ICT Risk Manager (f/m/d) — linkedin — Frankfurt, Hesse, Germany

## q6, first 10 titles

1. Data Analyst (Maternity Cover / Temporary contract) — indeed — Paris, A8, France
2. Internship - 6 months - Risk Analyst F/M — indeed — Charenton-le-Pont, A8, France
3. Associate, Capital Advisory — linkedin — Paris, Île-de-France, France
4. Analyste M&A (H/F) – CDI – Paris — linkedin — Paris, Île-de-France, France
5. Analyst — indeed — Paris, A8, France
6. Internship - 6 months - Investment Banking - ETNR Industry group F/H — indeed — Paris, A8, France
7. Strategy Analyst — indeed — Paris, A8, France
8. Internship - 6 months - Analyst - Healthcare Sector F/H — indeed — Paris, A8, France
9. Investment Analyst (all genders) — linkedin — Paris, Île-de-France, France
10. Consultant Junior Modélisation Financière F/H — linkedin — La Défense, Île-de-France, France

## wrong_country on this run

No change to the metric. q4, q6, and q9 are now 0. The marks that remain from the queries that rose after 8b:

1. Senior Software Engineer (Fullstack) - Merchant EMEA — Wolt — `Berlin, Germany; Helsinki, Finland`. Multi-city. It names Berlin and also Finland, so the metric marks it.
2. Senior Software Engineer, Feature Engineering Platform — Wolt — `Berlin, Germany; Helsinki, Finland; Stockholm, Sweden; Tallinn, Estonia`. Multi-city. It names Berlin and three other countries.
3. Staff Product Manager - Loans — Qonto — `Paris, France; Berlin, Germany; Milan, Italy; Madrid, Spain; Barcelona, Spain`. Multi-city. It names Milan and other countries.

q7 (remote Europe) still has 7. There is no searched city on that query:

4. Senior Data Scientist — Morson Edge (Technology) — `London Area, UK`. The UK is outside the scorer's EU/EEA set. One place, not a second city beside a searched city.
5. Data Scientist | Machine Learning | Python, SQL — Kingo — `Sofia City, Bulgaria`. Bulgaria is in the EU, and it is missing from the scorer's EU/EEA set. One city.
6. Senior Data Scientist — Cint — `London, England, UK`. Same as the other UK row.
7. Senior Data Scientist — DuckDuckGo — `Iceland`. Iceland is in the EEA, and it is missing from that set. One country.
8. Junior Data Scientist — Ravelin Technology — `London, England, UK`. Same as the other UK rows.
9. Data Scientist (Predictive Maintenance system) — Capgemini Engineering — `Rivne, Lviv, Ukraine`. Ukraine is outside Europe-as-scored. Two Ukrainian cities, no searched city.
10. Senior Data Scientist (AI/ML/Predictive system maintenance) — Capgemini Engineering — `Rivne, Lviv, Ukraine`. Same as the row above.

## Slow tests

Before this change, `pytest -q --durations=10` took 62.6s in the sandbox. The waits were real `time.sleep` calls:

| test | seconds |
| --- | --- |
| tests/test_company_fanout.py::test_curated_cap_keeps_the_largest_boards | 29.67 |
| tests/test_benchmark.py::test_http_429_is_blocked_and_the_run_exits_zero | 9.45 |
| tests/test_benchmark.py::test_runner_does_not_touch_the_users_seen_file | 9.12 |
| tests/test_benchmark.py::test_value_error_is_recorded_and_the_run_continues | 9.11 |
| tests/test_company_fanout.py::test_blocked_and_missing_pages_are_named | 0.51 |
| tests/test_company_fanout.py::test_other_family_queries_curated_employers | 0.51 |

The cap test issued 60 Greenhouse reads on one host, and the host gap slept 0.5s between them. The three benchmark tests built a real config and then slept through that same gap, plus `pause_seconds`, while the getter returned an empty body. Those tests now pass a fake clock, and a stand-in getter no longer waits. The suite then took 4.53s (661 passed). `ruff check .` passed.
