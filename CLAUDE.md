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

- Python 3.14.7 (`.python-version`), installed as a package from `src/sleeper_dash/` (editable install)
- pandas, requests, pyarrow, pyyaml, scipy; pytest and jupyterlab as the `dev` extra. Exact versions pinned in `pyproject.toml` and `requirements-ci.txt` (see `docs/CODEBASE.md`, "Dependencies")
- Plotly for charts and Jinja2 for the HTML template (Phase 3)
- GitHub for version control, GitHub Actions for the weekly schedule, GitHub Pages for hosting (Phase 4)

## Key docs

- `docs/CODEBASE.md` — repo map, data flow, table schemas, Sleeper API quirks. **Update it in the same commit whenever you add a module, table, or column.**
- `docs/UI_GUIDE.md` — design system and dashboard layout. Follow it for anything user-facing.
- `docs/METRICS_SPEC.md` — source of truth for every metric definition. Written with me in Phase 2. Code follows the spec, not the other way round.
- `docs/DATA_DICTIONARY.md` — field-level notes on raw Sleeper responses (created in Phase 1).
- `docs/RUNBOOK.md` — the owner's plain-language guide for a bad Tuesday: checking a run, failures and what they mean, re-running, rolling back the page, pausing the schedule, updating pins. Keep it in step with the workflows.

## Commands

```powershell
git pull                           # start of every session: the weekly workflow's bot commits refreshed tables to main
.venv\Scripts\Activate.ps1         # start of every session, from the project folder (Mac/Linux: source .venv/bin/activate)
pip install -e ".[dev]"            # one-time setup, or after changing pyproject.toml (dev adds pytest and jupyterlab)
python -m sleeper_dash.pipeline    # full refresh: extract → transform → data checks → metrics → metric checks → save; summary lists every check, whether the week moved, and which tables changed; exit 1 on failure
python -m sleeper_dash.extract     # step 1 only: re-download raw JSON into data/raw/{season}/ and refresh the players cache
python -m sleeper_dash.transform   # step 2 only: rebuild tables from saved files, validate, save, print detailed reports
python -m sleeper_dash.lineup      # rebuild optimal lineups from the saved tables; print latest week, season, and Sleeper max-points check
python -m sleeper_dash.metrics.allplay      # rebuild every metric table; print the season table sorted by luck
python -m sleeper_dash.metrics.consistency  # rebuild every metric table; print volatility, floor/ceiling, booms and busts
python -m sleeper_dash.metrics.schedule     # rebuild every metric table; print strength of schedule, played and remaining
python -m sleeper_dash.metrics.power        # rebuild every metric table; print power rankings with each component's contribution
python -m sleeper_dash.metrics.awards       # rebuild every metric table; print this week's awards and the winners by week
python -m sleeper_dash.metrics.playoff_odds # rebuild every metric table; print the latest playoff odds (seed, bye, title) with their sums
python -m sleeper_dash.metrics.transactions # rebuild every metric table; print pickups, FAAB efficiency, and trade outcomes
python -m sleeper_dash.validate    # re-run the data and metric checks on the saved tables and print pass/fail
python -m sleeper_dash.dashboard   # build site/index.html from the saved tables and the last run record (run the pipeline first); prints weeks, sections, size
python -m http.server 8766 --directory site   # view the built page at http://localhost:8766 (Ctrl+C to stop)
python -m sleeper_dash.dashboard.explainer  # print the "How this works" draft, numbers filled in from config.yaml
pytest                             # run all tests
jupyter lab                        # open the notebooks
gh workflow run weekly.yml --ref main         # run the weekly refresh on GitHub now (same as the Actions tab's "Run workflow" button)
gh run list --workflow weekly.yml --limit 5   # recent weekly runs and whether they passed
gh run view RUN_ID --log                      # read a run's full log (start here when a run fails)
gh workflow run rollback.yml --ref main -f run_id=RUN_ID   # put back the page an earlier Weekly refresh run published (docs/RUNBOOK.md section 4)
gh workflow disable weekly.yml                # pause the schedule (manual runs stop too); gh workflow enable weekly.yml resumes it
```

Keep this list current as commands are added.

## Rules

