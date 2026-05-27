# datoon Skill

Smart TOON conversion workflow for structured data in AI-agent sessions.

The skill tells the agent to:

1. inspect structured JSON-like payloads;
1. convert only when the payload is table-like and savings are meaningful;
1. keep JSON when conversion would hurt clarity or efficiency;
1. preserve semantic values and key names exactly.

## Trigger Phrases

- `/datoon`
- `datoon mode`
- `convert to TOON`
- `optimize tokens for this JSON`
- `use TOON for this dataset`

## What It Does

For suitable uniform object arrays, `datoon` can reduce prompt payload size substantially. In the saved agent evaluation artifacts:

| Scenario | Avg JSON Tokens | Avg TOON Tokens | Avg Payload Saved |
|---|---:|---:|---:|
| small | 225.33 | 118.00 | 47.63% |
| medium | 2,972.00 | 1,138.00 | 61.71% |
| large | 17,757.00 | 6,673.00 | 62.42% |

Both with-skill and without-skill agents answered the deterministic evaluation tasks correctly in all saved runs. The skill's value in that test was payload reduction, not answer-quality improvement.

## Example

```bash
echo '{"users":[{"id":1,"name":"Ada"},{"id":2,"name":"Lin"},{"id":3,"name":"Grace"}]}' \
  | datoon --report-stdout
```

If policy accepts conversion, the agent should pass the TOON payload forward. If policy returns `decision: "skip"`, the agent should pass normalized JSON forward.

## Requirements

- `datoon` CLI available in `PATH`
- Node.js and `npx` available for TOON conversion

If TOON conversion is unavailable, auto mode keeps JSON and reports the fallback reason.

## Source Files

- LLM-facing skill: `skills/datoon/SKILL.md`
- Human docs: `skills/datoon/README.md`
- CLI implementation: `src/datoon/cli.py`
- Conversion policy: `src/datoon/converter.py`
- Sync validator: `scripts/validate_skill_sync.py`
