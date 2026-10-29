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

A normal run writes the full spreadsheet and, on that computer only, the daily files. It does not commit anything.

```bash
python scrape.py
```

`--daily` does the same search, then commits three files so a later run can tell what is new:

- `data/seen_jobs.json` — listings already collected
- `output/new_jobs.csv` — only the rows that are new (header only when nothing is new)
- `output/last_run.json` — Rome time, totals, and a count per source

```bash
python scrape.py --daily
```

`--daily` needs this folder to be a git repository with a remote. It commits those three files and pushes them. Use a normal run when you only want the spreadsheet on your computer.

The first run takes several minutes. It pauses between requests on purpose.

```bash
python -m pytest
```

The tests do not contact job sites.

## Configuration

Edit `config.yaml`. Lines starting with `#` are comments.

- `roles` — search phrases. Add or remove a line.
- `title_keywords` — a posting is kept when its title contains one of these phrases. Set `require_title_match` to `false` to keep every result.
- `locations` — Milan and remote, for Indeed and LinkedIn. `distance_miles: 30` is about 50 km. Job sites measure the radius in miles.
- `sources` — set `enabled` to `false` to switch a source off. Leave `kind` as it is.
- `companies` — each block is a name, a hiring system, and a public id from the careers address (`token`). The token is not a password.
- `results_per_search` — how many Indeed and LinkedIn results to ask for. Company pages are not limited by this.
- `posted_within_days` — skip older Indeed and LinkedIn jobs. Open company jobs are kept even when they are older.
- `pause_seconds` — wait between requests. Leave a pause in place.
- `fetch_descriptions` — set to `false` for a faster run. LinkedIn snippets will be blank.

To add a company, match its careers address:

| Address | system | token |
| --- | --- | --- |
| `boards.greenhouse.io/NAME` | `greenhouse` | `NAME` |
| `jobs.lever.co/NAME` | `lever` | `NAME` |
| `jobs.ashbyhq.com/NAME` | `ashby` | `NAME` |
| `apply.workable.com/NAME` | `workable` | `NAME` |
| `NAME.recruitee.com` | `recruitee` | `NAME` |
| a `jobs.rss` feed | `teamtailor` | the full `https://` address |

```yaml
  - name: Example
    system: greenhouse
    token: example
    enabled: true
```

## Output columns

| Column | Meaning |
| --- | --- |
| New since last run | `yes` if this job was not saved on an earlier run |
| Title | Job title |
| Company | Hiring company |
| Location | City or remote, as the source wrote it |
| Date posted | When the source says it was posted |
| Source | Where it was found, for example `Satispay careers` or `indeed` |
| Source type | `company site`, `remote board`, or `aggregator` |
| URL | Link to the posting. Clickable in Excel |
| Description | A short snippet, not the full advert |
| Role searched | Which role in `config.yaml` matched the title |
| Place searched | `Milan, Italy` or `Remote` |

Files:

- `output/jobs.xlsx` — Excel, with filters and links
- `output/jobs.csv` — the same rows, for Google Sheets
- `output/new_jobs.csv` — new rows only
- `output/last_run.json` — counts for the latest run

On a first run, every row says **yes**. Later runs say **yes** only for jobs that were not in `data/seen_jobs.json`. Delete that file to treat every current job as new again.

The same title at the same company is kept once. The company-site link wins when a board lists it too. A job found on two sites is counted under both names in `last_run.json`. `total_listings` is the number of rows.

## Project structure

```text
scrape.py           Command line. Runs the search and writes the files.
config.yaml         Roles, places, sources, and companies.
config.py           Reads config.yaml and checks the settings.
sources.py          Indeed and LinkedIn, through python-jobspy.
boards.py           Company career pages and remote-board feeds.
listings.py         Snippets, title filter, dedupe, and the new/seen flag.
save_results.py     CSV, Excel, the seen file, and the daily summary.
daily.py            Commits the daily files when you pass --daily.
tests/              Checks that do not contact the job sites.
sample/             Example spreadsheet from one real run.
```

## Limitations

- Some boards block automated requests. startup.jobs and EU-Startups answered with a bot check when this was built. Headless requests to Welcome to the Jungle were blocked as well. Those sources are not included. If Indeed or LinkedIn refuses a request, that search is skipped and the rest are still saved.
- LinkedIn's public search cannot force "remote only", so a few office jobs in Italy can appear in the Remote rows. Read the Location column.
- Company pages are kept when the office is Milan, or when the role is remote and open to Italy, the EU, or worldwide. A Paris or London office job is left out. A remote role listed in both Europe and the US is kept.
- An unusual title is dropped until you add a phrase under `title_keywords`. "Product Manager" and "Senior Product Manager" stay as two rows.
- Descriptions are shortened. Open the link for the full advert. Some company pages, notably Workable, send no description.
- Dates are whatever the source sent. Company jobs older than 30 days are still listed while they are open.
- Indeed and LinkedIn return a limited number of results per search (`results_per_search`), not every posting on the site.

## License

MIT. See [LICENSE](LICENSE).
