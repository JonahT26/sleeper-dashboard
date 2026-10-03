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
python -m sleeper_dash.pipeline    # full refresh: extract → transform → data checks → metrics → metric checks → save; summary lists every check; exit 1 on failure
python -m sleeper_dash.extract     # step 1 only: re-download raw JSON into data/raw/{season}/ and refresh the players cache
python -m sleeper_dash.transform   # step 2 only: rebuild tables from saved files, validate, save, print detailed reports
python -m sleeper_dash.lineup      # rebuild optimal lineups from the saved tables; print latest week, season, and Sleeper max-points check
python -m sleeper_dash.metrics.allplay      # rebuild every metric table; print the season table sorted by luck
python -m sleeper_dash.metrics.consistency  # rebuild every metric table; print volatility, floor/ceiling, booms and busts
python -m sleeper_dash.metrics.schedule     # rebuild every metric table; print strength of schedule, played and remaining
python -m sleeper_dash.metrics.power        # rebuild every metric table; print power rankings with each component's contribution
python -m sleeper_dash.metrics.awards       # rebuild every metric table; print this week's awards and the winners by week
python -m sleeper_dash.validate    # re-run the data and metric checks on the saved tables and print pass/fail
python -m sleeper_dash.dashboard   # build site/index.html from the saved tables (run the pipeline first)
python -m sleeper_dash.dashboard.explainer  # print the "How this works" draft, numbers filled in from config.yaml
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

**Phase 3 — Dashboard: in progress** (static HTML per `docs/UI_GUIDE.md`; plan in `docs/HANDOFF.md` section 9). Phase 2 — Metrics: complete (2026-10-02). Update this section at the end of every phase.

**Starting a new session? Read `docs/HANDOFF.md` first.** It covers working style, environment quirks, the decisions log, open questions, and the next steps.

Where things stand:
- `python -m sleeper_dash.pipeline` runs a full refresh: extract → transform → 7 data checks → optimal lineups and metrics → 7 metric invariant checks → save → re-check the saved files. Either group of checks stops the run before anything is saved. Weeks 1–3: every check passes, 23 API calls, ~6.5 seconds, and two consecutive runs give byte-identical outputs.
- 11 tables in `data/processed/` (schemas in `docs/CODEBASE.md`): `teams`, `team_weeks`, `player_weeks`, `transactions`, `schedule`, `lineups_optimal`, `lineups_optimal_players`, `metrics_team_weeks`, `metrics_season`, `power_rankings`, `awards`.
- Every metric follows `docs/METRICS_SPEC.md` (owner-approved): all-play record, expected wins and luck, lineup efficiency, consistency, strength of schedule, power score, weekly awards. Every weight and threshold is in `config.yaml` under `metrics:`.
- 274 tests pass. Notebooks: `01_data_check.ipynb` (data eyeballing), `02_power_score_sensitivity.ipynb` (power weights ±25%: rankings robust; only near-tied teams move).
- Phase 3 step 1 done (2026-10-02): `metrics_season` has season-to-date lineup efficiency (Σ actual ÷ Σ optimal) and points left on the bench, with their own metric check.
- Phase 3 step 3 under way (2026-10-02): `python -m sleeper_dash.dashboard` builds `site/index.html` with the masthead, the power rankings ladder, and weekly awards, and all five charts (luck, lineup efficiency, consistency, strength of schedule, rank history) for every completed week (week selector, no network calls; charts use the shared theme in `dashboard/theme.py`). "How this works" (owner-approved copy, numbers from `config.yaml`) is the last section. Phase 3 is functionally complete; next is a final review with the owner, then Phase 4.
- To verify at week 15: whether Sleeper plays the median game in the playoffs, whether roster `wins`/`fpts`/`ppts` include playoff games, and how non-playoff teams appear in matchups.

Roadmap:
- Phase 0: Setup (environment, repo, API smoke test) — complete
- Phase 1: Data pull (raw extract, tidy tables, validation) — complete
- Phase 2: Metrics (spec, optimal lineups, luck, consistency, schedule, power score, awards) — complete
- Phase 3: Dashboard (static HTML per `docs/UI_GUIDE.md`)
- Phase 4: Automation (weekly GitHub Action, GitHub Pages)
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
- **Hosting** (Claude, delegated by the owner, 2026-10-02): GitHub Pages publishes the built `site/` folder through a GitHub Actions workflow (Pages source: "GitHub Actions"), not from a branch or the `docs/` folder. `site/` is a build output and stays out of git; `docs/` stays internal.

## Open decisions

- Where league members see updates: bookmark only, or also an automatic post to a group chat (Phase 5).
