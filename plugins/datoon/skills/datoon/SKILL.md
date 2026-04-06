---
name: datoon
description: >
  Smart TOON conversion workflow for structured data in Claude Code.
  Converts JSON-like payloads to TOON only when structure is suitable and token savings are meaningful.
  Use when the user asks to analyze, transform, or reason over structured datasets with an LLM,
  especially when context size or token cost matters.
---

# datoon mode

## Core Rule

Before sending structured payloads to the model:

1. Detect whether payload is a good TOON candidate.
2. Convert only when expected savings are meaningful.
3. Keep JSON when conversion likely hurts clarity or efficiency.

## Trigger Phrases

- `/datoon`
- `datoon mode`
- `convert to TOON`
- `optimize tokens for this JSON`
- `use TOON for this dataset`

## Decision Policy

Convert when all conditions pass:

- payload has at least one uniform object array (table-like records);
- nesting depth is moderate;
- estimated savings are above threshold (default 15%).

Skip conversion when any condition fails:

- deeply nested or highly non-uniform structures;
- tiny payloads with negligible savings;
- free-form text tasks without structured data.

## Execution Workflow

1. Normalize input to valid JSON.
2. Run:
    - `echo '<json>' | datoon --report-stdout`
    - or `datoon input.json -o output.toon --report report.json`
3. Read report:
    - if `decision == "convert"`, pass TOON to model;
    - if `decision == "skip"`, pass normalized JSON.
4. Keep report metadata for observability.

## Reliability Rules

- Never change semantic values or key names.
- Fail loudly for invalid JSON.
- If TOON CLI dependency is unavailable, keep JSON and report fallback reason.
- Use `--force` only for controlled experiments.

## Boundaries

- This skill is for structured data payload optimization, not general prose rewriting.
- For sensitive data, preserve exact fields and avoid unnecessary reformatting outside conversion path.
