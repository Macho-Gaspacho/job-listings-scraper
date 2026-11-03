# Changelog

## Unreleased

### Added

- An offline CV generator tailors one saved job from facts in `profile/cv_profile.yaml`. It does not invent employers, dates, or skills. See [docs/cv-generator-design.md](docs/cv-generator-design.md). `python-docx` is the only new dependency.
- A guided interview (`python scrape.py --cv-interview`, and the launcher line "I don't have a CV yet - help me make one") writes `profile/cv_profile.yaml` from answers you type. Every section can be skipped, including paid work.
- CV formats are discovered from `cv_templates/presets/*.yaml`. New formats: `nl_cv`, `es_cv`, `pl_cv`, and `ca_resume`. The job location suggests a format. `--format` overrides that suggestion.
- GitHub Actions runs the tests on Ubuntu, Windows, and macOS, for Python 3.10, 3.12, and 3.13.
- `requirements-dev.txt` and `pyproject.toml` for the test tools. The double-click launchers still install `requirements.txt`.
- Example searches for a nurse in the Netherlands, a warehouse worker in Poland, a graduate marketing role in Spain, remote customer support, and an accountant in Toronto.
- `docs/scheduling.md` explains a daily run with Task Scheduler, Calendar, launchd, and cron.
- `tools/make_sample.py` rebuilds the sample spreadsheet from local fixtures.
- Level words now treat staff, principal, and the same idea in the starter languages as Senior.
- The Excel About sheet credits Remote OK.

### Changed

- The normal command no longer offers `--daily`. A search does not commit or push.
- Publishing the seen-jobs file is a separate script, `examples/automation/daily_git_commit.py`. It refuses to push unless `config.yaml` opts in with `daily_git.enabled` and `daily_git.i_understand_this_is_public_if_repo_is_public`.
- The sample spreadsheet is made up, and it includes salary, job type, remote, level, languages, and visa.

### Security

- Job-search history is no longer force-added and pushed by the default command. That history stays on your computer unless you opt in, and the opt-in is meant for a private repository only.
