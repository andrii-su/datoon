# Format reading benchmark

Can the JSON objects that an MCP `run_sql` tool returns today be replaced by a
more compact serialization without losing reading accuracy? This harness
gives a Claude model the same tabular query result in five serializations and
measures how accurately the model answers questions about it, and what each
serialization costs in input tokens.

## What it measures

| Format | Shape |
| ---------- | ------------------------------------------------------------ |
| `objects` | compact JSON `{"columns": [...], "rows": [{...}, ...]}` |
| `arrays` | compact JSON `{"columns": [...], "rows": [[...], ...]}` |
| `toon` | `toon_format.encode({"rows": rows})` |
| `markdown` | pipe table, `NULL` for missing values, `\|` escaped |
| `csv` | header row, `NULL` for missing values (not an empty field) |

Tables are synthetic and deterministic (`datasets.py`, seeded
`random.Random`): a unique `row_id` key (`r-0001`, ...) plus analytics-like
columns that cycle through category, unique integer, nullable integer, float,
ISO date, text (sometimes with a comma), boolean and ISO timestamp. Default
shapes (rows x columns): 20x4, 20x11, 100x4, 100x11, 100x30, 300x4, 300x10;
two seeds per shape.

Each table gets six questions with gold answers computed in Python
(`questions.py`), the same questions for every format:

| Kind | Question |
| -------------- | ---------------------------------------------------------- |
| `row_count` | number of rows |
| `lookup` | value of one column in a row from the middle or end |
| `filter_count` | rows where a category column equals a value |
| `argmax` | `row_id` of the row with the largest unique integer |
| `diff` | an integer column in one row minus the same in another |
| `null_count` | NULL values in the nullable column |

One Messages API call per (table, format, repeat). The system prompt asks for
one JSON object mapping question ids to answers; the user message holds the
table inside `<table format="...">...</table>` and the numbered questions.
`temperature` and `thinking` are not sent unless `--thinking disabled` is
given, so the model's defaults apply.

## How to run

Look at the plan first. `--dry-run` builds every prompt, prints the number of
calls, per-format payload size and a local token estimate, and one rendered
prompt per format for the smallest table. It makes no API call:

```bash
uv run --extra claude python -m benchmarks.format_eval.run \
  --model claude-haiku-5-5 --dry-run
```

Then run it for real. The `anthropic` SDK reads credentials from the
environment (for example `ANTHROPIC_API_KEY`); the harness never reads or logs
them:

```bash
uv run --extra claude python -m benchmarks.format_eval.run \
  --model claude-haiku-5-5
```

Options: `--repeats` (default 1), `--seeds` (default 2), `--shapes 20x4,100x11`,
`--formats objects,toon`, `--max-tokens` (default 8000), `--concurrency`
(default 4), `--thinking default|disabled`, `--out PATH` (default
`benchmarks/results/format_eval/<model>-<UTC timestamp>.json`, git-ignored).

A pilot run that keeps the cost small:

```bash
uv run --extra claude python -m benchmarks.format_eval.run \
  --model claude-haiku-5-5 --shapes 20x4,100x11 --seeds 1
```

Rate-limit, overload and connection errors are retried up to 4 times with
exponential backoff (2, 4, 8, 16 s); the SDK's own retries are off. Any other
error is recorded on that call and the run continues.

## What the numbers mean

The result JSON has `meta` (model, settings, timestamps, datoon version,
total real input/output tokens, call and error counts), `calls` (one record
per call: real `usage` tokens, latency, `stop_reason`, raw reply, parsed
answers, per-question correctness) and `summary`. The same summary prints as
text tables:

- **accuracy** per format, with a 95% Wilson interval, per format x question
  kind, and per format x shape;
- **mean in tok**: mean real `usage.input_tokens` per call, including the
  system prompt and questions, not only the table;
- **vs objects**: input tokens of the format divided by `objects` input
  tokens, over the same (table, repeat) pairs; below 1 is cheaper;
- **parse err**: replies with no decodable JSON object (all six answers count
  as wrong); **max_tokens**: replies cut off by `--max-tokens` before a
  parseable answer; **errors**: calls that failed at the API. Cut-off and
  failed calls are left out of accuracy and token means: they measure the
  harness limit or the API, not how well the format is read.

The plan's token figures come from the local `auto` tokenizer
(`tiktoken:o200k_base` or a character heuristic), not Claude's tokenizer. Use
them to size a run; use the `usage` numbers in the result to compare formats.

## Limits

- Synthetic data: no real query results, no long free text, no nested values.
- Single-turn question answering, not agent behaviour: it does not measure
  whether a model picks the right follow-up query or copies values into later
  steps correctly.
- Small samples give wide intervals. A default run (14 tables, 1 repeat)
  yields 84 graded answers per format; at 90% accuracy the 95% Wilson
  interval is about 82% to 95%. Differences of a few points between formats
  need more seeds or repeats before they mean anything.
- With thinking on by default (Claude Haiku 5.5 runs adaptive thinking unless
  told otherwise), thinking tokens count against `--max-tokens`; watch the
  `max_tokens` column and raise the limit or pass `--thinking disabled` where
  the model accepts it.

## Recorded runs (2026-11-11)

Synthetic tables, one repeat, six tables per shape, shapes 100x11, 100x30,
300x4 and 300x10 (24 tables, 144 graded answers per format). Token ratios
are real `usage.input_tokens`. Raw result files are not committed.

| Model | Format | Accuracy | 95% CI | Input tokens vs objects |
|---|---|---:|---|---:|
| `claude-haiku-5-5` | objects | 93.1% (134/144) | 87.7–96.2% | 1.00 |
| | markdown | 94.4% (136/144) | 89.4–97.2% | 0.60 |
| | toon | 94.2% (130/138) | 89.0–97.0% | 0.50 |
| | arrays | 92.0% (127/138) | 86.3–95.5% | 0.51 |
| | csv | 92.4% (133/144) | 86.8–95.7% | 0.48 |
| `claude-sonnet-5-5` | objects | 98.6% (142/144) | 95.1–99.6% | 1.00 |
| | markdown | 98.6% (142/144) | 95.1–99.6% | 0.60 |
| | toon | 99.3% (143/144) | 96.2–99.9% | 0.50 |

On Haiku one `arrays` and one `toon` reply were cut off by the output limit
and left out (138 answers). The Sonnet run covered three formats only.

Reading of these numbers: the intervals overlap for every pair of formats on
both models, so the runs show no accuracy difference between formats; they do
show that the compact formats cost about half the input tokens of JSON
objects. Every miss was a count over the whole table (rows matching a filter,
NULL values, one argmax); row count, single-cell lookup and the difference
between two rows were answered correctly in every format on both models.
