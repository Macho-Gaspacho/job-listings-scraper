# Job listings scraper

[![Tests](https://github.com/Macho-Gaspacho/job-listings-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/Macho-Gaspacho/job-listings-scraper/actions/workflows/tests.yml)
[![Python 3.10 | 3.12 | 3.13](https://img.shields.io/badge/python-3.10%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A free job search for any profession, country, or level of experience.
Answer a few questions (job title, city, country, remote) and get matching listings in one Excel file.
No coding needed. The spreadsheet stays on your computer.

## Screenshots

These pictures are placeholders. Replace the files with captures from your own computer. Do not commit a spreadsheet that contains a real person's job search.

![The spreadsheet of matching jobs](docs/img/spreadsheet.png)

![The setup questions](docs/img/wizard.gif)

To capture them:

1. `docs/img/spreadsheet.png` — run a search, open `output/jobs.xlsx`, and take a screenshot of the Jobs sheet. Crop out anything you would not want public.
2. `docs/img/wizard.gif` — run `python scrape.py --setup` and record the questions. A short GIF, or a still image, is enough. If you save a PNG instead, change the link above to that file name.

## How it works

```mermaid
flowchart LR
  wizard[Wizard] --> config[config.yaml]
  config --> sources[Sources]
  sources --> filter[Filter and dedupe]
  filter --> files[Excel and CSV]
```

You answer the questions, or edit `config.yaml`. The program asks Indeed, LinkedIn, remote job boards, and any company career pages you listed. It keeps titles and places that match, drops duplicates, and writes `output/jobs.xlsx` and `output/jobs.csv`.

## Legal and fair use

This program is for your own job search.

Indeed and LinkedIn's terms of service do not allow automated scraping. Use it for yourself, leave the pause between requests in place, and stop if a site tells you to. The program does not log in and does not try to get past a block. You are responsible for following each site's terms.

Remote boards are read from their public feeds. When a result comes from Remote OK, credit Remote OK and link to [https://remoteok.com](https://remoteok.com). Their API asks for that attribution. The Excel file's About sheet includes the same credit.

## Privacy

A normal run keeps every file on your computer: the spreadsheet, the list of jobs already seen, `config.yaml`, and any CV profile. Nothing is uploaded. The CV generator does not send your photo, date of birth, or contact details anywhere unless you set your own model key, and even then those fields are left out of the request.

Do not commit `config.yaml`, `data/`, or `output/` to a public repository. Those files are your job search. Git already ignores them. An optional script can publish them, and it refuses to run unless you opt in. Read the warning in [examples/automation/daily_git_commit.py](examples/automation/daily_git_commit.py) before you consider it. Only use that script with a private repository.

## For beginners: 5 minutes, no coding

This program searches public job sites and saves what it finds in a spreadsheet. You choose the job titles and the city by answering a few questions. You do not write any code.

### Step 1. Install Python 3.12

Download it from [python.org/downloads](https://www.python.org/downloads/).

**Mac.** Open the installer and follow the steps. Then open Finder, go to Applications, open the **Python 3.12** folder, and double-click **Install Certificates.command**. That lets the program open job websites. You only do this once. If you skip it, a search can stop with `CERTIFICATE_VERIFY_FAILED`.

**Windows.** Run the installer. On the first screen, turn on **Add python.exe to PATH**, then click Install.

### Step 2. Download this project

Open [github.com/Macho-Gaspacho/job-listings-scraper](https://github.com/Macho-Gaspacho/job-listings-scraper). Click the green **Code** button, then **Download ZIP**. Unzip the file. You get a folder named `job-listings-scraper`.

If you already use Git, this is the same thing:

```bash
git clone https://github.com/Macho-Gaspacho/job-listings-scraper.git
```

### Step 3. Start the program

**Mac:** double-click `start.command`. Terminal opens.

**Windows:** double-click `start.bat`.

Or open a terminal in the project folder and run:

```bash
./start.sh
```

The first time, it creates a private folder named `.venv` and installs the tools the program needs. That can take a few minutes. Leave the window open. When it is finished, press Enter to close the window.

### Step 4. Answer the questions

It asks, one at a time:

- which job titles you want (for example `Project Manager, Product Manager`)
- which city and country (for example `Berlin, Germany`)
- whether to include remote jobs, and in which country
- extra words that must appear in the title (you can leave this blank)
- which websites to use
- company career pages, which you can skip

Press Enter to accept a choice shown in brackets. Indeed and LinkedIn are enough for most searches.

A fresh download has no `config.yaml`, so the first run asks these questions and writes one. If you save a new search later, the old file is copied to `config.backup.yaml` first. Ready-made examples are in `examples/`.

### Step 5. Open the spreadsheet

When the search finishes, open `output/jobs.xlsx`. The same rows are in `output/jobs.csv`. The first run can take several minutes.

### Make a CV for one job

After a search, you can tailor a CV to one row. The generator only uses facts you write in `profile/cv_profile.yaml`. It does not invent employers, dates, or skills. Copy `profile/cv_profile.example.yaml` to `profile/cv_profile.yaml` and fill it in. That file and `profile/photo.*` stay off git.

```bash
python scrape.py --cv 1 --format us_resume
```

`1` is the first job in `output/jobs.csv`. You can pass a job URL instead. Formats: `us_resume`, `uk_cv`, `de_lebenslauf`, `eu_europass`, `it_cv`, `fr_cv`. The files land in `output/cv/`. The design, including what each country preset leaves out, is in [docs/cv-generator-design.md](docs/cv-generator-design.md).

Double-clicking the start file, once `config.yaml` exists, asks whether to search or make a CV. Press Enter to search. A scheduled run does not ask.

### FAQ

**Python was not found, or `python` is not recognized**

Install Python 3.12 from the link in step 1. On Windows, run the installer again and turn on **Add python.exe to PATH**. Close the window and double-click the start file again.

**`CERTIFICATE_VERIFY_FAILED`**

On a Mac, double-click this file, then start the search again:

```text
"/Applications/Python 3.12/Install Certificates.command"
```

If your Python is 3.11 or 3.10, open that version's folder under Applications instead. The program prints the same path when this error happens.

**The spreadsheet has 0 jobs**

Try a broader job title, or turn remote jobs on. Indeed and LinkedIn only return a limited set of recent posts, so some searches come back empty. Company career pages and the remote boards keep offices in the cities you named, and remote roles open in the country or region you named.

**LinkedIn or Indeed blocked the search**

Those sites sometimes refuse a lot of requests. The program skips that one search and keeps the others. Wait a while, then run it again. Leave the pause between requests in place.

**How do I run this every day?**

See [docs/scheduling.md](docs/scheduling.md). That runs the same search on your computer. It does not upload your results.

**How do I change the search later?**

Double-clicking the start file asks whether to search or make a CV, then runs the search you already saved if you press Enter. To change the titles or the city, open a terminal in the project folder and run:

```bash
.venv/bin/python scrape.py --setup
```

On Windows:

```bat
.venv\Scripts\python scrape.py --setup
```

You can also delete `config.yaml` and double-click the start file again. Saving from the questions copies the previous file to `config.backup.yaml`.

## For developers

A configurable Python program that collects public job postings for any profession and any location. Roles, cities, companies, and sources are set in `config.yaml`. Edit that file, or run `python scrape.py --setup`. The search code stays as it is.

A fresh copy of this repository has no `config.yaml`, so the first run asks the setup questions. Ready-made searches for different professions and countries are in `examples/`. Copy one to `config.yaml` to try it. See [examples/README.md](examples/README.md).

It reads public career pages and job boards. It does not log in, and it does not try to get past a block. Results land in a CSV file and an Excel file. The same title at the same company is kept once, and each row is marked new or already seen.

```bash
python scrape.py
```

A made-up spreadsheet is in `sample/`. It was built by `tools/make_sample.py` from local fixtures, with no network and no real job search. Regenerate it with `python tools/make_sample.py`.

## Quick start for any job

To use this for your own search, answer the setup questions, or copy a file from `examples/` to `config.yaml`. You can also replace `roles`, `title_keywords`, and `locations`, and change `country` to match. Clear or replace the `companies` list when you do not want the example employers. For most searches, Indeed and LinkedIn are enough: set the other sources to `enabled: false`.

The blocks below are examples. Each one searches only the places it names. Indeed, LinkedIn, company career pages, and the remote boards all follow those places. A Berlin search keeps Berlin offices and remote roles open in Germany. It does not keep an office in another city, or a remote role limited to a different country.

### Software Engineer in Berlin + Remote

```yaml
roles:
  - Software Engineer
title_keywords:
  Software Engineer:
    - software engineer
    - software developer
    - backend engineer
    - frontend engineer
locations:
  - name: Berlin, Germany
    indeed_location: Berlin, Germany
    linkedin_location: Berlin, Germany
    remote: false
    distance_miles: 25
  - name: Remote
    indeed_location: Germany
    linkedin_location: Germany
    remote: true
country: germany
```

### Nurse in Amsterdam, with Dutch titles

```yaml
roles:
  - Nurse
title_keywords:
  Nurse:
    - nurse
    - registered nurse
    - verpleegkundige
    - verpleger
    - verpleegster
locations:
  - name: Amsterdam, Netherlands
    indeed_location: Amsterdam, Netherlands
    linkedin_location: Amsterdam, Netherlands
    remote: false
    distance_miles: 25
  - name: Remote
    indeed_location: Netherlands
    linkedin_location: Netherlands
    remote: true
country: netherlands
```

### Nurse or Doctor in Italy

```yaml
roles:
  - Nurse
  - Doctor
title_keywords:
  Nurse:
    - nurse
    - nursing
    - infermiere
  Doctor:
    - doctor
    - physician
    - medico
locations:
  - name: Italy
    indeed_location: Italy
    linkedin_location: Italy
    remote: false
country: italy
```

### Data Analyst in Paris + Remote

```yaml
roles:
  - Data Analyst
title_keywords:
  Data Analyst:
    - data analyst
    - data analytics
    - business analyst
locations:
  - name: Paris, France
    indeed_location: Paris, France
    linkedin_location: Paris, France
    remote: false
    distance_miles: 25
  - name: Remote
    indeed_location: France
    linkedin_location: France
    remote: true
country: france
```

## Sources

Sources are switched on or off in `config.yaml`. The spreadsheet column **Source type** is one of `company site`, `remote board`, or `aggregator`.

| Source | Type | Why it is included |
| --- | --- | --- |
| Company career pages | company site | You apply on the company's own site, not in a crowded board inbox. The list is optional. Leave it empty, or add the employers you want. |
| We Work Remotely | remote board | The public all-jobs feed, unless you list `categories` on that source. A posting is kept when it is open in your country or region. |
| Remote OK | remote board | Public remote jobs, kept when they match your country or region. Listings from [Remote OK](https://remoteok.com) are included when they pass that filter. |
| Indeed and LinkedIn | aggregator | These follow `roles` and `locations`. For most searches they are enough on their own. |

Remotive and Working Nomads are in the config and switched off. When they were tested against the example roles, they did not return matching jobs.

These were tried and left out, because they did not return a public job list: Wellfound, Welcome to the Jungle, Y Combinator Work at a Startup, Himalayas, InfoJobs Italia, startup.jobs, EU-Startups, SmartRecruiters, and Personio. Some of them answer with a bot check. This program does not try to get around that.

The example files leave `companies` empty and turn company career pages off. Add employers you want to read, or leave the list empty.

## Setup

You need Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, create the environment with `py -m venv .venv` and activate it with `.venv\Scripts\activate`.

After you clone the repository, run `python scrape.py --setup` or edit `config.yaml` for your roles and location, then run `python scrape.py`. If `config.yaml` is missing, `python scrape.py` asks the setup questions instead of stopping.

## Usage

A normal run writes the full spreadsheet and, on that computer only, the daily files. It does not commit or upload anything.

```bash
python scrape.py
```

Answer the questions again and rewrite `config.yaml` with:

```bash
python scrape.py --setup
```

An existing `config.yaml` is copied to `config.backup.yaml` before it is replaced. `--setup` then offers to run the search.

To run the search every day, follow [docs/scheduling.md](docs/scheduling.md). That uses `start.bat`, `start.command`, or cron. It does not publish your search.

`python scrape.py` also writes three local files so the next run can tell what is new:

- `data/seen_jobs.json` — listings already collected
- `output/new_jobs.csv` — only the rows that are new (header only when nothing is new)
- `output/last_run.json` — the time on your computer (or the `timezone` in config.yaml), totals, and a count per source

Those files stay on your computer. Git ignores them.

There is a separate script, [examples/automation/daily_git_commit.py](examples/automation/daily_git_commit.py), that can commit and push those three files. **Only use it with a private repo. It publishes your job search history.** It refuses to push unless `config.yaml` sets both `daily_git.enabled` and `daily_git.i_understand_this_is_public_if_repo_is_public` to `true`. It is not part of the normal command and not part of the beginner steps.

The first run takes several minutes. It pauses between requests on purpose.

Developers: `pip install -r requirements-dev.txt`, then `ruff check .` and `pytest`. See [CONTRIBUTING.md](CONTRIBUTING.md). The tests do not contact job sites. Beginners can skip this. The start files install `requirements.txt` only.

## Configuration

Edit `config.yaml` (create it with `python scrape.py --setup`, or copy a file from `examples/`). Lines starting with `#` are comments. The files in `examples/` are complete searches for different jobs and countries. See [examples/README.md](examples/README.md).

- `roles` — search phrases. Add or remove a line. Any job title works: engineer, teacher, nurse, analyst, or something else.
- `title_keywords` — a posting is kept when its title contains one of these phrases. The keys should match `roles`. Set `require_title_match` to `false` to keep every result. If a role has no phrases, all of its results are kept.
- `locations` — places for Indeed and LinkedIn. Each block needs a `name`. `remote: true` asks Indeed for work-from-home jobs in that country and adds the word "remote" on LinkedIn. `distance_miles: 30` is about 50 km. Job sites measure the radius in miles.
- `country` — the Indeed country, such as `italy`, `france`, `germany`, `uk`, or `usa`. If you leave it out, it is taken from the first office. An unknown country stops the run and tells you why.
- `timezone` — optional. Used for the run summary. When omitted, the computer's own timezone is used. Example: `America/Chicago`.
- `location_filter` — optional. `offices` are words that mean a workplace you can go to. `remote_regions` are places a remote job may be open to. `exclude_regions` are phrases that mean "not for me", such as `US only`. When this block is missing, offices come from your locations, and remote regions follow your country.
- `sources` — set `enabled` to `false` to switch a source off. Leave `kind` as it is. Indeed and LinkedIn are enough for most searches. On `we_work_remotely`, an optional `categories` list (for example `product` or `design`) picks feeds. When omitted, the all-jobs feed is used.
- `companies` — optional. Leave it empty, or add employers whose public careers page you want to read. Set `company_pages` to `enabled: false` to skip them. Each block is a name, a hiring system, and a public id from the careers address (`token`). The token is not a password.
- `results_per_search` — how many Indeed and LinkedIn results to ask for. Company pages are not limited by this.
- `posted_within_days` — skip older Indeed and LinkedIn jobs. Open company jobs are kept even when they are older.
- `pause_seconds` — wait between requests. Leave a pause in place.
- `fetch_descriptions` — set to `false` for a faster run. LinkedIn snippets will be blank.
- `filters` — optional. Leave the block out to keep every job that matches the title and place. A blank value is not a reason to drop a row, except where the list itself names `Unknown`.

```yaml
filters:
  job_types: [Full-time, Internship]   # Full-time, Part-time, Contract, Internship, Temporary
  levels: [Entry, Unknown]             # Entry, Senior, or Unknown
  min_salary: 30000                    # yearly amount; monthly × 12, hourly × 2,080, weekly × 52, daily × 260
  exclude_title_words: [senior, lead]  # whole words, so lead does not match leader
  exclude_if_language_required: [German]  # English names: German, Dutch, Spanish, Polish, …
  only_visa_sponsorship: false         # true keeps Sponsorship offered and Unknown
```

`min_salary` is compared only when the posting states a salary and a time period. The number is not converted between currencies: 30,000 means 30,000 in whatever currency the source used. A job with no salary, or with a salary and no period, is kept.

`job_types` is also sent to Indeed when the list has exactly one type. LinkedIn ignores `job_type` in python-jobspy 1.4.0, so LinkedIn results are filtered after the search. Several types are always filtered after the search, because jobspy accepts one type at a time.

Languages and visa are guessed from the description text. They can be wrong. `only_visa_sponsorship: true` drops rows labelled "No sponsorship" and keeps "Sponsorship offered" and "Unknown".

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
| Place searched | The location name from your config that matched this posting. Company pages and remote boards use that name, or `Remote` |
| Salary | Pay range when the source gave one, such as `40,000–50,000 EUR/year`. Blank when it did not |
| Job type | `Full-time`, `Part-time`, `Contract`, `Internship`, or `Temporary` when the source says |
| Remote | `Yes`, `No`, or `Unknown` |
| Level | `Entry`, `Senior`, or `Unknown`. From the source when it sends a level, otherwise from words in the title |
| Languages | Languages the description appears to require. Guessed from the text |
| Visa | `No sponsorship`, `Sponsorship offered`, or `Unknown`. Guessed from the text |

Files:

- `output/jobs.xlsx` — Excel, with filters and links
- `output/jobs.csv` — the same rows, for Google Sheets
- `output/new_jobs.csv` — new rows only
- `output/last_run.json` — counts for the latest run

On a first run, every row says **yes**. Later runs say **yes** only for jobs that were not in `data/seen_jobs.json`. Delete that file to treat every current job as new again.

The same title at the same company is kept once. The company-site link wins when a board lists it too. A job found on two sites is counted under both names in `last_run.json`. `total_listings` is the number of rows.

## Project structure

```text
start.command       Mac double-click. Opens Terminal and runs start.sh.
start.sh            Creates .venv, installs requirements, runs the scraper.
start.bat           The same flow on Windows.
scrape.py           Command line. Runs the search and writes the files.
setup_wizard.py     Questions that write config.yaml. Also: scrape.py --setup.
environment.py      Plain messages for old Python, missing packages, and Mac SSL.
examples/           Sample config files for different jobs and countries.
examples/automation/daily_git_commit.py
                    Optional. Commits and pushes the daily files. Refuses unless you opt in. Private repos only.
config.yaml         Your search. Created by the wizard. Not included in a fresh download.
config.py           Reads config.yaml and checks the settings.
regions.py          Country names and the location rules built from your config.
sources.py          Indeed and LinkedIn, through python-jobspy.
boards.py           Company career pages and remote-board feeds.
listings.py         Snippets, title filter, dedupe, and the new/seen flag.
enrichment.py       Salary, job type, level, language, and visa.
signals/            Word lists used to guess level, language, and visa from the text.
save_results.py     CSV, Excel, the seen file, and the run summary.
daily.py            Points at the optional private-repo script. It cannot push.
docs/scheduling.md  How to run the search every day on your computer.
tools/make_sample.py  Rebuilds the made-up spreadsheet in sample/.
tests/              Checks that do not contact the job sites.
sample/             Made-up spreadsheet, so you can see the columns before you search.
```

## Limitations

- Some boards block automated requests. startup.jobs and EU-Startups answered with a bot check when this was built. Headless requests to Welcome to the Jungle were blocked as well. Those sources are not included. If Indeed or LinkedIn refuses a request, that search is skipped and the rest are still saved.
- LinkedIn's public search cannot force "remote only", so a few office jobs in the country you set can appear in the Remote rows. Read the Location column.
- Company pages and remote boards are kept when the office matches a city you listed, or when the role is remote and open in your country or the regions in `location_filter`. An office in another city is left out. A remote role limited to a different country is left out.
- We Work Remotely is read from the all-jobs feed unless you set `categories` on that source. The title filter still applies, so an unusual profession mostly comes from Indeed and LinkedIn.
- An unusual title is dropped until you add a phrase under `title_keywords`. "Product Manager" and "Senior Product Manager" stay as two rows.
- Descriptions are shortened. Open the link for the full advert. Some company pages, notably Workable, send no description. Language and visa notes are guessed from that text before it is shortened.
- A salary filter does not drop a job that leaves the pay blank. It also does not convert between currencies.
- Dates are whatever the source sent. Company jobs older than 30 days are still listed while they are open.
- Indeed and LinkedIn return a limited number of results per search (`results_per_search`), not every posting on the site.

## License

MIT. See [LICENSE](LICENSE).
