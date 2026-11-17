# Benchmark

Nine fixed searches in `queries.yaml`. Run them before and after a change and compare the summaries. Do not edit the queries unless a prompt says to.

```bash
.venv/bin/python benchmarks/run_benchmark.py --label baseline_before_prompt7
.venv/bin/python benchmarks/run_benchmark.py --label after_prompt7
```

Each run writes `benchmarks/results/<label>/summary.md` and `summary.json`. Raw configs and spreadsheets go under `benchmarks/results/<label>/raw/` and stay out of git. `--offline FIXTURE_DIR` reads canned JSON instead of the network (tests only): `<query id>/<source>.json` or `<source>.json`, a list of rows, or `{"raise": "HTTPError", "code": 429}`.
