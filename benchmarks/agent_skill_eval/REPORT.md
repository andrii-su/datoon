# Agent Skill Evaluation Report

## Goal

Compare agent behavior on the same structured-data analysis tasks with and without the `datoon` skill.

The benchmark uses 3 scenarios and 3 deterministic iterations per scenario:

- `small`: 5 uniform records
- `medium`: 75 uniform records
- `large`: 450 uniform records

Each payload asks the agent to compute exact values: `record_count`, `active_count`, `total_revenue_cents`, `top_region`, `top_category`, and `anomaly_ids`.

## Files

- Payload generator: `benchmarks/agent_skill_eval/generate_payloads.py`
- JSON payloads: `benchmarks/agent_skill_eval/payloads/*.json`
- Expected answers: `benchmarks/agent_skill_eval/expected_answers.json`
- `datoon` reports: `benchmarks/agent_skill_eval/reports/*.report.json`
- Optimized TOON payloads: `benchmarks/agent_skill_eval/toon/*.toon`
- Raw agent outputs: `benchmarks/agent_skill_eval/agent_results.json`

## Method

For every payload, two agents were run:

- `with_skill`: received the `datoon` skill and was instructed to follow the skill workflow.
- `without_skill`: was instructed to use the JSON payload directly and not use `datoon`, TOON, or preconverted files.

Total agent runs: 18

The same expected-answer file was used to score both variants. Scoring compared exact values for all required output fields.

## Payload Token Estimates

These token estimates come from `datoon` conversion reports. They measure payload representation size, not total model usage.

| Scenario | Avg JSON Tokens | Avg TOON Tokens | Avg Savings | Convert |
|---|---|---|---|---|
| large | 17,757.00 | 6,673.00 | 62.42% | 3/3 |
| medium | 2,972.00 | 1,138.00 | 61.71% | 3/3 |
| small | 225.33 | 118.00 | 47.63% | 3/3 |

## Correctness

| Variant | Runs | Correct | Failures | Accuracy |
|---|---|---|---|---|
| with_skill | 9 | 9 | 0 | 100.00% |
| without_skill | 9 | 9 | 0 | 100.00% |

Exact-answer failures: 0

## Agent-Reported Time

The `elapsed_seconds` values below are self-reported by agents. They are useful as directional telemetry but not strict wall-clock measurements from the parent runner.

| Scenario | Variant | Runs | Avg Seconds | Median | Min | Max |
|---|---|---|---|---|---|---|
| large | with_skill | 3 | 0.515517 | 0.762988 | 0.000509 | 0.783055 |
| large | without_skill | 3 | 0.002974 | 0.000738 | 0.000000 | 0.008185 |
| medium | with_skill | 3 | 0.793337 | 0.829030 | 0.710107 | 0.840874 |
| medium | without_skill | 3 | 2.066760 | 0.000280 | 0.000000 | 6.200000 |
| small | with_skill | 3 | 1.202319 | 1.247206 | 1.110000 | 1.249752 |
| small | without_skill | 3 | 0.000406 | 0.000149 | 0.000069 | 0.001000 |

One no-skill medium run reported `6.2s`, while comparable runs reported near-zero values. Treat this as timing noise in agent self-reporting rather than a stable performance signal.

## Observations

- The skill consistently made a conversion decision and produced TOON for all payloads.
- The largest benefit was payload-size reduction: about 62% fewer estimated payload tokens for medium and large inputs.
- Correctness stayed identical in this task: all exact outputs matched the expected answers.
- For small payloads, `datoon` still converted because the generated small payload was uniform and savings exceeded the 15% threshold. A different tiny or non-table JSON would likely be skipped.
- Full model token usage per subagent was not exposed by the multi-agent tool, so this report cannot claim total end-to-end token savings. It reports payload-token savings from `datoon`.

## Conclusion

In this benchmark, using the `datoon` skill did not change answer correctness, but it reduced the structured payload size substantially before the agent consumed it. The practical value is strongest for medium and large uniform arrays.
