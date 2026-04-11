# datoon

[![Tests](https://github.com/andrii-su/datoon/actions/workflows/tests.yml/badge.svg)](https://github.com/andrii-su/datoon/actions/workflows/tests.yml)
[![Pre-commit](https://github.com/andrii-su/datoon/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/andrii-su/datoon/actions/workflows/pre-commit.yml)
[![Release](https://github.com/andrii-su/datoon/actions/workflows/release.yml/badge.svg)](https://github.com/andrii-su/datoon/actions/workflows/release.yml)
[![Docs](https://github.com/andrii-su/datoon/actions/workflows/pages.yml/badge.svg)](https://github.com/andrii-su/datoon/actions/workflows/pages.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/github/license/andrii-su/datoon)](./LICENSE)

![datoon banner](assets/datoon-banner.svg)

`datoon` is a pragmatic smart TOON gateway for LLM data workloads: it converts JSON payloads to [TOON](https://github.com/toon-format/toon) only when conversion is likely to improve token efficiency.

Raw JSON is often verbose in prompts. TOON can save tokens, but blind conversion can also make payloads worse. `datoon` adds a decision layer so pipelines can convert when savings are meaningful, skip when structure is a poor TOON fit, and always report exactly why the decision was made.

______________________________________________________________________

## Contents

- [Setup](#-setup)
- [Install](#-install)
- [Quick Start](#-quick-start)
- [Python API](#-python-api)
- [MCP Server](#-mcp-server)
- [Claude Code Plugin](#-claude-code-plugin)
- [CLI Reference](#-cli-reference)
- [Benchmarks](#-benchmarks)
- [Development](#-development)

______________________________________________________________________

## ⚡ Setup

One-command setup — installs all dependencies and registers `datoon` globally so it's available in any terminal:

```bash
./setup.sh
```

What it does:

1. Checks Python 3.12+ (fails fast if missing)
1. Installs `uv` if not present
1. Warns if Node.js is missing (required for TOON conversion)
1. Runs `uv sync --extra dev`
1. Registers the `datoon` CLI globally via `uv tool install --editable .`
1. Adds `~/.local/bin` to your shell profile if needed

After setup:

```bash
datoon --help
echo '{"users":[{"id":1,"name":"Ada"}]}' | datoon --report-stdout
```

______________________________________________________________________

## 📦 Install

```bash
# via uv (recommended)
uv add datoon

# via pip
pip install datoon

# with optional tiktoken-based token counting
pip install "datoon[tokens]"

# with MCP server support
pip install "datoon[mcp]"
```

Requires Python `3.12+`. TOON conversion requires Node.js with `npx` in `PATH`.

______________________________________________________________________

## 🚀 Quick Start

**stdin:**

```bash
echo '{"users":[{"id":1,"name":"Ada"},{"id":2,"name":"Lin"}]}' | datoon --report-stdout
```

**file:**

```bash
datoon ./input.json -o ./output.toon --report ./report.json
```

**force conversion:**

```bash
datoon ./input.json --force --report-stdout
```

______________________________________________________________________

## 🐍 Python API

```python
from datoon import convert_json_for_llm, ConversionConfig, DatoonError

config = ConversionConfig(
    min_savings_ratio=0.15,   # skip if savings below 15%
    max_depth=6,              # skip if nesting deeper than 6
    min_uniform_rows=3,       # require at least 3 uniform rows
    toon_cli_timeout=30,      # seconds before CLI call is aborted
    force=False,
)

try:
    outcome = convert_json_for_llm(raw_json, config)
except DatoonError as exc:
    print(f"conversion failed: {exc}")
    raise

# outcome.payload_text — TOON or original JSON depending on decision
# outcome.report.decision — "convert" | "skip"
# outcome.report.reason — human-readable explanation
# outcome.report.savings_ratio — float, e.g. 0.281
send_to_model(outcome.payload_text)
```

**Structure-only analysis (no Node.js required):**

```python
from datoon.analyzer import analyze_payload
from datoon.models import ConversionConfig

analysis = analyze_payload(parsed_data, ConversionConfig())
print(analysis.is_candidate, analysis.reason)
```

______________________________________________________________________

## 🔌 MCP Server

`datoon` ships an [MCP](https://modelcontextprotocol.io) server with two tools:

| Tool | Description |
|---|---|
| `convert_json` | Full conversion with policy gating |
| `analyze_json` | Structure analysis only — no Node.js needed |

**Run locally:**

```bash
datoon-mcp
```

**Claude Desktop / Cursor / Windsurf config:**

```json
{
  "mcpServers": {
    "datoon": {
      "command": "uvx",
      "args": ["datoon[mcp]", "datoon-mcp"]
    }
  }
}
```

______________________________________________________________________

## 🧩 Claude Code Plugin

Install directly from GitHub:

```bash
claude plugin marketplace add andrii-su/datoon
claude plugin install datoon@datoon
```

Trigger in-session:

```
/datoon
convert this JSON to TOON if it saves tokens
use datoon mode for structured data
```

______________________________________________________________________

## ⚙️ CLI Reference

| Flag | Default | Description |
|---|---|---|
| `--force` | `false` | Bypass gating and minimum savings threshold |
| `--min-savings` | `0.15` | Minimum relative token savings required |
| `--max-depth` | `6` | Maximum nesting depth for auto-conversion |
| `--min-uniform-rows` | `3` | Minimum rows in uniform object arrays |
| `--timeout` | `30` | Seconds before TOON CLI call is aborted |
| `--report <path>` | — | Write JSON conversion report to file |
| `--report-stdout` | — | Print JSON conversion report to stderr |
| `-o <path>` | stdout | Output file path |

______________________________________________________________________

## 📈 Benchmarks

```bash
PYTHONPATH=src python benchmarks/run.py --dry-run
PYTHONPATH=src python benchmarks/run.py
PYTHONPATH=src python benchmarks/run.py --update-readme
```

### Why auto mode outperforms forced conversion

Auto mode avoids low-benefit and high-risk payloads (`orders-nested`, `mixed-non-uniform`) while matching forced TOON's average token count on suitable ones. Every decision comes with a reasoned report.

| Scenario | JSON Baseline | Forced TOON | `datoon` Auto |
|---|---:|---:|---:|
| Average tokens | 77 | 50 | 50 |
| Avg token saved | 0.0% | 26.8% | **28.1%** |
| Decision quality | n/a | Converts all | Converts `3/5`, skips harmful cases |

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

______________________________________________________________________

## 🛠 Development

**Setup:**

```bash
uv sync --extra dev
uvx pre-commit install
```

**Tests:**

```bash
# unit only
pytest -m "not integration"

# with integration (requires Node.js + npx)
pytest
```

**Pre-commit:**

```bash
uvx pre-commit run --all-files
```

**Skill sync check:**

```bash
python scripts/validate_skill_sync.py
```

______________________________________________________________________

## 🌐 Docs

- Live site: [andrii-su.github.io/datoon](https://andrii-su.github.io/datoon/)
- Source: [`docs/`](docs/)

______________________________________________________________________

## 🔒 Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting and response policy.
