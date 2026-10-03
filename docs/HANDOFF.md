# Session handoff

Rewritten 2026-10-02 at the end of Phase 3 (the dashboard). A new Claude session should read this file first, then `CLAUDE.md`, `docs/CODEBASE.md`, `docs/METRICS_SPEC.md`, and `docs/UI_GUIDE.md`, before doing anything. Those docs are the source of truth for design, data, metrics, and the page; this file covers everything else: how the owner works, environment quirks, decisions and their reasons, open questions, risks, and the plan for Phase 4.

## 1. Where things stand

| Phase | Status |
|---|---|
| 0 · Setup (environment, repo, API smoke test) | **Complete** |
| 1 · Data pull (raw extract, tidy tables, validation, pipeline) | **Complete** |
| 2 · Metrics (seven owner-approved metrics) | **Complete** |
| 3 · Dashboard | **Complete** (2026-10-02) |
| 4 · Automation (weekly GitHub Action, GitHub Pages) | **In progress** (started 2026-10-03). Owner's answers in section 6; risk 1 fixed; next: pin dependencies (risk 2) |
| 5 · Extras | Not started |

At the end of Phase 3 (NFL week 4 in progress, so weeks 1–3 are the completed weeks):

- `python -m sleeper_dash.pipeline`: extract → transform → 7 data checks → optimal lineups and metrics → 7 metric checks → save 11 tables → re-check the saved CSVs. 14 of 14 checks pass, 23 API calls, ~6.5 seconds, processed CSVs byte-identical across runs. A successful run also writes `data/cache/pipeline_run.json` (finish time, league name, season, weeks, and league facts: 12 teams, median game on, playoffs from week 15).
- `python -m sleeper_dash.dashboard`: builds `site/index.html` from the saved CSVs and the run record. Sections, top to bottom: masthead with week selector, power rankings ladder (tap a row for its breakdown), weekly awards, five charts (Luck, Lineup efficiency, Consistency, Strength of schedule, Rank history), and "How this works". Every completed week is in the page; each week shows rankings, records, awards, and charts as of that week. 27 KB compressed (196 KB raw) for weeks 1–3; this season stretched to 17 weeks would be ~135 KB compressed.
- The page passed a full design review against `docs/UI_GUIDE.md` at 360, 390, 1024 and 1280px in light and dark mode; every approved fix is in.
- Privacy check at the close of Phase 3: no value from `data/raw/` (user settings, mascot messages, player nicknames, league chat fields, avatars) appears in the page or in any tracked file. Owner IDs appear only in `data/processed/teams.csv` (owner-approved). Notebooks are committed without outputs; fixtures are anonymised. The page's only outside requests are Google Fonts and cdn.plot.ly.
- **348 tests pass.** Git clean and in sync with `origin/main` at the `Phase 3: dashboard` commit.

## 2. Working with the owner

`CLAUDE.md` "About the owner" applies. Patterns that matter just as much:

- **Plain language, no syntax lessons.** End every step with what changed, what the data shows, and how it was verified. Tables for results.
- **Show the data.** After any data or metric step, print a sample table and summary stats and reconcile with Sleeper where possible.
- **Commands:** one command per fenced `bash` block (the app adds a Run button), no `$` prompt. The owner uses PowerShell.
- **Decisions:** ask short numbered questions with options and a recommendation. The owner answers tersely by number ("1. agree 2. reword to … 3. agree 4. defer to you"), sometimes overrides the recommendation, and sometimes supplies exact copy. "Defer to you" means pick, do it, and say what you picked. Record every answer in section 6 in the same commit.
- **Reviews:** list every finding in a table with a proposed fix and wait for approval before changing anything (design review, 2026-10-02). If you find a related bug while fixing an approved item, fix it only when it's the same code, and call it out at the top of the report.
- **Mobile first** is a standing priority (owner, 2026-10-02): design and check every component at 390px first.
- **Show drafts before publishing anything user-facing.** Copy changes need the owner's approval; "How this works" needs it again for any wording change.
- **Never quietly change a rule or a test to make something pass.** When a check fails because a rule or a doc is wrong, mark it as an expected failure with the reason written on it, ask the owner, then fix it their way. Used twice in Phase 3: the raw page-weight budget (owner chose compressed bytes) and the guide's misstated 11.9:1 contrast ratio (corrected to 11.8).
- **When a check fails, explain why before changing code** (standing instruction).
- **Small steps; plan before touching more than ~3 files.** When the owner explicitly asks for a larger piece of work, proceed, and list the files touched in the report.
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
| Installed versions (pin these in Phase 4) | pandas 3.0.6, numpy 2.5.3, requests 2.34.2, pyarrow 25.0.1, PyYAML 6.0.3, scipy 1.18.1, plotly 7.1.0, Jinja2 3.1.6, MarkupSafe 3.0.3, pytest 9.1.1, tzdata 2026.4, jupyterlab 4.6.4 |

