# Contributing

The checks do not contact job sites. They use local fixtures only.

## Run the tests

Python 3.10 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest
```

On Windows, create the environment with `py -m venv .venv`, activate it with `.venv\Scripts\activate`, and use the same `pip`, `ruff`, and `pytest` commands.

`requirements.txt` is what the double-click launchers install. `requirements-dev.txt` adds the test tools on top of that. Beginners do not need the dev file.

## Add a CV format

Add one file, `cv_templates/presets/<id>.yaml`. The file name is the id passed to `--format`, and the help text lists it on the next run. No Python edit is required.

Copy a nearby preset and set:

- `page_size` (`a4` or `letter`), `photo` (`forbidden`, `optional`, or `customary`), and `personal_fields` (only fields that may print, and only when the person opted in)
- `language`, plus `section_titles` in that language and in `en` (English is the fallback when a local title is missing)
- `countries`: the country codes `regions.canonical_country` returns, such as `netherlands` or `canada`

To be suggested for places that have no dedicated file, set `fallback_words` (for example `europe`), `fallback_countries`, or `fallback_eu_eea: true`. One preset in the folder should set `default_fallback: true`. That file is used when the location is unknown or only says remote.

## What to leave out of a commit

- `config.yaml` and `config.backup.yaml` — your search
- `data/` and `output/` — jobs already seen, and the spreadsheet
- `profile/cv_profile.yaml` and `profile/photo.*` — your CV facts and photo
- `.venv/`

Those paths are already in `.gitignore`. Do not force-add them. The optional script in `examples/automation/daily_git_commit.py` publishes that history and refuses to run unless you opt in. Do not use it on a public repository.

## Sample spreadsheet

`sample/` is a made-up file, generated with no network:

```bash
python tools/make_sample.py
```

Regenerate it when the spreadsheet columns change.
