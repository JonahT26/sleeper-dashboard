# Codebase guide

What lives where, how data moves, and the shape of every table. This file describes the **planned** design. As modules get built, change their status from `planned` to `built`.

> Claude: keep this file current. When you add or change a module, table, or column, update this file in the same commit.

## Data flow

```
Sleeper API
    │
    ▼
extract.py ─────────► data/raw/{season}/*.json        untouched API responses (gitignored)
    │      └────────► data/cache/players_nfl.json     player list, refreshed at most once a day (gitignored)
    ▼
transform.py                                          builds tidy tables in memory (see Data model)
    │
    ▼
validate.py                                           6 checks on the in-memory tables; any failure stops the run
    │                                                 before anything is saved
    ▼
data/processed/*.csv                                  saved, then re-read and checked again
    │
    ▼
lineup.py + metrics/ ► data/processed/metrics_*.csv   Phase 2: optimal lineups, luck, power score, awards
    │
    ▼
dashboard/  (Phase 3) ► site/index.html               static page
    │
    ▼
GitHub Pages (Phase 4)                                rebuilt every Tuesday by GitHub Actions
```

`python -m sleeper_dash.pipeline` runs every built step in order as a full refresh (currently extract → transform → validate → save → re-validate). Nothing is appended incrementally. Two back-to-back runs produce byte-identical raw and processed files (verified 2026-10-02: 16 of 16 files). It prints weeks processed, API calls, rows per table, checks passed, and run time (~3 seconds), and exits with code 1 on any failure, leaving the last good tables in place.

## Repository layout

```
sleeper-dashboard/
├── CLAUDE.md                    project context for Claude Code
├── config.yaml                  league_id, season, model weights, thresholds
├── pyproject.toml               package definition and dependencies
├── docs/
│   ├── CODEBASE.md              this file
│   ├── UI_GUIDE.md              design system and dashboard layout
│   ├── METRICS_SPEC.md          metric definitions (Phase 2, owner-approved)
│   └── DATA_DICTIONARY.md       raw Sleeper field notes (Phase 1)
├── src/sleeper_dash/
│   ├── __init__.py
│   ├── config.py                loads config.yaml
│   ├── api.py                   Sleeper HTTP client: retries, pacing, players cache
│   ├── extract.py               API → data/raw/
│   ├── transform.py             data/raw/ → data/processed/ tidy tables
│   ├── validate.py              reconciliation and integrity checks
│   ├── lineup.py                optimal lineup solver
│   ├── metrics/
│   │   ├── __init__.py
│   │   ├── allplay.py           all-play record, expected wins, luck
│   │   ├── efficiency.py        lineup efficiency, bench points
│   │   ├── consistency.py       volatility, floor/ceiling, boom/bust
│   │   ├── schedule.py          strength of schedule
│   │   ├── power.py             power score and weekly rankings
│   │   └── awards.py            weekly awards
│   ├── dashboard/               Phase 3: templates, chart theme, page builder
│   └── pipeline.py              `python -m sleeper_dash.pipeline`
├── scripts/
│   └── smoke_test.py            one-off API check from Phase 0
├── data/
│   ├── raw/{season}/            gitignored: the season's raw JSON (personal settings; re-downloaded every run)
│   ├── cache/                   gitignored: players_nfl.json
│   └── processed/               committed: tidy CSVs
├── notebooks/                   validation and model-exploration notebooks
├── tests/
│   ├── fixtures/                saved API responses for offline tests
│   └── test_*.py
├── site/                        Phase 3 build output
└── .github/workflows/weekly.yml Phase 4 schedule
```

## Modules

| Module | Responsibility | Phase | Status |
|---|---|---|---|
| `config.py` | Load and validate `config.yaml` | 0 | built |
| `api.py` | `get(path)` with timeout, retries, backoff, pacing; `get_players()` with 24h file cache | 1 | built |
| `extract.py` | Pull league, users, rosters, state, drafts, picks (`picks/draft_{id}.json`), and per-week matchups and transactions (`matchups/week_XX.json`, `transactions/week_XX.json`) into `data/raw/{season}/`. Writes to a `.partial` staging folder and swaps it in only when every call succeeds. Also refreshes the players cache via `api.get_players()` (at most once a day) | 1 | built |
| `transform.py` | Build the tidy tables below from saved files only (raw JSON plus the players cache): `teams`, `team_weeks`, `player_weeks`, `transactions` | 1 | built |
| `validate.py` | Six checks: one row per team per completed week (and no missing weeks); each `matchup_id` has exactly 2 teams; starter points equal team points (±0.01); regular-season W–L–T matches Sleeper's roster settings, counting median games when the league has them; regular-season points for/against match `fpts`/`fpts_against` (±0.01); no duplicate keys in any table. `transform` runs them **before saving** and stops with a pass/fail table if any fail; `python -m sleeper_dash.validate` re-checks the saved CSVs | 1 | built |
| `pipeline.py` | Orchestrates extract → transform → validate → save → re-validate the saved CSVs; prints a run summary; exit code 1 on failure. Metrics are added in Phase 2 | 1–2 | built (Phase 1 steps) |
| `lineup.py` | Optimal lineup per team-week, solved as an assignment problem | 2 | planned |
| `metrics/*` | Pure functions implementing `docs/METRICS_SPEC.md` | 2 | planned |
| `dashboard/*` | Render `site/index.html` per `docs/UI_GUIDE.md` | 3 | planned |

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
Grain: one row per player move in a completed transaction. Key: (`transaction_id`, `player_id`, `action`). Source: `transactions/week_XX.json`, the players cache, and `state.json` `season_start_date`.

