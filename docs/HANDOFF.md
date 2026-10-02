# Session handoff

Written 2026-10-02 at the end of the first working session (Phases 0 and 1). A new Claude session should read this file, then `CLAUDE.md`, `docs/CODEBASE.md`, and `docs/DATA_DICTIONARY.md`, before doing anything. Those three docs are the source of truth for design and data; this file covers everything else: how the owner likes to work, environment quirks, the reasoning behind decisions, open questions, and the plan for Phase 2.

## 1. Where things stand

| Phase | Status |
|---|---|
| 0 · Setup (environment, repo, API smoke test) | **Complete** |
| 1 · Data pull (raw extract, tidy tables, validation, pipeline) | **Complete** |
| 2 · Metrics | **Next.** Start by drafting `docs/METRICS_SPEC.md` *with* the owner |
| 3 · Dashboard, 4 · Automation, 5 · Extras | Not started |

As of 2026-10-02 (NFL week 4 in progress): weeks 1–3 are complete and processed, `python -m sleeper_dash.pipeline` passes all 6 validation checks in ~3 seconds with 12 API calls, two consecutive runs give byte-identical outputs, and 63 tests pass.

| Table (`data/processed/`) | Rows | Grain |
|---|---|---|
| `teams.csv` | 12 | team × season |
| `team_weeks.csv` | 36 | team × completed week |
| `player_weeks.csv` | 603 | lineup slot or bench spot × team × week |
| `transactions.csv` | 189 | player move in a completed transaction (114 transactions) |

## 2. Working with the owner

`CLAUDE.md` "About the owner" applies. Patterns from this session that matter just as much:

- **Plain language, no syntax lessons.** End every step with: what changed, what the data shows, how it was verified. Use tables for results.
- **Show the data.** After any data step, print a sample table and summary stats, and run a reconciliation against Sleeper's own numbers where one exists. The owner responds well to "here is the check, here is why it passes or fails."
- **Commands:** one command per fenced `bash` block (the app adds a Run button), with no `$` prompt. The owner uses PowerShell.
- **Decisions:** surface metric and data-interpretation choices as short numbered questions with options and a recommendation. The owner sometimes delegates ("use your judgement; just notify me"); when they do, decide, record the decision and evidence in the docs, and report it clearly.
- **When a check fails, explain why before changing code.** The owner asked for this explicitly. Example: the FAAB check failed for 4 teams; investigation showed the in-progress week and a FAAB trade explained every dollar, so the check was relabelled rather than "fixed."
- **Commit and push after every working step.** This is standing approval, recorded in `CLAUDE.md` rule 10. Stage specific files or review `git status --short` first.
- **Privacy before publishing.** The repo is public. Before committing, check that nothing personal is staged. This session scanned staged files for real user IDs, usernames, and team names taken from `data/raw/2026/users.json`. Claude Code's auto-mode safety check once blocked a push of raw data containing managers' personal settings; the owner then chose to keep `data/raw/` off GitHub. Never route around such a block. Explain it and let the owner decide.
- **Confirm ambiguous instructions that publish something.** "commit then" could have meant either option, so it was confirmed before publishing `teams.csv`.

## 3. Environment and gotchas

| Item | Detail |
|---|---|
| OS / shells | Windows 11. PowerShell **5.1** is primary (no `&&`, `?:`, or `??`); Bash is also available |
| Project root | `C:\Personal Projects\FF\Dev`. **Sessions should open here**, not in the parent `FF` folder |
| Python | 3.14.7 (`C:\Python314`). Project venv: `.venv`, package installed editable (`pip install -e .`). In tool calls, use `.venv\Scripts\python.exe` directly |
| git | 2.55. This repo's **local** `user.email` is `jonahtersol@gmail.com`; the global git email is a work address and must not be used here |
| GitHub | `gh` 2.102, logged in as **JonahT26**. Remote `https://github.com/JonahT26/sleeper-dashboard` (public), branch `main`. Fresh tool shells may not see `gh` on PATH; prefix with `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')` |
| Unicode output | Team names include curly quotes. Set `$env:PYTHONIOENCODING='utf-8'` before running Python that prints them |
| BOM trap | PowerShell 5.1 `Set-Content -Encoding utf8` writes a byte-order mark into source files. Prefer the Edit/Write tools; if a BOM appears, strip the first 3 bytes |
| Harmless noise | "LF will be replaced by CRLF" git warnings. Exit code −1 when Python output is piped to `Select-Object -First N` (truncation, not failure). Jupyter's "running over TCP without encryption" warning |
| Excel | Opening CSVs directly corrupts 18-digit IDs (Excel keeps 15 significant digits). CSVs are written `utf-8-sig` so special characters display correctly |
| Sleeper politeness | Tests block the network (`tests/conftest.py`). `api.get` paces calls at 0.25s or more apart. `/players/nfl` is cached in `data/cache/` for 24h |

## 4. Repository map (built)

