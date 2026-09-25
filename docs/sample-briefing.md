# Dev Radar - 2026-09-25

_Repo `dev-radar` · last 7d · deterministic mode_

## TL;DR
- 40 commit(s) in the last 7 days by 1 author(s)
- Hottest file: `src/dev_radar/briefing.py` (6 commits)
- CI failing on sakshamchitkara-dotcom/issue-autopilot-sandbox
- Machine healthy (no metric over threshold)

## What changed since 2026-09-25 01:30
- 2 new commit(s): `e273049` docs: add CHANGELOG covering 0.1.0 and the unreleased work, `4220338` docs(readme): document the five servers, formats, history and HTTP
- CI `sakshamchitkara-dotcom/scrapekit`: success → **pending**
- CI `sakshamchitkara-dotcom/issue-autopilot`: pending → **success**
- CI `sakshamchitkara-dotcom/finagent`: success → **pending**

## Repo activity
- `e273049` docs: add CHANGELOG covering 0.1.0 and the unreleased work — sakshamchitkara-dotcom, 2026-09-25
- `4220338` docs(readme): document the five servers, formats, history and HTTP — sakshamchitkara-dotcom, 2026-09-25
- `53fdc91` ci: smoke-test GitHub server, HTML/Slack output and history diff — sakshamchitkara-dotcom, 2026-09-25
- `da0e342` feat(history): keep past briefings and diff against yesterday — sakshamchitkara-dotcom, 2026-09-25
- `38274dd` feat(render): self-contained HTML and Slack webhook output (--format) — sakshamchitkara-dotcom, 2026-09-25
- `6444dfa` feat(cli): --since window (36h, 3d, 2w, yesterday or ISO date) — sakshamchitkara-dotcom, 2026-09-25
- `f3fbf0c` fix(briefing): render unconfigured GitHub as a setup hint, not a failure — sakshamchitkara-dotcom, 2026-09-25
- `d2c75cb` feat(briefing): GitHub and Dependencies sections in both modes — sakshamchitkara-dotcom, 2026-09-25
- `1f24abf` feat(hub): wire github-activity and deps-watch in; allow HTTP servers — sakshamchitkara-dotcom, 2026-09-25
- `8ed260b` feat: subscribable report resources for CI state and vulnerabilities — sakshamchitkara-dotcom, 2026-09-25
- `53092cf` feat: add MCP prompt templates to git, github and deps servers — sakshamchitkara-dotcom, 2026-09-25
- `dab3219` test(deps-watch): cover lockfile parsing, registry and OSV lookups — sakshamchitkara-dotcom, 2026-09-25
- `3e15cd8` feat(deps-watch): add MCP server for outdated deps and OSV.dev vulnerabilities — sakshamchitkara-dotcom, 2026-09-25
- `e951e67` test(github-activity): cover review filter, CI head status, releases window — sakshamchitkara-dotcom, 2026-09-25
- `b80bb22` feat(github-activity): add read-only GitHub MCP server — sakshamchitkara-dotcom, 2026-09-25
- …and 25 more

Active authors: sakshamchitkara-dotcom (40)

## Churn hotspots
| File | Commits | +lines | -lines |
|---|---:|---:|---:|
| `src/dev_radar/briefing.py` | 6 | 293 | 16 |
| `src/dev_radar/cli.py` | 6 | 162 | 21 |
| `src/dev_radar/servers/git_insights.py` | 5 | 171 | 9 |
| `tests/test_stdio_e2e.py` | 5 | 113 | 4 |
| `src/dev_radar/servers/deps_watch.py` | 4 | 281 | 4 |

## GitHub
- CI `sakshamchitkara-dotcom/dev-radar` main@53fdc91: **success**
- CI `sakshamchitkara-dotcom/rag-engine` main@5501783: **success**
- CI `sakshamchitkara-dotcom/issue-autopilot-sandbox` main@e8e687b: **failure** · [check](https://github.com/sakshamchitkara-dotcom/issue-autopilot-sandbox/actions/runs/36113077775) failure
- CI `sakshamchitkara-dotcom/gtm-engine` main@f555e3c: **success**
- CI `sakshamchitkara-dotcom/review-bot` main@1eb6512: **success**
- CI `sakshamchitkara-dotcom/review-bot-sandbox` main: no workflow runs
- CI `sakshamchitkara-dotcom/scrapekit` main@4d5dd4f: **pending**
- CI `sakshamchitkara-dotcom/issue-autopilot` main@380867b: **success**
- CI `sakshamchitkara-dotcom/finagent` main@554db11: **pending**
- CI `sakshamchitkara-dotcom/teaspoon-landing` main@effd2b6: **success**
- CI `sakshamchitkara-dotcom/claude` main: no workflow runs
- No PRs awaiting review across 11 repo(s)
- No releases in the last 7 days

## Dependencies
- 0 known vulnerabilit(ies) across 45 pinned package(s) (OSV.dev)
- 0 of 4 direct dependencies behind latest

## Industry radar (ai, llm, llms, python, rust, postgres, security, mcp)
- [Using LLMs to trace alchemical knowledge and decode 17th century letters](https://resobscura.substack.com/p/ai-labs-need-to-start-funding-historical) — 130 pts, [25 comments](https://news.ycombinator.com/item?id=49835531)
- [Security auditing in the age of (good enough) AI](https://blog.trailofbits.com/2026/09/18/auditing-in-the-age-of-good-enough-ai/) — 85 pts, [12 comments](https://news.ycombinator.com/item?id=49793957)
- [Tutoring company tells parents to save their money and 'use AI instead'](https://www.afr.com/policy/health-and-education/tutoring-company-tell-parents-to-save-their-money-and-use-ai-instead-20260923-p60z0r) — 111 pts, [174 comments](https://news.ycombinator.com/item?id=49831690)
- ['That's so AI ' What gen Alpha's biggest insult tells us](https://www.theguardian.com/society/2026/sep/24/thats-so-ai-what-gen-alphas-biggest-insult-tells-us) — 154 pts, [214 comments](https://news.ycombinator.com/item?id=49829650)
- [Early rogue AI agent activity and attempts to hack found on urlquery.net](https://transluce.org/agent-activity) — 257 pts, [260 comments](https://news.ycombinator.com/item?id=49826565)
- [Best LLM for every budget, updated daily](https://bestmodelforyourbudget.terrydjony.com/) — 173 pts, [106 comments](https://news.ycombinator.com/item?id=49830866)

## Machine health
- CPU 0% across 10 cores (load 3.4)
- Memory 72% (11.46 / 16.0 GiB)
- Disk `/` 35% used, 29.35 GiB free
- Heaviest processes: OrbStack Helper (1293 MiB), 2.1.282 (635 MiB), 2.1.268 (320 MiB)

## Suggested focus today
- Fix the red default branch on sakshamchitkara-dotcom/issue-autopilot-sandbox before merging anything else.
- Review test coverage for `src/dev_radar/briefing.py` — it changes more than anything else.
- Skim "Using LLMs to trace alchemical knowledge and decode 17th century letters" — top match for your keywords.
