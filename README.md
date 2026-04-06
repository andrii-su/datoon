# datoon

`datoon` is a pragmatic bootstrap for a "smart TOON gateway": it converts JSON payloads to [TOON](https://github.com/toon-format/toon) only when conversion is likely to improve token efficiency for LLM prompts.

## Why

For LLM workloads, raw JSON is often verbose. TOON can reduce prompt size, but conversion is not always beneficial. `datoon` adds a simple decision layer so pipelines can:

- convert when savings are meaningful;
- skip when structure is a poor TOON fit;
- report exactly why a decision was made.

## What Is Included

- Python package with typed modules and explicit error handling.
- CLI command: `datoon`.
- Auto-gating heuristic for TOON suitability.
- Conversion report with token estimates and savings ratio.
- Claude Code plugin metadata and a packaged `datoon.skill`.

## Quick Start

### 1) Install locally

```bash
python -m pip install -e .
```

Runtime requirement: Python `3.12+`.

### 2) Convert JSON from stdin

```bash
echo '{"users":[{"id":1,"name":"Ada"},{"id":2,"name":"Lin"}]}' | datoon --report-stdout
```

### 3) Convert file input

```bash
datoon ./examples/input.json -o ./examples/output.toon --report ./examples/report.json
```

## Development Checks

Install and run pre-commit hooks:

```bash
python -m pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Configured hooks validate Python and Markdown:

- `ruff` + `ruff-format` for Python files.
- `mdformat` for Markdown formatting.

## Claude Code Setup

Install directly from GitHub:

```bash
claude plugin marketplace add andrii-su/datoon
claude plugin install datoon@datoon
```

Then trigger in session with prompts like:

- `/datoon`
- `convert this JSON to TOON if it saves tokens`
- `use datoon mode for structured data`

## Dependencies

`datoon` uses the official TOON CLI through `npx`:

- Node.js with `npx` available in `PATH`;
- network access for first-time package resolution (or a warmed npm cache).

By default it invokes:

```bash
npx --yes @toon-format/cli@2
```

## Decision Model (Auto Mode)

`datoon` currently converts only when:

- payload contains uniform arrays of objects (table-like structures);
- nesting depth is below configured threshold;
- estimated token savings are above configured minimum.

Otherwise it returns normalized JSON unchanged and explains the skip reason.

## CLI Flags

- `--force`: bypass gating and minimum savings threshold.
- `--min-savings`: minimum relative savings required (default: `0.15`).
- `--max-depth`: maximum payload depth considered safe for TOON auto-convert (default: `6`).
- `--min-uniform-rows`: minimum rows in uniform object arrays (default: `3`).
- `--report`: write JSON report to a file.
- `--report-stdout`: print JSON report to stderr.

## Benchmarks

`datoon` includes a local benchmark runner inspired by `caveman/benchmarks/run.py`.

Run:

```bash
PYTHONPATH=src python benchmarks/run.py --dry-run
PYTHONPATH=src python benchmarks/run.py
PYTHONPATH=src python benchmarks/run.py --update-readme
```

<!-- BENCHMARK-TABLE-START -->

| Dataset | JSON | TOON (forced) | Raw Saved | Auto | Auto Tokens | Auto Saved |
|---|---:|---:|---:|---|---:|---:|
| users-small | 42 | 23 | 45.2% | convert | 23 | 45.2% |
| events-medium | 148 | 84 | 43.2% | convert | 84 | 43.2% |
| orders-nested | 70 | 69 | 1.4% | skip | 70 | 0.0% |
| mixed-non-uniform | 26 | 28 | -7.7% | skip | 26 | 0.0% |
| metrics-wide | 100 | 48 | 52.0% | convert | 48 | 52.0% |
| **Average** | **77** | **50** | **26.8%** | **3/5 convert** | **50** | **28.1%** |

*Forced conversion succeeded for 5/5 payloads.*

<!-- BENCHMARK-TABLE-END -->

## Next Steps

- Add policy profiles (`strict`, `balanced`, `aggressive`).
- Add optional CSV pre-normalization for tabular sources.
- Add integration wrappers for FastAPI/Celery/Airflow entrypoints.