1. **Full refresh every run.** The pipeline re-pulls and recomputes the whole season each time, so Sleeper stat corrections and model changes flow through everywhere. No incremental appends.
2. **Raw before tidy.** Save untouched API JSON to `data/raw/` first, then transform from those files. Transform and metric code never calls the API.
3. **Tests never hit the network.** Use saved fixtures in `tests/fixtures/`.
4. **Config, not constants.** League ID, season, season start dates, model weights, and thresholds live in `config.yaml`.
5. **IDs are strings:** `league_id`, `user_id`, `owner_id`, `player_id`, `transaction_id`, `draft_id`. `roster_id` is a small integer and is the team key everywhere.
6. **Be polite to Sleeper.** Stay far below 1,000 calls per minute. Fetch `/players/nfl` at most once per day and cache it.
7. **No secrets are needed.** If anything seems to need a key, token, or password, stop and ask me.
8. **Validate before publishing.** Every pipeline run ends with reconciliation checks. A failed check stops the run with a clear message. Never publish numbers that fail. A failed workflow run publishes nothing: the last good page stays live and GitHub emails me.
9. **Metrics are pure functions:** DataFrames in, DataFrames out, no file or network access inside them.
10. **Commit after each working step** with a short plain message, e.g. `Add team_weeks table`, then push to GitHub right away (owner's standing approval). The repo is public, so check that nothing private is staged before committing. The weekly workflow also commits (refreshed `data/processed/` tables), so pull before starting work.
11. **Publish only through the workflows.** The live page comes from `weekly.yml` (refresh) or `rollback.yml` (put back an earlier page), never from a hand-built `site/`. Wording on the page needs my approval before it's pushed, because the next run publishes whatever is on `main`.
12. **Keep `docs/RUNBOOK.md` true.** When a workflow, a step name, the schedule, or what a failure does changes, update the runbook in the same commit. It's what I use when something goes wrong.
13. **When a run fails, explain before fixing.** Read the log, tell me in plain language which step failed and why, and wait for my go-ahead before changing code, data, or settings.

## Current status

**Phase 4 — Automation: complete (2026-10-03),** including monitoring (run summaries, failure emails tested, the stale-data line), rollback, and the runbook. Phase 5 — Extras is in progress: playoff odds (`docs/METRICS_SPEC.md` section 8) are built on the `playoff-odds` branch (2026-10-05) and the page wording is approved; the branch is merged to `main` once the Tuesday Oct 6 run is checked (`docs/HANDOFF.md` section 9). Past seasons and History (wording approved) follow on `past-seasons`, and the playoff bracket (the Playoffs section, wording approved) on `bracket-view`, merged in that order. The plan for the other extras is in section 9 too. Update this section at the end of every phase.

**Starting a new session? Read `docs/HANDOFF.md` first.** It covers working style, environment quirks, the decisions log, open questions, and the next steps.

Where things stand:
- **Live at https://jonaht26.github.io/sleeper-dashboard/.** `.github/workflows/weekly.yml` runs every Tuesday and Thursday at 12:17 PM Eastern (and on demand): tests → pipeline → dashboard → page tests on the fresh tables → commit changed tables → publish to GitHub Pages. Any failure stops before publishing and GitHub emails me. Running it, failures, and the season-rollover checklist: `docs/HANDOFF.md` section 7a; my plain-language guide: `docs/RUNBOOK.md`.
- **Monitoring:** each run's GitHub page opens with a summary (latest week, checks passed, tables written, commit, step results, published URL, or where it failed). Failure emails reach me (tested 2026-10-03 with a run that failed on purpose). The page's "Updated" time is pinned to the top of the screen; after 8 days without an update (`config.yaml` `dashboard.stale_after_days`) it says which week the rankings are from and when the next update is due, or "Final rankings for the 2026 season." once Sleeper marks the season complete.
- **Rollback:** `.github/workflows/rollback.yml` republishes the page from any Weekly refresh run in the last 90 days (published pages are kept 90 days).
- Python 3.14.7 and every package pinned (`.python-version`, `pyproject.toml`, `requirements-ci.txt`); tests check the installed versions match. Updating: `docs/CODEBASE.md` "Dependencies".
- `python -m sleeper_dash.pipeline` runs a full refresh: extract → transform → 10 data checks → optimal lineups and metrics → 9 metric invariant checks → save → re-check the saved files, for every season from 2020 (`config.yaml` `history_from`) to 2026, each against its own league settings and Sleeper standings. Either group of checks stops the run before anything is saved. Through 2026 week 3: every check passes in every season, 262 API calls, ~80 seconds, and two consecutive runs give byte-identical outputs. A run with no new completed week succeeds and leaves every table unchanged unless Sleeper corrected a past score.
- 18 tables in `data/processed/` (schemas in `docs/CODEBASE.md`), every season stacked by its `season` column: `teams`, `team_weeks`, `player_weeks`, `transactions`, `trade_assets`, `schedule`, `winners_bracket`, `lineups_optimal`, `lineups_optimal_players`, `metrics_team_weeks`, `metrics_season`, `power_rankings`, `awards`, `playoff_odds`, `start_credits`, `pickups`, `trades`, plus `managers` (one row per Sleeper owner ID across seasons). The page shows the current season only.
- Every metric follows `docs/METRICS_SPEC.md` (owner-approved). Every weight and threshold is in `config.yaml` under `metrics:`.
- `python -m sleeper_dash.dashboard` builds `site/index.html`: masthead with week selector, power rankings ladder (tap a row for its breakdown), playoff odds (from week 3), weekly awards, five charts (luck, lineup efficiency, consistency, strength of schedule, rank history), Roster moves (on the `transaction-metrics` branch: best pickups, FAAB, trades), History (every finished season since 2020), and "How this works". Every completed week is in the page; no network calls except Google Fonts and the Plotly CDN; 28 KB compressed for weeks 1–3. Checked at 360, 390, 1024 and 1280px in light and dark mode.
- 489 tests pass, locally and in GitHub Actions, including page-level tests (every number on the page equals the CSVs), the UI_GUIDE quality floor, and the whole pipeline run offline against a fake Sleeper league (season rollover, off-season, no new week, stat corrections). Notebooks: `01_data_check.ipynb`, `02_power_score_sensitivity.ipynb`, `04_playoff_odds_calibration.ipynb`.
- Playoff weeks: the assumptions held on this league's 2025 season (standings are regular season only; every team listed every week; byes unpaired; consolation games paired) and the pipeline passes on its real playoff weeks. In playoff weeks the standings checks accept either counting standard (one must fit every team); missing or unscored teams stop the run; consolation games count for awards (owner, 2026-10-03).

Roadmap:
- Phase 0: Setup (environment, repo, API smoke test) — complete
- Phase 1: Data pull (raw extract, tidy tables, validation) — complete
- Phase 2: Metrics (spec, optimal lineups, luck, consistency, schedule, power score, awards) — complete
- Phase 3: Dashboard (static HTML per `docs/UI_GUIDE.md`) — complete
- Phase 4: Automation (weekly GitHub Action, GitHub Pages, monitoring, rollback, runbook) — complete
- Phase 5: Extras (weekly league-chat post, playoff odds simulation, boom/bust display, past seasons, season rollover); order and plan in `docs/HANDOFF.md` section 9

## Decisions made

- **Public GitHub repo** (`sleeper-dashboard`), decided 2026-10-02 in Phase 0, so the dashboard can use free GitHub Pages hosting. Everything committed is visible to anyone, so never commit anything that isn't safe to share.
- **Raw data stays off GitHub** (2026-10-02). `data/raw/` is gitignored because it holds managers' personal settings; the pipeline re-downloads it every run. Test fixtures are anonymised (fake `owner_id`s, nicknames replaced).
- **Processed tables are committed publicly** (2026-10-02, owner's explicit choice). `data/processed/*.csv`, including usernames, team names, and Sleeper owner IDs in `teams.csv`, go to GitHub.
- **Metric data rules** (2026-10-02; details and evidence in `docs/DATA_DICTIONARY.md`, carried into `docs/METRICS_SPEC.md`):
  - Injured-reserve players count as bench in past weeks (Claude's call, delegated by the owner).
  - Median ties are not handled; validation stops the run if one ever happens.
  - Preseason transactions (week 1, created before `season_start_date`) are kept separate from week 1.
- **Metric definitions** (Phase 2, 2026-10-02): all seven in `docs/METRICS_SPEC.md`, each confirmed by the owner. Notable choices: the displayed record includes median games; luck uses all-play expected wins; the power score blends season scoring 0.35, recent form 0.25, roster strength 0.20, head-to-head results 0.20; every past week is recomputed on each run (no frozen rankings).

- **Before Phase 3** (owner, 2026-10-02):
  - The dashboard is public and indexable (no `noindex`); usernames stay on the ladder.
  - Power scores show 1 decimal place; near-ties may show identical numbers.
  - Metric sections that aren't available yet (consistency and strength of schedule before week 3) are hidden entirely.
  - The owner reviews the "How this works" copy before it goes live.
  - Nail-biter is enabled (nine weekly awards).
  - The power score's results weight stays at 0.20 for now.
- **Dark-mode masthead** (owner, 2026-10-02): a `--masthead` colour token, `#18392B` in both light and dark modes, so the masthead stands out from the dark-mode page (`docs/UI_GUIDE.md` Color).
- **Ladder design** (owner, prototype review 2026-10-02; details in `docs/UI_GUIDE.md` Ladder row): build mobile first; power score bars run from the league average (50), not 0–100; the tap-to-expand breakdown shows each component's "Score" (contribution), then its gap from average as a small bar and signed number, totalling "Power score"; the results component is labelled "Head-to-head wins" with the head-to-head record, while the ladder keeps the overall record; the latest week is written into the HTML at build time, and "Updated" is the pipeline's run time.
- **Page weight** (owner, 2026-10-02): the 1 MB budget counts compressed bytes, what a visitor downloads.
- **How this works** (owner, 2026-10-02): the draft was approved with no edits and is published; any wording change needs the owner's approval again.
- **Phase 3 wrap-up** (owner, 2026-10-02): the guide's chalk-on-turf contrast corrected to 11.8:1; design-review fixes approved (ladder key "League average: 50"; rank-history team names cut to 14 characters on phones; reading text ~72 characters a line; compact award tiles on desktop; centred 1200px column). Details in `docs/UI_GUIDE.md` and `docs/HANDOFF.md` section 6.
- **Hosting** (Claude, delegated by the owner, 2026-10-02): GitHub Pages publishes the built `site/` folder through a GitHub Actions workflow (Pages source: "GitHub Actions"), not from a branch or the `docs/` folder. `site/` is a build output and stays out of git; `docs/` stays internal.

- **Automation** (owner, 2026-10-03): weekly runs Tuesday and Thursday 12:17 PM Eastern; the workflow commits refreshed tables back to the repo; Python 3.14.7 with every dependency pinned; failures email the owner (GitHub's default). Season start dates are stored per season in `config.yaml`, never taken from Sleeper's current-season state, so off-season runs and past seasons work. Details in `docs/HANDOFF.md` section 6.
- **Past seasons** (owner, 2026-10-05): every season Sleeper has (2020–2025) is rebuilt on every run alongside 2026, through `previous_league_id`; managers matched by owner ID; past seasons' usernames, team names and owner IDs committed publicly like 2026's; start dates the Wednesday before kickoff; Sleeper's known stale season totals (2020, 2021, 2023) listed in `config.yaml` `sleeper_points_gaps` and allowed exactly; a player may fill the single-position slot he started in that week (METRICS_SPEC.md section 3); the regular season counts from week 1 whatever Sleeper's `start_week` says. The History section's design is approved (champions, all-time records with former managers folded, last season's luck, the highest weekly score; usernames; regular-season records including median games); its wording is approved as drafted (2026-10-05).
- **Playoff odds** (owner, 2026-10-05): the definition in `docs/METRICS_SPEC.md` section 8 (every recommended option), per-seed odds, the page section and its "How this works" paragraph approved as drafted; built on the `playoff-odds` branch and merged after the Tuesday Oct 6 run is checked.
- **Season rollover** (owner, 2026-10-05): `config.yaml` stays on 2026 until 2027's week 1 is scored (the page shows 2026's final rankings until then); a scheduled Claude session on Tue Sep 14 2027 (`sleeper-season-2027-rollover`) switches it on a branch and reports; switching early stops the run with a plain message. Past seasons' weekly pages aren't kept; History covers them.
- **Monitoring and recovery** (owner, 2026-10-03): a run summary on every run's page; "Updated" always visible; a stale-data line after 8 days ("The latest rankings are from week N. Next update due …", approved wording), which becomes "Final rankings for the XXXX season." after the season, and in both cases appears only after 8 days; a rollback workflow; the runbook.

## Open decisions

- Where league members see updates: bookmark only, or also a weekly post to the league chat (Phase 5).
