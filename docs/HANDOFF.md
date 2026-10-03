# Session handoff

Rewritten 2026-10-02 at the end of the second working session (Phase 3, the dashboard). A new Claude session should read this file first, then `CLAUDE.md`, `docs/CODEBASE.md`, `docs/METRICS_SPEC.md`, and `docs/UI_GUIDE.md`, before doing anything. Those docs are the source of truth for design, data, metrics, and the page; this file covers everything else: how the owner works, environment quirks, decisions and their reasons, open questions, risks, and the plan for Phase 4.

## 1. Where things stand

| Phase | Status |
|---|---|
| 0 · Setup (environment, repo, API smoke test) | **Complete** |
| 1 · Data pull (raw extract, tidy tables, validation, pipeline) | **Complete** |
| 2 · Metrics (seven owner-approved metrics) | **Complete** |
| 3 · Dashboard | **Functionally complete** (2026-10-02). Remaining: the owner's final look-through |
| 4 · Automation (weekly GitHub Action, GitHub Pages) | **Next**. Fix risks 1 and 4 first (section 8) |
| 5 · Extras | Not started |

At the end of this session (NFL week 4 in progress, so weeks 1–3 are the completed weeks):

- `python -m sleeper_dash.pipeline`: extract → transform → 7 data checks → optimal lineups and metrics → 7 metric checks → save 11 tables → re-check the saved CSVs. 14 of 14 checks pass, 23 API calls, ~7 seconds, processed CSVs byte-identical across runs. A successful run also writes `data/cache/pipeline_run.json` (finish time, league name, season, weeks, and league facts: 12 teams, median game on, playoffs from week 15).
- `python -m sleeper_dash.dashboard`: builds `site/index.html` from the saved CSVs and the run record. Sections, top to bottom: masthead with week selector, power rankings ladder (tap a row for its breakdown), weekly awards, five charts (Luck, Lineup efficiency, Consistency, Strength of schedule, Rank history), and "How this works". Every completed week is in the page; each week shows rankings, records, awards, and charts as of that week. 26 KB compressed (194 KB raw) for weeks 1–3.
- **274 tests pass.** Git clean and in sync with `origin/main` at `a733794`.

## 2. Working with the owner

`CLAUDE.md` "About the owner" applies. Patterns that matter just as much:

