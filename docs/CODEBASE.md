# Codebase guide

What lives where, how data moves, and the shape of every table. Phases 0–4 are built (data pull, metrics, and the dashboard, 2026-10-02; automation, 2026-10-03). As modules get built, change their status from `planned` to `built`.

> Claude: keep this file current. When you add or change a module, table, or column, update this file in the same commit.

## Data flow

```
Sleeper API
    │
    ▼
extract.py ─────────► data/raw/{season}/*.json        untouched API responses, one folder per season (gitignored)
    │      └────────► data/cache/players_nfl.json     player list, refreshed at most once a day (gitignored)
    ▼
transform.py                                          tidy tables in memory, per season: teams, team_weeks, player_weeks,
    │                                                 transactions, schedule, winners_bracket; then managers (see Data model)
    ▼
validate.py: data checks                              8 checks per season, against that season's league and standings,
    │                                                 plus managers across seasons (9);
    │                                                 any failure stops the run
    ▼
lineup.py + metrics/                                  optimal lineups, then every metric table, in memory:
    │                                                 lineups_optimal(_players), metrics_team_weeks, metrics_season,
    │                                                 power_rankings, awards, playoff_odds
    ▼
validate.py: metric checks                            8 checks (the spec's invariants); any failure stops the run
    │
    ▼
data/processed/*.csv                                  all 14 tables, seasons stacked, saved only now, then re-read and all 17 checks run again
    │
    ▼
dashboard/ ► site/index.html                          static page (python -m sleeper_dash.dashboard); reads the saved CSVs
    │                                                 and data/cache/pipeline_run.json (when the pipeline last finished)
    │
    ▼
GitHub Pages                                          .github/workflows/weekly.yml, Tue + Thu 12:17 PM Eastern: pytest →
                                                      pipeline → dashboard → page tests on the fresh tables → commit
                                                      changed data/processed/*.csv → publish site/ (never committed);
                                                      a run summary on the run's page; the published page kept 90 days.
                                                      .github/workflows/rollback.yml (manual) republishes an earlier one
```

