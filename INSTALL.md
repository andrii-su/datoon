# Install datoon

`datoon` ships as a Python package, command-line tool, MCP server, and AI-agent skill/plugin. Use the path that matches how you want to consume it.

## Quick Setup From Source

For local development or testing this repository:

```bash
git clone https://github.com/andrii-su/datoon.git
cd datoon
./setup.sh
```

The setup script:

- checks for Python 3.12+;
- installs `uv` if it is missing;
- warns if Node.js is missing;
- runs `uv sync --extra dev`;
- installs the editable `datoon` CLI globally through `uv tool install`.

Verify:

```bash
echo '{"users":[{"id":1,"name":"Ada"},{"id":2,"name":"Lin"},{"id":3,"name":"Grace"}]}' \
  | datoon --report-stdout
```

## Python Package

```bash
uv add datoon
```

or:

```bash
pip install datoon
```

Optional extras:

```bash
pip install "datoon[tokens]"  # tiktoken token estimates
pip install "datoon[mcp]"     # MCP server dependencies
```

## CLI

Read from stdin:

```bash
echo '{"users":[{"id":1,"name":"Ada"},{"id":2,"name":"Lin"},{"id":3,"name":"Grace"}]}' \
  | datoon --report-stdout
```

Read and write files:

```bash
datoon input.json -o output.toon --report report.json
```

Force conversion for controlled experiments:

```bash
datoon input.json --force --report-stdout
```

## TOON Dependency

`datoon` calls the official TOON CLI through `npx`.

Required for conversion:

- Node.js
- `npx` in `PATH`

Without Node.js, structure analysis still works, but conversion falls back to JSON in auto mode. Forced conversion fails loudly.

In auto mode, `datoon` skips conversion and returns compact JSON when:

- the payload has no uniform object array with at least the configured row count;
- the payload exceeds the configured maximum nesting depth;
- estimated TOON savings are below `--min-savings`;
- Node.js or `npx` is unavailable, or the TOON CLI fails.

Invalid JSON never falls back silently. It raises an error.

## MCP Server

Install with MCP support:

```bash
pip install "datoon[mcp]"
```

Run:

```bash
datoon-mcp
```

Example client config:

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

## Claude Code Plugin

Install from the Claude Code marketplace source:

```bash
claude plugin marketplace add andrii-su/datoon
claude plugin install datoon@datoon
```

Trigger in a session:

```text
/datoon
convert this JSON to TOON if it saves tokens
use datoon mode for structured data
```

## Codex Skill/Plugin

The Codex plugin source lives at:

```text
plugins/datoon/
```

The LLM-facing skill source lives at:

```text
skills/datoon/SKILL.md
```

For local Codex development, install or load the plugin through your Codex app/plugin workflow using `plugins/datoon/` as the plugin root.

## Installer

`install.sh` is a product installer wrapper for Claude Code, Codex, and MCP config targets. It is separate from `setup.sh`, which remains a developer bootstrap script.

Preview every action without writing files or running install commands:

```bash
./install.sh --dry-run
```

Install all targets:

```bash
./install.sh --install
```

Install one target:

```bash
./install.sh --install --target mcp --mcp-config ~/.config/datoon/mcp.json
```

Uninstall one or more targets:

```bash
./install.sh --uninstall --target claude --target mcp
```

Targets:

| Target | Dry-run | Install | Uninstall |
|---|---|---|---|
| `claude` | Show marketplace/plugin commands and current detection state. | Run `claude plugin marketplace add andrii-su/datoon` and `claude plugin install datoon@datoon`. | Run the matching Claude plugin uninstall command when available. |
| `codex` | Show local plugin path and marketplace entry that would be used. | Register or expose `plugins/datoon/` through the Codex plugin workflow without changing source files. | Remove only the local registration, never delete repository source files. |
| `mcp` | Show target MCP config file and JSON block. | Merge a `datoon` MCP server entry using `uvx datoon[mcp] datoon-mcp`. | Remove only the `datoon` MCP server entry. |