- **Plain language, no syntax lessons.** End every step with what changed, what the data shows, and how it was verified. Tables for results.
- **Show the data.** After any data or metric step, print a sample table and summary stats and reconcile with Sleeper where possible. Example this session: season efficiency shown next to the mean of weekly efficiencies, with the largest gap (0.68 points) and the one rank swap.
- **Commands:** one command per fenced `bash` block (the app adds a Run button), no `$` prompt. The owner uses PowerShell.
- **Decisions:** ask short numbered questions with options and a recommendation. The owner answers tersely ("1. agree 2. agree 3. rename it Score…") and sometimes overrides the recommendation (kept the "Score" column for transparency; wanted Score before "vs average"). Record every answer in the docs (section 6) in the same commit.
- **Mobile first** is a standing priority (owner, 2026-10-02): design and check every component at 390px first.
- **Show drafts before publishing anything user-facing.** The owner reviews copy as plain text first; the "How this works" text needs the owner's approval again for any wording change.
- **Never quietly change a rule or a test to make something pass.** Example: when the page outgrew the 1 MB budget, the raw-size test was marked as an expected failure with the reason written on it, and the owner was asked; the owner chose "compressed bytes" (option 1).
- **When a check fails, explain why before changing code** (standing instruction).
- **Small steps; plan before touching more than ~3 files.** When the owner explicitly asks for a larger piece of work ("build the dashboard…"), proceed, and list the files touched in the report.
- **Commit and push after every working step** (standing approval, `CLAUDE.md` rule 10). Stage specific files; check `git status --short` first.
- **Privacy:** the repo is public. Never commit `data/raw/` (managers' personal settings) or `data/cache/`. Never route around a safety block; explain it and let the owner decide.

## 3. Environment and gotchas

| Item | Detail |
|---|---|
| OS / shells | Windows 11. PowerShell **5.1** is primary (no `&&`, `?:`, `??`); Bash (Git Bash) also available |
| Project root | `C:\Personal Projects\FF\Dev`. Sessions may open in the parent `FF`; work in `Dev` |
| Python | 3.14.7. Venv `.venv`, package installed editable. In tool calls use `.venv\Scripts\python.exe` directly |
| git / GitHub | Repo-local `user.email` is `jonahtersol@gmail.com` (never the global work address). `gh` logged in as **JonahT26**; remote `https://github.com/JonahT26/sleeper-dashboard` (public), branch `main`. Fresh shells may not see `gh`; prefix with `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')` |
| Unicode output | Set `$env:PYTHONIOENCODING='utf-8'` before Python that prints team names (curly quotes) |
| Editing files | Prefer the Edit/Write tools. For multi-file edits, write a small Python script to the scratchpad with the Write tool and run it; each replacement asserts its target appears exactly once. **Bash heredocs break on some content** (apostrophes, backslashes): don't pipe Python through heredocs when the code contains them. **PowerShell `[IO.File]` methods use the .NET working directory, not the PowerShell location**: always pass absolute paths |
| BOM trap | PowerShell 5.1 `Set-Content -Encoding utf8` writes a byte-order mark. Don't use it on source files |
| Harmless noise | "LF will be replaced by CRLF" git warnings; exit code −1 when output is piped to `Select-Object -First N` |
| Excel | Opening CSVs directly corrupts 18-digit IDs. CSVs are `utf-8-sig` |
| Sleeper politeness | Tests block the network. `api.get` paces calls ≥0.25 s apart; `/players/nfl` cached for 24 h |
| Plotly version | Python `plotly` 7.1.0 pairs with plotly.js **4.1.1**, loaded from `cdn.plot.ly` (basic bundle). `theme.PLOTLY_JS_VERSION` must match `plotly.offline.get_plotlyjs_version()` (a test checks). `charts.js` uses Plotly internals (`_fullLayout`, axis `_offset`, `l2p`) for label placement; re-check it after any Plotly upgrade |

### Previewing the page (browser pane)

- Preview servers are defined in **`C:\Personal Projects\FF\.claude\launch.json`** (outside the repo; the preview tool looks in the parent `FF` folder). `dashboard` serves `Dev\site` on port 8766: start it with the preview tool's `preview_start` and name `dashboard`. (Last session's throwaway prototype lived in a session scratchpad and is gone; its decisions are in section 6.)
- Use a server, not `file://`: local documents always render light, so dark mode can't be checked.
- Set the viewport with `resize_window` (390×844 phone, 1280×900 desktop) and set it again whenever the pane changes width; the app clears it.
- **Screenshots are unreliable** in this pane: they often show the frame before a scroll, or a magnified view after a resize. Verify layout with JavaScript measurements (element widths, `scrollWidth`, Plotly's `_fullLayout`), reload the page, then take a fresh screenshot.
- The ladder's grow-in animation runs very slowly in the pane, so screenshots catch bars mid-animation. For screenshots only, inject `*{transition:none!important}` and remove the `preload` class through the browser's JavaScript tool. Never change the page itself for this.
- Use `form_input` on the week selector (combobox "Week N") to switch weeks like a user would.

## 4. Repository map

```
Dev/
├── CLAUDE.md                     rules, commands, current status, decisions, open decisions
├── config.yaml                   league_id (quoted), season, every metric weight and threshold
├── pyproject.toml                package + dependencies (UNPINNED: risk 4); dashboard templates as package data
├── docs/
│   ├── CODEBASE.md               data flow, modules, table schemas, Sleeper quirks, changelog
│   ├── METRICS_SPEC.md           owner-approved metric definitions (code follows the spec)
│   ├── UI_GUIDE.md               design system and every dashboard decision (ladder, charts, copy)
│   ├── DATA_DICTIONARY.md        raw Sleeper fields and findings
│   └── HANDOFF.md                this file
├── src/sleeper_dash/
│   ├── config.py, api.py, extract.py, transform.py, validate.py (14 checks), lineup.py, metrics/
│   ├── pipeline.py               full refresh; writes data/cache/pipeline_run.json on success
│   └── dashboard/
│       ├── build.py              tables → view (every number formatted once) → HTML; `python -m sleeper_dash.dashboard`
│       ├── theme.py              the one shared Plotly theme; colours as CSS tokens ("@pylon"); CDN URL
│       ├── charts.py             five chart sections as Plotly figure dicts (pure functions)
│       ├── explainer.py          "How this works" copy, numbers from config.yaml (owner-approved)
│       └── templates/            index.html.j2, styles.css, page.js (week selector), charts.js (drawing,
│                                 highlight, label placement); CSS and JS are inlined into the page
├── tests/                        274 tests, one file per module; conftest blocks the network
├── data/raw/, data/cache/        GITIGNORED
├── data/processed/               COMMITTED, public (owner decision)
└── site/                         GITIGNORED build output (index.html)
```

### How the page works (read before changing it)

- **One renderer.** Python formats every number (`build.view`); one Jinja2 macro draws a week. The latest week is drawn into the page; each earlier week sits in a `<template id="week-N">` block that `page.js` swaps in. No JavaScript copy of the drawing code exists, so nothing can drift. Chart figures are embedded per week as JSON in `<script type="application/json">` (every `<` escaped as `\u003c`).
- **Charts** are plain dicts built from `theme.py`; colours are token names that `charts.js` fills from the CSS custom properties, so dark mode follows the page. A team's `roster_id` rides in trace `meta` and in name-label `name`; tapping a point, a team name, or opening a ladder row highlights that team in every chart (the week's #1 by default).
- **Hidden sections:** a chart or the awards are left out entirely when their data doesn't exist yet (consistency and schedule from week 3, rank history from week 2). No placeholders.
- **"How this works"** is generated by `explainer.sections(params, league)`; a test proves every number changes with `config.yaml`.

## 5. League facts that drive the code

- **League:** 12-team redraft, season 2026, league ID `1369887235935059968` (always a string).
- **Lineup:** QB, RB, RB, WR, WR, FLEX, REC_FLEX, SUPER_FLEX, K, DEF + 6 bench + 1 IR. No TE slot.
- **Scoring:** half PPR, TE premium, 4-point passing TDs. Never recompute Sleeper's points.
- **Weekly median game is on**; records include it.
- **Calendar:** playoffs from week 15 (6 teams). The 14-week schedule is an 11-week round robin plus weeks 1–3 repeated, so **remaining strength of schedule is exactly 0.0 for everyone after week 3** (the chart shows one panel and says so in its subtitle); from week 4 the second panel appears.
- **Completed-week rule:** the smaller of league `last_scored_leg` and `/state/nfl` week − 1. Week 4 becomes available after Monday night's game is scored (likely Tuesday Oct 6).
- **Previous season** league ID `1243747994637963265` (Phase 5).

## 6. Decisions log

| Date | Decision | Who | Where recorded |
|---|---|---|---|
| 2026-10-02 | Project root is `FF\Dev`; `CLAUDE.md` moved there from `docs/` | Claude (default) | — |
| 2026-10-02 | Public GitHub repo `sleeper-dashboard` (free GitHub Pages) | Owner | CLAUDE.md |
| 2026-10-02 | Commits use `jonahtersol@gmail.com` (repo-local config) | Owner | git config |
| 2026-10-02 | Push after every commit | Owner | CLAUDE.md rule 10 |
| 2026-10-02 | `data/raw/` kept off GitHub; test fixtures anonymised | Owner | CLAUDE.md, .gitignore |
| 2026-10-02 | Processed tables committed publicly, including usernames and owner IDs | Owner (confirmed explicitly) | CLAUDE.md |
| 2026-10-02 | Injured-reserve players count as bench in past weeks | Claude, delegated by owner | DATA_DICTIONARY.md |
| 2026-10-02 | Median ties not handled; transform raises if one occurs | Owner | DATA_DICTIONARY.md |
| 2026-10-02 | Preseason transactions kept separate (`is_preseason`) | Owner (rule), Claude (column design) | CODEBASE.md |
| 2026-10-02 | All seven metric definitions confirmed | Owner | METRICS_SPEC.md |
| 2026-10-02 | Past weeks recomputed every run (no frozen rankings) | Owner | METRICS_SPEC.md §6 |
| 2026-10-02 | Displayed record = overall (head-to-head + median) | Owner | METRICS_SPEC.md §2 |
| 2026-10-02 | Power score's results component is head-to-head only | Owner | METRICS_SPEC.md §6 |
| 2026-10-02 | Dashboard public and indexable; usernames on the ladder | Owner | CLAUDE.md, UI_GUIDE.md |
| 2026-10-02 | Power scores at 1 decimal; near-ties may show identical numbers | Owner | UI_GUIDE.md |
| 2026-10-02 | Sections without data yet are hidden entirely | Owner | UI_GUIDE.md |
| 2026-10-02 | Nail-biter enabled (nine awards); results weight stays 0.20 | Owner | config.yaml |
| 2026-10-02 | Site published from `site/` by a GitHub Actions workflow; `site/` gitignored | Claude, delegated by owner | CLAUDE.md, .gitignore |
| 2026-10-02 | Season efficiency (Σ actual ÷ Σ optimal) and season points left on the bench stored in `metrics_season`, with a metric check | Owner (request), Claude (bench column) | CODEBASE.md |
| 2026-10-02 | Dark-mode masthead `#18392B` in both modes | Owner | UI_GUIDE.md |
| 2026-10-02 | Prototype review of the ladder: mobile first; bars from the league average (50); breakdown with a "Score" column (contribution) then "vs average" bars; bottom row "Power score"; results labelled "Head-to-head wins" with the head-to-head record; 52px rank column; latest week drawn at build time; "Updated" = pipeline run time | Owner | UI_GUIDE.md, METRICS_SPEC.md §2 and §6 |
| 2026-10-02 | Fixed bar axes for the season (largest gap so far, rounded up) | Claude | UI_GUIDE.md |
| 2026-10-02 | Earlier weeks pre-drawn into `<template>` blocks (one renderer) rather than JSON + a JavaScript renderer; chart data embedded as JSON | Claude (reported to owner) | CODEBASE.md |
| 2026-10-02 | Charts: the week's #1 highlighted by default; tapping a point, team name, or ladder row moves the highlight; highlighted labels bold, never pylon text | Claude | UI_GUIDE.md |
| 2026-10-02 | Efficiency and one-row-per-team charts taller than 320px (≈30px a row) so 12 rows stay readable | Claude | UI_GUIDE.md |
| 2026-10-02 | Strength of schedule: when every remaining value is 0.0, one panel plus a subtitle note instead of empty bars | Claude | UI_GUIDE.md |
| 2026-10-02 | Page-weight budget (1 MB) counts compressed bytes | Owner (option 1) | UI_GUIDE.md, CLAUDE.md |
| 2026-10-02 | "How this works" generated from `config.yaml` at build time | Owner | explainer.py |
| 2026-10-02 | "How this works" approved with no edits and published; boom/bust sentence kept for a future display; 2.4–97.6 range kept; awards not explained; future wording changes need approval | Owner | UI_GUIDE.md |

## 7. Open questions and assumptions to verify

**Verify at week 15 (first playoff week):** whether Sleeper plays the median game in the playoffs (code assumes not); whether roster `wins`/`losses`/`fpts` include playoff games (validation assumes not); how non-playoff teams appear in matchups (null `matchup_id` handled either way).

**Verify at week 4 (first new data since the dashboard was built):** the Strength of schedule chart should switch to two panels (remaining no longer all 0.0); luck labels and the efficiency chart should still read cleanly at 390px with new values; the pipeline should commit four weeks of processed CSVs.

**Known gaps:** Sleeper's `ppts` sits 0.02–4.00 points below our optimal lineups for 7 teams (soft check only); FAAB and picks traded inside trades aren't in `transactions`; player positions describe today, not past weeks; `winners_bracket` not pulled (Phase 5).

**Open product questions:**
- Where league members see updates: bookmark only, or also a group-chat post (Phase 5).
- Phase 4 schedule: GitHub Actions cron runs in UTC, so a 9 AM ET run shifts an hour with daylight saving. Decide the run time and whether the workflow commits the refreshed processed CSVs back to the repo (today they are committed by hand after each run).
- Boom/bust weeks are explained in "How this works" but not displayed yet (owner wants them kept for a future display).

## 8. Known risks

Ordered by impact.

1. **Off-season breakage (fix before Phase 4).** Transform needs `/state/nfl` to describe the league's season (`season_start_date`). When Sleeper rolls over to 2027, transform stops with an error, so an unattended job would start failing. Store the season start date with the season's raw data, or derive it from the league.
2. **Week 15 untested on real data** (section 7). A wrong assumption fails "Records match Sleeper" and stops the run: safe, but the page stops updating.
3. **Sleeper's API is unofficial.** Shape changes surface as failed checks, without notice.
4. **Unpinned dependencies (fix before Phase 4)**, local Python 3.14. Pin them so GitHub Actions matches local. Plotly in particular: the CDN version is tied to the Python package (section 3).
5. **Label placement is a heuristic** (`charts.js`): crowded luck charts could still overlap in some weeks. Check new weeks at 390px.
6. **The page depends on two CDNs** (Google Fonts, cdn.plot.ly). If Plotly fails to load, each chart shows its one-sentence text summary instead.
7. **Player positions are today's**, so a mid-season position change alters past optimal lineups.
8. **Posted numbers can change** after stat corrections (deliberate full recompute; explained in "How this works").
9. **Near-ties at the top** of the power rankings (#1 and #2 both show 57.8 through week 3).

## 9. Plan

**Finish Phase 3:** walk the owner through the finished page at phone and desktop widths (light and dark), collect any last changes, then mark Phase 3 complete in `CLAUDE.md` and `docs/CODEBASE.md`.

**Phase 4 (automation), in order; propose this plan to the owner before starting:**
1. Fix risk 1 (season start date) with tests.
2. Pin dependencies (risk 4); choose the Python version for Actions to match local.
3. Add `.github/workflows/weekly.yml`: scheduled run (time agreed with the owner, section 7) plus manual trigger → install → `pytest` → `python -m sleeper_dash.pipeline` → `python -m sleeper_dash.dashboard` → upload `site/` as the Pages artifact → deploy. A failed check must stop the job before anything is published (rule 8). Permissions: `contents: read` (or write, if the workflow commits processed CSVs), `pages: write`, `id-token: write`.
4. The owner must switch the repo's Pages source to "GitHub Actions" in the repository settings (an account-settings change; ask the owner to do it, or ask before doing it).
5. Watch the first run, then share the URL with the owner.

## 10. Commit history

Phase 1 ends at `1ad16d1`; Phase 2 ends at `38eba07 Phase 2: metrics`; Phase 3 runs from `487e76c` (season-to-date lineup efficiency) to `a733794` (publish the approved How this works section). Use `git log --oneline` for the full list.

## 11. First steps for the new session

1. Read `CLAUDE.md`, this file, `docs/CODEBASE.md`, `docs/METRICS_SPEC.md`, and `docs/UI_GUIDE.md`.
2. Confirm the environment: `.venv\Scripts\python.exe -m pytest -q` (expect **274 passed**) and `git status` (expect clean, in sync with `origin/main`).
3. Refresh: `.venv\Scripts\python.exe -m sleeper_dash.pipeline` (every check passes; 9 awards a week; week 4 appears once Sleeper has scored it), then `.venv\Scripts\python.exe -m sleeper_dash.dashboard`. Commit and push any changed processed CSVs.
4. Start the `dashboard` preview server and check the page at 390px and 1280px (section 3), paying attention to the week-4 items in section 7.
5. Then section 9: the owner's final Phase 3 review, and the Phase 4 plan.