`python -m sleeper_dash.pipeline` runs every step in order as a full refresh: extract → transform → data checks → metrics (optimal lineups and every metric table) → metric checks → save → re-read and re-check the saved CSVs. Data checks and metric checks each stop the run on any failure, before anything is saved. The summary lists tables and row counts, every data and metric check with PASS/FAIL, the saved-file re-check, soft-check warnings (e.g. optimal points vs Sleeper's max points) that never stop the run, API calls, and run time (~6.5 seconds). Nothing is appended incrementally. Two back-to-back runs produce byte-identical raw and processed files (verified 2026-10-02 with every metric table in place: 35 of 35 files, SHA-256). Exit code 1 on any failure, leaving the last good tables in place.

**When there is no new completed week** (e.g. a run before Sleeper has scored Monday night, a Thursday run, or any run in the off-season), the pipeline does the same full refresh and succeeds. If Sleeper's data hasn't changed, every saved table comes out byte-identical; only a stat correction to a past week changes numbers. The summary says which, compared with the tables already in `data/processed/` (so it works on a fresh GitHub Actions machine): "Latest completed week: 3 (no new completed week since the last run)" and "Tables vs the last run: unchanged (every file identical)" or the list of tables that changed. The run record and the page's "Updated" time still move to this run, and the workflow commits nothing when no table changed.

## Repository layout

```
sleeper-dashboard/
├── CLAUDE.md                    project context for Claude Code
├── config.yaml                  league_id, season, season_start_dates (one per season), model weights, thresholds
├── pyproject.toml               package definition and exact dependency versions (dev extra: pytest, jupyterlab)
├── requirements-ci.txt          lock file: every package GitHub Actions installs, pinned (see Dependencies)
├── .python-version              Python version for GitHub Actions and local (3.14.7)
├── docs/
│   ├── CODEBASE.md              this file
│   ├── UI_GUIDE.md              design system and dashboard layout
│   ├── METRICS_SPEC.md          metric definitions (Phase 2, owner-approved)
│   ├── DATA_DICTIONARY.md       raw Sleeper field notes (Phase 1)
│   ├── RUNBOOK.md               the owner's plain-language guide for a failed or doubtful weekly run
│   └── HANDOFF.md               session handoff: working style, environment, decisions, open questions
├── src/sleeper_dash/
│   ├── __init__.py
│   ├── config.py                loads config.yaml
│   ├── api.py                   Sleeper HTTP client: retries, pacing, players cache
│   ├── extract.py               API → data/raw/
│   ├── transform.py             data/raw/ → data/processed/ tidy tables
│   ├── validate.py              data checks and metric invariant checks
│   ├── lineup.py                optimal lineup solver (assignment problem); lineup efficiency, points left on the bench
│   ├── metrics/
│   │   ├── __init__.py          combines the modules into the metric tables
│   │   ├── allplay.py           all-play record, expected wins, luck
│   │   ├── consistency.py       volatility, floor/ceiling, boom/bust
│   │   ├── schedule.py          strength of schedule
│   │   ├── power.py             power score and weekly rankings
│   │   └── awards.py            weekly awards
│   ├── dashboard/
│   │   ├── build.py             page builder: tables → view (formatted values) → HTML
│   │   ├── __main__.py          `python -m sleeper_dash.dashboard`
│   │   ├── theme.py             the one shared Plotly theme: base layout, config, colour tokens, CDN URL
│   │   ├── charts.py            chart sections as Plotly figure dicts: luck, efficiency, consistency, schedule, rank history
│   │   ├── explainer.py         "How this works" copy (owner-approved), numbers filled in from config.yaml
│   │   └── templates/           index.html.j2 (Jinja2); styles.css, page.js (week selector), charts.js (drawing, highlight, labels), inlined into the page
│   └── pipeline.py              `python -m sleeper_dash.pipeline`
├── scripts/
│   └── smoke_test.py            one-off API check from Phase 0
├── data/
│   ├── raw/{season}/            gitignored: the season's raw JSON (personal settings; re-downloaded every run)
│   ├── cache/                   gitignored: players_nfl.json
│   └── processed/               committed: tidy CSVs
├── notebooks/                   committed without outputs
│   ├── 01_data_check.ipynb      standings and score distributions (Phase 1)
│   ├── 02_power_score_sensitivity.ipynb   power weights perturbed ±25% (Phase 2)
│   └── 04_playoff_odds_calibration.ipynb  playoff odds against 2025's real outcomes: Brier and reliability (Phase 5)
├── tests/
│   ├── fixtures/                saved API responses for offline tests
│   └── test_*.py
├── site/                        Phase 3 build output (gitignored; GitHub Actions builds and publishes it to Pages)
└── .github/workflows/
    ├── weekly.yml               weekly refresh and GitHub Pages publish (Phase 4)
    └── rollback.yml             manual: republish the page an earlier weekly run published (Phase 4)
```

## Modules

| Module | Responsibility | Phase | Status |
|---|---|---|---|
| `config.py` | Load and validate `config.yaml`: quoted `league_id`, whole-number `season`, `season_start_dates` (one YYYY-MM-DD date per season, each in its own year; the configured season must have one); `Config.start_date(season)` | 0 | built |
| `api.py` | `get(path)` with timeout, retries, backoff, pacing; `get_players()` with 24h file cache | 1 | built |
| `extract.py` | Pull league, users, rosters, state, drafts, picks (`picks/draft_{id}.json`), and per-week matchups and transactions (`matchups/week_XX.json`, `transactions/week_XX.json`) into `data/raw/{season}/`, plus the published pairings for the rest of the regular season (`schedule/week_XX.json`: matchups for future weeks, 0 points; about 11 extra calls early in the season, none after it), and Sleeper's winners bracket (`winners_bracket.json`: provisional during the regular season, the real one in the playoffs; stored as `[]` when Sleeper returns nothing). Writes to a `.partial` staging folder and swaps it in only when every call succeeds (`_swap_in`, which retries up to 5 times, 2 s at most, when Windows briefly refuses to replace the folder). Also refreshes the players cache via `api.get_players()` (at most once a day) | 1 | built |
| `transform.py` | Build the tidy tables below from saved files only (raw JSON plus the players cache), one season at a time: `teams`, `team_weeks`, `player_weeks`, `transactions`, `schedule`, `winners_bracket`. `python -m sleeper_dash.transform` builds and checks every configured season and saves them stacked, with `managers` | 1–2, 5 | built |
| `seasons.py` | Several seasons at once (Phase 5): `season_slice`, `stack` (every season's rows, in season order), `build_managers` (one row per owner ID: latest display name, first and last season, seasons played), `with_known_gaps` (adds `config.yaml` `sleeper_points_gaps` back to Sleeper's stored totals before the points check), `league_files` | 5 | built |
| `validate.py` | Seventeen checks in two groups (Phase 5: `validate_seasons` runs each group once per season against that season's league and rosters and `combine_season_results` merges them, one line per check naming any season that failed; `check_managers` runs once across seasons): `run_data_checks` (on the transform tables) and `run_metric_checks` (on the lineup and metric tables); `run_checks` runs both, and `validate(..., checks, stage)` raises `ValidationError` naming the stage. The checks: one row per team per completed week (and no missing weeks); each `matchup_id` has exactly 2 teams; starter points equal team points (±0.01); W–L–T matches Sleeper's roster settings, counting median games when the league has them, and points for/against match `fpts`/`fpts_against` (±0.01): regular season only, which is how Sleeper counts (2025 season); in playoff weeks a standard that also counts playoff games, a playoff median, or playoff points is accepted, but one standard must fit every team, and the check's detail names it (owner decision 2026-10-03); optimal lineups are consistent (one per team-week, actual = team score, optimal ≥ actual, optimal = sum of chosen players, no player used twice; only when the lineup tables are present); all-play and luck are consistent (all-play W + L + T = teams − 1, league all-play wins = n(n − 1)/2 per week, expected wins = actual wins and luck sums to 0 in every regular-season week where all teams played, `median_result` = W exactly when all-play wins ≥ n/2, season totals = weekly sums, season record = Sleeper's official record; only when the metric tables are present); the schedule is complete and matches games played (one row per team in every regular-season week, symmetric pairings, `is_completed` right, completed pairings = `team_weeks`); consistency and schedule metrics are consistent (no week both boom and bust, floor ≤ ceiling, volatility ≥ 0, booms + busts ≤ weeks, SOS games played + remaining = regular-season weeks); season lineup efficiency is consistent (every team and `through_week` has a row, efficiency = Σ actual ÷ Σ optimal from `lineups_optimal` to 4 dp and within 0–1, null only when Σ optimal ≤ 0, points left on the bench = Σ (optimal − actual) within 0.01); power rankings are consistent (one row per team-week, contributions sum to the power score, league mean 50 every week, scores within 0–100, ranks 1…N without duplicates, rank_change = previous rank − rank); weekly awards are consistent (each score or margin award's value equals the winner's own score or margin and the week's best among eligible teams, Heartbreaker winners lost and Robbery winners won, Bench blunder equals points left on the bench, no empty captions); seeding matches Sleeper's bracket (our seeding by wins, then points for, gives the byes and first-round pairings of Sleeper's provisional or real `winners_bracket`; passes with "nothing to compare" when Sleeper has no filled-in bracket; Phase 5); playoff odds add up (METRICS_SPEC.md section 8 sanity checks 1–5: probabilities in 0–1, bye and title odds ≤ playoff odds, each week 6 playoff spots, 2 byes, 1 title and every seed once, a team's seed odds sum to its playoff odds, average final wins sum to the season's wins, Clinched teams at 1 and Out teams at 0, and after the last regular-season week the final standings; Phase 5); no duplicate keys, checked once for the data tables and once for the metric tables. `python -m sleeper_dash.transform` runs the data checks before saving its tables; the pipeline runs both groups (see Data flow); `python -m sleeper_dash.validate` re-checks the saved CSVs and prints both groups | 1–2 | built |
| `pipeline.py` | Orchestrates extract → transform → data checks → metrics → metric checks → save → re-check the saved CSVs; either group of checks failing stops the run before saving. A successful run writes `data/cache/pipeline_run.json` (finish time in UTC, league name, season, weeks, and `league`: teams, median game, playoff start, for the "How this works" copy, and `season_complete` (Sleeper's league `status` is `complete`), which turns the page's stale-data line into "Final rankings for the XXXX season."; gitignored, so the processed tables stay byte-identical across runs). Prints a run summary listing every check, plus soft-check warnings; exit code 1 on failure. The summary also says whether the latest completed week moved and which tables changed, compared with the tables already saved (`saved_snapshot`: SHA-256 of each CSV, read before and after saving). In GitHub Actions (`GITHUB_STEP_SUMMARY` set) it also writes the summary as markdown to the run's page (`summary_markdown`: latest week, checks passed, tables written with rows and whether each changed, every check), or the reason it stopped (`failure_markdown`); tests clear the variable (`conftest.py`) | 1–3 | built |
| `lineup.py` | Optimal lineup per team-week (METRICS_SPEC.md section 3), solved exactly as an assignment problem with `scipy.optimize.linear_sum_assignment`: slots × players, cost −points where eligible and 10⁶ where not, so every fillable slot is filled before points are maximised; tiny bonuses (< 0.01 in total) break exact ties toward the manager's own starters and slots. Eligibility from the players cache `fantasy_positions` (fallback: `position`; neither stops the run). `efficiency_season` adds season-to-date efficiency and points left on the bench to `metrics_season`. `compare_to_sleeper_max` is the `ppts` soft check. `python -m sleeper_dash.lineup` rebuilds from the saved CSVs, validates, saves, and prints the latest week, season totals, and the soft check | 2 | built |
| `metrics/allplay.py` | All-play record, expected wins, and luck (METRICS_SPEC.md sections 1–2): `build_metrics_team_weeks`, `build_metrics_season`. All-play by within-week ranking of points (2 dp); expected wins = weekly all-play % + median result; actual wins = head-to-head + median result; luck = actual − expected, regular season only. `python -m sleeper_dash.metrics.allplay` rebuilds every metric table from the saved CSVs, validates, saves, and prints the season table sorted by luck | 2 | built |
| `metrics/consistency.py` | Volatility, floor/ceiling, boom/bust (section 4): `consistency_team_weeks`, `consistency_season`; `check_params` stops on unusable `config.yaml` values. `python -m sleeper_dash.metrics.consistency` reports | 2 | built |
| `metrics/schedule.py` | Strength of schedule, played and remaining (section 5): `strength_of_schedule` from `team_weeks` and `schedule`. `python -m sleeper_dash.metrics.schedule` reports | 2 | built |
| `metrics/power.py` | Power score and rankings as of every completed week (section 6): `build_power_rankings` from `team_weeks` and `lineups_optimal`; every weight and parameter from `config.yaml` `metrics.power`, checked by `check_params` (weights exactly the four components, ≥ 0, summing to 1; `scale` small enough to keep scores in 0–100). `python -m sleeper_dash.metrics.power` reports the rankings with each component's contribution | 2 | built |
| `metrics/playoff_odds.py` | Playoff odds (section 8): `build_playoff_odds` from `team_weeks`, `schedule`, and the league settings, for every completed regular-season week from `min_weeks`. Scores relative to each week's league mean; strength shrunk toward the league mean with `shrink_weeks`; one pooled score SD; `simulate` draws each team's true mean once per simulated season, then every remaining regular-season and playoff week, plays the schedule, the median game, seeding (wins, then points for), and the fixed 6-team bracket; `proven_status` gives Clinched / Out from a bound. A seed per (season, week) from `SeedSequence([seed, season, week])`, so every week is reproducible on its own. `league_format` stops the run unless the settings are the verified format (`VERIFIED_FORMAT`); `check_params` checks `config.yaml` `metrics.playoff_odds`. `python -m sleeper_dash.metrics.playoff_odds` reports the latest week | 5 | built |
| `metrics/__init__.py` | `build_metric_tables` merges the modules' columns into `metrics_team_weeks` and `metrics_season` and adds `power_rankings`, `awards`, and `playoff_odds` (only when given the league settings); `rebuild_from_saved` backs the modules' report commands | 2 | built |
| `metrics/awards.py` | Weekly awards (section 7): all 11 defined awards are computed each week; `metrics.awards.enabled` in `config.yaml` picks which appear and their order (`check_params` rejects unknown or repeated keys). Captions follow `UI_GUIDE.md`. Pickup of the week uses each team's latest `add` of the player (waiver or free agent only). `python -m sleeper_dash.metrics.awards` prints this week's awards and the winners by week | 2 | built |
| `dashboard/history.py` | The History section (Phase 5; UI_GUIDE.md "History"): `history_view(tables, current_season)` from every saved season's `teams`, `managers`, `metrics_season`, `team_weeks` and `winners_bracket`: champions, all-time regular-season records with playoff appearances and titles, current and former managers, last season's luckiest and unluckiest teams, and the highest weekly score; `None` (section hidden) until a season has finished | 5 | built |
| `dashboard/bracket.py` | The Playoffs section (Phase 5; UI_GUIDE.md "Playoffs"): `bracket_view(bracket, team_weeks, names, league, week)` from one season's `winners_bracket` and `team_weeks`: each round with its week, seeds (our seeding of the final regular-season standings, `metrics.playoff_odds.seeding`), the week's points, Sleeper's winner, the byes, and the champion, as known by `week` (round r is played in week `playoff_week_start` + r − 1; a slot shows its team once the game feeding it is played, otherwise "Winner of 1 v 5"). Returns `None` (section hidden) before the playoffs | 5 | built |
| `dashboard/build.py` | Renders `site/index.html` per `docs/UI_GUIDE.md` from `teams`, `team_weeks`, `power_rankings`, `metrics_season`, `lineups_optimal`, `awards`, the pipeline run record, and `config.yaml` `metrics.power`. `build_view` (pure) formats every number once for every completed week: ladder rows (record and all-play as of that week, power score bar from 50, movement, the four-component breakdown) and award tiles (co-winners share a tile). One Jinja2 template draws a week; the latest week is drawn straight into the page and each earlier week into a `<template id="week-N">` block that the selector swaps in with a few lines of JavaScript, so no week needs a network call and there is no second renderer to drift. A section with no data for a week (e.g. awards) is left out. Bars share one fixed axis for the season. Template indentation is stripped (~15% of the page). Sections: masthead, ladder, playoff odds (Phase 5: from week 3 to the last regular-season week; `_odds_section` sorts the teams and formats each chance with `chance`, which says "<1%" or ">99%" unless the value is certain, and "Clinched"/"Out" only when `playoff_odds` proves them), weekly awards, all five charts (each left out until its data exists), and "How this works". The build summary reports the compressed size, which is what the 1 MB budget counts. **Status bar** (2026-10-03): "Updated" pinned to the top while scrolling, plus a hidden stale-data line that `page.js` shows when the run record's `finished_at` is more than `config.yaml` `dashboard.stale_after_days` old on the viewer's clock. `workflow_schedule` reads the cron lines (and `timezone`) from `.github/workflows/weekly.yml`, so the page can't name a different time than GitHub runs; `upcoming_updates` lists the scheduled runs in the 120 days after the run, formatted in Python, and the browser picks the first one still ahead. A cron line other than "minute hour * * weekdays" stops the build | 3 | built |
| `dashboard/theme.py` | The one shared Plotly theme (UI_GUIDE.md Charts): `base_layout()` (fonts, transparent backgrounds, horizontal gridlines only, no legend, no zoom or drag), `CONFIG` (no mode bar, responsive), `PLOTLY_CDN` (basic bundle, version matched to the installed `plotly`), `team_colour` (pylon for the highlighted team, bar grey for the rest). Colours are token names (`@pylon`) that the page fills from CSS custom properties; `resolve_tokens` does the same in Python for tests. `to_script_json` embeds JSON safely (every `<` written `\u003c`) | 3 | built |
| `dashboard/explainer.py` | The "How this works" copy as `sections(params, league)` → headings and paragraphs, with every weight, window, threshold, and league fact (teams, median game, playoff start) filled in when built; `as_text` for review. `python -m sleeper_dash.dashboard.explainer` prints it as plain text. Approved by the owner 2026-10-02 and rendered once as the page's last section; wording changes need the owner's approval | 3 | built |
| `dashboard/charts.py` | Pure functions returning a chart section per week (title, how-to-read subtitle, text summary, figure): `luck_chart` (metrics_season actual vs expected wins, 45° line, one label per team) and `efficiency_chart` (lineups_optimal points per week, actual vs optimal, sorted by `metrics_season.efficiency`), `consistency_chart` (team_weeks scores as a strip plot with floor–ceiling bars and the league median; None until volatility exists), `schedule_chart` (sos_played and sos_remaining as bars from 0 in two panels; one panel when remaining is all 0.0 or over; None until SOS exists), `rank_history_chart` (power rank by week, one trace per team; None before week 2). Team-name labels carry the `roster_id` in `name` and `captureevents`, so tapping one moves the highlight. Teams carry their `roster_id` in each trace's `meta` so `charts.js` can move the highlight. Team names are HTML-escaped for Plotly text | 3 | built |
| `dashboard/templates/` | `index.html.j2` (one Jinja2 macro draws a week; the latest week in the page, earlier weeks in `<template>` blocks), `styles.css` (tokens, mobile-first layout, the ladder's one-line layout as a container query), `page.js` (week selector, first-load grow-in), `charts.js` (fills colour tokens, draws with Plotly, moves the highlight, places luck labels, applies phone labels). All inlined into the page | 3 | built |
| `dashboard/__main__.py` | `python -m sleeper_dash.dashboard`: runs `build.main` (prints weeks, sections, size; exit 1 with a clear message if the pipeline hasn't run) | 3 | built |
| `.github/workflows/weekly.yml` | Weekly refresh and publish. Triggers: Tuesday and Thursday 12:17 PM `America/New_York` (follows daylight saving) and `workflow_dispatch` (a manual run); one run at a time. Build job (`contents: write`): Python from `.python-version` → `pip install -r requirements-ci.txt` and `pip install --no-deps -e .` → `pytest` → pipeline → dashboard → `pytest tests/test_page.py` on this run's tables → commit changed `data/processed/*.csv` as `github-actions[bot]` ("Weekly refresh: tables through week N"; nothing when unchanged) → upload `site/`. Deploy job (`pages: write`, `id-token: write`): `actions/deploy-pages` to the `github-pages` environment. Any failed step stops the run before publishing, so the last good page stays live. Pages source: "GitHub Actions". Each step has an `id`; the commit step and an always-run "Run summary" step add to the run's summary page (commit result; each step's outcome, and "Build: FAILED. Nothing was published" on failure), after the pipeline's own summary; the deploy job adds "Published: <url>". The uploaded page is kept 90 days (`retention-days`, default 1) so `rollback.yml` can restore it | 4 | built |
| `.github/workflows/rollback.yml` | Manual only (input `run_id`, digits checked). Restore job (`actions: read`): `actions/download-artifact` fetches the `github-pages` artifact of that run → unpack `artifact.tar` into `site/` → upload it again (90 days) → summary naming the restored page's title and "Updated" time. Deploy job as in `weekly.yml`. Shares the `weekly-refresh` concurrency group, so it never publishes at the same time as a refresh. Changes no data and makes no commit; the next weekly run publishes fresh numbers again. Tested 2026-10-03: the live page came back byte-identical | 4 | built |

## Data model

All tables are long and tidy: one row per observation at the stated grain. `season` is included everywhere so past seasons can be stacked later.

CSV conventions (`transform.save_table`): UTF-8 with a byte-order mark so Excel shows special characters; list columns stored as JSON text (e.g. `[]`). IDs are 18-digit strings, so read them as text (`pd.read_csv(path, dtype={"owner_id": str})`). Excel keeps only 15 significant digits and will corrupt IDs if a CSV is opened directly.

### `players` (from the cached `/players/nfl`)
Grain: one row per NFL player. Key: `player_id`.

| Column | Type | Notes |
|---|---|---|
| player_id | str | Team defenses use the team abbreviation, e.g. `KC` |
| full_name | str | For defenses, build from team name |
| position | str | Primary position |
| fantasy_positions | list[str] | Eligibility for lineup slots |
| nfl_team | str | Current team; may be null for free agents |

### `teams` (built)
Grain: one row per fantasy team per season. Key: (`season`, `roster_id`). Source: `rosters.json` left-joined to `users.json` on `owner_id` = `user_id`.

| Column | Type | Notes |
|---|---|---|
| season | int | From `league.json` (a string in the API) |
| roster_id | int | Team key used everywhere |
| owner_id | str | Joins to users; can be null for an orphaned team (row kept, names null) |
| co_owners | list[str] | Raw `null` becomes `[]`; stored as JSON text in CSV |
| display_name | str | Manager's Sleeper username; whitespace stripped |
| team_name | str | User's `metadata.team_name` if set and not blank, else display_name; whitespace stripped |

### `team_weeks` (built)
Grain: one row per team per completed week. Key: (`season`, `week`, `roster_id`). Source: every `matchups/week_XX.json` that extract saved (completed weeks only) plus `league.json` settings.

| Column | Type | Notes |
|---|---|---|
| season, week | int | |
| roster_id | int | |
| matchup_id | Int64 | Null when the team has no game (e.g. playoff bye). Each non-null ID must appear exactly twice per week, or the run stops |
| points | float | Rounded to 2 dp |
| opponent_roster_id | Int64 | Paired via matching `matchup_id` within the week; null with no game |
| opponent_points | float | Null with no game |
| margin | float | points − opponent_points, 2 dp; null with no game |
| result | str | `W`, `L`, or `T` (head-to-head only); null with no game |
| median_result | str | Column exists only if `league_average_match` = 1. `W` above that week's median of all team scores, `L` below. Null in playoff weeks (assumed regular season only; verify at week 15). A score exactly at the median stops the run (owner decision) |
| is_playoff | bool | week ≥ `playoff_week_start` |

Reconciliation (printed by `python -m sleeper_dash.transform`): head-to-head + median wins/losses and summed points equal each roster's Sleeper `wins`, `losses`, `ties`, `fpts`, `fpts_against`. Verified for all 12 teams through week 3.

### `player_weeks` (built)
Grain: one row per lineup slot or bench spot per team per week. Key: (`season`, `week`, `roster_id`, `slot_order`). Source: matchups, `league.json` `roster_positions`, and the players cache (`data/cache/players_nfl.json`, refreshed by extract).

| Column | Type | Notes |
|---|---|---|
| season, week, roster_id | int | |
| slot_order | int | 0-based index in the starters list (0–9 here); bench rows numbered after starters in the matchup's `players` order |
| lineup_slot | str | The i-th starter fills the i-th non-`BN` entry of `roster_positions`, e.g. `QB`, `FLEX`, `SUPER_FLEX`; `BN` for bench. Injured-reserve players are bench (owner decision), so a team-week has 6 or 7 bench rows |
| player_id | str | `"0"` means an empty starting slot; team defenses are abbreviations like `"KC"` |
| is_starter | bool | |
| is_empty_slot | bool | True when a starting slot was left empty. The row is kept with 0 points, because an empty slot is a manager decision worth measuring |
| points | float | `starters_points` for starters, `players_points` for bench; 2 dp |
| position, full_name, nfl_team | str | From the players cache. Defenses have no `full_name`, so it is built from first + last name ("Jacksonville Jaguars"). Describes the player **today**, not in that week. Null for empty slots or IDs missing from the cache |

Checks (printed by `python -m sleeper_dash.transform`): starter points sum to `team_weeks.points` for every team-week; counts of empty slots and players missing from the cache; starters by slot × position.

### `transactions` (built)
Grain: one row per player move in a completed transaction. Key: (`transaction_id`, `player_id`, `action`). Source: `transactions/week_XX.json`, the players cache, and `config.yaml` `season_start_dates`.

| Column | Type | Notes |
|---|---|---|
| transaction_id | str | |
| season, week | int | `week` is Sleeper's `leg`, which must equal the file's week or the run stops |
| is_preseason | bool | Week 1 move created before the season's start date (midnight ET). Preseason moves are kept separate from week 1 (owner decision); `week` stays 1 |
| type | str | `waiver`, `free_agent`, `trade` |
| status | str | Always `complete`; failed claims are dropped |
| roster_id | int | Team receiving (`add`) or releasing (`drop`) the player |
| player_id | str | Team defenses are abbreviations |
| player_name | str | From the players cache (defenses: first + last name) |
| action | str | `add` or `drop`. A 1-for-1 trade is 4 rows: each player is dropped by one team and added by the other |
| waiver_bid | Int64 | FAAB bid, on the **add** rows of waiver claims only (null on drops, free agents, trades), so summing never double-counts |
| created_at | datetime | Epoch ms converted to US Eastern (`America/New_York`) |

Not represented: draft picks and FAAB traded inside trades (`draft_picks`, `waiver_budget`). Roster `waiver_budget_used` therefore won't match summed bids when FAAB is traded or when the in-progress week has claims (seen 2026-10-02: 4 teams differ by $8, all explained by week 4).

The season start date comes from `config.yaml` `season_start_dates`, one date per season, never from `/state/nfl`, which only describes the current NFL season and rolls over in the off-season. While `/state/nfl` describes the league's season and gives a date, transform checks the two agree and stops if they don't (a typo guard); otherwise the configured date is used alone (`transform.season_start_date`). So the 2026 tables come out the same whether Sleeper is in 2026, in the off-season, or in 2027 (`test_pipeline_offline`, and checked on the real league 2026-10-03), and past seasons (Phase 5) only need their date added.

### `schedule` (built)
Grain: one row per team per regular-season week, played and future. Key: (`season`, `week`, `roster_id`). Source: completed `matchups/week_XX.json` plus future `schedule/week_XX.json`. Playoff weeks are excluded (opponents come from the bracket).

| Column | Type | Notes |
|---|---|---|
| season, week, roster_id | int | |
| matchup_id | Int64 | Sleeper's game ID within the week |
| opponent_roster_id | Int64 | The team paired with this one that week |
| is_completed | bool | True for weeks in `team_weeks` |

2026 structure (checked 2026-10-02): weeks 1–11 are a full round-robin and weeks 12–14 repeat the pairings of weeks 1–3.

### `winners_bracket` (built, Phase 5)
Grain: one row per game in Sleeper's winners bracket. Key: (`season`, `matchup_id`). Source: `winners_bracket.json`. During the regular season Sleeper publishes a provisional bracket from the current standings (round 1 and the byes filled in, no winners); in the playoffs it is the real one. Empty before Sleeper has one.

| Column | Type | Notes |
|---|---|---|
| season, round, matchup_id | int | Round 1 = first playoff week; `matchup_id` is the bracket's own numbering (Sleeper's `m`), not a week's `matchup_id` |
| t1_roster_id, t2_roster_id | Int64 | The two teams, once known |
| t1_from, t2_from | str | Where a slot's team comes from: `W1` = winner of bracket game 1, `L2` = loser of game 2; null for a seeded slot |
| winner_roster_id, loser_roster_id | Int64 | Once played |
| place | Int64 | The place the game decides (1 = final, 3, 5); null for earlier rounds |

2026 format (verified 2026-10-05): round 1 is seeds 3 v 6 and 4 v 5; round 2 puts seed 1 against the 4/5 winner and seed 2 against the 3/6 winner (no reseeding); round 3 is the final plus 3rd- and 5th-place games.

### `lineups_optimal` (built)
Grain: one row per team per completed week. Key: (`season`, `week`, `roster_id`). Source: `lineup.py` from `player_weeks`, `team_weeks`, league `roster_positions`, and the players cache. Definitions: `docs/METRICS_SPEC.md` section 3.

| Column | Type | Notes |
|---|---|---|
| season, week, roster_id | int | |
| actual_points | float | `team_weeks.points` |
| optimal_points | float | Best possible score from that week's matchup `players` (starters, bench, IR) with hindsight, 2 dp |
| bench_points_lost | float | optimal − actual, ≥ 0, 2 dp (the spec's "points left on the bench") |
| efficiency | float | actual ÷ optimal as a fraction (0.8761, 4 dp); null if optimal ≤ 0. Season efficiency is Σ actual ÷ Σ optimal, never the mean of this column; it is stored in `metrics_season.efficiency` |

### `lineups_optimal_players` (built)
Grain: one row per starting slot of each team's optimal lineup per week. Key: (`season`, `week`, `roster_id`, `slot_order`).

| Column | Type | Notes |
|---|---|---|
| season, week, roster_id | int | |
| slot_order | int | 0-based index of the starting slot, same numbering as `player_weeks` |
| lineup_slot | str | e.g. `QB`, `FLEX`, `SUPER_FLEX` |
| player_id, full_name, position | str | The player the optimal lineup puts in this slot; null if the slot can't be filled (no eligible player rostered) |
| points | float | That player's points; 0 for an unfillable slot |
| is_empty_slot | bool | True when no eligible player was available |
| was_started | bool | The manager actually started this player (in any slot). False rows are the start/sit mistakes, used by awards |

Soft check (printed by the pipeline and `python -m sleeper_dash.lineup`): regular-season Σ optimal_points vs Sleeper's `ppts`; warns if below, or above by more than `metrics.efficiency.ppts_warn_gap`. Through week 3: 5 teams match exactly, 7 are 0.02–4.00 above, no warnings. An independent integer-programming solve (scipy `milp`) matched all 36 team-weeks to the cent (2026-10-02).

### `metrics_team_weeks` (built: all-play, luck, consistency)
Grain: one row per team per completed week. Key: (`season`, `week`, `roster_id`). Source: `metrics/` modules from `team_weeks`, combined by `metrics.build_metric_tables`. Definitions: `docs/METRICS_SPEC.md` sections 1, 2, and 4. Later metrics add columns to this table.

| Column | Type | Notes |
|---|---|---|
| season, week, roster_id | int | |
| allplay_wins, allplay_losses, allplay_ties | int | Teams that week scoring less / more / the same; sum = teams that week − 1 (11). Every week, playoffs included |
| allplay_win_pct | float | (wins + ½ ties) ÷ (teams − 1), full precision |
| h2h_actual_wins | float | Head-to-head result: 1, ½, or 0 |
| median_wins | float | Median-game result: 1 or 0; null when the league or week has no median game |
| actual_wins | float | h2h_actual_wins + median_wins (0–2), the scale of Sleeper's standings |
| expected_wins | float | allplay_win_pct + median_wins |
| luck | float | actual_wins − expected_wins (= h2h_actual_wins − allplay_win_pct) |
| points_vs_median | float | points − that week's league median, 3 dp (consistency's *d*) |
| is_boom, is_bust | bool | points_vs_median ≥ `boom_margin` / ≤ −`bust_margin` |

h2h_actual_wins through luck are null in playoff weeks and for a team-week without a head-to-head game.

### `metrics_season` (built: all-play, luck, consistency, schedule, lineup efficiency)
Grain: one row per team as of every completed week. Key: (`season`, `through_week`, `roster_id`). Running totals of `metrics_team_weeks` over weeks 1…`through_week`.

| Column | Type | Notes |
|---|---|---|
| season, through_week, roster_id | int | |
| allplay_wins, allplay_losses, allplay_ties | int | Sums over every week, playoffs included |
| allplay_win_pct | float | (Σ wins + ½ Σ ties) ÷ Σ comparisons |
| wins, losses, ties | int | **The record shown on the dashboard**: head-to-head + median games, regular season. Equals Sleeper's roster `wins`/`losses`/`ties` (validated) |
| h2h_wins, h2h_losses, h2h_ties | int | Head-to-head part of the record (used by the power score's results component; not displayed) |
| median_wins, median_losses | int | Median-game part of the record (not displayed) |
| actual_wins, expected_wins, luck | float | Regular-season sums on the overall scale; frozen from the first playoff week on. League luck sums to 0 for every `through_week` |
| weeks | int | Weeks played so far, playoffs included (consistency's *n*) |
| volatility | float | Sample SD of points_vs_median, 2 dp; null until `metrics.consistency.min_weeks` weeks |
| floor, ceiling | float | 10th / 90th percentile of weekly points (linear interpolation), 2 dp; null until `min_weeks` |
| boom_weeks, bust_weeks | int | Counts so far |
| boom_rate, bust_rate | float | Counts ÷ weeks |
| sos_played, sos_remaining | float | Strength of schedule, points per week vs the other 11 teams' average, 2 dp; null until `metrics.schedule.min_weeks`; remaining null when no regular-season games are left |
| sos_games_played, sos_games_remaining | int | Regular-season games behind and ahead; they sum to the number of regular-season weeks |
| efficiency | float | Season lineup efficiency: Σ actual ÷ Σ optimal points over weeks 1…`through_week`, playoffs included, as a fraction (4 dp); null if Σ optimal ≤ 0. Weights each week by its optimal points; **not** the mean of weekly efficiencies (owner decision). From `lineup.efficiency_season` |
| bench_points_lost | float | Season points left on the bench: Σ (optimal − actual), 2 dp |

### `power_rankings` (built)
Grain: one row per team as of every completed week. Key: (`season`, `week`, `roster_id`); `week` means "rankings as of the end of this week". Source: `metrics/power.py`. Definitions: `docs/METRICS_SPEC.md` section 6.

| Column | Type | Notes |
|---|---|---|
| season, week, roster_id | int | |
| rank | int | 1 = highest power score; ties broken by season scoring, then head-to-head win %, then lower roster_id |
| rank_change | Int64 | Previous week's rank − this week's rank (positive = moved up); null in week 1 |
| power_score | float | Sum of the four contributions; league mean exactly 50 every week |
| season_scoring, recent_form, roster_strength, results | float | Raw component values: mean points per week, mean of the last `recent_weeks` weeks, mean optimal points per week, head-to-head win % (regular season) |
| contrib_season_scoring, contrib_recent_form, contrib_roster_strength, contrib_results | float | weight × (50 + scale · f · z); always positive. Minus 50 × weight, each is that component's push above or below an average team |

### `awards` (built)
Grain: one row per enabled award per week per winning team (co-winners get one row each). Key: (`season`, `week`, `award`, `roster_id`). Source: `metrics/awards.py`. Definitions: `docs/METRICS_SPEC.md` section 7.

| Column | Type | Notes |
|---|---|---|
| season, week | int | |
| award | str | Key, e.g. `bench_blunder`; rows follow the order of `metrics.awards.enabled` |
| award_name | str | Display name in sentence case, e.g. "Bench blunder" |
| roster_id | int | Winning team |
| value | float | Points, margin, points left on the bench, efficiency (fraction), player points, or a count, depending on the award |
| caption | str | One factual line, e.g. "Left 33.9 points on the bench." (points to 1 dp) |
| player_id | str | The player for MVP and Pickup of the week; null otherwise |

### `managers` (built, Phase 5)
Grain: one row per manager across every saved season. Key: (`owner_id`). Source: `seasons.build_managers` from `teams`. Managers are matched by Sleeper owner ID, never by team name (owner, 2026-10-05).

| Column | Type | Notes |
|---|---|---|
| owner_id | str | Sleeper user ID; joins `teams.owner_id` in any season |
| display_name | str | Sleeper username in the latest season the manager played |
| first_season, last_season | int | Seasons in which they owned a team |
| seasons | int | How many seasons they owned a team |

### `playoff_odds` (built, Phase 5)
Grain: one row per team as of every completed regular-season week from `metrics.playoff_odds.min_weeks` (3). Key: (`season`, `week`, `roster_id`); `week` means "odds after this week". Source: `metrics/playoff_odds.py`. Definitions: `docs/METRICS_SPEC.md` section 8.

| Column | Type | Notes |
|---|---|---|
| season, week, roster_id | int | |
| strength | float | m̂: points per week above the league average, shrunk toward 0; 4 dp |
| strength_sd | float | √v, the uncertainty in `strength`; the same for every team in a week |
| score_sd | float | σ̂, the pooled week-to-week SD of relative scores this season; the same for every team in a week |
| p_playoffs, p_bye | float | Share of simulations seeded 1–6, and 1–2; counts ÷ `simulations`, stored to 6 dp |
| p_seed_1 … p_seed_6 | float | Share of simulations with each seed; they sum to `p_playoffs` |
| p_title | float | Share of simulations in which the team wins the final |
| avg_wins, avg_losses | float | Average final regular-season record, head-to-head plus median games; 4 dp |
| clinched, out | bool | Proved by a bound (not the simulation); after the last regular-season week, the final standings |

## Sleeper API — what we use

Base URL `https://api.sleeper.app/v1`. Read-only, no authentication.

| Endpoint | Returns | Used for |
|---|---|---|
| `/state/nfl` | Current NFL season and week | Deciding which weeks are complete |
| `/league/{league_id}` | Settings, scoring, `roster_positions`, `previous_league_id` | Slots, playoff week, median setting, history |
| `/league/{league_id}/users` | Managers and display names | `teams` |
| `/league/{league_id}/rosters` | Rosters plus season W/L and points totals in `settings` | `teams`, reconciliation |
| `/league/{league_id}/matchups/{week}` | Per team: `matchup_id`, `points`, `starters`, `starters_points`, `players`, `players_points` | `team_weeks`, `player_weeks` |
| `/league/{league_id}/transactions/{week}` | Adds, drops, trades, waiver bids | `transactions` |
| `/league/{league_id}/drafts`, `/draft/{draft_id}/picks` | Draft results | Draft value (later) |
| `/league/{league_id}/winners_bracket` | Playoff bracket | Phase 5 |
| `/players/nfl` | Every NFL player (large file) | `players`; fetch once per day max |

### Known quirks

Field-by-field detail, example records, and the evidence behind each point are in **[DATA_DICTIONARY.md](DATA_DICTIONARY.md)** (profiled 2026-10-02 on weeks 1–3).

- **Joins:** matchups only reference `roster_id`. Rosters map `roster_id` → `owner_id`, and users map `user_id` (= `owner_id`) → names. Confirmed: no missing owners.
- **Opponents:** two rows sharing a `matchup_id` in the same week played each other. Confirmed: each ID appears exactly twice per week. **Playoff weeks** (checked on this league's 2025 season): every team is still listed, with a full lineup and points; teams on a bye have a null `matchup_id`; winners-bracket and consolation-bracket games are both paired (2025 week 15: 4 games and 4 byes; week 16: 6 games; week 17: 4 games and 4 byes).
- **Empty slots:** `starters` uses `"0"` for an empty starting slot (none seen yet). `starters_points` is aligned to `starters` by position (confirmed).
- **Bench points:** `players_points` covers every player in `players`: starters, bench, **and injured reserve**. Matchups don't say which player was on IR.
- **Reconciliation:** roster `settings` totals = whole part + decimal part / 100. Confirmed to the cent against summed matchup points. `ppts` is *(likely)* Sleeper's max possible points; use it only as a soft check (our optimal lineups run 0–4 points above it).
- **Playoffs in the standings:** roster `wins`, `losses`, `fpts` and `fpts_against` count the **regular season only** (2025 season: 12 of 12 teams), so no playoff game or playoff median counts.
- **Median game:** on in this league. Sleeper's `wins`/`losses` **include** median games; `metadata.record` lists head-to-head then median result for each week. The comparison is against the median, not the mean.
- **Defenses:** player IDs are team abbreviations (always in the `DEF` slot).
- **Snapshots:** roster `starters`, `players`, `reserve`, and `metadata.record` describe today, not past weeks. `settings.total_moves` is always 0; don't use it.
- **Past seasons:** follow `previous_league_id` back through earlier leagues: 2026 → 2025 → … → 2020, where it ends (checked 2026-10-05). Every season has 12 teams, a median game, and the same 6-team bracket; 2020's regular season was 13 weeks (playoffs from week 14) and 2020–2021 had 10 starting slots, 2022–2025 9.
- **Stale season totals in past seasons:** Sleeper's stored `fpts`/`fpts_against` disagree with the sum of its own weekly scores for a few teams in 2020, 2021 and 2023 (one game each: 1.00 to 21.36 points), apparently stat corrections never carried into the totals. Records and weekly scores agree. `config.yaml` `sleeper_points_gaps` lists them; `seasons.with_known_gaps` adds them back before the points check, which allows exactly these.
- **`start_week` can be wrong:** 2020's league settings say `start_week` 4, but weeks 1–3 were played and count in Sleeper's standings. Checks treat the regular season as week 1 to `playoff_week_start` − 1 and ignore `start_week`.
- **Positions change between seasons:** e.g. a 2021 WR whom Sleeper lists as RB today; lineup.`week_positions` adds the single-position slot a player started in that week to his eligible positions.
- **Time:** transaction `created` is epoch milliseconds.
- **Completed weeks:** the latest completed week is the smaller of league `settings.last_scored_leg` (last week Sleeper finished scoring) and, while the league's NFL regular season is under way, `/state/nfl` `week` − 1. Verified 2026-10-02: state week 4 (TNF played), `last_scored_leg` 3.
- **Null instead of 404:** some bad IDs return 200 with a `null` body; extract treats `null` as an error.
- **Transaction status:** includes `failed` (lost waiver claims) as well as `complete`. `adds`/`drops` are `null`, not `{}`, when empty. Week 1 includes all preseason moves.
- **Public data:** `league.json` carries the last league-chat author and time (so far Sleeper's system bot; text null), and `users.json` carries notification preferences and custom mascot messages.

## Testing

- `pytest` runs everything; tests never call the network.
- Fixtures in `tests/fixtures/` are real responses saved during Phase 1, anonymised before committing (`rosters.json`: fake `owner_id`s `1000000000000000NN` where NN is the roster ID, player nicknames replaced with `"nickname"`).
- Every metric has invariant tests (e.g. all-play wins + losses + ties = 11 per team-week in a 12-team league), and the same invariants run as validation checks on every pipeline run.
- 489 tests (211 at the end of Phase 2, 348 at the end of Phase 3, 433 at the end of Phase 4), the same locally and in GitHub Actions. `test_playoff_odds` (Phase 5: odds sum across teams and seeds, average wins add up with and without a median game, Clinched teams at 100% and Out teams at 0%, the bounds as proofs, the final standings after week 14, identical reruns, a different seed moving odds by Monte Carlo error only, each week's own seed, better past scores never lowering playoff or bye odds, the strength formula, seeding by wins then points for, ties at the cutoff, unverified formats and bad settings stopping the run, and the validator catching broken odds). `conftest.py` blocks the network and clears `GITHUB_STEP_SUMMARY`, so tests never write to a real run's summary. `test_config` (required settings, a start date per season, each in its own year, `dashboard.stale_after_days`), `test_dependencies` (every version exact; the lock has pyproject's versions plus pytest, not jupyterlab; installed packages and Python equal the pins; the lock misses nothing a locked package needs), `test_pipeline_offline` (the real pipeline end to end, in a temporary folder, against `tests/fake_sleeper.py`: a made-up 6-team league with a median game, 3 scored weeks, and one preseason and one in-season pickup. With `/state/nfl` describing 2026, the off-season, 2027's preseason, or 2027 under way, every check passes and all 11 tables are byte-identical; a wrong start date is caught while Sleeper can confirm it; a run with no new week succeeds and leaves every file identical; a stat correction changes the numbers; a new week is reported; and an 8-team `PlayoffLeague` through two playoff weeks in each plausible Sleeper behaviour, checking that standings counting the playoffs are accepted when one standard fits every team, and that missing or unscored teams stop the run), `test_api`, `test_extract`, `test_transform`, `test_validate`, `test_pipeline` (step order, stop-on-failure, the run record including `season_complete`, and the markdown run summary or failure reason written only inside GitHub Actions, with every step faked), `test_lineup` (including brute-force comparison), `test_allplay`, `test_consistency`, `test_schedule`, `test_power`, `test_awards`, `test_dashboard` (each week shows its own records and awards, hidden sections, co-winners, escaping, only Google Fonts and Plotly loaded from outside, a 17-week season under 1 MB compressed, number and date formats; the schedule read from `weekly.yml`, upcoming update times across daylight saving, unreadable cron lines, and the stale-data and final-rankings lines), `test_charts` (theme rules, every figure valid Plotly once colours are filled in, charts follow the week selector and appear only once their data exists, default highlight, each chart's order and values, playoff wording, escaping), `test_page` (the built page read back as HTML, for this season's saved tables and a synthetic 17-week season: the status bar's update time and the hidden stale-data line naming the latest week and the next scheduled update; every week's sections in guide order and only when their data exists, nothing left behind by a hidden section, well-formed HTML, no outside requests but Google Fonts and the Plotly CDN, under 1 MB compressed including a full season stretched from this season's data, and every number on the ladder, award tiles, and charts equal to `power_rankings`, `metrics_season`, and `awards` for every week), `test_quality_floor` (UI_GUIDE.md quality floor: reduced motion stops every transition, a visible focus ring with 3:1 contrast on every background, keyboard-reachable controls, CSS tokens equal to the guide's table, the guide's stated contrast ratios, WCAG AA for all page and chart text in both modes, pylon only on large text). Metric tests mostly use hand-built or synthetic 17-week seasons, so playoff-week behaviour is tested even though no real playoff data exists yet.

## Dependencies

GitHub Actions installs exactly what runs locally: the same Python and the same version of every package.

| File | Pins |
|---|---|
| `.python-version` | Python **3.14.7**. The workflow reads it (`python-version-file`); `requires-python` in `pyproject.toml` is `>=3.14` |
| `pyproject.toml` | The direct dependencies (requests, pandas, pyarrow, pyyaml, scipy, plotly, jinja2), exact versions. pytest and jupyterlab are the `dev` extra: `pip install -e ".[dev]"` locally |
| `requirements-ci.txt` | The lock file: every package Actions installs (the direct dependencies, pytest, and everything they pull in), exact versions. Actions runs `pip install -r requirements-ci.txt`, then `pip install --no-deps -e .` (editable, because `config.PROJECT_ROOT` finds `config.yaml` and `data/` relative to the source folder) |

`tests/test_dependencies.py` keeps them honest, locally and in Actions: every pin is exact; the lock has pyproject's versions plus pytest (not jupyterlab); every locked package is installed at its locked version; everything a locked package needs is locked too; and the running Python equals `.python-version`. A local environment that drifts (e.g. a `pip install --upgrade`, or a new Python) fails these tests with a pointer here.

Not pinned, because they can't change an output: pip itself and the setuptools used to install the project.

**Updating a pin** (e.g. a new pandas), from the project folder in PowerShell:

1. Change the version in `pyproject.toml` (and pytest's in the `dev` extra if that's the one changing).
2. Build a throwaway environment from the current lock, then install the project with its new pins, so pip changes only what the new pins require; write the result out. Use the pytest version from `pyproject.toml`:
   ```powershell
   py -3.14 -m venv $env:TEMP\lockenv
   & $env:TEMP\lockenv\Scripts\python.exe -m pip install -r requirements-ci.txt
   & $env:TEMP\lockenv\Scripts\python.exe -m pip install . "pytest==9.1.1"
   & $env:TEMP\lockenv\Scripts\python.exe -m pip freeze --exclude sleeper-dash | Out-File -Encoding ascii lock-new.txt
   ```
3. Replace the package lines in `requirements-ci.txt` (keep the comment header) with `lock-new.txt`, then delete `lock-new.txt` and `$env:TEMP\lockenv`. Look over the diff: only the package you changed, and anything it needs, should move. (Installing from `pyproject.toml` alone would also pull the newest version of every indirect package.)
4. Update the local environment and check everything: `pip install -r requirements-ci.txt`, `pip install -e ".[dev]"`, `pytest`, `python -m sleeper_dash.pipeline` (tables unchanged unless the upgrade is meant to change them), `python -m sleeper_dash.dashboard`.
5. After a `plotly` upgrade, also update `theme.PLOTLY_JS_VERSION` (a test checks it) and re-check the charts in the browser, because `charts.js` uses Plotly internals.

**Updating Python:** install the new version locally, rebuild `.venv` with it, change `.python-version` (and `requires-python` for a new minor version), then follow steps 2–4. GitHub must offer that exact version (`actions/python-versions` releases).

## Adding a new metric

1. Write the definition in `docs/METRICS_SPEC.md` and get the owner's approval. Put any tunable parameter in `config.yaml` under `metrics:`.
2. Implement it as a pure function in `metrics/`, with a `check_params` for its config values.
3. Add invariant and edge-case tests.
4. Wire it into `metrics.build_metric_tables` (new columns on `metrics_team_weeks` / `metrics_season`, or a new table added to `validate.KEYS`), and add its invariants to `validate.run_metric_checks`. The pipeline picks it up automatically.
5. Update this file.

## League settings snapshot

Filled in by the Phase 0 API smoke test (`scripts/smoke_test.py`) on 2026-10-02, during NFL week 4. For reference only; code reads live settings.

- League name: 12 Supersexy Superflexy Hoekies
- Teams: 12
- Status: `in_season`
- Roster slots: QB, RB, RB, WR, WR, FLEX, REC_FLEX, SUPER_FLEX, K, DEF + 6 BN (10 starters, 16 total). No dedicated TE slot: TEs only start via FLEX, REC_FLEX, or SUPER_FLEX.
- Scoring: half PPR (`rec` 0.5) with a TE premium (`bonus_rec_te` 0.5, so TEs get 1.0 per catch); pass 0.04/yd, 4/TD, −2/INT; rush and rec 0.1/yd, 6/TD; fumble lost −2. 47 scoring keys in total.
- Playoff start week: 15
- Weekly median game: yes (`league_average_match` = 1)
- Previous league ID: `1243747994637963265` (a prior season exists for Phase 5)

## Changelog

- Project planned; docs created.
- Phase 0: repo skeleton, `pyproject.toml`, `config.yaml`, `config.py`, `.venv` with editable install.
- Phase 0: `scripts/smoke_test.py` API check; league settings snapshot filled in.
- Phase 1: `api.py` (`get` with 10s timeout, 3 retries with 1/2/4s backoff, 0.25s pacing; `get_players` with 24h cache). `tests/conftest.py` blocks real network access in every test.
- Phase 1: `extract.py` with completed-week logic and tests; first raw pull (weeks 1–3, 12 API calls); fixtures `tests/fixtures/matchups_week_01.json` and `rosters.json`.
- Phase 1: `docs/DATA_DICTIONARY.md` written from the first pull; known quirks updated with confirmed findings.
- Phase 1: `data/raw/` moved out of git (owner decision); fixtures anonymised; IR, median-tie, and preseason rules recorded.
- Phase 1: `transform.py` with `teams` table and `save_table` CSV writer; tests in `tests/test_transform.py`.
- Phase 1: `team_weeks` table (head-to-head and separate median results); standings reconcile with Sleeper for all 12 teams.
- Phase 1: `player_weeks` table (603 rows for weeks 1–3); extract now refreshes the players cache.
- Phase 1: `transactions` table (189 moves in 114 completed transactions; 19 preseason); all four Phase 1 tidy tables built.
- Phase 1: `validate.py` with six checks, run by transform before saving; all pass on weeks 1–3. Assumption to verify at week 15: Sleeper's roster `wins`/`fpts` exclude playoff games.
- Phase 1: `pipeline.py` runs the full refresh end to end; two consecutive runs gave identical outputs. `transform.build_tables` / `save_tables` shared by transform and pipeline.
- Phase 1 complete: `notebooks/01_data_check.ipynb` (standings, weekly box plot, score histogram, team-by-week heatmap; committed without outputs).
- Phase 2: `docs/METRICS_SPEC.md` written with the owner (all seven metrics confirmed); metric parameters added to `config.yaml` under `metrics:` and exposed as `Config.metrics`.
- Phase 2: `lineup.py` builds `lineups_optimal` and `lineups_optimal_players`; the pipeline builds them before validation; validation gains a seventh check (optimal lineups are consistent); `ppts` soft check printed as a warning. Tests in `tests/test_lineup.py`, including a FLEX/REC_FLEX case where a greedy fill loses 16 points and a brute-force comparison on 300 random lineups.
- Phase 2: `metrics/allplay.py` builds `metrics_team_weeks` and `metrics_season` (all-play, expected wins, luck); eighth validation check (all-play and luck invariants, including the median cross-check). Tests in `tests/test_allplay.py` on synthetic 17-week seasons (one with forced ties) and the real week 1 fixture. Head-to-head records verified against Sleeper's `metadata.record` for all 12 teams.
- Phase 2: record scale changed to overall (head-to-head + median games) by the owner after seeing the first luck table; `metrics_team_weeks` gains `h2h_actual_wins` and `median_wins`, `metrics_season` gains `wins`/`losses`/`ties` and the median split (`games` removed). Luck values unchanged. The validation check now also compares the record with Sleeper's.
- Phase 2: extract pulls the future regular-season schedule; transform builds the `schedule` table; `metrics/consistency.py` and `metrics/schedule.py` add consistency and strength-of-schedule columns; `metrics/__init__.py` combines all metric modules; two new validation checks (10 in total). Tests in `tests/test_consistency.py` and `tests/test_schedule.py`. Pipeline now makes 23 API calls through week 3.
- Phase 2: `metrics/power.py` builds `power_rankings` (power score, rank, rank_change, raw components, one contribution column per component) as of every completed week; eleventh validation check. Tests in `tests/test_power.py`, including a hand-worked example and the spec's ranking invariances (zero weight, any `shrink_weeks`).
- Phase 2: pipeline reordered to extract → transform → data checks → metrics → metric checks → save, so metric invariants stop a run before anything is saved; the summary lists every check by group. Two consecutive full runs gave byte-identical outputs (35 of 35 files).
- Phase 2: `metrics/awards.py` builds the `awards` table (8 enabled awards per week at first, 9 once Nail-biter was switched on; all 11 defined); twelfth validation check. Tests in `tests/test_awards.py`: every award's winner and caption, pickup history rules (trades, drafted players, waiver-then-traded, preseason, mid-week adds), ties, head-to-head ties, playoff weeks, config errors, and copy rules.
- Phase 2: `notebooks/02_power_score_sensitivity.ipynb`: each power weight perturbed by ±25% (others rescaled proportionally); teams changing rank, Spearman correlation, and per-team rank ranges. As of week 3, rho >= 0.979 in every scenario; only the two near-tied pairs (#1/#2, #7/#8) move. Committed without outputs.
- **Phase 2 complete (2026-10-02).** Pipeline: extract → transform → 7 data checks → optimal lineups and metrics → 6 metric checks → save 11 tables → re-check. 211 tests pass; two consecutive runs give byte-identical outputs. Known gap: season-to-date lineup efficiency is not yet a `metrics_season` column. Next: Phase 3, the dashboard.
- Phase 3: season-to-date lineup efficiency and points left on the bench added to `metrics_season` (`lineup.efficiency_season`); seventh metric check, "Season lineup efficiency is consistent" (14 checks in total). 221 tests. Through week 3 it differs from the mean of weekly efficiencies by at most 0.68 percentage points.
- Phase 3: `dashboard/` builds `site/index.html` (masthead, power rankings ladder with tap-to-expand breakdown, weekly awards) from the saved tables; `python -m sleeper_dash.dashboard`. The pipeline now records each successful run in `data/cache/pipeline_run.json` for the "Updated" line. 245 tests. Weeks 1–3: 111 KB (37 KB a week; about 11 KB compressed).
- Phase 3: `dashboard/theme.py` (the shared Plotly theme) and `dashboard/charts.py`: Luck (expected vs actual wins, 45° line, collision-free labels) and Lineup efficiency (points per week scored vs best possible, sorted by season efficiency) for every week; the week's #1 is highlighted, and tapping a point or opening a ladder row moves the highlight. Plotly 4.1.1 from cdn.plot.ly. 263 tests. Weeks 1–3: 157 KB (53 KB a week).
- Phase 3: Consistency (strip plot with floor–ceiling bars and the league median), Strength of schedule (played and remaining bars from the average), and Rank history (bump chart) added; each appears once its data exists. Tapping a team name in any chart moves the highlight. 270 tests + 1 expected failure (raw page weight, pending the owner). Weeks 1–3: 188 KB; a synthetic 17-week season is ~1.2 MB raw, ~115 KB compressed.
- Phase 3: "How this works" (owner-approved, no edits) published as the page's last section, with every number from `config.yaml` and league facts from the pipeline run record. The page-weight budget counts compressed bytes (owner decision); weeks 1–3: 26 KB compressed. 274 tests.
- Phase 3: page-level tests (`test_page`, `test_quality_floor`; plan step 5). Weeks 1–3: 26 KB compressed; this season stretched to 17 weeks: 135 KB compressed. One finding: UI_GUIDE.md stated chalk on turf as 11.9:1, but it is 11.85:1; the guide now says 11.8:1 (owner). 346 tests.
- Phase 3: design review at 360, 390, 1024 and 1280px, light and dark (approved fixes): the ladder's one-line layout now depends on the ladder's width (a CSS container query), fixing a 1024px collapse; reading text ~72 characters a line; compact award tiles on desktop; luck labels on a page background; rank-history names cut to 14 characters on phones (`charts.SHORT_NAME`, figure `phone` labels and margin applied by `charts.js` below 768px); centred 1200px column; key "League average: 50". 348 tests.
- **Phase 3 complete (2026-10-02).** `python -m sleeper_dash.dashboard` builds the full page (masthead and week selector, ladder with breakdowns, nine weekly awards, five charts, "How this works") for every completed week. Privacy check before closing: no value from `data/raw/` (user settings, mascot messages, player nicknames, league chat fields, avatars) appears in the page or in any tracked file; owner IDs appear only in `data/processed/teams.csv` (owner-approved); notebooks have no outputs; fixtures are anonymised. Pipeline: 14 of 14 checks, byte-identical outputs. 348 tests. Next: Phase 4 (HANDOFF.md section 9).
- Phase 4: the season start date moved to `config.yaml` (`season_start_date`), checked against `/state/nfl` while that still describes the league's season, so the weekly job keeps working after Sleeper rolls over to the next season (risk 1). Rebuilding weeks 1–3 with a simulated 2027 `/state/nfl` gives tables identical to the committed CSVs. New `test_config`. 361 tests.
- Phase 4: dependencies pinned (risk 2): exact versions in `pyproject.toml`, pytest and jupyterlab moved to a `dev` extra, Python 3.14 required, and `requirements-ci.txt` pinning every package Actions installs. A fresh environment installed from it passed `pip check`, 361 tests, the pipeline (14 of 14 checks, byte-identical CSVs), and the dashboard build. New `test_dependencies` keeps the two files in step. 363 tests.
- Phase 4: season start dates for every season (`season_start_dates` in `config.yaml`, replacing the single `season_start_date`), so past seasons can be rebuilt in Phase 5; the `/state/nfl` cross-check skips a missing date. The pipeline defines and reports a run with no new completed week. Path defaults in `transform` and `api.get_players` are looked up when called, so tests can point the whole pipeline at a temporary folder. New `test_pipeline_offline` with a fake Sleeper (`tests/fake_sleeper.py`). On the real league, with `/state/nfl` swapped four ways, every check passed and all 11 tables matched the committed CSVs. 392 tests.
- Phase 4: Python pinned to exactly 3.14.7 (`.python-version`, read by the workflow) and `test_dependencies` extended to compare the installed packages and Python with the pins; update steps written out with commands. A fresh environment from the lock matched it exactly, passed 395 tests, and produced all 11 tables and the page byte-identical. 395 tests.
- Phase 4: extract's raw-folder swap retries when Windows briefly refuses it (`_swap_in`); found by the offline tests (about 1 in 14 back-to-back runs), which now reuse one raw folder again and passed 6 runs in a row. 397 tests.
- **Phase 4 complete (2026-10-03).** Live at https://jonaht26.github.io/sleeper-dashboard/, refreshed by `.github/workflows/weekly.yml` every Tuesday and Thursday at 12:17 PM Eastern; three manual runs succeeded and the owner approved the live page in every format. Unattended-job risks fixed: season start dates per season (off-season and past seasons), every dependency and Python pinned and tested against what's installed, page tests on each run's fresh tables, a defined no-new-week run, and the Windows folder swap. 397 tests. Next: Phase 5 (HANDOFF.md section 9).
- Phase 4 follow-up: playoff assumptions checked on this league's finished 2025 season (standings count the regular season only; every team listed every playoff week; byes unpaired; consolation games paired), and the real pipeline passed all 14 checks on its 17 weeks. `tests/fake_sleeper.py` gained `PlayoffLeague` and switchable playoff behaviours; `test_pipeline_offline` records which pass and which stop the run today. Check behaviour in playoff weeks awaits the owner's decision. 404 tests.
- Phase 4 follow-up: owner decisions on playoff weeks. The standings checks ("Records match Sleeper", "Points for/against match Sleeper", and the record part of "All-play and luck are consistent") accept either counting standard in playoff weeks, as long as one fits every team, and name it; teams missing from the matchups or without a lineup still stop the run; consolation games count for matchup awards (METRICS_SPEC.md section 7). This season and the real 2025 season both match "regular season". 406 tests.
- Phase 4 follow-up: monitoring. The pipeline writes its summary (latest week, checks passed, tables written) or its failure reason to the GitHub run's page; the workflow adds the commit result, each step's outcome, and the published URL. Failure emails confirmed with a throwaway branch whose run failed on purpose (nothing published). 410 tests.
- Phase 4 follow-up: the page's "Updated" time moved into a status bar pinned to the top of the screen, and a stale-data line appears after `dashboard.stale_after_days` (8) days on the viewer's clock, with the next update time read from `weekly.yml`'s cron lines; once Sleeper marks the season `complete` it reads "Final rankings for the XXXX season." (owner-approved wording). Tested in the browser with fake old timestamps (7 days 23.9 hours: hidden; 8 days 0.1 hours: shown; 130 days: no update time). 433 tests.
- Phase 4 follow-up: `rollback.yml` and 90-day retention of published pages, so an earlier page can be put back (tested: byte-identical); `docs/RUNBOOK.md`, the owner's guide for a bad Tuesday.
- **Phase 4 closed (2026-10-03)** with the monitoring, rollback, and runbook follow-ups; commit "Phase 4: automation" (the second with that name; the first, `df8f4cf`, shipped the workflow). 433 tests. Next: Phase 5 (HANDOFF.md section 9).
- Phase 5: `notebooks/04_playoff_odds_calibration.ipynb`: the model as of each week of 2025 (weeks 3–14) against who made the playoffs. Playoff Brier 0.134 (everyone 50%: 0.250; "top 6 right now": 0.222), bye Brier 0.142 (everyone 2/12: 0.139); a reliability table; more shrinkage scored better in-sample (`shrink_weeks` 20: 0.128). Committed without outputs.
- Phase 5: the Playoff odds section on the page after the ladder (UI_GUIDE.md "Playoff odds"): a table of projected record, playoff, bye, and title odds, with "Chance of each seed" folded below, plus a "How this works" paragraph; wording approved by the owner as drafted (2026-10-05). The run record's league facts gain `playoff_teams`. `test_page` checks every number in the section against `playoff_odds.csv` for every week. 467 tests.
- Phase 5: the History section (design and wording owner-approved): champions, all-time records (current managers, former ones folded), 2025's luckiest and unluckiest teams, and the highest weekly score, after Rank history. The page reads `managers` and `winners_bracket` too, and builds the weekly sections from the current season only. 30 KB compressed. Checked at 360, 390 and 1280px, light and dark. `test_page` checks every History number against the saved tables; `test_dashboard` covers a synthetic finished season. 489 tests.
- Phase 5: the Playoffs section (UI_GUIDE.md "Playoffs"; wording owner-approved): new `dashboard/bracket.py`; shown in playoff weeks in the playoff odds' place, each week as of that week. Tested on the six finished brackets (2020–2025: every winner, score and seed; what each playoff week shows), on a provisional bracket Sleeper hasn't filled in, on 2025's page week by week (`test_page`), and on the fake `PlayoffLeague` page. Checked before building: in all 42 games of 2020–2025 the bracket's winner outscored its opponent that week and the pairing matches `team_weeks`. New `tests/test_bracket.py`. 515 tests.
- Phase 5: past seasons. `config.yaml` `history_from: 2020`: every run downloads 2020–2026 through `previous_league_id` (262 calls, ~80 s locally), builds and checks each season with its own league settings, and saves the tables stacked by `season`, plus a new `managers` table (14 managers; 10 played all seven seasons). New `seasons.py`; extract walks the chain (`extract_season`); the step commands (`transform`, `lineup`, the metric reports, `validate`) work season by season; the page filters to the current season. Owner decisions: Sleeper's known stale totals listed in `sleeper_points_gaps`; eligibility from the slot a player started in (one team-week changes: 2021 week 8, +5.12 optimal points); the regular season from week 1 whatever `start_week` says. All 17 checks pass in every season; every 2026 row is identical to the single-season tables; a second run is byte-identical. New `tests/test_seasons.py`; `fake_sleeper.FakeHistory` serves several seasons. 486 tests.
- Phase 5: playoff odds (METRICS_SPEC.md section 8). New `metrics/playoff_odds.py` and `playoff_odds` table (playoff, bye, per-seed, and title odds, average final record, Clinched / Out, for every regular-season week from week 3); extract downloads Sleeper's `winners_bracket` (one more API call, 25 in all) into a new `winners_bracket` table; two new checks ("Seeding matches Sleeper's bracket", "Playoff odds add up"), 16 in all; `config.yaml` `metrics.playoff_odds`; `tests/fake_sleeper.py` serves the playoff settings and a bracket. On the real league through week 3: 16 of 16 checks, and our seeding matches Sleeper's provisional bracket. New `tests/test_playoff_odds.py`. 462 tests.
