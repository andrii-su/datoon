# CLAUDE.md - datoon

This file is the maintainer guide for agents working in this repository. It explains source-of-truth files, generated mirrors, and checks that must stay green.

## Project Overview

`datoon` is a smart JSON-to-TOON gateway for LLM data workloads. It converts structured JSON only when the payload is a good TOON candidate and estimated token savings clear the configured threshold.

It ships as:

- Python package under `src/datoon/`;
- CLI command `datoon`;
- MCP server command `datoon-mcp`;
- Claude Code plugin metadata under `.claude-plugin/`;
- Codex plugin under `plugins/datoon/`;
- standalone skill artifact `datoon.skill`;
- docs and benchmarks.

## Repository Layout

```text
datoon/
├── README.md                         # Product overview and benchmark summary
├── INSTALL.md                        # User install guide
├── CONTRIBUTING.md                   # Contributor workflow
├── CLAUDE.md                         # Maintainer guide for agents
├── SECURITY.md
├── pyproject.toml
├── uv.lock
│
├── src/datoon/                       # Python package source
│   ├── analyzer.py                   # Payload structure suitability checks
│   ├── converter.py                  # JSON normalization, TOON CLI call, policy gating
│   ├── models.py                     # Config/report/outcome dataclasses
│   ├── cli.py                        # CLI entrypoint
│   └── mcp_server.py                 # MCP server tools
│
├── skills/datoon/                    # Skill source of truth
│   ├── SKILL.md                      # LLM-facing behavior
│   └── README.md                     # Human-facing skill docs
│
├── SKILL.md                          # Mirrored skill copy
├── datoon/SKILL.md                   # Mirrored skill copy for .skill layout
├── plugins/datoon/                   # Codex plugin distribution
├── datoon.skill                      # ZIP artifact containing datoon/SKILL.md
│
├── benchmarks/
│   ├── payloads.json                 # Main benchmark payload config
│   ├── run.py                        # JSON/TOON efficiency benchmark
│   └── agent_skill_eval/             # Saved subagent evaluation artifacts
│
├── scripts/
│   ├── validate_skill_sync.py        # Mirror/archive consistency check
│   ├── ab_skill_benchmark.py         # Claude CLI A/B benchmark harness
│   └── summarize_agent_skill_eval.py # Summarizes saved subagent artifacts
│
├── tests/                            # Unit and integration tests
├── docs/                             # Static docs site
└── .github/workflows/                # CI, release, publish, skill sync
```

## Source Of Truth

Edit these files directly:

| Area | Source |
|---|---|
| Conversion policy | `src/datoon/converter.py` |
| Payload analysis | `src/datoon/analyzer.py` |
| Public data contracts | `src/datoon/models.py` |
| CLI behavior | `src/datoon/cli.py` |
| MCP behavior | `src/datoon/mcp_server.py` |
| Skill behavior | `skills/datoon/SKILL.md` |
| Human skill docs | `skills/datoon/README.md` |
| Main benchmark inputs | `benchmarks/payloads.json` |
| README benchmark table | `benchmarks/run.py --update-readme` |
| Agent eval report | `scripts/summarize_agent_skill_eval.py` |

## Mirrored Files

`skills/datoon/SKILL.md` is mirrored to:

- `SKILL.md`
- `datoon/SKILL.md`
- `plugins/datoon/skills/datoon/SKILL.md`
- `datoon.skill` archive member `datoon/SKILL.md`

Do not hand-edit mirrors unless the task is specifically to repair sync. Prefer editing `skills/datoon/SKILL.md`, then syncing mirrors through the workflow or an explicit patch.

Validate sync:

```bash
python scripts/validate_skill_sync.py
```

CI workflow:

```text
.github/workflows/validate-artifacts.yml
```

It runs on pull requests and pushes to `main`. The old auto-sync-on-main flow was removed; PRs must include updated mirrors and `datoon.skill` before merge.

## Critical Invariants

- Never change semantic values or key names during conversion.
- Invalid JSON must fail loudly.
- Missing `npx` must not break auto mode; fallback to JSON unless `force=True`.
- `--force` is for controlled experiments and should bypass gating, not hide conversion errors.
- Auto mode skips before conversion when analysis rejects the payload, and skips after conversion when estimated savings are below `min_savings_ratio`.
- Keep skip reasons user-facing, specific, and stable enough for CLI/MCP troubleshooting.
- Token counts are estimates. Be precise about whether a number is payload-token estimate, visible output estimate, or real model usage.
- Benchmarks in README must come from committed scripts/artifacts.
- Keep generated caches out of commits: `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, local benchmark result JSON under `benchmarks/results/`.

## Test Commands

```bash
uv run pytest
python scripts/validate_skill_sync.py
python scripts/validate_plugin_metadata.py
uvx pre-commit run --all-files
```

Integration tests require Node.js and `npx`.

## Benchmark Commands

```bash
PYTHONPATH=src python benchmarks/run.py --dry-run
PYTHONPATH=src python benchmarks/run.py
PYTHONPATH=src python benchmarks/run.py --update-readme
python scripts/summarize_agent_skill_eval.py
```

`scripts/ab_skill_benchmark.py` calls the Claude CLI and can use real token/cost telemetry when the local Claude setup supports it. Do not run it casually without checking budget and plugin state.

## Release Flow

The release workflow runs on pushes to `main`:

```text
.github/workflows/release.yml
```

Artifact validation runs as a separate required CI check before merge. The release workflow assumes `main` is already consistent and then runs semantic-release. PyPI publish runs from GitHub Releases through:

```text
.github/workflows/publish.yml
```

Use Conventional Commits so semantic-release can classify changes correctly.

## Installer

`install.sh` wraps `scripts/install.py` and supports `--dry-run`, `--install`, and `--uninstall` for `claude`, `codex`, and `mcp` targets. Keep installer behavior testable in Python helpers; the shell script should stay a thin wrapper.

User-facing installer docs must stay explicit about the write surface:

- `claude` runs Claude Code plugin commands and leaves file ownership to Claude Code;
- `codex` defaults to `.agents/plugins/marketplace.json` and manages only the `plugins[]` entry named `datoon`;
- `mcp` defaults to `~/.config/datoon/mcp.json` and manages only `mcpServers.datoon`.

Config writes must:

- preserve unrelated JSON entries;
- create timestamped backups before overwriting existing files;
- remove only `datoon`-owned entries on uninstall;
- keep dry-run side-effect free.

Security and privacy docs should state that the installer does not read or upload user payloads, but selected targets may call external tooling: Claude Code through `claude plugin ...`, Python package resolution through `uvx`, and TOON conversion through `npx --yes @toon-format/cli@2` when conversion actually runs.

## Known Gaps

- The saved subagent eval reports payload-token savings, not full end-to-end model token savings.
