# Dev Radar - 2026-09-25

_Repo `dev-radar` · last 7d · deterministic mode_

## TL;DR
- 56 commit(s) in the last 7 days by 1 author(s)
- Hottest file: `src/dev_radar/cli.py` (12 commits)
- CI failing on sakshamchitkara-dotcom/teaspoon-landing, sakshamchitkara-dotcom/issue-autopilot-sandbox
- 1 meeting(s) today, first at 09:30 (Team standup)
- Machine healthy (no metric over threshold)

## What changed since 2026-09-25 03:06
- CI `sakshamchitkara-dotcom/issue-autopilot`: pending → **success**
- CI `sakshamchitkara-dotcom/scrapekit`: success → **pending**
- CI `sakshamchitkara-dotcom/dev-radar`: pending → **success**

## Today's meetings
- 09:30–09:45 Team standup (Zoom)

## Repo activity
- `ef8fe25` ci: smoke-test config sections, calendar, timings and bearer-token HTTP — sakshamchitkara-dotcom, 2026-09-25
- `71ca2da` feat: register the calendar server in .mcp.json and the Desktop example — sakshamchitkara-dotcom, 2026-09-25
- `8bcef6e` feat(config): TOML config file with per-section enable/disable — sakshamchitkara-dotcom, 2026-09-25
- `001f3ec` feat(briefing): Today's meetings section from the calendar server — sakshamchitkara-dotcom, 2026-09-25
- `d53bc57` feat(calendar): MCP server for today's meetings from local .ics files — sakshamchitkara-dotcom, 2026-09-25
- `92be138` feat(servers): bearer-token auth for the Streamable HTTP transport — sakshamchitkara-dotcom, 2026-09-25
- `dcafc4e` fix(github-activity): follow pagination for open PRs — sakshamchitkara-dotcom, 2026-09-25
- `2b4d8b6` feat(history): cap saved briefings with --keep (default 90) — sakshamchitkara-dotcom, 2026-09-25
- `e9831b8` feat(hub): record per-tool call latency; --timings prints it — sakshamchitkara-dotcom, 2026-09-25
- `db353c4` fix(hub): an unreachable server no longer aborts the whole briefing — sakshamchitkara-dotcom, 2026-09-25
- `8c6d7f5` fix(deps-watch): compare versions with PEP 440 ordering — sakshamchitkara-dotcom, 2026-09-25
- `a2d4822` test(briefing): Claude loop stops on refusal, max_tokens and the turn cap — sakshamchitkara-dotcom, 2026-09-25
- `a227b96` test(briefing): cover populated GitHub/deps sections and all-sources-down — sakshamchitkara-dotcom, 2026-09-25
- `399f25e` test(cli): cover argument validation and --list-history in-process — sakshamchitkara-dotcom, 2026-09-25
- `d2380b7` fix(cli): find Claude credentials from ant auth profiles, not only env vars — sakshamchitkara-dotcom, 2026-09-25
- …and 41 more

Active authors: sakshamchitkara-dotcom (56)

## Churn hotspots
| File | Commits | +lines | -lines |
|---|---:|---:|---:|
| `src/dev_radar/cli.py` | 12 | 209 | 28 |
| `src/dev_radar/briefing.py` | 8 | 319 | 20 |
| `tests/test_stdio_e2e.py` | 8 | 142 | 6 |
| `src/dev_radar/hub.py` | 7 | 154 | 17 |
| `pyproject.toml` | 6 | 40 | 0 |

