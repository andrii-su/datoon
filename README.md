<p align="center">
  <img src="assets/datoon-banner.svg" width="720" />
</p>

<h1 align="center">datoon</h1>

<p align="center">
  <strong>smart structured-data→TOON gateway — converts only when it actually saves tokens</strong>
</p>

<p align="center">
  <a href="https://github.com/andrii-su/datoon/actions/workflows/tests.yml"><img src="https://github.com/andrii-su/datoon/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/andrii-su/datoon/actions/workflows/pre-commit.yml"><img src="https://github.com/andrii-su/datoon/actions/workflows/pre-commit.yml/badge.svg" alt="Pre-commit"></a>
  <a href="https://github.com/andrii-su/datoon/actions/workflows/release.yml"><img src="https://github.com/andrii-su/datoon/actions/workflows/release.yml/badge.svg" alt="Release"></a>
  <a href="https://pypi.org/project/datoon/"><img src="https://img.shields.io/pypi/v/datoon?color=0EA5E9" alt="PyPI"></a>
  <a href="https://img.shields.io/badge/python-3.12%2B-3776AB"><img src="https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/andrii-su/datoon" alt="License: MIT"></a>
</p>

<p align="center">
  <a href="#before--after">Before/After</a> •
  <a href="#install">Install</a> •
  <a href="#what-you-get">What You Get</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#benchmarks">Benchmarks</a> •
  <a href="./INSTALL.md">Full install guide</a>
</p>

______________________________________________________________________