```
Dev/
├── CLAUDE.md                     project rules, commands, decisions, current status
├── config.yaml                   league_id (quoted string), season 2026
├── pyproject.toml                package + dependencies (unpinned)
├── docs/
│   ├── CODEBASE.md               data flow, module status, table schemas, quirks, changelog
│   ├── DATA_DICTIONARY.md        every raw field, examples (anonymised), findings, decisions
│   ├── UI_GUIDE.md               design system for Phase 3 (unchanged from the start)
│   └── HANDOFF.md                this file
├── src/sleeper_dash/
│   ├── config.py                 load_config() → Config(league_id: str, season: int)
│   ├── api.py                    get(path): 10s timeout, 3 retries (1/2/4s), 0.25s pacing; get_players() 24h cache
│   ├── extract.py                raw JSON → data/raw/{season}/ via .partial staging; latest_completed_week()
│   ├── transform.py              build_teams / build_team_weeks / build_player_weeks / build_transactions;
│   │                             build_tables(season), save_tables(); main() prints detailed reports
│   ├── validate.py               6 checks; validate() raises ValidationError; load_tables() reads CSVs with IDs as text
│   ├── pipeline.py               extract → build → validate → save → re-validate saved CSVs; exit 1 on failure
│   ├── metrics/__init__.py       empty (Phase 2)
│   └── dashboard/                empty (Phase 3)
├── scripts/smoke_test.py         Phase 0 one-off API check
├── notebooks/01_data_check.ipynb standings, box plot, histogram, heatmap (committed without outputs)
├── tests/                        63 tests: api, extract, transform, validate, pipeline; conftest blocks network
│   └── fixtures/                 matchups_week_01.json, rosters.json (owner IDs and nicknames anonymised)
├── data/raw/                     GITIGNORED (personal settings); re-downloaded every run
├── data/cache/                   GITIGNORED players cache
└── data/processed/               COMMITTED, public (owner decision)
```

## 5. League facts that drive the code