### Previewing the page (browser pane)

- Preview servers are defined in **`C:\Personal Projects\FF\.claude\launch.json`** (outside the repo; the preview tool looks in the parent `FF` folder). `dashboard` serves `Dev\site` on port 8766: start it with `preview_start` and name `dashboard`. If another session already holds port 8766, open `http://127.0.0.1:8766/` with `preview_start` and a `url` instead: it serves the same folder, so a rebuilt page shows on reload.
- Use a server, not `file://`: local documents always render light, so dark mode can't be checked.
- Set the viewport with `resize_window` (360×780, 390×844, 1024×800, 1280×900; `colorScheme` light or dark) and set it again whenever the pane changes width; reset to the `desktop` preset when done. **Check 1024px too**: it's where the awards first sit beside the ladder, and it hid a layout collapse that 390 and 1280 didn't show.
- **Screenshots are unreliable** in this pane: after any scroll they come back magnified or cropped, and half-scale screenshots crop too. What works: navigate (reload), inject a style that hides the sections above the one you want (e.g. `.mast,.ladder-section{display:none!important}`), fire a `resize` event so charts redraw, then take a full-scale screenshot without scrolling. Never change the page itself for this.
- Verify layout with JavaScript measurements rather than screenshots: `scrollWidth` vs the viewport, row heights, Plotly's `_fullLayout` plot sizes, label bounding boxes for overlaps, characters per line. A measuring script saved in the page's `localStorage` survives reloads.
- The ladder's grow-in animation runs very slowly in the pane. For screenshots only, inject `*{transition:none!important}` and remove the `preload` class.
- Use `form_input` on the week selector (combobox "Week N") to switch weeks like a user would.

## 4. Repository map

```
Dev/
├── CLAUDE.md                     rules, commands, current status, decisions, open decisions
├── config.yaml                   league_id (quoted), season, every metric weight and threshold
├── pyproject.toml                package + dependencies (UNPINNED: risk 2); dashboard templates as package data
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
│                                 highlight, label placement, phone labels); CSS and JS are inlined into the page
├── tests/                        348 tests, one file per module, plus page-level test_page (every number on the
│                                 page equals the CSVs) and test_quality_floor; conftest blocks the network.
│                                 Tests read only committed files, so they run unchanged in GitHub Actions
├── .github/workflows/            EMPTY: weekly.yml is Phase 4
├── data/raw/, data/cache/        GITIGNORED
├── data/processed/               COMMITTED, public (owner decision)
└── site/                         GITIGNORED build output (index.html)
```

### How the page works (read before changing it)

