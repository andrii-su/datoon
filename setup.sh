#!/usr/bin/env bash
# datoon setup — installs dependencies and registers the CLI globally.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_blue()  { printf '\033[0;34m▶ %s\033[0m\n' "$*"; }
_green() { printf '\033[0;32m✓ %s\033[0m\n' "$*"; }
_warn()  { printf '\033[1;33m! %s\033[0m\n' "$*"; }
_err()   { printf '\033[0;31m✗ %s\033[0m\n' "$*" >&2; }

# ── 1. Python 3.12+ ──────────────────────────────────────────────────────────
_blue "Checking Python version..."

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null || true)
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    _err "Python 3.12+ not found. Install from https://python.org or use pyenv."
    exit 1
fi

_green "Python OK — $($PYTHON_BIN --version)"

# ── 2. uv ─────────────────────────────────────────────────────────────────────
_blue "Checking uv..."

if ! command -v uv &>/dev/null; then
    _warn "uv not found — installing via official installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

_green "uv OK — $(uv --version)"

# ── 3. Node.js (optional — needed for TOON CLI conversion) ───────────────────
_blue "Checking Node.js..."

if command -v node &>/dev/null; then
    _green "Node.js OK — $(node --version)"
else
    _warn "Node.js not found. Install from https://nodejs.org to enable TOON conversion."
    _warn "analyze_json and policy gating work without Node.js; CLI conversion requires it."
fi

# ── 4. Dev dependencies ───────────────────────────────────────────────────────
_blue "Installing dev dependencies via uv sync..."
cd "$REPO_DIR"
uv sync --extra dev
_green "Dev dependencies installed"

# ── 5. Register datoon CLI globally via uv tool ───────────────────────────────
_blue "Installing datoon CLI via uv tool..."

uv tool install --editable "$REPO_DIR"

UV_TOOL_BIN_DIR="$(uv tool dir)/bin"
UV_LOCAL_BIN="$HOME/.local/bin"

_green "datoon CLI installed"

# ── 6. Ensure CLI is on PATH ──────────────────────────────────────────────────
_blue "Checking PATH..."

if ! command -v datoon &>/dev/null; then
    SHELL_RC=""
    case "${SHELL:-}" in
        */zsh)  SHELL_RC="$HOME/.zshrc" ;;
        */bash) SHELL_RC="$HOME/.bashrc" ;;
    esac

    ADD_LINE='export PATH="$HOME/.local/bin:$PATH"'

    if [[ -n "$SHELL_RC" && -f "$SHELL_RC" ]]; then
        if ! grep -qF '.local/bin' "$SHELL_RC"; then
            echo "" >> "$SHELL_RC"
            echo "# added by datoon setup.sh" >> "$SHELL_RC"
            echo "$ADD_LINE" >> "$SHELL_RC"
            _green "Added ~/.local/bin to $SHELL_RC"
        fi
    fi

    export PATH="$HOME/.local/bin:$PATH"

    if ! command -v datoon &>/dev/null; then
        _warn "datoon not on PATH yet. Run: export PATH=\"\$HOME/.local/bin:\$PATH\""
        _warn "Or restart your terminal after setup."
    fi
fi

# ── 7. Verify ─────────────────────────────────────────────────────────────────
if command -v datoon &>/dev/null; then
    _green "datoon CLI ready — $(datoon --help | head -1)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " datoon setup complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  CLI usage:"
echo "    echo '{\"users\":[{\"id\":1}]}' | datoon --report-stdout"
echo "    datoon input.json -o output.toon --report report.json"
echo ""
echo "  Run tests:"
echo "    pytest -m 'not integration'"
echo ""
echo "  MCP server (requires datoon[mcp]):"
echo "    uv run --extra mcp datoon-mcp"
echo ""
