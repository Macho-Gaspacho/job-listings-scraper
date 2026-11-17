# Employer list

Each file is one country. `europe_remote.yaml` lists employers with at least three jobs that say Remote and Europe, EMEA, or EU.

Add an employer only after the checker shows `status: ok` and at least one job in that country (`jobs_in_country` of 3 or more for `europe_remote`). `system` must be one of `greenhouse`, `lever`, `ashby`, `workable`, `recruitee`, `teamtailor`, `bendingspoons`. `families` must be keys from `sourcemap/role_families.yaml`. Set `region` to `eu` only for `jobs.eu.lever.co` / `api.eu.lever.co`.

Check one country, without changing the file:

    .venv/bin/python tools/verify_employers.py --country netherlands

Write `last_check` and `checked_on` back into the file:

    .venv/bin/python tools/verify_employers.py --write

Anything other than `ok` is kept and marked `enabled: false`. The job search skips those rows. The search never runs this checker.
