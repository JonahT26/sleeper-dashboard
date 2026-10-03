# Session handoff

Written 2026-10-02 at the end of the first working session (Phases 0 and 1). A new Claude session should read this file, then `CLAUDE.md`, `docs/CODEBASE.md`, and `docs/DATA_DICTIONARY.md`, before doing anything. Those three docs are the source of truth for design and data; this file covers everything else: how the owner likes to work, environment quirks, the reasoning behind decisions, open questions, and the plan for Phase 2.

## 1. Where things stand

| Phase | Status |
|---|---|
| 0 · Setup (environment, repo, API smoke test) | **Complete** |
| 1 · Data pull (raw extract, tidy tables, validation, pipeline) | **Complete** |
| 2 · Metrics | **Complete** (2026-10-02): spec written with the owner, all seven metrics built and validated |
| 3 · Dashboard | **In progress**: plan steps 1–2 done (2026-10-02) |
| 4 · Automation, 5 · Extras | Not started |

**Update at the end of Phase 2 (2026-10-02):** the pipeline now runs extract → transform → 7 data checks → optimal lineups and metrics → 6 metric checks → save 11 tables, with 23 API calls in about 6.5 seconds; 211 tests pass; outputs are byte-identical across runs. `CLAUDE.md` "Current status" and `docs/CODEBASE.md` describe the current state; the Phase 1 notes below are kept for history. Phase 2 decisions are in section 6 and in `docs/METRICS_SPEC.md`.

At the end of Phase 1 (NFL week 4 in progress): weeks 1–3 were complete and processed, `python -m sleeper_dash.pipeline` passes all 6 validation checks in ~3 seconds with 12 API calls, two consecutive runs give byte-identical outputs, and 63 tests pass.

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
│   ├── validate.py               14 checks (7 data, 7 metric); validate() raises ValidationError; load_tables() reads CSVs with IDs as text
│   ├── pipeline.py               extract → transform → data checks → metrics → metric checks → save → re-check; exit 1 on failure
│   ├── lineup.py                 optimal lineups (assignment problem); weekly and season-to-date efficiency
│   ├── metrics/                  allplay, consistency, schedule, power, awards; __init__ combines them
│   └── dashboard/                empty (Phase 3)
├── scripts/smoke_test.py         Phase 0 one-off API check
├── notebooks/                    01_data_check, 02_power_score_sensitivity (committed without outputs)
├── tests/                        221 tests (one file per module); conftest blocks network
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
| 2026-10-02 | All seven metric definitions confirmed in the Phase 2 interview | Owner | METRICS_SPEC.md |
| 2026-10-02 | Past weeks are recomputed every run (no freezing of posted rankings) | Owner | METRICS_SPEC.md §6 |
| 2026-10-02 | Displayed record = overall (head-to-head + median games), with no split shown; expected and actual wins on the same scale. First chosen as head-to-head only, changed by the owner after seeing the luck table | Owner | METRICS_SPEC.md §2 |
| 2026-10-02 | Power score's results component stays head-to-head only (median wins excluded to avoid double-counting scoring) | Owner | METRICS_SPEC.md §6 |
| 2026-10-02 | Dashboard stays public and indexable; usernames stay on the ladder | Owner | CLAUDE.md, UI_GUIDE.md |
| 2026-10-02 | Power scores at 1 decimal; near-ties may show identical numbers, no tie marker | Owner | UI_GUIDE.md |
| 2026-10-02 | Metric sections not available yet are hidden entirely (no placeholder) | Owner | UI_GUIDE.md |
| 2026-10-02 | Owner reviews the "How this works" copy before it goes live | Owner | UI_GUIDE.md |
| 2026-10-02 | Nail-biter award enabled (nine awards) | Owner | config.yaml, METRICS_SPEC.md §7 |
| 2026-10-02 | Results weight in the power score kept at 0.20 for now, despite penalising unlucky teams | Owner | — |
| 2026-10-02 | Site published from `site/` by a GitHub Actions workflow; `site/` gitignored | Claude, delegated by owner | CLAUDE.md, .gitignore |
| 2026-10-02 | Dark-mode masthead: `--masthead` `#18392B` in both modes | Owner | CLAUDE.md, UI_GUIDE.md |
| 2026-10-02 | Season efficiency stored in `metrics_season` with season points left on the bench alongside it | Claude (spec §3 defines both) | CODEBASE.md |
| 2026-10-02 | Prototype review of the masthead and ladder: mobile first; bars from the league average; breakdown with gap-from-average bars and a "Score" column; "Head-to-head wins" label; two-digit rank column; latest week in the HTML at build time; "Updated" = pipeline run time | Owner | UI_GUIDE.md, METRICS_SPEC.md §2 and §6, CLAUDE.md |
| 2026-10-02 | Fixed bar axes for the season (largest gap so far, rounded up) so bars compare across weeks | Claude | UI_GUIDE.md |

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
- ~~**Ladder record:**~~ Settled 2026-10-02: overall record including median games (see decisions log).
- ~~**Retroactive changes:**~~ Settled 2026-10-02: recompute everything every run (see decisions log).
- **Where league members see updates:** bookmark only, or also a group-chat post (CLAUDE.md open decision, Phase 5).
- **Phase 4 scheduling:** GitHub Actions cron runs in UTC, so 9 AM ET shifts by an hour with daylight saving.

