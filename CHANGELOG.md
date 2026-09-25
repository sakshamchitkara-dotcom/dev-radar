# Changelog

All notable changes to this project. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.2.1] - 2026-09-25

### Fixed
- `calendar`: `MONTHLY`/`YEARLY` recurrence is expanded (`INTERVAL`, `COUNT`, `UNTIL`, `BYMONTH`, `BYMONTHDAY` incl. negative days, `BYDAY` with ordinals like `2TU`/`-1FR`, `BYSETPOS`); previously only the first occurrence showed. Dates a month lacks are skipped per RFC 5545.
- `calendar`: a `RECURRENCE-ID` instance now replaces its slot in the series (or removes it when cancelled) instead of being dropped.
- `calendar`: `VALARM` properties no longer override the event's; open-ended series started years ago (a daily meeting since before ~2013) no longer disappear after the old 5,000-step walk.

## [0.2.0] - 2026-09-25

### Added
- `calendar` MCP server (`dev-radar-calendar`): `events` tool and `calendar://today` resource from local `.ics` files (`DEV_RADAR_CALENDARS` / `--calendars`), with TZID/UTC/all-day times, `DURATION`, `EXDATE` and DAILY/WEEKLY recurrence. The briefing gains a "Today's meetings" section and TL;DR line.
- TOML config file (`--config`, or `$XDG_CONFIG_HOME/dev-radar/config.toml`): flag defaults plus `[sections]` to disable briefing sections; a disabled section's tools are not called.
- Bearer-token auth for Streamable HTTP servers (`DEV_RADAR_HTTP_TOKEN`); the host sends it for `--connect`. Binding a non-loopback `--host` without a token is refused.
- `--timings`: per-tool call count, errors and latency from `McpHub`.
- `--keep N` (default 90) prunes old history records.
- The calendar server in `.mcp.json` and the Claude Desktop example; a test keeps both in sync with the servers the host launches.
- `github-activity` MCP server: `prs_awaiting_review`, `ci_status`, `recent_releases`. Read-only (GET only); token from `GITHUB_TOKEN`, then `gh auth token`, else anonymous. Repos from the call, `--github-repos` or `DEV_RADAR_GITHUB_REPOS`.
- `deps-watch` MCP server: `list_dependencies`, `outdated` (PyPI/npm) and `vulnerabilities` (OSV.dev) for `uv.lock`, `poetry.lock`, `requirements*.txt` and `package-lock.json`.
- MCP prompt templates: `git-insights/standup`, `github-activity/review_queue`, `deps-watch/triage_dependencies`.
- Subscribable resources `github://ci` and `deps://vulnerabilities`, updated through `subscriptions/listen` when CI state or vulnerability IDs change.
- Streamable HTTP transport for every server (`--transport streamable-http --host --port`) and `dev-radar --connect NAME=URL` to use a running HTTP server.
- Briefing: GitHub and Dependencies sections; `--since` (`36h`, `3d`, `2w`, `yesterday`, ISO date); `--format html` (self-contained) and `--format slack` (incoming-webhook JSON).
- Briefing history under `$XDG_STATE_HOME/dev-radar/history` with a "What changed since yesterday" section; `--history-dir`, `--no-history`, `--list-history`.
- git-insights tools accept an ISO-8601 `since` that overrides `days`.

### Changed
- The host launches six servers (13 tools) and forwards GitHub/OSV/registry/calendar settings to them.
- `--mode auto` finds Claude credentials through the SDK's chain (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ant auth login` profiles, federation); `--mode claude` says why none were found.
- CI smoke-runs github-activity against this repository with a read-only token and checks the HTML/Slack output and the history diff, a config file with disabled sections plus the example calendar, and a token-guarded HTTP server.

### Fixed
- An unreachable `--connect` server or a server that crashes on start no longer aborts the run; its sections show "server unavailable".
- `deps-watch` compares versions with PEP 440 ordering (`packaging`): `2.0` is no longer "outdated" against `2.0.0`, and pre-releases sort before releases.
- `prs_awaiting_review` follows pagination (100 per page, up to 5 pages) instead of reading only the first 50 open PRs.

## [0.1.0] - 2026-09-25

### Added
- MCP host (`McpHub`) over stdio with `git-insights`, `hn-trends` and `system-health` servers.
- Claude agent-loop briefing and a deterministic fallback; `dev-radar` CLI with `auto`/`claude`/`fallback` modes.
- `.mcp.json` and Claude Desktop config, tests over stdio, CI on Linux and macOS.