Raw structured data is often verbose in LLM prompts. [TOON](https://github.com/toon-format/toon) can save tokens — but blind conversion can also make payloads *worse*. `datoon` adds a decision layer: convert when structure and savings justify it, skip when they don't, and always explain why.

Supports **JSON, CSV, JSONL, YAML, XML, Parquet, Avro, ORC, Excel, and Apple Numbers** — auto-detected from file extension.

## Before / After

<table>
<tr>
<td width="50%">

### JSON in the prompt (42 tokens)

```json
{"users":[
  {"id":1,"name":"Ada","role":"admin"},
  {"id":2,"name":"Lin","role":"analyst"},
  {"id":3,"name":"Grace","role":"viewer"}
]}
```

</td>
<td width="50%">

### datoon converts → TOON (35 tokens)

```toon
users[3]{id,name,role}:
  1,Ada,admin
  2,Lin,analyst
  3,Grace,viewer
```

```json
{"decision":"convert","reason":"Estimated savings 16.67% (threshold 15.00%)."}
```

</td>
</tr>
<tr>
<td>

### CSV from a data pipeline (40 tokens as JSON)

```csv
id,name,role
1,Ada,admin
2,Lin,analyst
3,Grace,viewer
```

</td>
<td>

### datoon auto-converts → TOON (34 tokens)

```bash
datoon data.csv --report-stdout
```

Same rows as TOON. Zero JSON serialization in your code.

</td>
</tr>
<tr>
<td>

### Non-uniform payload (14 tokens)

```json
{"config":{"debug":true},"tags":["a","b"]}
```

</td>
<td>

### datoon skips → keeps JSON

```json
{"decision":"skip","reason":"No uniform object arrays found with at least 3 rows."}
```

No silent corruption.

</td>
</tr>
</table>

**Same data. Right format. Always explained.**

Token counts on this page come from `tiktoken:o200k_base`. Three rows barely clear the 15% threshold; savings grow with the table. Uniform payloads in the [benchmarks](#benchmarks) save 22–28%, and 100–300-row query results cost Claude about half the input tokens of JSON objects.

> [!IMPORTANT]
> datoon saves **payload tokens** — the structured data portion of your prompt. Token savings depend on payload shape: uniform tabular data converts well; deeply nested or non-uniform structures are skipped. Every decision includes a reason so pipelines can log, debug, and trust the outcome.

## Install

```bash
# core (JSON, CSV, JSONL, XML — no extra deps)
uv add datoon
pip install datoon

# with YAML support
pip install "datoon[yaml]"

# with Excel support
pip install "datoon[excel]"

# with Parquet / ORC / Avro support
pip install "datoon[columnar]"

# with Apple Numbers support
pip install "datoon[numbers]"

# with tiktoken-based token counting
pip install "datoon[tokens]"

# with Claude token counting (Anthropic API) / Hugging Face tokenizers
pip install "datoon[claude]"
pip install "datoon[hf]"

# with MCP server
pip install "datoon[mcp]"

# everything
pip install "datoon[all]"
```

Requires Python 3.12+. TOON conversion is pure Python (official [`toon-format`](https://pypi.org/project/toon-format/) encoder, installed automatically) — no Node.js needed.

For Claude Code plugin, Codex, and MCP config → [**INSTALL.md**](./INSTALL.md).

## What You Get

| | What |
|---|---|
| `datoon` **CLI** | Auto-gate any supported format → TOON from terminal or scripts |
| **Python API** | `convert_json_for_llm()` + `read_tabular()` for any LLM pipeline |
| **MCP Server** | `convert_json`, `convert_text`, `analyze_json` tools for Claude Desktop, Cursor, Windsurf |
| **Claude Code Plugin** | `/datoon` in-session trigger, installs from GitHub in one command |
| **Codex Plugin** | Marketplace plugin — structured-data mode for Codex |

### Supported input formats

| Format | Extension | Extra needed |
|---|---|---|
| JSON | `.json` | — |
| JSONL | `.jsonl`, `.ndjson` | — |
| CSV | `.csv` | — |
| XML | `.xml` | — |
| YAML | `.yaml`, `.yml` | `datoon[yaml]` |
| Excel | `.xlsx`, `.xls` | `datoon[excel]` |
| Parquet | `.parquet` | `datoon[columnar]` |
| Avro | `.avro` | `datoon[columnar]` |
| ORC | `.orc` | `datoon[columnar]` |
| Apple Numbers | `.numbers` | `datoon[numbers]` |

## How It Works

1. **Detect format** — from `--format` flag, file extension, or default to JSON for stdin
1. **Read + normalize** — parse source into list of row dicts; serialize to compact JSON
1. **Analyze structure** — uniform object arrays? acceptable depth? minimum rows?
1. **Gate early** — non-candidates skip before any TOON encoding
1. **Convert + estimate** — TOON encoder runs in-process, token savings calculated
1. **Gate savings** — below threshold → return JSON; above → return TOON with report

Every path returns a `ConversionReport` with `decision`, `reason`, token estimates, and the `tokenizer` that produced them. Pipelines never get silent surprises.

## Choosing a tokenizer

Token estimates drive the savings gate, so pick the counter that fits the job. Pass one spec with `--tokenizer`, the `tokenizer` MCP argument, `ConversionConfig(tokenizer=...)`, or the `DATOON_TOKENIZER` environment variable; in Python any callable `str -> int` works too. The MCP tools accept only local counters (`auto`, `chars`, `tiktoken`) per call; `claude:` and `hf:` reach the network, so only the server operator can enable them through `DATOON_TOKENIZER`.

| Spec | Counts with | Needs |
|---|---|---|
| `auto` (default) | `tiktoken:o200k_base` when tiktoken is installed, else `chars:3` | — |
| `chars` / `chars:<N>` | `ceil(len(text) / N)`, default `N = 3` | — |
| `tiktoken` / `tiktoken:<encoding>` | tiktoken, default `o200k_base` | `datoon[tokens]` |
| `claude:<model-id>` | Anthropic token counting API for that model | `datoon[claude]`, Anthropic credentials (e.g. `ANTHROPIC_API_KEY`) |
| `hf:<repo-id>` | Hugging Face `tokenizers` tokenizer from the Hub | `datoon[hf]` |
| a callable (Python) | your own function, reported as `custom` | — |

Use the local counters (`auto`, `chars`, `tiktoken`) to gate payloads at runtime: they are fast and run locally (tiktoken fetches its encoding file once on first use). Use `claude:` or `hf:` in benchmarks and evals where counts for the target model matter. `claude:` makes network calls, and Anthropic documents its counts as estimates. Only `auto` falls back silently: an explicit spec with a missing package fails with an error that names the extra to install, and `claude:` without Anthropic credentials fails too. Every report records the resolved name in `tokenizer`.

______________________________________________________________________

## Quick Start

**JSON (stdin):**

```bash
echo '{"users":[{"id":1,"name":"Ada"},{"id":2,"name":"Lin"},{"id":3,"name":"Grace"}]}' | datoon --report-stdout
```

**CSV (auto-detected from extension):**

```bash
datoon data.csv --report-stdout
```

**JSONL:**

```bash
datoon data.jsonl -o output.toon
```

**YAML (requires `datoon[yaml]`):**

```bash
datoon data.yaml --report-stdout
```

**Parquet (requires `datoon[columnar]`):**

```bash
datoon data.parquet --report ./report.json
```

**Explicit format override:**

```bash
datoon --format csv < data.csv --report-stdout
```

**Force conversion (bypass gating — for experiments):**

```bash
datoon data.json --force --report-stdout
```

______________________________________________________________________

## Python API

**JSON conversion:**

```python
from datoon import convert_json_for_llm, ConversionConfig, DatoonError

config = ConversionConfig(min_savings_ratio=0.15, max_depth=6, min_uniform_rows=3)

try:
    outcome = convert_json_for_llm(raw_json, config)
except DatoonError as exc:
    raise

# outcome.payload_text  — TOON or original JSON
# outcome.report.decision  — "convert" | "skip"
# outcome.report.reason    — human-readable explanation
send_to_model(outcome.payload_text)
```

**Any format via `read_tabular`:**

```python
import json
from pathlib import Path
from datoon import read_tabular, convert_json_for_llm, ConversionConfig

# text formats: csv, jsonl, yaml, xml
rows = read_tabular("csv", text=csv_string)

# binary formats: excel, parquet, orc, avro, numbers
rows = read_tabular("parquet", path=Path("data.parquet"))

json_text = json.dumps(rows, separators=(",", ":"))
outcome = convert_json_for_llm(json_text, ConversionConfig())
send_to_model(outcome.payload_text)
```

**Structure-only analysis:**

```python
from datoon.analyzer import analyze_payload
from datoon.models import ConversionConfig

analysis = analyze_payload(parsed_data, ConversionConfig())
print(analysis.is_candidate, analysis.reason)
```

______________________________________________________________________

## MCP Server

<!-- mcp-name: io.github.andrii-su/datoon -->

`datoon` ships an [MCP](https://modelcontextprotocol.io) server with three tools:

| Tool | Description |
|---|---|
| `convert_json` | Full JSON conversion with policy gating |
| `convert_text` | Converts CSV, YAML, XML, or JSONL text with policy gating |
| `analyze_json` | Structure analysis only — no conversion |

**Claude Desktop / Cursor / Windsurf config:**

```json
{
  "mcpServers": {
    "datoon": {
      "command": "uvx",
      "args": ["--from", "datoon[mcp]", "datoon", "mcp"]
    }
  }
}
```

**Run locally:**

```bash
datoon mcp     # or the standalone script: datoon-mcp
```

Listed on the [MCP Registry](https://registry.modelcontextprotocol.io), [Smithery](https://smithery.ai), and [Glama](https://glama.ai). See [MARKETPLACES.md](./MARKETPLACES.md).

______________________________________________________________________

## Claude Code Plugin

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

## CLI Reference

| Flag | Default | Description |
|---|---|---|
| `--format` | auto | Input format: `json`, `csv`, `jsonl`, `yaml`, `xml`, `excel`, `parquet`, `avro`, `orc`, `numbers` |
| `--force` | `false` | Bypass gating and minimum savings threshold |
| `--min-savings` | `0.15` | Minimum relative token savings required |
| `--max-depth` | `6` | Maximum nesting depth for auto-conversion |
| `--min-uniform-rows` | `3` | Minimum rows in uniform object arrays |
| `--sheet` | `0` | Worksheet index for Excel / Numbers input |
| `--table` | `0` | Table index within a Numbers sheet |
| `--tokenizer <spec>` | `$DATOON_TOKENIZER`, else `auto` | Token counter for estimates — see [Choosing a tokenizer](#choosing-a-tokenizer) |
| `--report <path>` | — | Write JSON conversion report to file |
| `--report-stdout` | — | Print JSON conversion report to stderr |
| `-o <path>` | stdout | Output file path |
| `--version` | — | Print version and exit |

Format is auto-detected from file extension. Use `--format` to override or when reading from stdin.

______________________________________________________________________

## Benchmarks

```bash
PYTHONPATH=src python benchmarks/run.py --dry-run
PYTHONPATH=src python benchmarks/run.py --tokenizer tiktoken
PYTHONPATH=src python benchmarks/run.py --formats --tokenizer tiktoken --update-readme
```

Both tables below are counted with `tiktoken:o200k_base`. The `chars` counter is a length heuristic and reports larger savings on the same payloads.

### Auto mode against forced conversion

Forced conversion makes two of the five payloads larger (`orders-nested`, `mixed-non-uniform`). Auto mode skips those two, converts the other three, and returns a reason for every decision.

<!-- BENCHMARK-TABLE-START -->

| Dataset | JSON | TOON (forced) | Raw Saved | Auto | Auto Tokens | Auto Saved |
|---|---:|---:|---:|---|---:|---:|
| users-small | 54 | 40 | 25.9% | convert | 40 | 25.9% |
| events-medium | 219 | 162 | 26.0% | convert | 162 | 26.0% |
| orders-nested | 106 | 116 | -9.4% | skip | 106 | 0.0% |
| mixed-non-uniform | 35 | 47 | -34.3% | skip | 35 | 0.0% |
| metrics-wide | 142 | 103 | 27.5% | convert | 103 | 27.5% |
| **Average** | **111** | **94** | **7.1%** | **3/5 convert** | **89** | **15.9%** |

*Forced conversion succeeded for 5/5 payloads.*

<!-- BENCHMARK-TABLE-END -->

### Format conversion benchmark

Token savings when converting from common structured formats (CSV, JSONL, XML, YAML).
Baseline is the JSON representation of the same data — what an LLM would receive without datoon.

<!-- FORMAT-BENCHMARK-TABLE-START -->

| Dataset | Format | JSON Tokens | TOON (forced) | Auto | Auto Tokens | Auto Saved |
|---|---|---:|---:|---|---:|---:|
| users-csv | csv | 51 | 39 | convert | 39 | 23.5% |
| events-jsonl | jsonl | 216 | 161 | convert | 161 | 25.5% |
| catalog-xml | xml | 94 | 73 | convert | 73 | 22.3% |
| metrics-yaml | yaml | 139 | 102 | convert | 102 | 26.6% |
| **Average** | — | **125** | **94** | **4/4 convert** | **94** | **24.5%** |

*Forced conversion succeeded for 4/4 payloads.*

<!-- FORMAT-BENCHMARK-TABLE-END -->

### Reading accuracy

Fewer tokens only help if the model still reads the data correctly. [`benchmarks/format_eval/`](benchmarks/format_eval/) gives a Claude model the same query result as JSON objects, a markdown table and TOON, then asks six questions per table with answers computed in Python (row count, cell lookup, filtered count, maximum, difference, NULL count).

24 synthetic tables of 100–300 rows and 4–30 columns, one API call per table and format. Input tokens are real API usage.

| Model | Format | Correct answers | 95% interval | Input tokens vs JSON objects |
|---|---|---:|---|---:|
| Claude Sonnet 5.5 | JSON objects | 142/144 (98.6%) | 95.1–99.6% | 100% |
| Claude Sonnet 5.5 | markdown | 142/144 (98.6%) | 95.1–99.6% | 60% |
| Claude Sonnet 5.5 | TOON | 143/144 (99.3%) | 96.2–99.9% | 50% |
| Claude Haiku 5.5 | JSON objects | 134/144 (93.1%) | 87.7–96.2% | 100% |
| Claude Haiku 5.5 | markdown | 136/144 (94.4%) | 89.4–97.2% | 60% |
| Claude Haiku 5.5 | TOON | 130/138 (94.2%) | 89.0–97.0% | 50% |

The intervals overlap: these runs show no accuracy difference between formats, and TOON halves the input tokens. One Haiku TOON reply was cut off at the output limit, so its six answers are not graded. Sonnet is close to the ceiling on this set, so a 1–2 point gap between formats would go unseen.

An earlier with-skill / without-skill agent comparison is kept in [`benchmarks/agent_skill_eval/`](benchmarks/agent_skill_eval/REPORT.md); its token figures predate the selectable tokenizers.

______________________________________________________________________

## Development

Contributor workflow: [CONTRIBUTING.md](./CONTRIBUTING.md). Maintainer/agent notes: [CLAUDE.md](./CLAUDE.md).

**Setup:**

```bash
uv sync --extra dev
uvx pre-commit install
```

**Tests:**

```bash
pytest
```

**Skill sync + plugin metadata:**

```bash
python scripts/validate_skill_sync.py
python scripts/validate_plugin_metadata.py
```

______________________________________________________________________

## Links

- [INSTALL.md](./INSTALL.md) — full install matrix, all targets, per-agent detail
- [CONTRIBUTING.md](./CONTRIBUTING.md) — contributor workflow
- [CLAUDE.md](./CLAUDE.md) — maintainer guide for agents
- [CHANGELOG.md](./CHANGELOG.md) — release history
- [SECURITY.md](./SECURITY.md) — vulnerability reporting
- [Live docs](https://andrii-su.github.io/datoon/) — `docs/`
- [Issues](https://github.com/andrii-su/datoon/issues) — bugs, features, questions

______________________________________________________________________

## License

MIT
