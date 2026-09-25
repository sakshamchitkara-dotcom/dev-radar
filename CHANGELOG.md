# Changelog

All notable changes to this project. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `github-activity` MCP server: `prs_awaiting_review`, `ci_status`, `recent_releases`. Read-only (GET only); token from `GITHUB_TOKEN`, then `gh auth token`, else anonymous. Repos from the call, `--github-repos` or `DEV_RADAR_GITHUB_REPOS`.
- `deps-watch` MCP server: `list_dependencies`, `outdated` (PyPI/npm) and `vulnerabilities` (OSV.dev) for `uv.lock`, `poetry.lock`, `requirements*.txt` and `package-lock.json`.
- MCP prompt templates: `git-insights/standup`, `github-activity/review_queue`, `deps-watch/triage_dependencies`.
- Subscribable resources `github://ci` and `deps://vulnerabilities`, updated through `subscriptions/listen` when CI state or vulnerability IDs change.
- Streamable HTTP transport for every server (`--transport streamable-http --host --port`) and `dev-radar --connect NAME=URL` to use a running HTTP server.
- Briefing: GitHub and Dependencies sections; `--since` (`36h`, `3d`, `2w`, `yesterday`, ISO date); `--format html` (self-contained) and `--format slack` (incoming-webhook JSON).
- Briefing history under `$XDG_STATE_HOME/dev-radar/history` with a "What changed since yesterday" section; `--history-dir`, `--no-history`, `--list-history`.
- git-insights tools accept an ISO-8601 `since` that overrides `days`.

### Changed
- The host launches five servers (12 tools) and forwards GitHub/OSV/registry settings to them.
- CI smoke-runs github-activity against this repository with a read-only token and checks the HTML/Slack output and the history diff.

## [0.1.0] - 2026-09-25

### Added
- MCP host (`McpHub`) over stdio with `git-insights`, `hn-trends` and `system-health` servers.
- Claude agent-loop briefing and a deterministic fallback; `dev-radar` CLI with `auto`/`claude`/`fallback` modes.
- `.mcp.json` and Claude Desktop config, tests over stdio, CI on Linux and macOS.
