# Session handoff

Rewritten 2026-10-02 at the end of Phase 3 (the dashboard); updated 2026-10-03 at the end of Phase 4 (automation) and its follow-ups (playoff weeks, workflow review). A new Claude session should read this file first, then `CLAUDE.md`, `docs/CODEBASE.md`, `docs/METRICS_SPEC.md`, and `docs/UI_GUIDE.md`, before doing anything. Those docs are the source of truth for design, data, metrics, and the page; this file covers everything else: how the owner works, environment quirks, decisions and their reasons, open questions, risks, running the weekly job, and what's next.

## 1. Where things stand

| Phase | Status |
|---|---|
| 0 · Setup (environment, repo, API smoke test) | **Complete** |
| 1 · Data pull (raw extract, tidy tables, validation, pipeline) | **Complete** |
| 2 · Metrics (seven owner-approved metrics) | **Complete** |
| 3 · Dashboard | **Complete** (2026-10-02) |
| 4 · Automation (weekly GitHub Action, GitHub Pages) | **Complete** (2026-10-03) |
| 5 · Extras | Not started. Ask the owner which extra comes first (section 9) |

As of 2026-10-03, end of session (NFL week 4 in progress, so weeks 1–3 are the completed weeks):

- **Live:** https://jonaht26.github.io/sleeper-dashboard/, published by `.github/workflows/weekly.yml` every Tuesday and Thursday at 12:17 PM Eastern (section 7a). Four manual runs on 2026-10-03 all succeeded; the owner checked the live page in every format and approved it, and reconfirmed the schedule and the commit-back. **No scheduled run has happened yet: the first is Tuesday Oct 6**, which should bring week 4, then Thursday Oct 8 (section 7).
- `python -m sleeper_dash.pipeline`: extract → transform → 7 data checks → optimal lineups and metrics → 7 metric checks → save 11 tables → re-check the saved CSVs. 14 of 14 checks, 23 API calls, ~7 seconds. The summary now says whether the latest week moved and which tables changed ("no new completed week since the last run", "unchanged (every file identical)").
- `python -m sleeper_dash.dashboard`: builds `site/index.html` (masthead with week selector, ladder, awards, five charts, "How this works"). 27 KB compressed for weeks 1–3.
- Unattended-job risks fixed: the season start date no longer depends on Sleeper's current season (risk 1); every dependency and Python 3.14.7 pinned, and tested against what's installed (risk 2); the page tests run again on each run's fresh tables (risk 5); extract's folder swap retries when Windows briefly refuses it (risk 5a); playoff-week behaviour checked on this league's real 2025 playoffs and settled with the owner (risk 4).
- **Playoff weeks:** the real pipeline passed 14 of 14 checks on all 17 weeks of the 2025 season. In playoff weeks the standings checks accept either counting standard (one must fit every team); teams missing from the matchups or without a lineup stop the run; consolation games count for awards (owner decisions, section 6).
- **406 tests pass**, locally and in GitHub Actions. Git clean and in sync with `origin/main`.

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
- **Requests may come from a pre-written list.** In this session several asked for work that was already done, or cited a risk number that didn't match this file ("risk 2" for the playoff risk, "risk 4" for pinning). Check each against the current state, say plainly what's already done and what the gap is, close only the gap, and present decisions already made as "confirm or change" rather than asking again from scratch.
- **Options land best with consequences.** For check-behaviour decisions, showing what would be published under each option (a "warn and continue" what-if run) let the owner decide in one reply.
- **The owner checks the live page themselves** (phone, and browser developer tools for widths and dark mode) and says so; no need to repeat a check they've reported.
- **Privacy:** the repo is public. Never commit `data/raw/` (managers' personal settings) or `data/cache/`. Never route around a safety block; explain it and let the owner decide.

## 3. Environment and gotchas

| Item | Detail |
|---|---|
| OS / shells | Windows 11. PowerShell **5.1** is primary (no `&&`, `?:`, `??`); Bash (Git Bash) also available |
| Project root | `C:\Personal Projects\FF\Dev`. Sessions may open in the parent `FF`; work in `Dev` |
| Python | 3.14.7, pinned in `.python-version` (GitHub Actions uses the same). Venv `.venv`, package installed editable with `pip install -e ".[dev]"`. In tool calls use `.venv\Scripts\python.exe` directly |
| git / GitHub | **The workflow's bot pushes commits to `main`** (refreshed tables), so `git pull` before starting local work. Repo-local `user.email` is `jonahtersol@gmail.com` (never the global work address). `gh` logged in as **JonahT26**; remote `https://github.com/JonahT26/sleeper-dashboard` (public), branch `main`. Fresh shells may not see `gh`; prefix with `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')` |
| Unicode output | Set `$env:PYTHONIOENCODING='utf-8'` before Python that prints team names (curly quotes) |
| Editing files | Prefer the Edit/Write tools. For multi-file edits, write a small Python script to the scratchpad with the Write tool and run it; each replacement asserts its target appears exactly once. **Bash heredocs break on some content** (apostrophes, backslashes): don't pipe Python through heredocs when the code contains them. **PowerShell `[IO.File]` methods use the .NET working directory, not the PowerShell location**: always pass absolute paths |
| BOM trap | PowerShell 5.1 `Set-Content -Encoding utf8` writes a byte-order mark. Don't use it on source files |
| Harmless noise | "LF will be replaced by CRLF" git warnings; exit code −1 when output is piped to `Select-Object -First N`; **exit code 255 after `git push -q`** (git writes progress to stderr): check `git status -sb` shows no "ahead" instead |
| Commit messages | In PowerShell use `git commit -m @'` … `'@` (closing `'@` at column 0). `git commit -F -` followed by a here-string does **not** work: git treats the text as a file path and commits nothing |
| `gh --jq` in PowerShell | Filters with string concatenation (`.a + "  " + .b`) get split into extra arguments; use object filters like `'{conclusion, jobs: [.jobs[] | {name, conclusion}]}'` |
| Scratch experiments | Write throwaway scripts to the session scratchpad with the Write tool (inline `python -c` and `printf` quoting kept breaking). The scratchpad is per session, so nothing there survives (e.g. this session's copy of the 2025 raw data). `pip install .` (not `-e`) leaves a `build/` folder in the project: delete it |
| Excel | Opening CSVs directly corrupts 18-digit IDs. CSVs are `utf-8-sig` |
| Sleeper politeness | Tests block the network. `api.get` paces calls ≥0.25 s apart; `/players/nfl` cached for 24 h |
| Plotly version | Python `plotly` 7.1.0 pairs with plotly.js **4.1.1**, loaded from `cdn.plot.ly` (basic bundle). `theme.PLOTLY_JS_VERSION` must match `plotly.offline.get_plotlyjs_version()` (a test checks). `charts.js` uses Plotly internals (`_fullLayout`, axis `_offset`, `l2p`) for label placement; re-check it after any Plotly upgrade |
| Installed versions (pinned 2026-10-03 in `pyproject.toml` and `requirements-ci.txt`) | pandas 3.0.6, numpy 2.5.3, requests 2.34.2, pyarrow 25.0.1, PyYAML 6.0.3, scipy 1.18.1, plotly 7.1.0, Jinja2 3.1.6, MarkupSafe 3.0.3, pytest 9.1.1, tzdata 2026.4, jupyterlab 4.6.4 |

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
├── config.yaml                   league_id (quoted), season, season_start_dates, every metric weight and threshold
├── pyproject.toml                package + exact dependency versions (dev extra: pytest, jupyterlab)
├── requirements-ci.txt           lock file: every package GitHub Actions installs, exact versions
├── .python-version               3.14.7, read by the workflow
├── .github/workflows/weekly.yml  Tue + Thu 12:17 PM Eastern and a manual button: tests → pipeline → dashboard →
│                                 page tests → commit changed tables → publish to GitHub Pages
├── docs/
│   ├── CODEBASE.md               data flow, modules, table schemas, Sleeper quirks, dependencies, changelog
│   ├── METRICS_SPEC.md           owner-approved metric definitions (code follows the spec)
│   ├── UI_GUIDE.md               design system and every dashboard decision (ladder, charts, copy)
│   ├── DATA_DICTIONARY.md        raw Sleeper fields and findings
│   └── HANDOFF.md                this file
├── src/sleeper_dash/
│   ├── config.py, api.py, extract.py, transform.py, validate.py (14 checks), lineup.py, metrics/
│   ├── pipeline.py               full refresh; reports week and table changes; writes data/cache/pipeline_run.json
│   └── dashboard/
│       ├── build.py              tables → view (every number formatted once) → HTML; `python -m sleeper_dash.dashboard`
│       ├── theme.py              the one shared Plotly theme; colours as CSS tokens ("@pylon"); CDN URL
│       ├── charts.py             five chart sections as Plotly figure dicts (pure functions)
│       ├── explainer.py          "How this works" copy, numbers from config.yaml (owner-approved)
│       └── templates/            index.html.j2, styles.css, page.js (week selector), charts.js (drawing,
│                                 highlight, label placement, phone labels); CSS and JS are inlined into the page
├── tests/                        406 tests, one file per module, plus test_page (every number on the page equals
│                                 the CSVs), test_quality_floor, test_dependencies (pins = installed), and
│                                 test_pipeline_offline (the real pipeline against fake_sleeper.py); conftest
│                                 blocks the network. Tests read only committed files, so they run in Actions
├── data/raw/, data/cache/        GITIGNORED
├── data/processed/               COMMITTED, public (owner decision); refreshed by the workflow's bot
└── site/                         GITIGNORED build output (index.html), published by the workflow
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
- **Previous season** league ID `1243747994637963265` (Phase 5): same settings (12 teams, 6-team playoffs from week 15, median game on, but 9 starting slots, not 10). Its finished playoffs are the evidence behind risk 4.

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
| 2026-10-03 | Python 3.14 in GitHub Actions, matching local (later pinned to exactly 3.14.7) | Owner | weekly.yml, pyproject.toml |
| 2026-10-03 | Failed runs: GitHub's default email to the account that last changed the workflow's schedule | Owner | — |
| 2026-10-03 | Season start date lives in `config.yaml`, checked against `/state/nfl` while Sleeper still describes the season (first version; replaced by `season_start_dates` below) | Owner | config.yaml, CODEBASE.md |
| 2026-10-03 | Claude switches the Pages source to "GitHub Actions" with `gh` | Owner | — |
| 2026-10-03 | Phase 4 plan (section 9) approved; commit and push after each step | Owner | — |
| 2026-10-03 | Season start dates stored per season (`season_start_dates`), never derived from `/state/nfl`, so rollover and past seasons (Phase 5) work; deriving from the NFL calendar rejected (Sleeper's 2026 date isn't kickoff Thursday) | Owner (requirement), Claude (design) | config.yaml, CODEBASE.md |
| 2026-10-03 | Python pinned to exactly 3.14.7 (`.python-version`, read by the workflow), matching local; the lock file is checked against the installed packages by tests | Owner (requirement), Claude (method) | CODEBASE.md "Dependencies" |
| 2026-10-03 | A run with no new completed week is a normal full refresh that succeeds; numbers change only through stat corrections; the summary reports whether the week moved and which tables changed, compared with the saved tables | Owner (requirement), Claude (reporting) | pipeline.py, CODEBASE.md |
| 2026-10-03 | Extract's raw-folder swap retries up to 5 times (2 s at most) when Windows refuses it, then stops with a clear message | Claude, delegated by owner | extract.py, CODEBASE.md |
| 2026-10-03 | Live page checked by the owner in every format (360–1280px, light and dark) and approved; Phase 4 closed | Owner | — |
| 2026-10-03 | Playoff weeks: standings checks accept either counting standard (one must fit every team, named in the check); teams missing from matchups or without a lineup keep stopping the run | Owner (options 2 and 1) | validate.py, CODEBASE.md |
| 2026-10-03 | Consolation and placement games count for matchup awards in playoff weeks | Owner | METRICS_SPEC.md §7 |
| 2026-10-03 | Workflow reviewed against the owner's requirements; Tuesday + Thursday 12:17 PM ET schedule and committing refreshed CSVs both reconfirmed, workflow unchanged | Owner | weekly.yml |

## 7. Open questions and assumptions to verify

**Verify at week 4 (Tuesday Oct 6, the first scheduled run):** the run succeeds and its bot commits "Weekly refresh: tables through week 4"; then `git pull`. On the live page: the Strength of schedule chart switches to two panels (remaining no longer all 0.0); luck labels and the efficiency chart still read cleanly at 390px with new values; rank-history labels at 360px. Thursday Oct 8's run should report "no new completed week" (and commit only if Sleeper made a stat correction).

**Week 15 (first playoff week, mid-December):** the three playoff assumptions held for this league's 2025 season (risk 4), and the pipeline passes on 2025's real playoff weeks. Still confirm the first 2026 playoff run succeeded. Consolation-bracket and placement games are paired like real games, so matchup awards (Heartbreaker, Robbery, Blowout, Nail-biter) in playoff weeks can go to them: kept by the owner (2026-10-03, METRICS_SPEC.md section 7).

**Known gaps:** Sleeper's `ppts` sits 0.02–4.00 points below our optimal lineups for 7 teams (soft check only); on the 2025 season the gap reached 8.5–15.3 points for 6 teams, probably because player positions are today's (risk 10), which matters for past seasons (Phase 5); FAAB and picks traded inside trades aren't in `transactions`; player positions describe today, not past weeks; `winners_bracket` not pulled (Phase 5). A season with no completed week yet (next season's preseason, after `config.yaml` moves to 2027) stops the pipeline with a misleading "matchups is missing. Run `python -m sleeper_dash.extract` first" message (checked with the fake league): decide the season-rollover behaviour before then (section 7a).