| Column | Type | Notes |
|---|---|---|
| transaction_id | str | |
| season, week | int | `week` is Sleeper's `leg`, which must equal the file's week or the run stops |
| is_preseason | bool | Week 1 move created before `season_start_date` (midnight ET). Preseason moves are kept separate from week 1 (owner decision); `week` stays 1 |
| type | str | `waiver`, `free_agent`, `trade` |
| status | str | Always `complete`; failed claims are dropped |
| roster_id | int | Team receiving (`add`) or releasing (`drop`) the player |
| player_id | str | Team defenses are abbreviations |
| player_name | str | From the players cache (defenses: first + last name) |
| action | str | `add` or `drop`. A 1-for-1 trade is 4 rows: each player is dropped by one team and added by the other |
| waiver_bid | Int64 | FAAB bid, on the **add** rows of waiver claims only (null on drops, free agents, trades), so summing never double-counts |
| created_at | datetime | Epoch ms converted to US Eastern (`America/New_York`) |

Not represented: draft picks and FAAB traded inside trades (`draft_picks`, `waiver_budget`). Roster `waiver_budget_used` therefore won't match summed bids when FAAB is traded or when the in-progress week has claims (seen 2026-10-02: 4 teams differ by $8, all explained by week 4).

`season_start_date` comes from `/state/nfl`, which only describes the current NFL season; transform stops with a clear error if the league's season is no longer current. Revisit before re-running past seasons (Phase 5).

### Metric tables (Phase 2)

| Table | Grain | Contents |
|---|---|---|
| `lineups_optimal` | season, week, roster_id | optimal_points, actual_points, efficiency, bench_points_lost |
| `metrics_team_weeks` | season, week, roster_id | all-play W/L/T, expected wins, luck, and other weekly metrics |
| `metrics_season` | season, through_week, roster_id | cumulative metrics as of each week |
| `power_rankings` | season, week, roster_id | power_score, rank, rank_change, one column per component contribution |
| `awards` | season, week, award | roster_id, value, caption |

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
- **Opponents:** two rows sharing a `matchup_id` in the same week played each other. Confirmed: each ID appears exactly twice per week; no nulls yet (expect them in playoff weeks).
- **Empty slots:** `starters` uses `"0"` for an empty starting slot (none seen yet). `starters_points` is aligned to `starters` by position (confirmed).
- **Bench points:** `players_points` covers every player in `players`: starters, bench, **and injured reserve**. Matchups don't say which player was on IR.
- **Reconciliation:** roster `settings` totals = whole part + decimal part / 100. Confirmed to the cent against summed matchup points. `ppts` is *(likely)* Sleeper's max possible points; use it only as a soft check (our optimal lineups run 0–4 points above it).
- **Median game:** on in this league. Sleeper's `wins`/`losses` **include** median games; `metadata.record` lists head-to-head then median result for each week. The comparison is against the median, not the mean.
- **Defenses:** player IDs are team abbreviations (always in the `DEF` slot).
- **Snapshots:** roster `starters`, `players`, `reserve`, and `metadata.record` describe today, not past weeks. `settings.total_moves` is always 0; don't use it.
- **Past seasons:** follow `previous_league_id` back through earlier leagues.
- **Time:** transaction `created` is epoch milliseconds.
- **Completed weeks:** the latest completed week is the smaller of league `settings.last_scored_leg` (last week Sleeper finished scoring) and, while the league's NFL regular season is under way, `/state/nfl` `week` − 1. Verified 2026-10-02: state week 4 (TNF played), `last_scored_leg` 3.
- **Null instead of 404:** some bad IDs return 200 with a `null` body; extract treats `null` as an error.
- **Transaction status:** includes `failed` (lost waiver claims) as well as `complete`. `adds`/`drops` are `null`, not `{}`, when empty. Week 1 includes all preseason moves.
- **Public data:** `league.json` carries the last league-chat author and time (so far Sleeper's system bot; text null), and `users.json` carries notification preferences and custom mascot messages.

## Testing

- `pytest` runs everything; tests never call the network.
- Fixtures in `tests/fixtures/` are real responses saved during Phase 1, anonymised before committing (`rosters.json`: fake `owner_id`s `1000000000000000NN` where NN is the roster ID, player nicknames replaced with `"nickname"`).
- Every metric has invariant tests (e.g. all-play wins + losses + ties = 11 per team-week in a 12-team league).

## Adding a new metric

1. Write the definition in `docs/METRICS_SPEC.md` and get the owner's approval.
2. Implement it as a pure function in `metrics/`.
3. Add invariant and edge-case tests.
4. Wire it into `pipeline.py` and its output table.
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
