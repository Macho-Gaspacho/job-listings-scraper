# CV generator

Phase 1 is a design plus an offline skeleton. It tailors a CV to one saved job. It can select, reorder, shorten, and rephrase facts the user already wrote. It cannot invent experience, skills, dates, employers, degrees, or certifications.

A missing keyword is a gap. It is written in the match report. It is never copied onto the CV to make the match look better.

Nothing in this feature calls a paid service. The optional model path uses an endpoint the user configures, and it is off until they do.

## Profile

`profile/cv_profile.yaml` is the only source of facts. People who already have the facts can copy `profile/cv_profile.example.yaml` and replace every value. People who do not have a CV yet can run the interview below. The example is safe to commit. The real profile is not.

### Interview

`python scrape.py --cv-interview` asks plain questions and writes `profile/cv_profile.yaml`. The same questions are menu item "I don't have a CV yet - help me make one" in the launcher (`start.sh`, `start.bat`, and `start.command` run that menu when a terminal is open). Choosing "Make a CV" when the profile file is missing offers the interview before it asks which job to tailor.

Every section can be skipped with Enter. `no work experience yet` leaves paid work empty and still writes a valid profile. Volunteering, school or university projects, and informal or family work are stored as experience only when the person types an organisation, a title, and one fact. Studies need a school or university. A skill can include where they used it. A language answer is a number from 1 to 6 (or the phrase next to that number) and is stored as one CEFR level: 1 is A1, 2 is A2, 3 is B1, 4 is B2, 5 is C1, 6 is C2. The file contains the words the person typed. It does not contain sample employers, dates, or skills. An existing profile is left in place unless they confirm the overwrite.

Git ignores:

- `profile/cv_profile.yaml`
- `profile/photo.*`

`output/` is already ignored, so generated CVs stay local too.

### Fields

| Field | Role |
| --- | --- |
| `contact` | Name, email, phone, location. Printed on the CV. Never sent to a model. |
| `summary` | The user's own paragraph. Copied, not rewritten, in offline mode. |
| `experience` | Employer, title, location, start, end, and bullet facts. Each item needs an employer, a title, and at least one bullet. |
| `education` | Institution, degree, field, start, end. |
| `skills` | A name plus `evidence` pointing at something the user did. A skill with no evidence is still the user's claim; the generator does not supply the evidence. |
| `languages` | Name plus one CEFR level: A1, A2, B1, B2, C1, or C2. Other labels are rejected. |
| `certifications` | Name, issuer, date. |
| `links` | Label and URL. |
| `photo.path` / `photo.include` | Optional file. `include` must be true and the file must exist. A preset can still forbid it. |
| `personal.include` plus `date_of_birth`, `nationality`, `marital_status` | Stored only so a preset can print them. Both the preset and `personal.include` have to allow a field. |
| `signature.include` / `signature.place` | Optional place the user wrote, plus a blank Ort/Datum line on presets that ask for one. |
| `gdpr_consent` | Prints the consent sentence on `it_cv` and `pl_cv` only. Both lines are opt-in. |
| `references_on_request` | Prints the UK references line only on `uk_cv`. |
| `document_language` | Stored. Phase 1 does not let it replace the preset's language, so a Lebenslauf stays German. |

Dates are strings the user wrote (`2019-03`, `2014`, `present`). The generator formats them. It does not invent a month when only a year was given.

## Job input

