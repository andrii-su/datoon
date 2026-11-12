# Contributing to datoon

Thanks for considering a contribution. `datoon` is a small package with several distribution surfaces: Python API, CLI, Claude Code plugin, Codex skill/plugin, benchmark artifacts, and docs.

Keep changes focused. A parser fix, a benchmark update, and a README rewrite should usually be separate PRs.

## Quick Start

```bash
git clone https://github.com/andrii-su/datoon.git
cd datoon
uv sync --extra dev
uv run pytest
python scripts/validate_skill_sync.py
python scripts/validate_plugin_metadata.py
```

Conversion is pure Python (the `toon-format` package); no Node.js is required for tests.

## What To Edit

| Goal | Edit |
|---|---|
| Conversion policy or fallback behavior | `src/datoon/converter.py` |
| Payload suitability analysis | `src/datoon/analyzer.py` |
| Public models and reports | `src/datoon/models.py` |
| CLI flags and input/output behavior | `src/datoon/cli.py` |
| LLM-facing skill behavior | `skills/datoon/SKILL.md` |
| Human-facing skill docs | `skills/datoon/README.md` |
| Main benchmark payloads | `benchmarks/payloads.json` |
| JSON/TOON efficiency benchmark | `benchmarks/run.py` |
| Agent skill evaluation summary | `scripts/summarize_agent_skill_eval.py` |
| Product installer | `scripts/install.py` and `install.sh` |
| Skill copy validation | `scripts/validate_skill_sync.py` |

## Generated And Mirrored Files

`skills/datoon/SKILL.md` is the source of truth for skill behavior.

These files must stay byte-for-byte synchronized with it:

- `SKILL.md`
- `datoon/SKILL.md`
- `plugins/datoon/skills/datoon/SKILL.md`
- `datoon.skill` member `datoon/SKILL.md`

Use:

```bash
python scripts/validate_skill_sync.py
```

The `.github/workflows/validate-artifacts.yml` workflow checks mirrors on pull requests and pushes to `main`. It does not auto-commit generated files; include updated mirrors and `datoon.skill` in the PR.

Plugin and marketplace metadata must also stay aligned across Claude Code and Codex manifests:

```bash
python scripts/validate_plugin_metadata.py
```

## Tests

Run the full suite:

```bash
uv run pytest
```

Run pre-commit locally:

```bash
uvx pre-commit run --all-files
```

Run installer unit tests:

```bash
uv run pytest tests/unit/test_installer.py
./install.sh --dry-run
```

## Benchmarks

JSON/TOON efficiency benchmark:

```bash
PYTHONPATH=src python benchmarks/run.py --dry-run
PYTHONPATH=src python benchmarks/run.py
PYTHONPATH=src python benchmarks/run.py --update-readme
```

Agent skill evaluation summary from committed artifacts:

```bash
python scripts/summarize_agent_skill_eval.py
```

The subagent evaluation artifacts do not include full model token usage. They report payload-token savings from `datoon` reports and exact-answer correctness from saved outputs.

## Release Notes

This repo uses semantic-release on `main`.

Use Conventional Commit subjects:

```text
feat: add an ORC reader
fix: preserve JSON fallback on encoder failure
docs: clarify Claude Code plugin install
test: cover non-uniform arrays
```

The release workflow validates skill sync before publishing release artifacts.
It also validates plugin metadata consistency.

## Pull Request Checklist

- Tests pass or the PR explains why they were not run.
- Skill changes update only `skills/datoon/SKILL.md` directly.
- README benchmark numbers come from `benchmarks/` or `benchmarks/agent_skill_eval/`, not manual estimates.
- CLI behavior changes update README or INSTALL when user-facing.
- New dependencies are justified and added to the appropriate optional extra when possible.
