# Marketplace & Registry Listings

How `datoon` is distributed across MCP marketplaces, what is automated, and the
one-time manual steps a maintainer performs.

`datoon` is a Python/PyPI MCP server launched over stdio with:

```bash
uvx --from datoon[mcp] datoon mcp
```

No API keys or runtime configuration are required.

______________________________________________________________________

## 1. Official MCP Registry — automated

- **Source of truth:** [`server.json`](./server.json) (schema `2025-12-11`).
- **Server name:** `io.github.andrii-su/datoon` (reverse-DNS namespace tied to the
  GitHub owner of this repo).
- **Ownership proof:** the `mcp-name: io.github.andrii-su/datoon` token in
  [`README.md`](./README.md) (PyPI renders the README as the package description,
  which the registry validates).
- **Publishing:** [`.github/workflows/publish-mcp.yml`](./.github/workflows/publish-mcp.yml)
  runs when the **Release** workflow completes (via `workflow_run`), and only
  when main HEAD carries a new version tag. It syncs `server.json`'s version to
  that tag, validates, waits for the version to appear on PyPI, authenticates via
  **GitHub OIDC** (no stored secret), and runs `mcp-publisher publish`.

> [!NOTE]
> **Trigger note.** Releases are cut by semantic-release using `GITHUB_TOKEN`,
> and GitHub does not fire `release: published` for `GITHUB_TOKEN`-created
> events. Both [`publish.yml`](./.github/workflows/publish.yml) (PyPI) and
> publish-mcp.yml therefore key off the **Release** workflow's completion
> instead, gated on a new tag at HEAD.

> [!NOTE]
> The ownership token first reaches PyPI with the release that includes the
> marketplace change. The first successful publish happens on the next release
> after that merge.

Manual publish — **Publish to MCP Registry** workflow → **Run workflow**
(`workflow_dispatch`); it publishes the latest tag. Or locally:

```bash
# Install mcp-publisher (see modelcontextprotocol/registry releases)
mcp-publisher validate
mcp-publisher login github        # interactive OAuth, namespace io.github.andrii-su/*
mcp-publisher publish
```

______________________________________________________________________

## 2. Smithery — one-time connect

- **Config:** [`smithery.yaml`](./smithery.yaml) (stdio, empty config schema).
- **Steps:**
  1. Sign in at [smithery.ai](https://smithery.ai) with GitHub.
  1. **Add Server** → select `andrii-su/datoon`.
  1. Smithery reads `smithery.yaml` and lists the server.

After the initial connect, Smithery re-syncs from the repo automatically.

______________________________________________________________________

## 3. Glama — mostly automatic

- **Config:** [`glama.json`](./glama.json) (maintainer metadata).
- Glama auto-indexes public GitHub MCP servers. To claim/maintain the listing,
  sign in at [glama.ai](https://glama.ai) with GitHub and claim `andrii-su/datoon`.

______________________________________________________________________

## 4. PulseMCP / mcp.so — directory submission

These are crawled directories with a submission form. Submit once:

- **PulseMCP:** <https://www.pulsemcp.com/submit>
- **mcp.so:** <https://mcp.so/submit>

Suggested listing copy:

> **datoon** — Smart structured-data → TOON gateway. Converts JSON, CSV, YAML,
> XML, Parquet, Avro, ORC, Excel, and Apple Numbers to TOON only when it
> actually saves LLM tokens, with a reasoned convert/skip decision on every call.
> Install: `uvx --from datoon[mcp] datoon mcp`.

______________________________________________________________________

## Maintainer checklist per release

1. Merge changes → semantic-release tags and publishes to PyPI (with README token).
1. **Publish to MCP Registry** workflow runs automatically on the Release.
1. Smithery / Glama re-sync from the repo; no action unless listing copy changes.
1. PulseMCP / mcp.so: only on first listing or major description changes.
