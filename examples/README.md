# Example searches

These files are examples. The program does not read them on its own.

A fresh copy of this project has no `config.yaml`. The first time you run `python scrape.py`, or double-click the start file, it asks a few questions and writes `config.yaml` for you.

To try a ready-made search instead, copy one of these files into the project folder:

```bash
cp examples/berlin-software-engineer.yaml config.yaml
```

```bash
cp examples/milan-product-manager.yaml config.yaml
```

Then run `python scrape.py`.

- `berlin-software-engineer.yaml` — software engineer jobs in Berlin, and remote jobs in Germany. Indeed and LinkedIn only.
- `milan-product-manager.yaml` — product and project jobs in Milan, remote jobs in Italy, plus an example list of companies.
