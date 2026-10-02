# Codebase guide

What lives where, how data moves, and the shape of every table. This file describes the **planned** design. As modules get built, change their status from `planned` to `built`.

> Claude: keep this file current. When you add or change a module, table, or column, update this file in the same commit.

## Data flow

```
Sleeper API
    │
    ▼
extract.py ─────────► data/raw/{season}/*.json        untouched API responses
    │
    ▼
transform.py ───────► data/processed/*.csv            tidy tables (see Data model)
    │
    ▼
validate.py                                           reconciliation checks; stops the run on failure
    │
    ▼
lineup.py + metrics/ ► data/processed/metrics_*.csv   optimal lineups, luck, power score, awards
    │
    ▼
dashboard/  (Phase 3) ► site/index.html               static page
    │
    ▼
GitHub Pages (Phase 4)                                rebuilt every Tuesday by GitHub Actions
```

`pipeline.py` runs every step in order as a full refresh. Nothing is appended incrementally.

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
│   ├── raw/{season}/            committed: the season's raw JSON (small, useful history)
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
| `api.py` | `get(path)` with timeout, retries, backoff, pacing; `get_players()` with 24h file cache | 1 | planned |
| `extract.py` | Pull league, users, rosters, state, drafts, picks, and per-week matchups and transactions into `data/raw/` | 1 | planned |
| `transform.py` | Build the tidy tables below from raw JSON only | 1 | planned |
| `validate.py` | Integrity and reconciliation checks; raises on failure | 1 | planned |
| `pipeline.py` | Orchestrates extract → transform → validate → metrics; prints a run summary | 1–2 | planned |
| `lineup.py` | Optimal lineup per team-week, solved as an assignment problem | 2 | planned |
| `metrics/*` | Pure functions implementing `docs/METRICS_SPEC.md` | 2 | planned |
| `dashboard/*` | Render `site/index.html` per `docs/UI_GUIDE.md` | 3 | planned |

## Data model

All tables are long and tidy: one row per observation at the stated grain. `season` is included everywhere so past seasons can be stacked later.

### `players` (from the cached `/players/nfl`)
Grain: one row per NFL player. Key: `player_id`.

| Column | Type | Notes |
|---|---|---|
| player_id | str | Team defenses use the team abbreviation, e.g. `KC` |
| full_name | str | For defenses, build from team name |
| position | str | Primary position |
| fantasy_positions | list[str] | Eligibility for lineup slots |
| nfl_team | str | Current team; may be null for free agents |

### `teams`
Grain: one row per fantasy team per season. Key: (`season`, `roster_id`).

| Column | Type | Notes |
|---|---|---|
| season | int | |
| roster_id | int | Team key used everywhere |
| owner_id | str | Joins to users; can be null for an orphaned team |
| co_owners | list[str] | Usually empty |
| display_name | str | Manager's Sleeper username display |
| team_name | str | `metadata.team_name` if set, else display_name |

### `team_weeks`
Grain: one row per team per completed week. Key: (`season`, `week`, `roster_id`).

| Column | Type | Notes |
|---|---|---|
| season, week | int | |
| roster_id | int | |
| matchup_id | int | Null when the team has no game (e.g. playoff bye) |
| points | float | Rounded to 2 dp |
| opponent_roster_id | int | Paired via matching `matchup_id` within the week |
| opponent_points | float | |
| margin | float | points − opponent_points |
| result | str | `W`, `L`, or `T` (head-to-head only) |
| median_result | str | Only if the league plays a weekly median game; kept separate from `result` |
| is_playoff | bool | week ≥ playoff start week |

### `player_weeks`
Grain: one row per lineup slot or bench spot per team per week. Key: (`season`, `week`, `roster_id`, `slot_order`).

| Column | Type | Notes |
|---|---|---|
| season, week, roster_id | | |
| slot_order | int | Index in the starters list; bench rows numbered after starters |
| lineup_slot | str | Roster slot, e.g. `QB`, `FLEX`, `SUPER_FLEX`, or `BN` for bench |
| player_id | str | `"0"` means an empty starting slot |
| is_starter | bool | |
| is_empty_slot | bool | True when a starting slot was left empty |
| points | float | From `players_points` / `starters_points` |
| position, full_name, nfl_team | str | Joined from `players` |

### `transactions`
Grain: one row per player move. Key: (`transaction_id`, `player_id`, `action`).

| Column | Type | Notes |
|---|---|---|
| transaction_id | str | |
| season, week | int | |
| type | str | `waiver`, `free_agent`, `trade` |
| status | str | Keep `complete` only |
| roster_id | int | Team making this move |
| player_id | str | |
| action | str | `add` or `drop` |
| waiver_bid | int | FAAB bid if applicable |
| created_at | datetime | Converted from epoch ms to US/Eastern |

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

Verify each against real responses during Phase 1 and record findings in `docs/DATA_DICTIONARY.md`.

- **Joins:** matchups only reference `roster_id`. Rosters map `roster_id` → `owner_id`, and users map `user_id` (= `owner_id`) → names.
- **Opponents:** two rows sharing a `matchup_id` in the same week played each other.
- **Empty slots:** `starters` uses `"0"` for an empty starting slot. `starters_points` is aligned to `starters` by position.
- **Bench points:** `players_points` covers every rostered player, starters and bench.
- **Reconciliation:** roster `settings` holds `wins`, `losses`, `ties`, `fpts` + `fpts_decimal`, and `fpts_against` + `fpts_against_decimal`. Totals = whole part + decimal part / 100.
- **Median game:** if the league plays a weekly median game, Sleeper's own win totals may include those wins. Check the league settings (look for `league_average_match`) and confirm.
- **Defenses:** player IDs are team abbreviations.
- **Past seasons:** follow `previous_league_id` back through earlier leagues.
- **Time:** transaction `created` is epoch milliseconds.

## Testing

- `pytest` runs everything; tests never call the network.
- Fixtures in `tests/fixtures/` are real responses saved during Phase 1.
- Every metric has invariant tests (e.g. all-play wins + losses + ties = 11 per team-week in a 12-team league).

## Adding a new metric

1. Write the definition in `docs/METRICS_SPEC.md` and get the owner's approval.
2. Implement it as a pure function in `metrics/`.
3. Add invariant and edge-case tests.
4. Wire it into `pipeline.py` and its output table.
5. Update this file.

## League settings snapshot

Filled in by the Phase 0 API smoke test. For reference only; code reads live settings.

- League name:
- Teams: 12
- Roster slots:
- Scoring (PPR value etc.):
- Playoff start week:
- Weekly median game:

## Changelog

- Project planned; docs created.
- Phase 0: repo skeleton, `pyproject.toml`, `config.yaml`, `config.py`, `.venv` with editable install.
