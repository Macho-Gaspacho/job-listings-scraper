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

## What to leave out of a commit

- `config.yaml` and `config.backup.yaml` — your search
- `data/` and `output/` — jobs already seen, and the spreadsheet
- `.venv/`

Those paths are already in `.gitignore`. Do not force-add them. The optional script in `examples/automation/daily_git_commit.py` publishes that history and refuses to run unless you opt in. Do not use it on a public repository.

## Sample spreadsheet

`sample/` is a made-up file, generated with no network:

```bash
python tools/make_sample.py
```

Regenerate it when the spreadsheet columns change.