The job comes from one row of `output/jobs.csv` (or `jobs.xlsx`'s sibling CSV). Pass a row number or the URL.

Row `1` is the first job under the header, not the header itself. A URL must match the URL column exactly.

The tailor reads the title, the description, and the language flags. The company and location name the vacancy on the cover letter and in the file name. They are not treated as the user's employers.

## Presets

Presets live in `cv_templates/presets/*.yaml`. The program lists every `*.yaml` file in that folder at startup. Each file sets section order, section titles per language, page size, photo policy (`forbidden`, `optional`, or `customary`), which personal fields are allowed, the date format, and the page cap.

The rendered headings are the preset language. A missing local title uses the `en` map in the same file. The other language maps stay in the file so a later version can switch headings without inventing them.

| Preset | Page | Cap | Photo | Personal fields that can print | Notes |
| --- | --- | --- | --- | --- | --- |
| `us_resume` | Letter | 1, or 2 when the career spans 10 years or more | Forbidden | None | Reverse chronological. Achievement bullets. Default when the place is unknown, remote with no region, or outside Europe. |
| `uk_cv` | A4 | 2 | Forbidden | None | Summary heading is "Personal statement". References line only if opted in. |
| `de_lebenslauf` | A4 | 2 | Customary, still opt-in | `date_of_birth` only, and only if opted in | Headings: Berufserfahrung, Ausbildung, Kenntnisse. Optional Ort/Datum line. |
| `eu_europass` | A4 | 2 | Optional | `date_of_birth`, `nationality`, if opted in | One CEFR column. Suggested for other EU/EEA countries and for remote Europe. Not the official Europass PDF. |
| `it_cv` | A4 | 2 | Optional | `date_of_birth`, if opted in | GDPR sentence only when `gdpr_consent` is true. |
| `fr_cv` | A4 | 2 | Optional | `date_of_birth`, if opted in | Photo and date of birth stay optional. |
| `nl_cv` | A4 | 2 | Optional | `date_of_birth` only, and only if opted in | Dutch headings (Werkervaring, Opleiding, Vaardigheden). A date of birth is not required. |
| `es_cv` | A4 | 2 | Customary, still opt-in | `date_of_birth` only, and only if opted in | Spanish headings (Experiencia profesional, Formación, Competencias). A photo is common and still optional. |
| `pl_cv` | A4 | 2 | Optional | `date_of_birth` only, and only if opted in | Polish headings (Doświadczenie zawodowe, Wykształcenie, Umiejętności). The RODO sentence prints only when `gdpr_consent` is true. |
| `ca_resume` | Letter | 1, or 2 when the career spans 10 years or more | Forbidden | None | Same personal-data rule as `us_resume`: photo, date of birth, marital status, and nationality are dropped. |

### Add a format

Adding a country is a new YAML file. Copy a nearby preset to `cv_templates/presets/<id>.yaml`.

- The file name is the `--format` id. Help text and unknown-format errors list whatever files are in the folder.
- Put section titles in the local language and an `en` map. A heading that exists only in `en` is used as the fallback.
- Set `countries` to codes from `regions.canonical_country`, such as `netherlands` or `canada`. A job in that country suggests this file.
- For a region that should share an existing file, set `fallback_words` (such as `europe` or `north america`), `fallback_countries`, or `fallback_eu_eea: true` on that file. `us_resume` sets `default_fallback: true` for an unknown place or a remote job with no region.
- A named country on the job row wins over a region fallback. `--format` wins over both.

### Which format is suggested

`cv/suggest.py` reads the job's `location`, then `place_searched` when the location is only a remote word such as `Remote` or `Worldwide`. Country names go through `regions.country_from_places`, so `Holland`, `España`, and `United States` match the same codes as the preset files. The suggestion is printed in the launcher; Enter accepts it.

`marital_status` is in the profile schema and on no preset. Older templates in several countries asked for it. This generator does not print it unless a future preset lists the field and the user opts in.

The Europass language block shows the single CEFR level from the profile. It does not copy that level into listening, reading, and speaking. That would invent assessments the user did not write.

Photo rules:

- `forbidden`: dropped even when a file is present and `photo.include` is true. Used by `us_resume`, `uk_cv`, and `ca_resume`.
- `optional` and `customary`: included only when `photo.include` is true and the file exists. Customary means readers often expect a photo. It does not mean the file is required. German law (AGG) is why a photo cannot be required; the preset still will not invent one.

### Conventions to double-check

These are ordinary practice, not legal advice, and they vary by industry, employer, and decade. Each preset repeats the relevant warning in the match report.

- **United States.** Photo, date of birth, age, marital status, and nationality are omitted. One page is the usual target; two pages after about ten years. Academic, medical, and federal CVs are often longer. A federal form can ask for data this preset drops. Add that by hand after you read the form.
- **United Kingdom.** Two pages, A4, no photo, no date of birth, is the modern default. Academic CVs differ. The references line does not invent referee names.
- **Germany.** A photo is customary and cannot be demanded. Date of birth is still common and increasingly left off. Nationality and marital status are not in this preset. Public-sector applications sometimes ask for more than this file prints. The signature line is a blank; the city is printed only when `signature.place` is filled in.
- **Europass.** The official template changes. Two pages is a reading target. Date of birth and nationality are optional on the official form. Marital status is not an official Europass field.
- **Italy.** A photo is common. The sentence `Autorizzo il trattamento dei dati personali ai sensi del Regolamento UE 2016/679` is widely used and the wording is not unique. Confirm it before you rely on it.
- **France.** A photo is common and cannot be required. Date of birth is often omitted now. Concours and academic CVs use their own forms.
- **Netherlands.** One or two pages on A4. A photo is optional. A date of birth is not required and prints only when `personal.include` is true.
- **Spain.** A photo is common and still optional. A date of birth is not required.
- **Poland.** A photo is optional. The sentence `Wyrażam zgodę na przetwarzanie moich danych osobowych dla potrzeb niezbędnych do realizacji procesu rekrutacji zgodnie z Rozporządzeniem Parlamentu Europejskiego i Rady (UE) 2016/679` prints only when `gdpr_consent` is true. Confirm the wording before you rely on it.
- **Canada.** Letter size. Photo, date of birth, marital status, and nationality are omitted, including when they are filled in on the profile. One page is the usual target; two pages after about ten years.

## Tailoring

Offline and deterministic. No network.

Keywords come from the job title, the description, and the language flags. Words come from `matching.normalise` (casefold, accents removed, whole words). Numbers such as `12` are kept separately, because `normalise` drops digits. Glue words (`the`, `and`, `years`, `required`, and the same kind of word in German, French, and Italian) are not keywords.

Each experience bullet and each skill is scored by how many keywords it already contains. Inside a role, matching bullets are ordered by that score. Roles themselves stay reverse-chronological, because the presets ask for that and reordering employers by keyword score would fight the format.

When at least one bullet matches, bullets with no overlap are left out of this CV. The same rule applies to skills. Left-out facts are listed in the match report under "Not selected from your profile". They remain in the profile. When nothing matches, the CV keeps the user's facts in the order they were written, rather than becoming empty.

Coverage is computed against the whole profile, including facts that were not selected:

- **Covered:** the keyword appears in the summary, experience, education, skills, languages, or certifications.
- **Missing:** it does not. The match report lists it. The CV does not gain a bullet, a skill, or a tool name to "cover" it.

The page count is a heuristic: 400 words to a page, rounded up, at least one page. It is not Word's layout engine. `us_resume` allows one page, or two when the earliest start and the latest end are ten years or more apart. Overlapping jobs are not added together. If the estimate is over the cap, the match report warns. The generator does not delete or invent text to force the page count down.

## Optional model

Off unless both of these are set:

- `CV_LLM_API_KEY`
- `CV_LLM_BASE_URL` (any OpenAI-compatible base, for example `https://example.com/v1`)

`CV_LLM_MODEL` defaults to `gpt-4o-mini`. The call uses `urllib` from the standard library. There is no SDK dependency.

The request body is the job title and the selected bullet strings. The system prompt contains the rule `use only the facts provided`. Photo path, date of birth, nationality, marital status, email, phone, and the person's name are not included.

The reply must be a JSON array of strings, one per bullet. Each bullet is checked before it replaces the original:

- every number in the reply must appear in the profile
- every word must appear in the profile, or be in a small closed list of glue words (`at`, `for`, `the`, and so on)

A fake employer, a new tool, or a new year fails the check. That bullet is thrown away, the original is kept, and the match report explains why. This check is stricter than "block proper nouns only". A synonym the user never wrote is also rejected. Falling back is the safe outcome. The check is a safeguard, not a proof that the model behaved.

If the key is missing, the HTTP call is not made.

## Outputs

All of these are written under `output/cv/` unless `--cv-dir` is set:

- `CV_<Company>_<Role>_<YYYY-MM-DD>.docx` via `python-docx` (pinned in `requirements.txt`)
- the same stem as Markdown and HTML
- `CV_<Company>_<Role>_<YYYY-MM-DD>_match.md` for covered keywords, gaps, left-out facts, and the double-check notes
- `Cover_<Company>_<Role>_<YYYY-MM-DD>.md` when `--cover-letter` is passed

Characters that do not belong in a file name become underscores.

PDF is optional and local. If `soffice` or `libreoffice` is on `PATH`, the DOCX is converted with:

```bash
soffice --headless --convert-to pdf --outdir output/cv output/cv/CV_....docx
```

If LibreOffice is not installed, the DOCX, Markdown, and HTML are still written. No hosted converter is used.

The cover letter names the vacancy (title and company from the job row) and then quotes the summary and the selected bullets. It does not add enthusiasm, tools, or years from the posting.

## Command

```bash
python scrape.py --cv-interview
python scrape.py --cv 1
python scrape.py --cv 1 --format us_resume
python scrape.py --cv https://example.com/jobs/nurse --format de_lebenslauf --cover-letter
```

`--cv-interview` writes the profile. `--format` is optional. When it is omitted, the job location chooses a preset from the YAML files in `cv_templates/presets/`. Passing `--format` uses that file instead. An unknown id prints the formats currently in the folder.

`--jobs` defaults to `output/jobs.csv`. `--profile` defaults to `profile/cv_profile.yaml`. `--cv-date` sets the date in the file name (default: today).

On a double-click, once `config.yaml` exists and a terminal is attached, the launcher asks:

```text
What do you want to do?
  1. Search for jobs
  2. Make a CV for one of these jobs
  3. I don't have a CV yet - help me make one
```

Enter keeps the old behaviour and searches. Option 2 with no profile offers the interview, then asks for a row. The format question shows the suggestion in brackets; Enter accepts it. A scheduled run has no terminal, so it searches and does not wait for a question. The first run, with no `config.yaml`, still opens the setup wizard.

## Privacy

The profile, the photo, the spreadsheet, and the generated CV stay on this computer. There is no telemetry. The profile and the photo are gitignored. A model receives bullet text only, and only after the user sets their own key and base URL.

## What phase 1 does not do

The interview writes a profile from answers. It does not offer a form, clone the official Europass PDF, paginate like Word, or rewrite the summary. It does not add a skill because the job asked for it. Warnings from the generator are in English even when the CV headings are not.
