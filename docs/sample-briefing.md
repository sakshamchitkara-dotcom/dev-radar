# Dev Radar - 2026-09-25

_Repo `dev-radar` · last 7d · deterministic mode_

## TL;DR
- 19 commit(s) in the last 7 days by 1 author(s)
- Hottest file: `src/dev_radar/briefing.py` (3 commits)
- Machine healthy (no metric over threshold)

## Repo activity
- `2103c49` fix(cli): clear errors for missing or rejected Claude credentials — sakshamchitkara-dotcom, 2026-09-25
- `c5932c5` fix(briefing): count commits from uncapped author totals — sakshamchitkara-dotcom, 2026-09-25
- `95c093b` feat: add .mcp.json and Claude Desktop config for the three servers — sakshamchitkara-dotcom, 2026-09-25
- `446b33b` ci: run tests and a fallback briefing on Linux and macOS — sakshamchitkara-dotcom, 2026-09-25
- `56a1406` test: end-to-end over stdio for hub, fallback, Claude loop and CLI — sakshamchitkara-dotcom, 2026-09-25
- `b2af903` test(system-health): cover snapshot thresholds, process ranking and validation — sakshamchitkara-dotcom, 2026-09-25
- `4ee2e7a` test(hn-trends): cover filtering, validation and API failure with a fake feed — sakshamchitkara-dotcom, 2026-09-25
- `a0e46c0` test(git-insights): cover tools and resource against a temp repo — sakshamchitkara-dotcom, 2026-09-25
- `1863f2c` fix(hub): forward HN_API_BASE to spawned servers — sakshamchitkara-dotcom, 2026-09-25
- `125f482` feat(git-insights): skip lockfiles in churn hotspots by default — sakshamchitkara-dotcom, 2026-09-25
- `d61068b` feat(cli): add dev-radar command with auto/claude/fallback modes — sakshamchitkara-dotcom, 2026-09-25
- `8ffa80f` feat(briefing): Claude agent loop over MCP tools — sakshamchitkara-dotcom, 2026-09-25
- `4c4b265` feat(briefing): deterministic fallback that templates a fixed tool set — sakshamchitkara-dotcom, 2026-09-25
- `2d8e56d` build: expose each MCP server as a console script — sakshamchitkara-dotcom, 2026-09-25
- `ccb23c7` feat(hub): launch MCP servers over stdio and route namespaced tool calls — sakshamchitkara-dotcom, 2026-09-25
- …and 4 more

Active authors: sakshamchitkara-dotcom (19)

## Churn hotspots
| File | Commits | +lines | -lines |
|---|---:|---:|---:|
| `src/dev_radar/briefing.py` | 3 | 203 | 4 |
| `src/dev_radar/servers/git_insights.py` | 2 | 138 | 2 |
| `src/dev_radar/hub.py` | 2 | 84 | 1 |
| `src/dev_radar/cli.py` | 2 | 77 | 2 |
| `pyproject.toml` | 2 | 36 | 0 |

## Industry radar (ai, llm, llms, python, rust, postgres, security, mcp)
- [Using LLMs to trace alchemical knowledge and decode 17th century letters](https://resobscura.substack.com/p/ai-labs-need-to-start-funding-historical) — 126 pts, [24 comments](https://news.ycombinator.com/item?id=49835531)
- [Security auditing in the age of (good enough) AI](https://blog.trailofbits.com/2026/09/18/auditing-in-the-age-of-good-enough-ai/) — 85 pts, [12 comments](https://news.ycombinator.com/item?id=49793957)
- [Tutoring company tells parents to save their money and 'use AI instead'](https://www.afr.com/policy/health-and-education/tutoring-company-tell-parents-to-save-their-money-and-use-ai-instead-20260923-p60z0r) — 110 pts, [174 comments](https://news.ycombinator.com/item?id=49831690)
- ['That's so AI ' What gen Alpha's biggest insult tells us](https://www.theguardian.com/society/2026/sep/24/thats-so-ai-what-gen-alphas-biggest-insult-tells-us) — 151 pts, [211 comments](https://news.ycombinator.com/item?id=49829650)
- [Early rogue AI agent activity and attempts to hack found on urlquery.net](https://transluce.org/agent-activity) — 257 pts, [259 comments](https://news.ycombinator.com/item?id=49826565)
- [I stopped letting LLMs do arithmetic](https://medium.com/@jwbobbink/best-search-console-mcp-in-2026-gsc-wizard-7a63f91191ca) — 7 pts, [0 comments](https://news.ycombinator.com/item?id=49840612)

## Machine health
- CPU 17% across 10 cores (load 3.1)
- Memory 69% (11.1 / 16.0 GiB)
- Disk `/` 34% used, 30.55 GiB free
- Heaviest processes: OrbStack Helper (1111 MiB), 2.1.282 (647 MiB), 2.1.268 (347 MiB)

## Suggested focus today
- Review test coverage for `src/dev_radar/briefing.py` — it changes more than anything else.
- Skim "Using LLMs to trace alchemical knowledge and decode 17th century letters" — top match for your keywords.
