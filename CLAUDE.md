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
python -m sleeper_dash.validate    # re-run the data and metric checks on the saved tables and print pass/fail
python -m sleeper_dash.dashboard   # build site/index.html from the saved tables and the last run record (run the pipeline first); prints weeks, sections, size
python -m http.server 8766 --directory site   # view the built page at http://localhost:8766 (Ctrl+C to stop)
python -m sleeper_dash.dashboard.explainer  # print the "How this works" draft, numbers filled in from config.yaml
pytest                             # run all tests
jupyter lab                        # open the notebooks
gh workflow run weekly.yml --ref main         # run the weekly refresh on GitHub now (same as the Actions tab's "Run workflow" button)
gh run list --workflow weekly.yml --limit 5   # recent weekly runs and whether they passed
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
8. **Validate before publishing.** Every pipeline run ends with reconciliation checks. A failed check stops the run with a clear message. Never publish numbers that fail.
9. **Metrics are pure functions:** DataFrames in, DataFrames out, no file or network access inside them.
10. **Commit after each working step** with a short plain message, e.g. `Add team_weeks table`, then push to GitHub right away (owner's standing approval). The repo is public, so check that nothing private is staged before committing. The weekly workflow also commits (refreshed `data/processed/` tables), so pull before starting work.

## Current status

**Phase 4 — Automation: complete (2026-10-03).** Phase 5 — Extras is next; ask me which extra comes first (`docs/HANDOFF.md` section 9). Update this section at the end of every phase.

**Starting a new session? Read `docs/HANDOFF.md` first.** It covers working style, environment quirks, the decisions log, open questions, and the next steps.

Where things stand:
- **Live at https://jonaht26.github.io/sleeper-dashboard/.** `.github/workflows/weekly.yml` runs every Tuesday and Thursday at 12:17 PM Eastern (and on demand): tests → pipeline → dashboard → page tests on the fresh tables → commit changed tables → publish to GitHub Pages. Any failure stops before publishing and GitHub emails me. Running it, failures, and the season-rollover checklist: `docs/HANDOFF.md` section 7a.
- Python 3.14.7 and every package pinned (`.python-version`, `pyproject.toml`, `requirements-ci.txt`); tests check the installed versions match. Updating: `docs/CODEBASE.md` "Dependencies".
- `python -m sleeper_dash.pipeline` runs a full refresh: extract → transform → 7 data checks → optimal lineups and metrics → 7 metric invariant checks → save → re-check the saved files. Either group of checks stops the run before anything is saved. Weeks 1–3: every check passes, 23 API calls, ~7 seconds, and two consecutive runs give byte-identical outputs. A run with no new completed week succeeds and leaves every table unchanged unless Sleeper corrected a past score.
- 11 tables in `data/processed/` (schemas in `docs/CODEBASE.md`): `teams`, `team_weeks`, `player_weeks`, `transactions`, `schedule`, `lineups_optimal`, `lineups_optimal_players`, `metrics_team_weeks`, `metrics_season`, `power_rankings`, `awards`.
- Every metric follows `docs/METRICS_SPEC.md` (owner-approved). Every weight and threshold is in `config.yaml` under `metrics:`.
- `python -m sleeper_dash.dashboard` builds `site/index.html`: masthead with week selector, power rankings ladder (tap a row for its breakdown), weekly awards, five charts (luck, lineup efficiency, consistency, strength of schedule, rank history), and "How this works". Every completed week is in the page; no network calls except Google Fonts and the Plotly CDN; 27 KB compressed for weeks 1–3. Checked at 360, 390, 1024 and 1280px in light and dark mode.
- 406 tests pass, locally and in GitHub Actions, including page-level tests (every number on the page equals the CSVs), the UI_GUIDE quality floor, and the whole pipeline run offline against a fake Sleeper league (season rollover, off-season, no new week, stat corrections). Notebooks: `01_data_check.ipynb`, `02_power_score_sensitivity.ipynb`.
- Playoff weeks: the assumptions held on this league's 2025 season (standings are regular season only; every team listed every week; byes unpaired; consolation games paired) and the pipeline passes on its real playoff weeks. In playoff weeks the standings checks accept either counting standard (one must fit every team); missing or unscored teams stop the run; consolation games count for awards (owner, 2026-10-03).

Roadmap:
- Phase 0: Setup (environment, repo, API smoke test) — complete
- Phase 1: Data pull (raw extract, tidy tables, validation) — complete
- Phase 2: Metrics (spec, optimal lineups, luck, consistency, schedule, power score, awards) — complete
- Phase 3: Dashboard (static HTML per `docs/UI_GUIDE.md`) — complete
- Phase 4: Automation (weekly GitHub Action, GitHub Pages) — complete
- Phase 5: Extras (playoff odds simulation, past seasons, posting to league chat)

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

## Open decisions

- Where league members see updates: bookmark only, or also an automatic post to a group chat (Phase 5).