- **League:** 12-team redraft, season 2026, league ID `1369887235935059968` (always a string).
- **Lineup:** QB, RB, RB, WR, WR, FLEX, REC_FLEX, SUPER_FLEX, K, DEF + 6 bench + 1 IR slot. **No TE slot**: TEs start only via FLEX (RB/WR/TE), REC_FLEX (WR/TE), or SUPER_FLEX (QB/RB/WR/TE).
- **Scoring:** half PPR, TE premium (+0.5 per TE catch), 4-point passing TDs. Sleeper's `players_points` already applies scoring; never recompute it.
- **Weekly median game is on.** Sleeper's `wins`/`losses` include median results; roster `metadata.record` gives two letters per week (head-to-head, then median). The comparison is against the median, not the mean (verified).
- **Calendar:** playoffs start week 15 with 6 teams (likely weeks 15–17). FAAB budget $100, $0 bids allowed. Waivers run early Wednesday ET.
- **Previous season** league ID `1243747994637963265` (for Phase 5).
- **Completed-week rule:** the smaller of league `settings.last_scored_leg` and (during this league's NFL regular season) `/state/nfl` week − 1.

## 6. Decisions log

| Date | Decision | Who | Where recorded |
|---|---|---|---|
| 2026-10-02 | Project root is `FF\Dev`; `CLAUDE.md` moved there from `docs/` | Claude (default) | — |
| 2026-10-02 | Public GitHub repo `sleeper-dashboard` (free GitHub Pages) | Owner | CLAUDE.md |
| 2026-10-02 | Commits use `jonahtersol@gmail.com` (repo-local config) | Owner | git config |
| 2026-10-02 | The unreferenced spreadsheet in `docs/` was moved to the Recycle Bin, never committed | Owner | — |
| 2026-10-02 | Push after every commit | Owner | CLAUDE.md rule 10 |
| 2026-10-02 | `data/raw/` kept off GitHub; test fixtures anonymised | Owner | CLAUDE.md, .gitignore |
| 2026-10-02 | Processed tables committed publicly, including usernames and owner IDs in `teams.csv` | Owner (confirmed explicitly) | CLAUDE.md |
| 2026-10-02 | Injured-reserve players count as bench in past weeks (past IR status is unknowable; evidence from `ppts`) | Claude, delegated by owner | DATA_DICTIONARY.md |
| 2026-10-02 | Median ties not handled; transform raises if one occurs | Owner | DATA_DICTIONARY.md |
| 2026-10-02 | Preseason transactions kept separate: `is_preseason` flag (week 1, created before `season_start_date`); `week` stays 1 | Owner (rule), Claude (column design) | CODEBASE.md |
| 2026-10-02 | `waiver_bid` only on the add rows of waiver claims (no double counting) | Claude | CODEBASE.md |
| 2026-10-02 | `slot_order` is 0-based; bench follows starters in Sleeper's `players` order | Claude (per spec wording) | CODEBASE.md |
| 2026-10-02 | CSVs written `utf-8-sig`; list columns as JSON text | Claude | CODEBASE.md |
| 2026-10-02 | Validation runs before saving; the pipeline re-validates the saved CSVs | Claude | CODEBASE.md |

## 7. Open questions and assumptions to verify

**Verify at week 15 (first playoff week):**
1. Whether Sleeper plays the median game in the playoffs (code assumes not: `median_result` is null in playoff weeks).
2. Whether roster `wins`/`losses`/`fpts` include playoff games (validation assumes regular season only).
3. Whether non-playoff teams get null `matchup_id` (code handles it either way).

**Known gaps:**
- **Sleeper's `ppts` does not match our optimal lineups exactly.** Including IR players matches `ppts` for 5 teams; the other 7 are 0.02–4.00 points above, including a team that never had an IR player. No single bench player explains any gap; possibly stat-correction timing or eligibility rules. Investigate in `lineup.py`, and treat `ppts` as a soft check.
- **Not in `transactions`:** FAAB and draft picks traded inside trades (`waiver_budget`, `draft_picks`). Roster `waiver_budget_used` is a current figure that includes the in-progress week. If FAAB metrics are wanted, add a small table.
- **Current, not historical:** `player_weeks.position`, `full_name`, and `nfl_team` describe each player today. Draft pick metadata has team-at-draft-time if history is needed.
- **Past seasons:** `season_start_date` comes from current `/state/nfl`. Transform stops with a clear error if the league's season is no longer current; revisit for Phase 5.
- **No playoff bracket:** `winners_bracket` is not pulled yet (Phase 5).
- **Dependencies are unpinned** in `pyproject.toml`. Pin them before Phase 4 so GitHub Actions matches local; local is Python 3.14.

**Open product questions (raised early, not yet decided):**
- **Ladder record:** head-to-head only, or overall including median? This affects Phase 3 and possibly the power score.
- **Retroactive changes:** full refresh can change already-posted rankings after stat corrections. Is that acceptable, or should posted weeks be frozen?
- **Where league members see updates:** bookmark only, or also a group-chat post (CLAUDE.md open decision, Phase 5).
- **Minor UI_GUIDE issue:** in dark mode the masthead band and the page background are both `--turf`, so the masthead doesn't stand out.
- **Phase 4 scheduling:** GitHub Actions cron runs in UTC, so 9 AM ET shifts by an hour with daylight saving.

## 8. Plan for Phase 2 (metrics)

Follow `CODEBASE.md` "Adding a new metric": spec first, owner approval, then a pure function, invariant tests, pipeline wiring, and a docs update.

1. **Draft `docs/METRICS_SPEC.md` with the owner, one metric at a time.** For each metric: definition, formula, edge cases (ties, byes, empty slots, IR, median game, playoffs), and the open choices posed as questions. Candidates from the roadmap and `UI_GUIDE.md`:
   - **Optimal lineup:** max points subject to slot eligibility. Use the players cache `fantasy_positions`; the eligibility map is in section 5; IR players are included per the decision.
   - **Lineup efficiency** (actual ÷ optimal) and **points left on the bench.**
   - **All-play record** (in a 12-team league, all-play W + L + T = 11 per team-week) and **expected wins**.
   - **Luck** (actual − expected wins). Ask whether median games count.
   - **Consistency:** volatility, floor/ceiling, boom/bust thresholds (thresholds go in `config.yaml`).
   - **Strength of schedule:** played and remaining.
   - **Power score:** components and weights in `config.yaml`, every weight shown on the dashboard.
   - **Weekly awards.**
2. **Build `lineup.py`** as an assignment problem with `scipy.optimize.linear_sum_assignment`. A working prototype from this session's IR analysis: cost matrix slots × players, `-points` where eligible, `1e6` otherwise. Compare to `ppts` as a soft check.
3. **Build `metrics/*.py` as pure functions** (DataFrames in, DataFrames out), with invariant tests, written to `data/processed/metrics_*.csv` and added to `validate.py` and `pipeline.py`.
4. **Update** `CODEBASE.md` module status, the "Current status" section of `CLAUDE.md`, and this file at the end of the phase.

## 9. Commit history (all pushed to `main`)

```
cbde4fb Project scaffold
5535795 Record public repo decision
e613550 Add Sleeper API smoke test and league settings snapshot
094bef3 Add Sleeper API client with retries, pacing, and players cache
1214d8f Push after every commit
c53d809 Add raw extract, data dictionary, and keep raw data off GitHub
9e97453 Add teams table to transform
f3c6708 Add teams table output
a969478 Add team_weeks table with separate median results
9a4f843 Add player_weeks table and refresh players cache in extract
8df98de Add transactions table
d1c15ec Add validation checks that run before saving tables
42b5ccb Add pipeline for a full end-to-end refresh
1ad16d1 Add data check notebook and mark Phase 1 complete
```

## 10. First steps for the new session

1. Read `CLAUDE.md`, `docs/CODEBASE.md`, `docs/DATA_DICTIONARY.md`, and this file.
2. Confirm the environment: `.venv\Scripts\python.exe -m pytest -q` (expect 63 passed) and `git status` (expect clean, in sync with `origin/main`).
3. Optionally refresh the data with `.venv\Scripts\python.exe -m sleeper_dash.pipeline`. If NFL week 4 has finished, expect weeks 1–4, roughly 14 API calls, and 6 of 6 checks passing. Commit the updated processed CSVs.
4. Start Phase 2 by proposing the `METRICS_SPEC.md` outline and the first metric definitions for the owner to approve.
