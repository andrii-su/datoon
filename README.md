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
- `SKILL.md` draft for agent workflows.

## Quick Start

### 1) Install locally

```bash
python -m pip install -e .
```

### 2) Convert JSON from stdin

```bash
echo '{"users":[{"id":1,"name":"Ada"},{"id":2,"name":"Lin"}]}' | datoon --report-stdout
```

### 3) Convert file input

```bash
datoon ./examples/input.json -o ./examples/output.toon --report ./examples/report.json
```

## Dependencies

`datoon` uses the official TOON CLI through `npx`:

- Node.js with `npx` available in `PATH`;
- network access for first-time package resolution (or a warmed npm cache).

By default it invokes:

```bash
npx --yes @toon-format/cli@3
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

## Next Steps

- Add policy profiles (`strict`, `balanced`, `aggressive`).
- Add optional CSV pre-normalization for tabular sources.
- Add integration wrappers for FastAPI/Celery/Airflow entrypoints.
