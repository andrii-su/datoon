---
name: datoon
description: Convert structured LLM input data to TOON only when the payload is a good fit and token savings are meaningful.
---

# datoon skill

Use this workflow when a user asks an LLM to process medium/large structured data and token efficiency matters.

## Goal

Convert JSON-like payloads to TOON format safely:

- keep semantic equivalence;
- reduce token count when useful;
- avoid conversion when structure is a poor TOON match.

## When To Apply

Apply when at least one is true:

- prompt includes arrays of records (table-like data);
- payload is clearly JSON and likely large;
- user asks for cost/context optimization.

Do not apply blindly for:

- deeply nested non-uniform payloads;
- tiny payloads where conversion overhead dominates;
- plain text tasks without structured data.

## Execution Steps

1. Normalize input to JSON.
2. Run `datoon` in auto mode.
3. Read conversion report:
   - if `decision == "convert"`, pass TOON to the model;
   - if `decision == "skip"`, pass normalized JSON.
4. Include report metadata in logs for observability.

## CLI Usage

```bash
# stdin -> stdout, with report to stderr
cat payload.json | datoon --report-stdout

# file -> file, with report artifact
datoon payload.json -o payload.toon --report payload.report.json
```

## Reliability Rules

- Use `--force` only for controlled experiments.
- Keep `--min-savings` explicit in production pipelines.
- Fail loudly on invalid JSON.
- Treat missing TOON CLI as an operational dependency issue, not silent success.