## 8. Known risks (end of Phase 2)

Ordered by impact. None of these are bugs today; each is a place where something outside our control could break the pipeline or the numbers.

1. **Off-season breakage.** Transform needs `/state/nfl` to describe the league's season (for `season_start_date`). When Sleeper rolls over to 2027, transform stops with an error, so an always-on dashboard would start failing. Fix before Phase 4 automation (for example, store the season start date with the season's raw data, or derive it from the league).
2. **Week 15 is untested on real data.** Median game in the playoffs, roster `wins`/`fpts`/`ppts` including playoff games, and how eliminated teams appear in matchups. A wrong assumption fails "Records match Sleeper" and stops the run (safe, but the dashboard stops updating).
3. **Sleeper's API is unofficial and undocumented.** Shape changes would surface as failed checks, not silently wrong numbers, but with no notice.
4. **Unpinned dependencies** (local Python 3.14). Pin before GitHub Actions runs unattended.
5. **Player positions are today's, not historical.** A mid-season position change would alter past optimal lineups.
6. **Unexplained `ppts` gaps** (0.02–4.00 points, below the warning threshold).
7. **Posted numbers can change** after stat corrections (deliberate: full recompute), including last week's ranks and awards.
8. **Near-ties at the top** of the power rankings (#1 and #2 are 0.004 apart through week 3); the order there is effectively arbitrary.

## 9. Plan for Phase 3 (dashboard)

Follow `docs/UI_GUIDE.md` for everything user-facing.

1. ~~Add season-to-date lineup efficiency to `metrics_season`, with a metric check.~~ Done 2026-10-02 (`efficiency`, `bench_points_lost`; check "Season lineup efficiency is consistent").
2. ~~Get the owner's answer on the dark-mode masthead proposal.~~ Approved 2026-10-02: `--masthead` `#18392B` in both modes.
3. A throwaway prototype of the masthead and ladder was reviewed with the owner on 2026-10-02 (decisions in section 6 and `UI_GUIDE.md` Ladder row). Build `src/sleeper_dash/dashboard/`: `theme.py` (the one shared Plotly theme), a Jinja2 template, and a page builder that writes `site/index.html` from the saved CSVs. Embed every week's data as JSON so the week selector needs no network call, but write the latest week into the HTML at build time so it shows without JavaScript. The pipeline must record its run time for the "Updated" line. Section order as in UI_GUIDE.md; hide metric sections that aren't available yet.
4. Draft the "How this works" copy and show it to the owner for review before it is published.
5. Add `python -m sleeper_dash.dashboard`, tests (sections present, no external calls besides fonts and the Plotly CDN, page weight under 1 MB), and preview the page in the browser pane at phone and desktop widths.
6. Phase 4 then adds the GitHub Actions workflow: run the pipeline, build `site/`, publish to Pages (fix risk 1 and pin dependencies first).

## 10. Commit history

Phase 1 commits are listed in `git log` up to `1ad16d1`; Phase 2 ran from `efaa869` (session handoff guide) to `38eba07 Phase 2: metrics`. Use `git log --oneline` for the full list.

## 11. First steps for the new session

1. Read `CLAUDE.md` (Current status, Decisions made, Open decisions), this file, `docs/CODEBASE.md`, `docs/METRICS_SPEC.md`, and `docs/UI_GUIDE.md`.
2. Confirm the environment: `.venv\Scripts\python.exe -m pytest -q` (expect 221 passed) and `git status` (expect clean, in sync with `origin/main`).
3. Refresh the data with `.venv\Scripts\python.exe -m sleeper_dash.pipeline`: expect every data and metric check to pass and 9 awards per week. Commit the updated processed CSVs.
4. Continue Phase 3 at step 3 of the plan above (steps 1 and 2 are done).