## GitHub
- CI `sakshamchitkara-dotcom/issue-autopilot` main@6cdfc2f: **success**
- CI `sakshamchitkara-dotcom/review-bot` main@2e86eb1: **success**
- CI `sakshamchitkara-dotcom/scrapekit` main@583a551: **pending**
- CI `sakshamchitkara-dotcom/rag-engine` main@8822c2c: **success**
- CI `sakshamchitkara-dotcom/dev-radar` main@ef8fe25: **success**
- CI `sakshamchitkara-dotcom/review-bot-sandbox` main: no workflow runs
- CI `sakshamchitkara-dotcom/finagent` main@19eeda7: **success**
- CI `sakshamchitkara-dotcom/office-eats` main@30ad45d: **success**
- CI `sakshamchitkara-dotcom/teaspoon-landing` main@6901109: **failure** · [Smoke tests](https://github.com/sakshamchitkara-dotcom/teaspoon-landing/actions/runs/36121473862) failure · [pages build and deployment](https://github.com/sakshamchitkara-dotcom/teaspoon-landing/actions/runs/36121472534) success
- CI `sakshamchitkara-dotcom/gtm-engine` main@9ae2acd: **success**
- CI `sakshamchitkara-dotcom/claw-telegram` main@eea3567: **success**
- CI `sakshamchitkara-dotcom/newsbrief` main@c5a6aa1: **success**
- CI `sakshamchitkara-dotcom/agent-fleet` main@0d0d12e: **success**
- CI `sakshamchitkara-dotcom/voice-agent` main@5f4994e: **success**
- CI `sakshamchitkara-dotcom/agent-fleet-sandbox` main: no workflow runs
- CI `sakshamchitkara-dotcom/issue-autopilot-sandbox` main@e8e687b: **failure** · [check](https://github.com/sakshamchitkara-dotcom/issue-autopilot-sandbox/actions/runs/36113077775) failure
- CI `sakshamchitkara-dotcom/claude` main: no workflow runs
- PR [sakshamchitkara-dotcom/agent-fleet-sandbox#4](https://github.com/sakshamchitkara-dotcom/agent-fleet-sandbox/pull/4) Fix #1: Discounts are inverted: apply_discount returns the discount... — sakshamchitkara-dotcom, 0d old, no reviews yet
- No releases in the last 7 days

## Dependencies
- 0 known vulnerabilit(ies) across 45 pinned package(s) (OSV.dev)
- 0 of 5 direct dependencies behind latest

## Industry radar (ai, llm, llms, python, rust, postgres, security, mcp)
- [Using LLMs to trace alchemical knowledge and decode 17th century letters](https://resobscura.substack.com/p/ai-labs-need-to-start-funding-historical) — 134 pts, [27 comments](https://news.ycombinator.com/item?id=49835531)
- [Tutoring company tells parents to save their money and 'use AI instead'](https://www.afr.com/policy/health-and-education/tutoring-company-tell-parents-to-save-their-money-and-use-ai-instead-20260923-p60z0r) — 116 pts, [178 comments](https://news.ycombinator.com/item?id=49831690)
- [Security auditing in the age of (good enough) AI](https://blog.trailofbits.com/2026/09/18/auditing-in-the-age-of-good-enough-ai/) — 90 pts, [14 comments](https://news.ycombinator.com/item?id=49793957)
- ['That's so AI ' What gen Alpha's biggest insult tells us](https://www.theguardian.com/society/2026/sep/24/thats-so-ai-what-gen-alphas-biggest-insult-tells-us) — 161 pts, [222 comments](https://news.ycombinator.com/item?id=49829650)
- [Early rogue AI agent activity and attempts to hack found on urlquery.net](https://transluce.org/agent-activity) — 257 pts, [264 comments](https://news.ycombinator.com/item?id=49826565)
- [Best LLM for every budget, updated daily](https://bestmodelforyourbudget.terrydjony.com/) — 174 pts, [108 comments](https://news.ycombinator.com/item?id=49830866)

## Machine health
- CPU 38% across 10 cores (load 11.41)
- Memory 62% (9.87 / 16.0 GiB)
- Disk `/` 50% used, 15.78 GiB free
- Heaviest processes: OrbStack Helper (1403 MiB), 2.1.282 (876 MiB), Google Chrome Helper (Renderer) (341 MiB)

## Suggested focus today
- Fix the red default branch on sakshamchitkara-dotcom/teaspoon-landing, sakshamchitkara-dotcom/issue-autopilot-sandbox before merging anything else.
- Review sakshamchitkara-dotcom/agent-fleet-sandbox#4 — oldest PR waiting (0d).
- Review test coverage for `src/dev_radar/cli.py` — it changes more than anything else.
- Skim "Using LLMs to trace alchemical knowledge and decode 17th century letters" — top match for your keywords.
