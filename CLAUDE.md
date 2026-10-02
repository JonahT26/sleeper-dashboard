# Sleeper League Dashboard

Automated weekly power rankings and analytics for our Sleeper fantasy football league. A scheduled job pulls league data from the Sleeper API, computes metrics in Python, and publishes a static dashboard the league can bookmark.

## About the owner — read this first

- I have deep expertise in statistical modeling and data analysis and very little coding experience.
- Explain changes in plain language: what changed, why, and how I can verify it. Skip syntax lessons unless I ask.
- Show me data, not just code. After any data or metrics step, print a small sample table plus summary stats so I can sanity-check the numbers.
- I own metric definitions. If something in `docs/METRICS_SPEC.md` is ambiguous or looks statistically off, ask me. Never silently pick an interpretation.
- Work in small steps. Before touching more than ~3 files, propose a plan and wait for my go-ahead.
- When I need to run something myself, give me the exact command to copy and paste.

## League facts

| Field | Value |
|---|---|
| League ID | `1369887235935059968` — always a **string**, never an int |
| Format | 12-team redraft |
| Season | 2026 |
| Platform | Sleeper API, base URL `https://api.sleeper.app/v1` (read-only, no auth) |

Scoring settings, roster slots, playoff start week, and whether the league plays a weekly median game all come from `GET /league/{league_id}`. Read them from the API at runtime; never hardcode them. A snapshot for reference lives in `docs/CODEBASE.md`.

## Stack

- Python 3.11+, installed as a package from `src/sleeper_dash/` (editable install)
- pandas, requests, pyarrow, pyyaml, scipy, pytest, jupyterlab
- Plotly for charts and Jinja2 for the HTML template (Phase 3)
- GitHub for version control, GitHub Actions for the weekly schedule, GitHub Pages for hosting (Phase 4)

## Key docs

- `docs/CODEBASE.md` — repo map, data flow, table schemas, Sleeper API quirks. **Update it in the same commit whenever you add a module, table, or column.**
- `docs/UI_GUIDE.md` — design system and dashboard layout. Follow it for anything user-facing.
- `docs/METRICS_SPEC.md` — source of truth for every metric definition. Written with me in Phase 2. Code follows the spec, not the other way round.
- `docs/DATA_DICTIONARY.md` — field-level notes on raw Sleeper responses (created in Phase 1).

## Commands

```powershell
.venv\Scripts\Activate.ps1         # start of every session, from the project folder (Mac/Linux: source .venv/bin/activate)
pip install -e .                   # one-time setup, or after adding a dependency to pyproject.toml
python -m sleeper_dash.pipeline    # full refresh: extract → transform → validate → save; short summary; exit 1 on failure
python -m sleeper_dash.extract     # step 1 only: re-download raw JSON into data/raw/{season}/ and refresh the players cache
python -m sleeper_dash.transform   # step 2 only: rebuild tables from saved files, validate, save, print detailed reports
python -m sleeper_dash.validate    # re-run the checks on the saved tables and print pass/fail
pytest                             # run all tests
jupyter lab                        # open the notebooks
```

Keep this list current as commands are added.

## Rules

1. **Full refresh every run.** The pipeline re-pulls and recomputes the whole season each time, so Sleeper stat corrections and model changes flow through everywhere. No incremental appends.
2. **Raw before tidy.** Save untouched API JSON to `data/raw/` first, then transform from those files. Transform and metric code never calls the API.
3. **Tests never hit the network.** Use saved fixtures in `tests/fixtures/`.
4. **Config, not constants.** League ID, season, model weights, and thresholds live in `config.yaml`.
5. **IDs are strings:** `league_id`, `user_id`, `owner_id`, `player_id`, `transaction_id`, `draft_id`. `roster_id` is a small integer and is the team key everywhere.
6. **Be polite to Sleeper.** Stay far below 1,000 calls per minute. Fetch `/players/nfl` at most once per day and cache it.
7. **No secrets are needed.** If anything seems to need a key, token, or password, stop and ask me.
8. **Validate before publishing.** Every pipeline run ends with reconciliation checks. A failed check stops the run with a clear message. Never publish numbers that fail.
9. **Metrics are pure functions:** DataFrames in, DataFrames out, no file or network access inside them.
10. **Commit after each working step** with a short plain message, e.g. `Add team_weeks table`, then push to GitHub right away (owner's standing approval). The repo is public, so check that nothing private is staged before committing.

## Current status

**Phase 1 — Data pull: complete (2026-10-02). Next: Phase 2 — Metrics**, starting with drafting `docs/METRICS_SPEC.md` with the owner (owner approves each definition before it is built). Update this section at the end of every phase.

Where things stand:
- `python -m sleeper_dash.pipeline` runs extract → transform → validate as a full refresh; all 6 checks pass on weeks 1–3, and two consecutive runs give identical outputs.
- Tables in `data/processed/`: `teams`, `team_weeks`, `player_weeks`, `transactions` (see `docs/CODEBASE.md`). Raw field notes and the IR, median-tie, and preseason decisions are in `docs/DATA_DICTIONARY.md`.
- `notebooks/01_data_check.ipynb`: standings and score distributions for eyeballing the data.
- To verify at week 15: whether Sleeper plays the median game in the playoffs, and whether roster `wins`/`fpts` include playoff games.

Roadmap:
- Phase 0: Setup (environment, repo, API smoke test) — complete
- Phase 1: Data pull (raw extract, tidy tables, validation) — complete
- Phase 2: Metrics (spec, optimal lineups, luck, consistency, schedule, power score, awards)
- Phase 3: Dashboard (static HTML per `docs/UI_GUIDE.md`)
- Phase 4: Automation (weekly GitHub Action, GitHub Pages)
- Phase 5: Extras (playoff odds simulation, past seasons, posting to league chat)

## Decisions made

- **Public GitHub repo** (`sleeper-dashboard`), decided 2026-10-02 in Phase 0, so the dashboard can use free GitHub Pages hosting. Everything committed is visible to anyone, so never commit anything that isn't safe to share.
- **Raw data stays off GitHub** (2026-10-02). `data/raw/` is gitignored because it holds managers' personal settings; the pipeline re-downloads it every run. Test fixtures are anonymised (fake `owner_id`s, nicknames replaced).
- **Processed tables are committed publicly** (2026-10-02, owner's explicit choice). `data/processed/*.csv`, including usernames, team names, and Sleeper owner IDs in `teams.csv`, go to GitHub.
- **Metric data rules** (2026-10-02; details and evidence in `docs/DATA_DICTIONARY.md`, to be carried into `docs/METRICS_SPEC.md`):
  - Injured-reserve players count as bench in past weeks (Claude's call, delegated by the owner).
  - Median ties are not handled; validation stops the run if one ever happens.
  - Preseason transactions (week 1, created before `season_start_date`) are kept separate from week 1.

## Open decisions

- Where league members see updates: bookmark only, or also an automatic post to a group chat (Phase 5).
