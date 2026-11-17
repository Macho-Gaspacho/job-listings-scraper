# Prompt 8a-fix

Benchmark rerun with `SSL_CERT_FILE` unset. Arbeitnow and the remote boards answered over HTTPS.

## Why Cologne stayed and Munich did not

`classify_place` keeps a non-remote row when `matching_office` finds any office phrase. For a Frankfurt search those phrases are `Frankfurt` and `Germany`. The country name is enough, so `Cologne, North Rhine-Westphalia, Germany`, `Regensburg, Bayern, Germany`, and `Holzkirchen, Germany` all matched `Germany` and were labelled Frankfurt. A row whose location is only `Munich` matches neither phrase, so it was already dropped.

That rule is unchanged for company pages and remote boards. Arbeitnow rows now also have to name the searched city, or name the country and no city. A remote Arbeitnow row still follows the existing remote rules.

## Before (`after_prompt8a`) vs after (`after_prompt8a_fix`)

| query | before total | after total | before relevant | after relevant | before per_source | after per_source | after blocked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| q1_data_analyst_amsterdam | 30 | 30 | 14/20 | 14/20 | indeed:11, linkedin:20 | indeed:11, linkedin:20 |  |
| q2_software_engineer_berlin | 25 | 26 | 19/20 | 19/20 | arbeitnow:2, indeed:8, linkedin:15 | arbeitnow:2, indeed:9, linkedin:15 |  |
| q3_product_manager_milano_italia | 26 | 28 | 20/20 | 19/20 | indeed:7, linkedin:19 | indeed:9, linkedin:19 |  |
| q4_risk_manager_frankfurt | 65 | 38 | 0/20 | 7/20 | arbeitnow:27, indeed:18, linkedin:20 | indeed:18, linkedin:20 |  |
| q5_strategy_consultant_london | 39 | 39 | 15/20 | 15/20 | indeed:20, linkedin:20 | indeed:20, linkedin:20 |  |
| q6_investment_banking_analyst_paris | 40 | 40 | 12/20 | 14/20 | indeed:20, linkedin:20 | indeed:20, linkedin:20 |  |
| q7_data_scientist_remote_eu | 19 | 19 | 11/19 | 11/19 | linkedin:19 | linkedin:19 |  |
| q8_project_manager_milan | 38 | 38 | 19/20 | 19/20 | indeed:18, linkedin:20 | indeed:18, linkedin:20 |  |
| q9_awkward_russian_title_city_only | 20 | 0 | 20/20 | 0/0 | linkedin:20 |  | linkedin |

q4 dropped 27 Arbeitnow rows. The sample is now the Indeed and LinkedIn rows, and 7 of the first 20 titles match the relevance phrases. q9 returned nothing because LinkedIn was blocked on this run (2.5s). Indeed already returned nothing for that title in the previous run.

## q4, first 10 titles on the Jobs sheet

1. Manager IT-Quality, Risk und BCM (w/m/d) — indeed — Frankfurt am Main, HE, Germany
2. Senior Credit Analyst m/w/d — indeed — Frankfurt am Main, HE, Germany
3. Manager IT-Quality, Risk und BCM (w/m/d) — linkedin — Frankfurt am Main, Hesse, Germany
4. (Senior) Principal - Rewards Consulting (m/w/d) — indeed — Frankfurt am Main, HE, Germany
5. Manager Group Customer Collaboration (m/f/d) — indeed — Darmstadt, HE, Germany
6. IT-Service Continuity Manager (m/w/d) — linkedin — Eschborn, Hesse, Germany
7. Senior ICT Risk Manager (f/m/d) — linkedin — Frankfurt, Hesse, Germany
8. Manager (w/m/d) IKT-Risikomanagement — linkedin — Frankfurt am Main, Hesse, Germany
9. Senior Risk Manager Central Europe — linkedin — Frankfurt, Hesse, Germany
10. (Senior) Manager Quality & Risk Management (m/w/d) in Frankfurt (Main) — linkedin — Frankfurt, Hesse, Germany

Whole-board sources that must match the typed role: `arbeitnow`, `we_work_remotely`, `remote_ok`, `remotive`, `working_nomads`.
