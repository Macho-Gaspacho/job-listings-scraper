# Example searches

These files are examples. The program does not read them on its own.

A fresh copy of this project has no `config.yaml`. The first time you run `python scrape.py`, or double-click the start file, it asks a few questions and writes `config.yaml` for you.

To try a ready-made search instead, copy one of these files into the project folder:

```bash
cp examples/berlin-software-engineer.yaml config.yaml
```

```bash
cp examples/nurse-netherlands.yaml config.yaml
```

Then run `python scrape.py`.

- `accountant-toronto-canada.yaml` — an accountant in Toronto. English and French titles.
- `berlin-software-engineer.yaml` — a software engineer in Berlin, and remote jobs in Germany. Indeed and LinkedIn only.
- `graduate-marketing-spain.yaml` — a first marketing job in Madrid. Senior titles are left out.
- `nurse-netherlands.yaml` — a nurse in Amsterdam, and remote jobs in the Netherlands, including Dutch titles.
- `remote-customer-support-worldwide.yaml` — remote customer support. Remote boards keep worldwide postings. Indeed and LinkedIn are asked for remote jobs in the United States, which you can change.
- `warehouse-worker-poland.yaml` — a warehouse worker in Warsaw, including Polish titles.

The files show an optional `filters` block in comments, except the Madrid file, which turns the level filter on. Salary, job type, language, and visa filters are off until you remove the `#`. A salary minimum keeps jobs that do not state a salary. Language and visa values are guessed from the posting text.

Company career pages are off in every example, and the company list is empty. Add your own employers if you want them. See the address table in [README.md](../README.md).