- **One renderer.** Python formats every number (`build.view`); one Jinja2 macro draws a week. The latest week is drawn into the page; each earlier week sits in a `<template id="week-N">` block that `page.js` swaps in. No JavaScript copy of the drawing code exists, so nothing can drift. Chart figures are embedded per week as JSON in `<script type="application/json">` (every `<` escaped as `\u003c`).
- **Charts** are plain dicts built from `theme.py`; colours are token names that `charts.js` fills from the CSS custom properties, so dark mode follows the page. A team's `roster_id` rides in trace `meta` and in name-label `name`; tapping a point, a team name, or opening a ladder row highlights that team in every chart (the week's #1 by default). Below 768px, `charts.js` swaps in a figure's `phone` labels and margin (rank history: names cut to 14 characters).
- **Ladder layout** switches to one line a team through a CSS container query on the ladder's own width (≥760px), not a screen-width media query. On a 1024px screen the awards sit beside the ladder, which keeps the three-line layout. `test_quality_floor` checks the one-line layout leaves the name column at least 180px.
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
| 2026-10-02 | Page-level tests (Phase 3 step 5): sections, hidden sections, outside requests, page weight, every number vs the CSVs for every week; plus the testable quality floor (reduced motion, focus rings, contrast) | Owner (request) | CODEBASE.md |
| 2026-10-02 | UI_GUIDE.md contrast note corrected: chalk on turf is 11.8:1 (was stated as 11.9) | Owner | UI_GUIDE.md |
| 2026-10-02 | Design review fixes: ladder key reads "League average: 50"; rank-history names cut to 14 characters on phones; reading width ~72 characters; movement 16px; spacing on the scale; compact award tiles on desktop; luck labels on a page background; 1200px column centred; guide reworded for tooltips, phone sketch, and the ladder's details element | Owner (approved list; movement size delegated to Claude) | UI_GUIDE.md |
| 2026-10-02 | The ladder's one-line layout switches on the ladder's own width (container query, 760px), fixing a collapse at 1024–1150px screens where team names had a 0px column | Claude (found in the design review) | UI_GUIDE.md |
| 2026-10-02 | The awards column may stay ~235px taller than the ladder at 1280px (no further tile tightening) | Owner | — |
| 2026-10-02 | Phase 3 closed after a privacy check of the built page and every tracked file | Owner (request) | CODEBASE.md changelog |
| 2026-10-03 | Weekly run Tuesday 12:17 PM Eastern (cron `17 12 * * 2`, `timezone: America/New_York`, so it follows daylight saving); "12:17 EST" read as 12:17 PM local Eastern time | Owner (time), Claude (PM and time-zone reading) | weekly.yml |
| 2026-10-03 | Second weekly run for stat corrections: Thursday 12:17 PM Eastern | Owner | weekly.yml |
| 2026-10-03 | The workflow commits refreshed `data/processed/*.csv` back to `main` as the GitHub Actions bot (`contents: write`); local work starts with `git pull` | Owner | weekly.yml, CLAUDE.md |
| 2026-10-03 | Python 3.14 in GitHub Actions, matching local | Owner | weekly.yml, pyproject.toml |
| 2026-10-03 | Failed runs: GitHub's default email to the account that last changed the workflow's schedule | Owner | — |
| 2026-10-03 | Season start date lives in `config.yaml` (`season_start_date`), checked against `/state/nfl` while Sleeper still describes the season (risk 1 fixed) | Owner | config.yaml, CODEBASE.md |
| 2026-10-03 | Claude switches the Pages source to "GitHub Actions" with `gh` | Owner | — |
| 2026-10-03 | Phase 4 plan (section 9) approved; commit and push after each step | Owner | — |

## 7. Open questions and assumptions to verify

