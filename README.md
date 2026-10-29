# Job listings scraper

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

The folder already contains an example `config.yaml` (product and project jobs in Milan). If you save a new search, that file is copied to `config.backup.yaml` first.

### Step 5. Open the spreadsheet

When the search finishes, open `output/jobs.xlsx`. The same rows are in `output/jobs.csv`. The first run can take several minutes.

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

Try a broader job title, or turn remote jobs on. Indeed and LinkedIn only return a limited set of recent posts, so some searches come back empty. Company career pages and the remote boards still prefer Milan offices or remote roles open in Europe. For another city, use Indeed and LinkedIn.

**LinkedIn or Indeed blocked the search**

Those sites sometimes refuse a lot of requests. The program skips that one search and keeps the others. Wait a while, then run it again. Leave the pause between requests in place.

**How do I change the search later?**

Double-clicking the start file runs the search you already saved. To change the titles or the city, open a terminal in the project folder and run:

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

The `config.yaml` in this repository is a working example from the author: product and project roles in Milan, plus remote roles a person in Italy or the EU can take. `config.example.yaml` is the same kind of file for a software engineer in Berlin and remote Germany.

It reads public career pages and job boards. It does not log in, and it does not try to get past a block. Results land in a CSV file and an Excel file. The same title at the same company is kept once, and each row is marked new or already seen.

```bash
python scrape.py
```

A sample spreadsheet from 22 October 2026 is in `sample/`. That run of the example search saved 121 listings: 14 from company career pages, 15 from remote boards, and 92 from Indeed and LinkedIn.

## Quick start for any job

To use this for your own search, replace `roles`, `title_keywords`, and `locations`, and change `country` to match. Clear or replace the `companies` list when you do not want the example employers. For most searches, Indeed and LinkedIn are enough: set the other sources to `enabled: false`.

Copy one of the blocks below over the matching sections in `config.yaml`, or start from `config.example.yaml` and run `python scrape.py --config config.example.yaml`.

Indeed and LinkedIn follow these settings. Company career pages and the remote boards still keep Milan offices, or remote roles open to Italy, the EU, or worldwide. For a city other than Milan, leave those sources off.

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

### Teacher or English Teacher in Milan or Remote

```yaml
roles:
  - Teacher
  - English Teacher
title_keywords:
  Teacher:
    - teacher
    - insegnante
  English Teacher:
    - english teacher
    - esl
    - efl
    - insegnante di inglese
locations:
  - name: Milan, Italy
    indeed_location: Milan, Lombardy, Italy
    linkedin_location: Milan, Lombardy, Italy
    remote: false
    distance_miles: 30
  - name: Remote
    indeed_location: Italy
    linkedin_location: Italy
    remote: true
country: italy
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
| Company career pages | company site | You apply on the company's own site, not in a crowded board inbox. The `companies` list is an example the author was tracking. Clear it, replace it, or turn this source off. |
| We Work Remotely | remote board | Public feeds for product, sales and marketing, and management. US-only postings are dropped. Other professions mostly come from Indeed and LinkedIn. |
| Remote OK | remote board | Public remote jobs, kept when they are open to Europe. Listings from [Remote OK](https://remoteok.com) are included when they pass that filter. |
| Indeed and LinkedIn | aggregator | These follow `roles` and `locations`. For most searches they are enough on their own. |

Remotive and Working Nomads are in the config and switched off. When they were tested against the example roles, they did not return matching jobs.

These were tried and left out, because they did not return a public job list: Wellfound, Welcome to the Jungle, Y Combinator Work at a Startup, Himalayas, InfoJobs Italia, startup.jobs, EU-Startups, SmartRecruiters, and Personio. Some of them answer with a bot check. This program does not try to get around that.

The companies in the example `config.yaml` are Bending Spoons, Satispay, Scalapay, Doctolib, Qonto, ElevenLabs, Synthesia, Hugging Face, Alan, and Mistral AI. PayFit and Pennylane are in the file as examples that are switched off.

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

A normal run writes the full spreadsheet and, on that computer only, the daily files. It does not commit anything.

```bash
python scrape.py
```

Answer the questions again and rewrite `config.yaml` with:

```bash
python scrape.py --setup
```

An existing `config.yaml` is copied to `config.backup.yaml` before it is replaced. `--setup` then offers to run the search.

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

Edit `config.yaml`. Lines starting with `#` are comments. The values already in the file are the author's Milan example. To use this for your own search, replace `roles`, `title_keywords`, and `locations`, and clear or replace `companies` when you want a different set of employers. `config.example.yaml` is a filled-in software-engineer search you can copy.

- `roles` — search phrases. Add or remove a line. Any job title works: engineer, teacher, nurse, analyst, or something else.
- `title_keywords` — a posting is kept when its title contains one of these phrases. The keys should match `roles`. Set `require_title_match` to `false` to keep every result. If a role has no phrases, all of its results are kept.
- `locations` — places for Indeed and LinkedIn. Each block needs a `name`. `remote: true` asks Indeed for work-from-home jobs in that country and adds the word "remote" on LinkedIn. `distance_miles: 30` is about 50 km. Job sites measure the radius in miles. Change `country` when you change the country (`italy`, `france`, `germany`, `spain`, `netherlands`, `uk`, `usa`).
- `sources` — set `enabled` to `false` to switch a source off. Leave `kind` as it is. Indeed and LinkedIn are enough for most searches.
- `companies` — optional. The list in `config.yaml` is an example of employers the author was tracking, not a required part of the scraper. Clear it, replace it, or set `company_pages` to `enabled: false`. Each block is a name, a hiring system, and a public id from the careers address (`token`). The token is not a password.
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
| Place searched | The location `name` from `config.yaml` for Indeed and LinkedIn. Company pages and remote boards use `Milan, Italy` or `Remote` |

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
config.yaml         Working example: roles, places, sources, and companies.
config.example.yaml Neutral example: software engineer, Berlin and remote.
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
- LinkedIn's public search cannot force "remote only", so a few office jobs in the country you set can appear in the Remote rows. Read the Location column.
- Company pages and remote boards are kept when the office is Milan, or when the role is remote and open to Italy, the EU, or worldwide. A Paris, Berlin, or London office job from those sources is left out. Indeed and LinkedIn follow `locations`, so a search in another city still works there.
- We Work Remotely is read from product, sales and marketing, and management feeds. A teacher, nurse, or engineer search will mostly come from Indeed and LinkedIn.
- An unusual title is dropped until you add a phrase under `title_keywords`. "Product Manager" and "Senior Product Manager" stay as two rows.
- Descriptions are shortened. Open the link for the full advert. Some company pages, notably Workable, send no description.
- Dates are whatever the source sent. Company jobs older than 30 days are still listed while they are open.
- Indeed and LinkedIn return a limited number of results per search (`results_per_search`), not every posting on the site.

## License

MIT. See [LICENSE](LICENSE).
