# datoon

[![Tests](https://github.com/andrii-su/datoon/actions/workflows/tests.yml/badge.svg)](https://github.com/andrii-su/datoon/actions/workflows/tests.yml)
[![Pre-commit](https://github.com/andrii-su/datoon/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/andrii-su/datoon/actions/workflows/pre-commit.yml)
[![Release](https://github.com/andrii-su/datoon/actions/workflows/release.yml/badge.svg)](https://github.com/andrii-su/datoon/actions/workflows/release.yml)
[![Docs](https://github.com/andrii-su/datoon/actions/workflows/pages.yml/badge.svg)](https://github.com/andrii-su/datoon/actions/workflows/pages.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/github/license/andrii-su/datoon)](./LICENSE)

![datoon banner](assets/datoon-banner.svg)

`datoon` is a pragmatic smart TOON gateway for LLM data workloads: it converts JSON payloads to [TOON](https://github.com/toon-format/toon) only when conversion is likely to improve token efficiency.

## ✨ Why `datoon`

Raw JSON is often verbose in prompts. TOON can save tokens, but blind conversion can also make payloads worse.

`datoon` adds a decision layer so pipelines can:

- ✅ convert when savings are meaningful;
- ✅ skip when structure is a poor TOON fit;
- ✅ report exactly why the decision was made.

## 🌐 Docs Site

- Live docs: [andrii-su.github.io/datoon](https://andrii-su.github.io/datoon/)
- Source: [`docs/`](docs/)

## 🚀 Quick Start

### 1. Install locally

```bash
uv sync
```

Runtime requirement: Python `3.12+`.

### 2. Convert JSON from stdin

```bash
echo '{"users":[{"id":1,"name":"Ada"},{"id":2,"name":"Lin"}]}' | datoon --report-stdout
```

### 3. Convert file input

```bash
datoon ./examples/input.json -o ./examples/output.toon --report ./examples/report.json
```

## 🔌 Claude Code Plugin

Install directly from GitHub:

```bash
claude plugin marketplace add andrii-su/datoon
claude plugin install datoon@datoon
```

Then trigger in-session with prompts like:

- `/datoon`
- `convert this JSON to TOON if it saves tokens`
- `use datoon mode for structured data`

## 📈 Benchmarks

`datoon` includes a local benchmark runner inspired by `caveman/benchmarks/run.py`.

Run:

```bash
PYTHONPATH=src python benchmarks/run.py --dry-run
PYTHONPATH=src python benchmarks/run.py
PYTHONPATH=src python benchmarks/run.py --update-readme
```

### ⚖️ Benchmark Comparison Snapshot

| Scenario | JSON Baseline | Forced TOON | `datoon` Auto |
|---|---:|---:|---:|
| Average tokens | 77 | 50 | 50 |
| Avg token saved | 0.0% | 26.8% | **28.1%** |
| Decision quality | n/a | Converts all | Converts `3/5`, skips harmful cases |

Why auto wins:

- 🧠 it avoids low-benefit/high-risk payloads (`orders-nested`, `mixed-non-uniform`);
- 📉 it keeps the same average token count as forced mode while improving stability;
- 🧾 it always returns a reasoned conversion report.

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

## ⚙️ Decision Model (Auto Mode)

`datoon` currently converts only when:

- payload contains uniform arrays of objects (table-like structures);
- nesting depth is below configured threshold;
- estimated token savings are above configured minimum.

Otherwise it returns normalized JSON unchanged and explains the skip reason.

## 🧰 CLI Flags

- `--force`: bypass gating and minimum savings threshold.
- `--min-savings`: minimum relative savings required (default: `0.15`).
- `--max-depth`: maximum payload depth considered safe for TOON auto-convert (default: `6`).
- `--min-uniform-rows`: minimum rows in uniform object arrays (default: `3`).
- `--report`: write JSON report to a file.
- `--report-stdout`: print JSON report to stderr.

## ✅ Development Checks

Install and run pre-commit hooks:

```bash
uvx pre-commit run --all-files
```

Configured hooks validate Python and Markdown:

- `ruff` + `ruff-format` for Python files;
- `mdformat` for Markdown formatting.

## 🧪 Tests

Install test dependencies:

```bash
uv sync --extra dev
```

Run unit tests:

```bash
pytest -m "not integration"
```

Run integration tests (requires Node.js + `npx`):

```bash
pytest -m integration
```

## 📦 Dependencies

`datoon` uses the official TOON CLI through `npx`:

- Node.js with `npx` available in `PATH`;
- network access for first-time package resolution (or a warmed npm cache).

By default it invokes:

```bash
npx --yes @toon-format/cli@2
```

## 🔒 Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting and response policy.

## 🛡️ Release Safety Checks

Before release, CI validates that all skill mirrors are synchronized:

- `skills/datoon/SKILL.md` (source of truth)
- `SKILL.md`
- `datoon/SKILL.md`
- `plugins/datoon/skills/datoon/SKILL.md`
- `datoon.skill` archive content

Local check:

```bash
python scripts/validate_skill_sync.py
```

## 🧭 Next Steps

- Add policy profiles (`strict`, `balanced`, `aggressive`).
- Add optional CSV pre-normalization for tabular sources.
- Add integration wrappers for FastAPI/Celery/Airflow entrypoints.