**Phase 4 decisions the owner needs to make before the workflow is written** (ask as numbered questions with recommendations):
1. **Run time.** GitHub Actions cron runs in UTC, so a fixed time shifts an hour when daylight saving ends (Nov 1). Recommended: Tuesday 11:00 UTC (7 AM EDT, 6 AM EST), after Monday night's game is scored. Sleeper's completed-week rule means a run before scoring finishes simply shows the previous week.
2. **A second weekly run for stat corrections?** NFL stat corrections land later in the week, and every run recomputes the season. Recommended: also Friday 11:00 UTC.
3. **Commit the refreshed processed CSVs back to the repo from the workflow?** Recommended: yes. It keeps `data/processed/` current (today they're committed by hand), gives a week-by-week history, means the tests check this week's data, and keeps the repo active so GitHub doesn't switch the schedule off (risk 3). It needs `contents: write` and commits as the GitHub Actions bot.
4. **Python version for Actions.** Recommended: 3.14, matching local.
5. **Who gets told when a run fails?** GitHub emails the account that last changed the workflow's schedule. Recommended: that's enough for now.

**Verify at week 4 (first new data since the dashboard was built):** the Strength of schedule chart should switch to two panels (remaining no longer all 0.0); luck labels and the efficiency chart should still read cleanly at 390px with new values; rank-history labels at 360px; the pipeline should produce four weeks of processed CSVs.

**Verify at week 15 (first playoff week):** whether Sleeper plays the median game in the playoffs (code assumes not); whether roster `wins`/`losses`/`fpts` include playoff games (validation assumes not); how non-playoff teams appear in matchups (null `matchup_id` handled either way).

**Known gaps:** Sleeper's `ppts` sits 0.02–4.00 points below our optimal lineups for 7 teams (soft check only); FAAB and picks traded inside trades aren't in `transactions`; player positions describe today, not past weeks; `winners_bracket` not pulled (Phase 5).

**Open product questions:**
- Where league members see updates: bookmark only, or also a group-chat post (Phase 5).
- Boom/bust weeks are explained in "How this works" but not displayed yet (owner wants them kept for a future display).

## 8. Known risks

Ordered by impact on an unattended weekly job.

1. **Off-season breakage: fixed 2026-10-03.** The season start date now comes from `config.yaml` and is only checked against `/state/nfl` while that still describes the league's season, so Sleeper's rollover to 2027 no longer stops transform. **Each new season, update `season` and `season_start_date` together** (config refuses a date outside the season).
2. **Unpinned dependencies (fix before Phase 4).** A fresh install in Actions gets whatever is newest. Plotly is the sharpest edge: a new Python `plotly` changes the expected CDN version, and the version test then stops the job (safe, but no update that week). `charts.js` also uses Plotly internals. `jupyterlab` and `pytest` sit in the runtime dependencies, which makes every Actions install much heavier than it needs to be; move them to an optional `[dev]` extra. Installed versions are in section 3.
3. **GitHub switches off scheduled workflows in public repos after 60 days with no repository activity.** A quiet stretch from mid-November would stop the weekly run without any error. Committing the refreshed CSVs from the workflow (section 7, question 3) prevents this.
4. **Week 15 untested on real data** (section 7). A wrong assumption fails "Records match Sleeper" and stops the run: safe, but the page stops updating until fixed.
5. **The tests in the workflow check the committed tables, not this run's.** `test_page` builds the page from `data/processed/` as committed. Run `pytest tests/test_page.py` again after the pipeline and dashboard steps, so the numbers about to be published are checked too.
6. **Sleeper's API is unofficial.** Shape changes surface as failed checks, without notice.
7. **Label placement is a heuristic** (`charts.js`): crowded luck charts could still overlap in some weeks. Check new weeks at 390px.
8. **The page depends on two CDNs** (Google Fonts, cdn.plot.ly). If Plotly fails to load, each chart shows its one-sentence text summary instead. Loading fonts from Google also tells Google each visitor's IP address; self-hosting the fonts would remove both.
9. **Newer CSS** (container queries, `::details-content`, `interpolate-size`): older browsers fall back to the three-line ladder on desktop and an instant (unanimated) breakdown. Nothing breaks.
10. **Player positions are today's**, so a mid-season position change alters past optimal lineups.
11. **Posted numbers can change** after stat corrections (deliberate full recompute; explained in "How this works").
12. **Near-ties at the top** of the power rankings (#1 and #2 both show 57.8 through week 3).

## 9. Plan: Phase 4 (automation)

Propose this plan to the owner and get the section 7 answers before starting. In order:

1. **Fix risk 1** (season start date) with tests, including one where `/state/nfl` describes the next season.
2. **Pin dependencies** (risk 2): exact versions from section 3 in `pyproject.toml` (or a lock file installed with `pip install -r`), `jupyterlab` and `pytest` moved to a `[dev]` extra, `requires-python` matching the Actions version. Prove it with a fresh virtual environment: install, `pytest`, pipeline, dashboard.
3. **Add `.github/workflows/weekly.yml`:**
   - Triggers: the agreed `schedule` (section 7) and `workflow_dispatch` (a manual run button). One run at a time (`concurrency`).
   - Build job: check out → set up Python with a pip cache → install → `pytest` → `python -m sleeper_dash.pipeline` → `python -m sleeper_dash.dashboard` → `pytest tests/test_page.py` (risk 5) → if approved, commit changed `data/processed/*.csv` only → upload `site/` as the Pages artifact.
   - Deploy job: `actions/deploy-pages` to the `github-pages` environment.
   - Any failed step stops the job before deploy (rule 8); the last good page stays live.
   - Permissions: `contents: read` (or `write` if committing CSVs), `pages: write`, `id-token: write`.
4. **The owner switches the repo's Pages source to "GitHub Actions"** (Settings → Pages). This is a repository-settings change: ask the owner to do it, or ask before doing it.
5. **First run by hand** (`workflow_dispatch`); watch it; open the live URL at 390 and 1280px in light and dark; share the URL with the owner.
6. Update `CLAUDE.md`, `docs/CODEBASE.md` (workflow module, data flow), and this file; mark Phase 4 complete.

## 10. Commit history

Phase 1 ends at `1ad16d1`; Phase 2 ends at `38eba07 Phase 2: metrics`; Phase 3 runs from `487e76c` (season-to-date lineup efficiency) to `Phase 3: dashboard`. Use `git log --oneline` for the full list.

## 11. First steps for the new session

1. Read `CLAUDE.md`, this file, `docs/CODEBASE.md`, `docs/METRICS_SPEC.md`, and `docs/UI_GUIDE.md`.
2. Confirm the environment: `.venv\Scripts\python.exe -m pytest -q` (expect **348 passed**) and `git status` (expect clean, in sync with `origin/main`).
3. Refresh: `.venv\Scripts\python.exe -m sleeper_dash.pipeline` (every check passes; 9 awards a week; week 4 appears once Sleeper has scored it), then `.venv\Scripts\python.exe -m sleeper_dash.dashboard`. Commit and push any changed processed CSVs.
4. If week 4 has arrived, check the page in the browser pane (section 3) at 360, 390, 1024 and 1280px, paying attention to the week-4 items in section 7.
5. Then section 9: ask the owner the section 7 Phase 4 questions, then start Phase 4.