### Files and settings changed

The installer has a deliberately small write surface:

| Target | Default changed path or state | What changes |
|---|---|---|
| `claude` | Claude Code's own plugin registry/state | Runs `claude plugin marketplace add andrii-su/datoon` and `claude plugin install datoon@datoon`. The exact files are owned by Claude Code and may vary by Claude version. |
| `codex` | `.agents/plugins/marketplace.json` in this repository, unless `--codex-marketplace` is set | Adds or updates one `plugins[]` entry named `datoon` pointing at `./plugins/datoon`. It also initializes minimal marketplace metadata if the file does not exist. |
| `mcp` | `~/.config/datoon/mcp.json`, unless `--mcp-config` is set | Adds or updates `mcpServers.datoon` with `{"command":"uvx","args":["datoon[mcp]","datoon-mcp"]}`. |

Config writes are idempotent, preserve unrelated entries, and create timestamped `.bak.<timestamp>` files before overwriting existing JSON. Uninstall removes only the `datoon` entries from the selected target config.

### Security and privacy

- `--dry-run` writes nothing and runs no install commands. Use it first when installing into shared or managed environments.
- The installer does not read, transform, or upload your data payloads. It only updates local plugin or MCP configuration for the selected targets.
- The MCP entry uses `uvx datoon[mcp] datoon-mcp`. When an MCP client starts that server, `uvx` may download the published `datoon` package and dependencies from the configured Python package index.
- The Claude target runs the local `claude` command, which may contact Claude Code's plugin marketplace or GitHub according to Claude Code's behavior.
- Existing JSON config files are parsed and rewritten. Keep the generated `.bak.<timestamp>` file until you have confirmed the target app still starts with the updated config.

### Troubleshooting

**`install error: claude command not found on PATH`**

Install Claude Code or select only non-Claude targets:

```bash
./install.sh --install --target mcp --target codex
```

**MCP client does not show `datoon`**

Confirm the client is reading the same config file you installed to. Many clients use their own MCP config locations, so pass that path explicitly:

```bash
./install.sh --install --target mcp --mcp-config /path/to/client/mcp.json
```

Then restart the MCP client so it reloads the config.

**Conversion always returns JSON**

Check the report reason first:

```bash
echo '{"users":[{"id":1,"name":"Ada"},{"id":2,"name":"Lin"},{"id":3,"name":"Grace"}]}' \
  | datoon --report-stdout
```

If the reason mentions the TOON dependency, install Node.js and confirm `npx` is available:

```bash
node --version
npx --version
```

If the reason mentions structure or savings, the skip is expected auto-mode behavior. Use `--force` only for controlled experiments where a failed TOON conversion should fail the command.

**Config JSON is invalid**

Restore the timestamped backup created next to the config file, fix the JSON, then rerun `./install.sh --dry-run` before installing again.

Options:

| Flag | Description |
|---|---|
| `--dry-run` | Print planned actions only. Writes nothing and runs no install commands. |
| `--install` | Install selected targets. |
| `--uninstall` | Uninstall selected targets. |
| `--target <name>` | Select `claude`, `codex`, or `mcp`. Repeatable. Defaults to all targets. |
| `--mcp-config <path>` | MCP JSON config path. Defaults to `~/.config/datoon/mcp.json`. |
| `--codex-marketplace <path>` | Codex marketplace JSON path. Defaults to `.agents/plugins/marketplace.json` in this repo. |

## Verify From A Clone

```bash
uv run pytest
python scripts/validate_skill_sync.py
PYTHONPATH=src python benchmarks/run.py --dry-run
```

Full integration tests require Node.js and `npx`.

## Uninstall

For the editable CLI installed by `setup.sh`:

```bash
uv tool uninstall datoon
```

For package installs:

```bash
pip uninstall datoon
```

For Claude Code plugin installs:

```bash
claude plugin uninstall datoon@datoon
```

If a command differs in your Claude Code version, run:

```bash
claude plugin --help
```
