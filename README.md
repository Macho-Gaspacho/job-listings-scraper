# Job listings scraper

A small Python program that collects job postings for project management, product, PMO, product marketing, and market research roles. The default search is Milan, plus remote roles a person in Italy or the EU can take.

It reads public career pages and job boards. It does not log in, and it does not try to get past a block. Results land in a CSV file and an Excel file. The same title at the same company is kept once, and each row is marked new or already seen.

```bash
python scrape.py
```

A sample spreadsheet from 22 October 2026 is in `sample/`. That run saved 121 listings: 14 from company career pages, 15 from remote boards, and 92 from Indeed and LinkedIn.

## Sources

Sources are switched on or off in `config.yaml`. The spreadsheet column **Source type** is one of `company site`, `remote board`, or `aggregator`.

| Source | Type | Why it is included |
| --- | --- | --- |
| Company career pages | company site | You apply on the company's own site, not in a crowded board inbox. The starter list is Milan and EU tech and AI teams that publish a public job feed (Greenhouse, Lever, Ashby, Workable, or their own page). |
| We Work Remotely | remote board | Public product and marketing feeds. US-only postings are dropped. |
| Remote OK | remote board | Public remote jobs, kept when they are open to Europe. Listings from [Remote OK](https://remoteok.com) are included when they pass that filter. |
| Indeed and LinkedIn | aggregator | Still useful for Milan roles that never appear on a startup careers page. These are the crowded ones. |

Remotive and Working Nomads are in the config and switched off. When they were tested, they did not return matching roles.

These were tried and left out, because they did not return a public job list: Wellfound, Welcome to the Jungle, Y Combinator Work at a Startup, Himalayas, InfoJobs Italia, startup.jobs, EU-Startups, SmartRecruiters, and Personio. Some of them answer with a bot check. This program does not try to get around that.

The starter companies are Bending Spoons, Satispay, Scalapay, Doctolib, Qonto, ElevenLabs, Synthesia, Hugging Face, Alan, and Mistral AI. PayFit and Pennylane are in the file as examples that are switched off.

## Setup

You need Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, create the environment with `py -m venv .venv` and activate it with `.venv\Scripts\activate`.

## Usage

Run a search and write the files:

```bash
python scrape.py
```

That reads `config.yaml`, searches, and writes:

- `output/jobs.csv`
- `output/jobs.xlsx`
- `data/seen_jobs.json` (the memory of listings already seen)

To search for different roles or a different city, edit `config.yaml`. You do not need to change the Python for ordinary use.

### Daily run

```bash
python scrape.py --daily
```

This does the full search, then commits and pushes `data/seen_jobs.json`, `output/new_jobs.csv`, and `output/last_run.json`. If nothing is new, `new_jobs.csv` is still written with the header only, and `last_run.json` is still updated.

A normal `python scrape.py` writes the same files on that computer and does not commit them.

## Config

`config.yaml` holds:

- the roles to search for
- the places (Milan, plus remote)
- which sources are on
- the company career page URLs
- pause between requests

## Output columns

The spreadsheet has these columns: Title, Company, Location, Source, Source type, Link, Status (New or Seen), Date found.

## Project structure

```
scrape.py          # entry point
sources.py         # company career pages
boards.py          # remote boards and aggregators
listings.py        # clean, dedupe, mark new
save_results.py    # write CSV and Excel
daily.py           # commit and push the daily files
config.py          # load config.yaml
config.yaml
tests/             # automated checks
sample/            # one real run from 22 October 2026
```

## Limitations

Some boards block bots. This program does not log in and does not try to get past a block. When a site answers with a bot check, that source is left out. Company career pages and the remote boards that stay public are the reliable ones.

## License

MIT. Copyright (c) 2026 Marat Gasparian.