**Open product questions:**
- Where league members see updates: bookmark only, or also a group-chat post (Phase 5).
- Boom/bust weeks are explained in "How this works" but not displayed yet (owner wants them kept for a future display).

## 7a. Running the weekly job

- **Schedule:** Tuesday and Thursday 12:17 PM Eastern (`timezone: America/New_York`, so it follows daylight saving). GitHub can start scheduled runs late, sometimes by tens of minutes. The Thursday run picks up stat corrections to the week just finished; Wednesday waiver pickups belong to the week in progress, so they appear the following Tuesday.
- **Manual run:** the "Run workflow" button on the repo's Actions tab, or `gh workflow run weekly.yml --ref main`. Watch with `gh run watch <id>`; read with `gh run view <id> --log`.
- **What a run does:** installs the lock file on Python 3.14.7 → all tests on the committed tables → pipeline → dashboard → page tests on this run's tables → commits changed `data/processed/*.csv` as `github-actions[bot]` ("Weekly refresh: tables through week N"; nothing when unchanged) → publishes `site/`. Any failure stops before publishing; the last good page stays live and GitHub emails the owner.
- **Run summary** (2026-10-03): each run's page on GitHub (Actions tab → the run) opens with its summary: the pipeline's latest week, checks passed, and tables written (rows, changed or not), or the reason it failed; whether tables were committed; a step-by-step results table that says "Build: FAILED. Nothing was published" when any step failed; and "Published: <url>" from the deploy job.
- **A failed run:** read the log first. A failed check names itself (e.g. "Records match Sleeper"); explain the cause to the owner before changing code (section 2).
- **Before local work:** `git pull`, because the bot commits to `main`.
- **Season rollover (before the 2027 season):**
  1. GitHub switches the schedule off after 60 days without repository activity, and in the off-season the tables stop changing, so expect it to be off by about March. Re-enable it on the Actions tab (or `gh workflow enable weekly.yml`).
  2. Put the 2027 league ID and season in `config.yaml`, and add `2027:` to `season_start_dates` (Sleeper's `/state/nfl` `season_start_date` once it describes 2027).
  3. Decide what the page shows between rollover and week 1 (it currently can't build a season with no completed week; section 7), and whether 2026 stays viewable (Phase 5, past seasons).

## 8. Known risks

Ordered by impact on the unattended weekly job.

1. **Off-season breakage: fixed 2026-10-03.** Season start dates live in `config.yaml` `season_start_dates`, one per season, and never come from `/state/nfl`, which is only a cross-check while it describes the league's season and gives a date. Proven offline (`test_pipeline_offline`: Sleeper in 2026, the off-season, 2027's preseason, 2027 under way, no date) and on the real league (four `/state/nfl` variants, 14 of 14 checks, all 11 tables identical to the committed CSVs). Phase 5 needs a line for each past season; `/state/nfl` can't supply them, and Sleeper's 2026 date (2026-09-09) falls on a Wednesday, so confirm what Sleeper's date marks before filling in 2025.
2. **Unpinned dependencies: fixed 2026-10-03.** Exact versions in `pyproject.toml`; `requirements-ci.txt` (the lock file) pins all 23 packages Actions installs; `.python-version` pins Python 3.14.7, which the workflow reads (GitHub already offers 3.14.8). `test_dependencies` fails, locally or in Actions, if the installed packages or Python differ from the pins or the lock misses a package. A fresh environment from the lock produced all 11 tables and the page byte-identical. Update steps in `docs/CODEBASE.md` "Dependencies".
3. **GitHub switches off scheduled workflows after 60 days with no repository activity.** In season the bot's weekly commits keep it on. After the season the tables stop changing, so it will switch off (expected, harmless); re-enable it before next season (section 7a).
4. **Playoff weeks: checked on real data and decided, 2026-10-03.** This league's finished 2025 season (same settings: 12 teams, 6-team playoffs from week 15, median game) shows Sleeper's roster wins, losses, points for and against count the **regular season only** (12 of 12 teams; so no median game counts in the playoffs either); **every team is listed every playoff week** with a full lineup and points; byes have no `matchup_id`; consolation games **are** paired. The real pipeline on all 17 weeks of 2025 passed 14 of 14 checks and built the page. `test_pipeline_offline` runs an 8-team fake league through two playoff weeks in each plausible Sleeper behaviour: as in 2025 and with no consolation games, everything passes and publishes; if Sleeper's standings counted playoff games or points, "Records match Sleeper" or "Points for/against match Sleeper" stops the run; teams left out of the matchups stop it at "Every week has one row per team"; teams with an empty lineup stop it in transform. **Owner decision 2026-10-03:** the standings checks accept either counting standard in playoff weeks (regular season only, or also playoff games, a playoff median, or playoff points), as long as one standard fits every team, and name the one that matched; teams missing from the matchups or without a lineup still stop the run. Standings that count the playoffs now pass with tables byte-identical to the 2025-style case, and standings that fit no single standard still stop the run (`test_pipeline_offline`).
5. **Tests on this run's tables: fixed.** The workflow runs `pytest tests/test_page.py` again after the pipeline and dashboard, so the numbers about to be published are checked.
5a. **Windows folder swap: fixed 2026-10-03.** Extract deleted `data/raw/{season}/` and renamed the new download into place; Windows sometimes refused the rename while antivirus or indexing still held the old folder (about 1 in 14 back-to-back test runs). `extract._swap_in` now retries up to 5 times (2 s at most) and then stops with a clear message; the offline tests reuse one raw folder again and passed 6 runs in a row. Never seen in real runs; can't happen on GitHub's Linux machines.
6. **Sleeper's API is unofficial.** Shape changes surface as failed checks, without notice.
7. **Label placement is a heuristic** (`charts.js`): crowded luck charts could still overlap in some weeks. Check new weeks at 390px.
8. **The page depends on two CDNs** (Google Fonts, cdn.plot.ly). If Plotly fails to load, each chart shows its one-sentence text summary instead. Loading fonts from Google also tells Google each visitor's IP address; self-hosting the fonts would remove both.
9. **Newer CSS** (container queries, `::details-content`, `interpolate-size`): older browsers fall back to the three-line ladder on desktop and an instant (unanimated) breakdown. Nothing breaks.
10. **Player positions are today's**, so a mid-season position change alters past optimal lineups.
11. **Posted numbers can change** after stat corrections (deliberate full recompute; explained in "How this works").
12. **Near-ties at the top** of the power rankings (#1 and #2 both show 57.8 through week 3).

## 9. Next: Phase 5 (extras)

Not planned yet. The roadmap in `CLAUDE.md` lists playoff odds (a simulation), past seasons, and posting to the league chat. Ask the owner which comes first, as numbered questions with a recommendation, before planning. What each needs:

- **Playoff odds:** a new section after the ladder (UI_GUIDE.md); a definition written into METRICS_SPEC.md with the owner first (model for future scores, number of simulations, tie-breakers, the median game); the remaining schedule is already in `schedule`. Most useful from mid-season.
- **Past seasons:** the previous league (`1243747994637963265`) through `previous_league_id`. Already shown to work end to end: on 2026-10-03 the real pipeline and page build ran on all 17 weeks of 2025 in a scratch folder (14 of 14 checks; page 1.3 MB raw, 17 weeks), by pointing the module paths at a temporary folder and passing a `Config` for 2025, the same pattern as the `run_pipeline` fixture in `tests/test_pipeline_offline.py`. Still needed: a `season_start_dates` line for each season (risk 1); extract and the pipeline run per season (`data/raw/{season}/` already separates them); the page needs a season selector; `winners_bracket` for playoff results.
- **Posting to the league chat:** decide where and how (open product question); Sleeper's API is read-only, so it needs another channel.

## 10. Commit history

Phase 1 ends at `1ad16d1`; Phase 2 ends at `38eba07 Phase 2: metrics`; Phase 3 runs from `487e76c` (season-to-date lineup efficiency) to `8966259 Phase 3: dashboard`; Phase 4 runs from `8dee0e8` (season start date in config) to `df8f4cf Phase 4: automation`; follow-ups `e8a3260` (playoff tests against 2025 behaviour), `86c1486` (either standings standard in playoff weeks), `38e081c` (workflow reconfirmed), and the handoff update after them. From Phase 4 on, `github-actions[bot]` commits refreshed tables ("Weekly refresh: tables through week N"). Use `git log --oneline` for the full list.

## 11. First steps for the new session

1. `git pull` (the bot commits to `main`).
2. Read `CLAUDE.md`, this file, `docs/CODEBASE.md`, `docs/METRICS_SPEC.md`, and `docs/UI_GUIDE.md`.
3. Confirm the environment: `.venv\Scripts\python.exe -m pytest -q` (expect **406 passed**; a `test_dependencies` failure means the local environment drifted from the pins, see `docs/CODEBASE.md` "Dependencies") and `git status` (clean, in sync).
4. Check the weekly job: `gh run list --workflow weekly.yml --limit 5`. Any failure comes first (section 7a). The first scheduled runs are Tue Oct 6 (should commit "Weekly refresh: tables through week 4") and Thu Oct 8 (should report no new week); if a session starts before then, there's nothing scheduled to check yet.
5. If week 4 or later has arrived, check the live page at 360, 390, 1024 and 1280px in light and dark (section 3), paying attention to the section 7 items.
6. Then section 9: ask the owner which Phase 5 extra comes first.
