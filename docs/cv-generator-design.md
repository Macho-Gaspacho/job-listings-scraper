# CV generator

Phase 1 is a design plus an offline skeleton. It tailors a CV to one saved job. It can select, reorder, shorten, and rephrase facts the user already wrote. It cannot invent experience, skills, dates, employers, degrees, or certifications.

A missing keyword is a gap. It is written in the match report. It is never copied onto the CV to make the match look better.

Nothing in this feature calls a paid service. The optional model path uses an endpoint the user configures, and it is off until they do.

## Profile

`profile/cv_profile.yaml` is the only source of facts. Copy `profile/cv_profile.example.yaml` and replace every value. The example is safe to commit. The real profile is not.

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
| `gdpr_consent` | Prints the Italian consent sentence only on `it_cv`. |
| `references_on_request` | Prints the UK references line only on `uk_cv`. |
| `document_language` | Stored. Phase 1 does not let it replace the preset's language, so a Lebenslauf stays German. |

Dates are strings the user wrote (`2019-03`, `2014`, `present`). The generator formats them. It does not invent a month when only a year was given.

## Job input

The job comes from one row of `output/jobs.csv` (or `jobs.xlsx`'s sibling CSV). Pass a row number or the URL.

Row `1` is the first job under the header, not the header itself. A URL must match the URL column exactly.

The tailor reads the title, the description, and the language flags. The company and location name the vacancy on the cover letter and in the file name. They are not treated as the user's employers.

## Presets

Presets live in `cv_templates/presets/*.yaml`. Each file sets section order, section titles per language, page size, photo policy (`forbidden`, `optional`, or `customary`), which personal fields are allowed, the date format, and the page cap.

Phase 1 renders the preset's own language. The other language maps are in the file so a later version can switch headings without inventing them.

| Preset | Page | Cap | Photo | Personal fields that can print | Notes |
| --- | --- | --- | --- | --- | --- |
| `us_resume` | Letter | 1, or 2 when the career spans 10 years or more | Forbidden | None | Reverse chronological. Achievement bullets. |
| `uk_cv` | A4 | 2 | Forbidden | None | Summary heading is "Personal statement". References line only if opted in. |
| `de_lebenslauf` | A4 | 2 | Customary, still opt-in | `date_of_birth` only, and only if opted in | Headings: Berufserfahrung, Ausbildung, Kenntnisse. Optional Ort/Datum line. |
| `eu_europass` | A4 | 2 | Optional | `date_of_birth`, `nationality`, if opted in | One CEFR column. Not the official Europass PDF. |
| `it_cv` | A4 | 2 | Optional | `date_of_birth`, if opted in | GDPR sentence only when `gdpr_consent` is true. |
| `fr_cv` | A4 | 2 | Optional | `date_of_birth`, if opted in | Photo and date of birth stay optional. |

`marital_status` is in the profile schema and on no preset. Older templates in several countries asked for it. This generator does not print it unless a future preset lists the field and the user opts in.

The Europass language block shows the single CEFR level from the profile. It does not copy that level into listening, reading, and speaking. That would invent assessments the user did not write.

Photo rules:

- `forbidden`: dropped even when a file is present and `photo.include` is true. Used by `us_resume` and `uk_cv`.
- `optional` and `customary`: included only when `photo.include` is true and the file exists. Customary means readers often expect a photo. It does not mean the file is required. German law (AGG) is why a photo cannot be required; the preset still will not invent one.

### Conventions to double-check

These are ordinary practice, not legal advice, and they vary by industry, employer, and decade. Each preset repeats the relevant warning in the match report.

- **United States.** Photo, date of birth, age, marital status, and nationality are omitted. One page is the usual target; two pages after about ten years. Academic, medical, and federal CVs are often longer. A federal form can ask for data this preset drops. Add that by hand after you read the form.
- **United Kingdom.** Two pages, A4, no photo, no date of birth, is the modern default. Academic CVs differ. The references line does not invent referee names.
- **Germany.** A photo is customary and cannot be demanded. Date of birth is still common and increasingly left off. Nationality and marital status are not in this preset. Public-sector applications sometimes ask for more than this file prints. The signature line is a blank; the city is printed only when `signature.place` is filled in.
- **Europass.** The official template changes. Two pages is a reading target. Date of birth and nationality are optional on the official form. Marital status is not an official Europass field.
- **Italy.** A photo is common. The sentence `Autorizzo il trattamento dei dati personali ai sensi del Regolamento UE 2016/679` is widely used and the wording is not unique. Confirm it before you rely on it.
- **France.** A photo is common and cannot be required. Date of birth is often omitted now. Concours and academic CVs use their own forms.

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
python scrape.py --cv 1 --format us_resume
python scrape.py --cv https://example.com/jobs/nurse --format de_lebenslauf --cover-letter
```

`--format` accepts `us_resume`, `uk_cv`, `de_lebenslauf`, `eu_europass`, `it_cv`, and `fr_cv`.

`--jobs` defaults to `output/jobs.csv`. `--profile` defaults to `profile/cv_profile.yaml`. `--cv-date` sets the date in the file name (default: today).

On a double-click, once `config.yaml` exists and a terminal is attached, the launcher asks:

```text
What do you want to do?
  1. Search for jobs
  2. Make a CV for one of these jobs
```

Enter keeps the old behaviour and searches. A scheduled run has no terminal, so it searches and does not wait for a question. The first run, with no `config.yaml`, still opens the setup wizard.

## Privacy

The profile, the photo, the spreadsheet, and the generated CV stay on this computer. There is no telemetry. The profile and the photo are gitignored. A model receives bullet text only, and only after the user sets their own key and base URL.

## What phase 1 does not do

It does not edit the profile in a form, clone the official Europass PDF, paginate like Word, or rewrite the summary. It does not add a skill because the job asked for it. Warnings from the generator are in English even when the CV headings are not.
