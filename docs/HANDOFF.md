# Session handoff

Rewritten 2026-10-02 at the end of Phase 3 (the dashboard); updated 2026-10-03 at the close of Phase 4 (automation); **rewritten 2026-10-05 at the end of the first Phase 5 session** (playoff odds, past seasons, History, all on unmerged branches; see section 1). **This file is most current on the `past-seasons` branch**: `main`'s copy is from before Phase 5 work began, so read this one (`git show origin/past-seasons:docs/HANDOFF.md`) before switching branches. A new Claude session should read this file first, then `CLAUDE.md`, `docs/CODEBASE.md`, `docs/METRICS_SPEC.md`, and `docs/UI_GUIDE.md`, before doing anything. Those docs are the source of truth for design, data, metrics, and the page; this file covers everything else: how the owner works, environment quirks, decisions and their reasons, open questions, risks, running the weekly job, and what's next.

## 1. Where things stand

| Phase | Status |
|---|---|
| 0 · Setup (environment, repo, API smoke test) | **Complete** |
| 1 · Data pull (raw extract, tidy tables, validation, pipeline) | **Complete** |
| 2 · Metrics (seven owner-approved metrics) | **Complete** |
| 3 · Dashboard | **Complete** (2026-10-02) |
| 4 · Automation (weekly GitHub Action, GitHub Pages, monitoring, rollback, runbook) | **Complete** (2026-10-03) |
| 5 · Extras | **In progress** (2026-10-05): playoff odds, past seasons + History, and the playoff bracket view built on three stacked branches, **not merged**; week 15 checks scheduled for Dec 22 (section 9) |

As of **Monday 2026-10-05, end of session** (NFL week 4's Monday game is tonight, so weeks 1–3 are the completed weeks):

**What's live (`main`) hasn't changed since 2026-10-03.** https://jonaht26.github.io/sleeper-dashboard/ shows weeks 1–3: ladder, awards, five charts, "How this works". **No scheduled run has happened yet: the first is Tuesday Oct 6, 12:17 PM ET** (should bring week 4), then Thursday Oct 8 (section 7). The only Phase 5 commit on `main` is the playoff odds spec (`90c3190`, docs only).

**Four branches** (all pushed; no workflow runs on branches, and **never** `gh workflow run weekly.yml --ref <branch>`: that would publish the branch and commit tables to it):

| Branch | Head | Adds | Tests | State |
|---|---|---|---|---|
| `main` | `90c3190` | Phase 4 + the playoff odds spec | 433 | Live; the workflow's bot commits refreshed tables here |
| `playoff-odds` | `e600246` | Playoff odds (metric, `playoff_odds` and `winners_bracket` tables, 2 checks → 16), calibration notebook 04, the Playoff odds section after the ladder, "How this works" paragraph | 467 | **Owner-approved, wording included.** Merge after the Tue Oct 6 run is checked |
| `past-seasons` | `bfbdc54` | Stacked on `playoff-odds`: seasons 2020–2025 in the pipeline, `managers` table (17 checks), three owner rules from past data, the History section | 489 | Built and checked; **History wording approved** (2026-10-05). Merge after `playoff-odds` |
| `bracket-view` | see `git log` | Stacked on `past-seasons`: the Playoffs section (`dashboard/bracket.py`), shown in playoff weeks in the odds' place | 515 | Built and checked on 2020–2025's brackets; **wording approved** (2026-10-05). Merge after `past-seasons`. The local checkout is on this branch |

**Owner input still pending:**
- **Order of the remaining extras** (section 9).
- **League-chat post:** the owner started a request for an automatic weekly post (webhook as a GitHub secret, dry-run mode, never posting a week twice, a CLAUDE.md rule 7 exception) and then said to **ignore it** in the same message. Nothing was built or asked. Don't act on it unless the owner raises it again.

**Scheduled:** a one-time Claude desktop session, `sleeper-week15-playoff-checks`, Tue Dec 22 2026 at 2:00 PM ET (section 7).

**Pipeline on `past-seasons`, through 2026 week 3:** every season 2020–2026 downloaded, built and checked against its own league settings and Sleeper standings: 17 of 17 checks in every season, 262 API calls, ~80 s locally, byte-identical on a second run, every 2026 row identical to the single-season tables. Raw data for 2020–2026 is in `data/raw/` locally (gitignored).
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
- **Work on a branch while a scheduled run is pending or page wording awaits approval** (2026-10-05). Whatever is on `main` publishes at the next run (rule 11). Push the branch (standing approval covers pushing), merge only when the owner has approved the wording and the latest run has been checked. Stacking a second branch on the first worked; merge them in order.
- **A failed check in new data is a decision, not a fix** (2026-10-05, past seasons). Stop before saving, run the remaining steps in a scratch script (nothing saved) so every failure surfaces at once, find each cause with data, then present options with a recommendation. The owner chose in one reply ("1a 2 agree 3 agree").
- **The owner sometimes approves a whole option list with "all of your recommended options are great"** or "1 agree 2 agree …". Record each answer in section 6 in the same commit as the change.
- **Time-sensitive asks that can't run yet** (e.g. "run this during week 15"): say why, separate what's already done from what's open, recommend what can be built now, and offer a scheduled session (`anthropic-skills:schedule` → `create_scheduled_task` with `fireAt`) that works on a branch and reports without merging.

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
| Bare `python` | **Hangs** in Bash on this machine (it reaches the Windows Store stub and waits; a backgrounded command had to be stopped, 2026-10-05). Always call `.venv/Scripts/python.exe` |
| Notebooks | Committed **without outputs**. To check one runs: `.venv/Scripts/jupyter nbconvert --to notebook --execute notebooks/X.ipynb --output-dir <scratchpad>` and read the outputs from the copy |
| Scratch experiments | Write throwaway scripts to the session scratchpad with the Write tool (inline `python -c` and `printf` quoting kept breaking; heredocs broke again on apostrophes and `\n` in 2026-10-05). The scratchpad is per session, so nothing there survives (e.g. this session's copy of the 2025 raw data). `pip install .` (not `-e`) leaves a `build/` folder in the project: delete it |
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
- **After `resize_window`, reload before measuring**: Plotly charts keep their old width until they redraw, which once looked like a sideways scroll at 1024px. `screenshot` sometimes times out when the app window is hidden; retry, or measure with JavaScript.

## 4. Repository map

```
Dev/
├── CLAUDE.md                     rules, commands, current status, decisions, open decisions
├── config.yaml                   league_id (quoted), season, history_from (2020), season_start_dates (one per season),
│                                 sleeper_points_gaps (Sleeper's known stale totals), every metric weight and threshold
├── pyproject.toml                package + exact dependency versions (dev extra: pytest, jupyterlab)
├── requirements-ci.txt           lock file: every package GitHub Actions installs, exact versions
├── .python-version               3.14.7, read by the workflow
├── .github/workflows/weekly.yml  Tue + Thu 12:17 PM Eastern and a manual button: tests → pipeline → dashboard →
│                                 page tests → commit changed tables → publish to GitHub Pages; run summary
├── .github/workflows/rollback.yml  manual: republish the page an earlier Weekly refresh run published (input run_id)
├── docs/
│   ├── CODEBASE.md               data flow, modules, table schemas, Sleeper quirks, dependencies, changelog
│   ├── METRICS_SPEC.md           owner-approved metric definitions (code follows the spec)
│   ├── UI_GUIDE.md               design system and every dashboard decision (ladder, charts, copy)
│   ├── DATA_DICTIONARY.md        raw Sleeper fields and findings
│   ├── RUNBOOK.md                the owner's plain-language guide for a failed or doubtful weekly run
│   └── HANDOFF.md                this file
├── src/sleeper_dash/
│   ├── config.py, api.py, extract.py, transform.py, validate.py, lineup.py, metrics/ (playoff_odds.py on the branches)
│   ├── seasons.py                (past-seasons) split by season, stack, managers by owner ID, known Sleeper gaps
│   ├── pipeline.py               full refresh of every season; reports week and table changes; writes data/cache/pipeline_run.json
│   └── dashboard/
│       ├── build.py              tables → view (every number formatted once) → HTML; `python -m sleeper_dash.dashboard`
│       ├── theme.py              the one shared Plotly theme; colours as CSS tokens ("@pylon"); CDN URL
│       ├── charts.py             five chart sections as Plotly figure dicts (pure functions)
│       ├── explainer.py          "How this works" copy, numbers from config.yaml (owner-approved)
│       ├── history.py            (past-seasons) the History section: champions, all-time records, luck, high score
│       ├── bracket.py            (bracket-view) the Playoffs section: the winners bracket as of each playoff week
│       └── templates/            index.html.j2, styles.css, page.js (week selector), charts.js (drawing,
│                                 highlight, label placement, phone labels); CSS and JS are inlined into the page
├── notebooks/                    01 data check, 02 power-score sensitivity, 04 playoff odds calibration (branches); no outputs
├── tests/                        433 tests on main (467 playoff-odds, 489 past-seasons), one file per module, plus test_page (every number on the page equals
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
- **Playoff format and tiebreaker** (verified 2026-10-05 against the 2025 bracket and Sleeper's provisional 2026 bracket): 6 teams, seeds 1 and 2 on a bye, one week per round (weeks 15–17), fixed bracket with no reseeding (1 v 4/5 winner, 2 v 3/6 winner); seeded by overall wins (head-to-head plus median), then points for. Sleeper publishes a provisional `winners_bracket` from the current standings during the regular season. Details in METRICS_SPEC.md section 8.
- **Past seasons** (checked 2026-10-05; `previous_league_id` chain): 2025 `1243747994637963265`, 2024 `1111660327269216256`, 2023 `917304836490715136`, 2022 `858463130051809280`, 2021 `650074750328090624`, 2020 `603428374169325568` (the chain ends there). All 12 teams, median game, the same 6-team bracket. 2020: 13-week regular season (playoffs from week 14) and a wrong `start_week` of 4; 2020–2021 had 10 starting slots, 2022–2025 9. Champions: 2020 Coryv9, 2021 jryan7, 2022 jsmetz97, 2023 nicholascole121, 2024 jryan7, 2025 jryan7. 14 managers over the seven seasons; 10 played all of them.

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
| 2026-10-03 | Run summary on each workflow run's GitHub page: latest week, checks passed, tables written, commit, step results, published URL, or where it failed | Owner (request), Claude (layout) | weekly.yml, pipeline.py |
| 2026-10-03 | "Updated" always visible (status bar pinned to the top while scrolling); stale-data line after 8 days (`dashboard.stale_after_days`), checked on the viewer's clock, next update time read from the workflow's cron lines | Owner (request, 8 days; approved Claude's wording and pinned bar unchanged) | UI_GUIDE.md "Status bar", config.yaml |
| 2026-10-03 | After the season (Sleeper `status: complete`) the stale-data line reads "Final rankings for the XXXX season." instead of naming a next update | Owner | UI_GUIDE.md "Status bar" |
| 2026-10-03 | Stale-data and final-rankings lines appear only after 8 days without an update, in season and after it | Owner | UI_GUIDE.md "Status bar" |
| 2026-10-03 | Owner's runbook (`docs/RUNBOOK.md`); rollback workflow added and published pages kept 90 days so last week's page can be restored | Owner (request), Claude (rollback design) | RUNBOOK.md, rollback.yml, weekly.yml |
| 2026-10-03 | Phase 4 closed; Phase 5 plan written with the extras ordered by value and effort (section 9), order awaiting the owner's confirmation; CLAUDE.md rules 11–13 added (publish only through the workflows, keep the runbook true, explain a failed run before fixing) | Owner (request), Claude (order, rule wording) | CLAUDE.md, section 9 |
| 2026-10-03 | Failure email and failed-run summary tested with a throwaway branch (`test-failure-email`, deleted after) whose run failed on purpose; nothing published | Owner (approved), Claude | — |
| 2026-10-05 | Phase 5 starts with the playoff odds spec (owner asked for the interview); the order of the other extras is still to confirm | Owner | section 9 |
| 2026-10-05 | Playoff odds built on a branch (`playoff-odds`), not `main`: the first scheduled run (Tue Oct 6) should be checked on unchanged code, and the page wording needs the owner's approval before the next run publishes it | Claude (rule 11; owner to confirm the merge) | section 9 |
| 2026-10-05 | Per-seed probabilities added to playoff odds (`p_seed_1` … `p_seed_6`) and shown in a folded "Chance of each seed" table | Owner (request), Claude (display) | METRICS_SPEC.md section 8, UI_GUIDE.md |
| 2026-10-05 | A tie on wins and points for at the end of the regular season stops the run only when it affects seeding (inside or straddling the top 6); "Seeding matches Sleeper's bracket" is a stopping check like the other Sleeper reconciliations, and passes with "nothing to compare" when Sleeper has no filled-in bracket | Claude's reading, flagged to the owner | METRICS_SPEC.md section 8 |
| 2026-10-05 | History section design: champions, all-time records, last season's luckiest and unluckiest, highest weekly score; current managers with former ones folded; Sleeper usernames with the current team name; regular-season records including median games. Built with the season count under each name instead of its own column, so the table fits 360px (Claude, to flag); wording awaiting approval | Owner (1–4 agree) | UI_GUIDE.md "History" |
| 2026-10-05 | Past seasons: every season Sleeper has (2020–2025, `history_from: 2020`), re-downloaded every run (rule 1); start dates the Wednesday before kickoff; past usernames, team names and owner IDs committed publicly like 2026's; managers matched by owner ID | Owner (1–4 agree) | config.yaml, CODEBASE.md |
| 2026-10-05 | Sleeper's stale season totals in 2020, 2021 and 2023 (13 teams, one game each) listed in `config.yaml` `sleeper_points_gaps`; the points check allows exactly these (option 1a over warning-only or dropping those seasons) | Owner | config.yaml, CODEBASE.md "Known quirks" |
| 2026-10-05 | A player may fill the single-position slot he actually started in that week, as well as his positions today (changes one past team-week, 2021 week 8, and nothing in 2026) | Owner | METRICS_SPEC.md section 3 |
| 2026-10-05 | The regular season is week 1 to the week before the playoffs in every check; Sleeper's `start_week` (4 in 2020, wrongly) is ignored | Owner | validate.py |
| 2026-10-05 | Playoff bracket view: build it now (after the playoff odds merge), tested on the real 2025 bracket and the fake league, so it can show from the Dec 22 run; it appears only in playoff weeks | Owner (option 1) | section 9 |
| 2026-10-05 | Restore the strict playoff-week standings checks (regular season only), reversing the 2026-10-03 "either standard" rule, but only once 2026's week 15 data confirms Sleeper counts the regular season only, as in 2025 | Owner (agreed with Claude's recommendation) | section 7, risk 4 |
| 2026-10-05 | A one-time scheduled session, Tue Dec 22 2026 at 2:00 PM ET (`sleeper-week15-playoff-checks`, Claude desktop app, Scheduled): checks today's run, verifies the three playoff assumptions on week 15, tightens the checks if they hold, builds the page, and reports on a branch (`playoff-week15-checks`) without merging or publishing | Owner (request), Claude (task) | section 7 |
| 2026-10-05 | Playoffs section design (Claude, for the owner's review): winners bracket only (no consolation bracket); placement games (5th, 3rd) shown under their round; seeds from our seeding of the final standings; each week shows what was known by then; open slots named by seeds ("Winner of 1 v 5"); in the odds' place after the ladder; champion line in ink rather than pylon | Claude (design); owner approved the wording as drafted (1–5) and kept the champion in ink (6) | UI_GUIDE.md "Playoffs" |
| 2026-10-05 | History wording approved as drafted (subtitle, headings, column headers, luck and high-score lines), with the season count under each manager's name rather than its own column, so the table fits 360px; merge `past-seasons` right after `playoff-odds` | Owner | UI_GUIDE.md "History" |
| 2026-10-05 | Playoff odds wording approved as drafted (section subtitle, column headers, "Clinched"/"Out"/"<1%"/">99%", the "How this works" paragraph); per-seed odds in the spec, the tie reading, and the stopping bracket check confirmed; merge after the Tue Oct 6 run is checked | Owner (1 approve, 2–4 agree) | UI_GUIDE.md "Playoff odds", METRICS_SPEC.md section 8 |
| 2026-10-05 | Playoff odds definition, every recommended option accepted: normal model on scores relative to the week's league mean; team means shrunk toward the league mean with fixed `shrink_weeks` 6 (2025 calibration 6.5) and posterior uncertainty drawn once per simulated season; one pooled score SD; no recency weighting; median game decided from the same simulated scores; seeding by wins then points for, verified format only (anything else stops the run); a new check that our seeding matches Sleeper's provisional `winners_bracket`; 10,000 simulations; a seed per (season, week); outputs playoff, bye, and title odds and average final record from week 3; "Clinched"/"Out" only when a bound proves it, otherwise "<1%"/">99%" | Owner | METRICS_SPEC.md section 8 |

## 7. Open questions and assumptions to verify

**Verify at week 4 (Tuesday Oct 6, the first scheduled run):**
- **The run:** it succeeds and its bot commits "Weekly refresh: tables through week 4"; then `git pull`. Its summary should say "Latest completed week: 4 (new: the last run ended at week 3)".
- **The live page:** the Strength of schedule chart switches to two panels (remaining no longer all 0.0); luck labels and the efficiency chart still read cleanly at 390px with new values; rank-history labels read at 360px.
- **Who gets the failure emails:** `gh api repos/JonahT26/sleeper-dashboard/actions/runs/<id> --jq .actor.login` should print `JonahT26`. Scheduled-run emails go to whoever set the schedule, and the commits that did so are authored as `jonahtersol@gmail.com`, which GitHub doesn't link to any account (risk 13). Manual-run failure emails do reach the owner (tested).
- **Thursday Oct 8:** its run should report "no new completed week", and commit only if Sleeper made a stat correction.

**First run after Oct 19, 2026:** GitHub moves `ubuntu-latest` to Ubuntu 26 (risk 14). Check that run passed.

**Week 15 (first playoff week, mid-December):** the three playoff assumptions held for this league's 2025 season (risk 4), and the pipeline passes on 2025's real playoff weeks. Still confirm the first 2026 playoff run succeeded. **Scheduled:** a one-time session on Tue Dec 22, 2:00 PM ET (`sleeper-week15-playoff-checks` in the Claude desktop app's Scheduled list; it runs when the app is open, or on its next launch) verifies the assumptions on week 15 (no playoff median; roster standings regular season only; byes unpaired, consolation games paired, every team listed with a lineup) and, if they hold, restores the strict regular-season-only standings checks (owner, 2026-10-05) on the branch `playoff-week15-checks`, reporting without merging. Consolation-bracket and placement games are paired like real games, so matchup awards (Heartbreaker, Robbery, Blowout, Nail-biter) in playoff weeks can go to them: kept by the owner (2026-10-03, METRICS_SPEC.md section 7).

**Known gaps:** Sleeper's `ppts` sits 0.02–4.00 points below our optimal lineups for 7 teams (soft check only); on the 2025 season the gap reached 8.5–15.3 points for 6 teams, probably because player positions are today's (risk 10), which matters for past seasons (Phase 5); FAAB and picks traded inside trades aren't in `transactions`; player positions describe today, not past weeks (partly mitigated, risk 10); `winners_bracket` is pulled on the branches. A season with no completed week yet (next season's preseason, after `config.yaml` moves to 2027) stops the pipeline with a misleading "matchups is missing. Run `python -m sleeper_dash.extract` first" message (checked with the fake league): decide the season-rollover behaviour before then (section 7a).

**Stale-data line after the season: decided and built (owner, 2026-10-03).** Once Sleeper marks the league `status: complete` (it did for 2025), the run record's `league.season_complete` is true and the stale-data line reads "Final rankings for the 2026 season." with no "next update". Verify after week 17: the first run after Sleeper flips the status records `"season_complete": true` (the page shows the line only once the data is 8 days old, as in season). Not yet seen on a live season end: Sleeper's timing for setting `complete` is unknown, but runs continue Tue/Thu for ~60 days, so it's picked up long before the page goes stale.

**Open product questions:**
- The order of the remaining Phase 5 extras (section 9).
- Where league members see updates: bookmark only, or also a weekly league-chat post (Phase 5 item 1). The owner is posting an introduction to the league by hand (2026-10-03).
- Boom/bust weeks are explained in "How this works" but not displayed yet (owner wants them kept for a future display).

## 7a. Running the weekly job

- **Schedule:** Tuesday and Thursday 12:17 PM Eastern (`timezone: America/New_York`, so it follows daylight saving). GitHub can start scheduled runs late, sometimes by tens of minutes. The Thursday run picks up stat corrections to the week just finished; Wednesday waiver pickups belong to the week in progress, so they appear the following Tuesday.
- **The owner's guide is `docs/RUNBOOK.md`** (checking a run, failures by step with Claude Code prompts, re-running, rollback, pausing, pins). Update it whenever a workflow or a step name changes.
- **Rollback:** `.github/workflows/rollback.yml` (manual, input `run_id`) downloads the page an earlier Weekly refresh run published and deploys it; data and code untouched. Weekly refresh keeps each published page 90 days (`retention-days: 90`; the default was 1 day). Tested 2026-10-03 by restoring the then-current page: the live page came back byte-identical. The oldest restorable page is run `37136344876` (week 3).
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

1. **Off-season breakage: fixed 2026-10-03.** Season start dates live in `config.yaml` `season_start_dates`, one per season, and never come from `/state/nfl`, which is only a cross-check while it describes the league's season and gives a date. Proven offline (`test_pipeline_offline`: Sleeper in 2026, the off-season, 2027's preseason, 2027 under way, no date) and on the real league (four `/state/nfl` variants, 14 of 14 checks, all 11 tables identical to the committed CSVs). Past seasons have their own lines (on `past-seasons`): the Wednesday before the NFL's opening game, Sleeper's 2026 rule (owner, 2026-10-05).
2. **Unpinned dependencies: fixed 2026-10-03.** Exact versions in `pyproject.toml`; `requirements-ci.txt` (the lock file) pins all 23 packages Actions installs; `.python-version` pins Python 3.14.7, which the workflow reads (GitHub already offers 3.14.8). `test_dependencies` fails, locally or in Actions, if the installed packages or Python differ from the pins or the lock misses a package. A fresh environment from the lock produced all 11 tables and the page byte-identical. Update steps in `docs/CODEBASE.md` "Dependencies".
3. **GitHub switches off scheduled workflows after 60 days with no repository activity.** In season the bot's weekly commits keep it on. After the season the tables stop changing, so it will switch off (expected, harmless); re-enable it before next season (section 7a).
4. **Playoff weeks: checked on real data and decided, 2026-10-03.** This league's finished 2025 season (same settings: 12 teams, 6-team playoffs from week 15, median game) shows Sleeper's roster wins, losses, points for and against count the **regular season only** (12 of 12 teams; so no median game counts in the playoffs either); **every team is listed every playoff week** with a full lineup and points; byes have no `matchup_id`; consolation games **are** paired. The real pipeline on all 17 weeks of 2025 passed 14 of 14 checks and built the page. `test_pipeline_offline` runs an 8-team fake league through two playoff weeks in each plausible Sleeper behaviour: as in 2025 and with no consolation games, everything passes and publishes; if Sleeper's standings counted playoff games or points, "Records match Sleeper" or "Points for/against match Sleeper" stops the run; teams left out of the matchups stop it at "Every week has one row per team"; teams with an empty lineup stop it in transform. **Owner decision 2026-10-03:** the standings checks accept either counting standard in playoff weeks (regular season only, or also playoff games, a playoff median, or playoff points), as long as one standard fits every team, and name the one that matched; teams missing from the matchups or without a lineup still stop the run. Standings that count the playoffs now pass with tables byte-identical to the 2025-style case, and standings that fit no single standard still stop the run (`test_pipeline_offline`).
5. **Tests on this run's tables: fixed.** The workflow runs `pytest tests/test_page.py` again after the pipeline and dashboard, so the numbers about to be published are checked.
5a. **Windows folder swap: fixed 2026-10-03.** Extract deleted `data/raw/{season}/` and renamed the new download into place; Windows sometimes refused the rename while antivirus or indexing still held the old folder (about 1 in 14 back-to-back test runs). `extract._swap_in` now retries up to 5 times (2 s at most) and then stops with a clear message; the offline tests reuse one raw folder again and passed 6 runs in a row. Never seen in real runs; can't happen on GitHub's Linux machines.
6. **Sleeper's API is unofficial.** Shape changes surface as failed checks, without notice.
7. **Label placement is a heuristic** (`charts.js`): crowded luck charts could still overlap in some weeks. Check new weeks at 390px.
8. **The page depends on two CDNs** (Google Fonts, cdn.plot.ly). If Plotly fails to load, each chart shows its one-sentence text summary instead. Loading fonts from Google also tells Google each visitor's IP address; self-hosting the fonts would remove both.
9. **Newer CSS** (container queries, `::details-content`, `interpolate-size`): older browsers fall back to the three-line ladder on desktop and an instant (unanimated) breakdown. Nothing breaks.
10. **Player positions are today's**, so a mid-season position change alters past optimal lineups. Partly mitigated (owner, 2026-10-05): a player may also fill the single-position slot he actually started in that week, which fixed the one past team-week where the best lineup came out below the real one (2021 week 8). Sleeper's `ppts` still sits 5+ points below our optimal lineups for 4–7 teams in 2020, 2023, 2024 and 2025 (soft check; reported for the current season only).
11. **Posted numbers can change** after stat corrections (deliberate full recompute; explained in "How this works").
12. **Near-ties at the top** of the power rankings (#1 and #2 both show 57.8 through week 3).
13. **Who receives scheduled-run failure emails.** GitHub sends them to whoever created the schedule or last changed it, or last re-enabled the workflow. The workflow's commits are authored as `jonahtersol@gmail.com`, which GitHub doesn't link to any account (`author.login` is null), so it's unconfirmed that GitHub recorded JonahT26. Mitigations: the owner adds and verifies that address on the account (Settings → Emails); the stale-data line on the page catches a silent failure after 8 days. Verify on Tuesday Oct 6 (section 7).
14. **Ubuntu 26 from October 19, 2026.** `ubuntu-latest` changes underneath the workflow. Python is pinned, so the likely failures are at setup or Install; the runbook tells the owner what to do.
15. **Rollback reaches back 90 days only,** and only to pages published from 2026-10-03 12:19 PM ET (run `37136344876`) onward; earlier pages expired after a day.
16. **The stale-data line needs JavaScript and trusts the visitor's clock.** Without JavaScript it never shows, though the "Updated" time always does. A wrong device clock shows it too early or too late.
17. **When Sleeper sets `status: complete`** after the final week is unknown. The "Final rankings" wording depends on it (section 7).
18. **Past seasons add surface to the weekly job** (2026-10-05): about 240 more Sleeper calls and a minute more per run, and a failed check in any past season stops the whole run (the detail names the season; the live page stays as it was). If Sleeper edits an old season again, the known-gaps list or a check may need updating.
19. **Merging the branches will conflict on `data/processed/*.csv`** once the bot has committed week 4 to `main`. Expected and harmless: resolve by taking either side, then run the pipeline (it rewrites every table from Sleeper) and commit its output (section 9, "Merging").

## 9. Next: Phase 5 (extras)

**Done in the 2026-10-05 session** (owner's order: playoff odds spec, then build; then past seasons and History; the chat post and boom/bust display were not taken up):

| Extra | State | Where |
|---|---|---|
| Playoff odds (METRICS_SPEC.md section 8) | Built, approved, unmerged | `playoff-odds` |
| Calibration on 2025 (notebook 04) | Done: playoff Brier 0.134 (vs 0.250 everyone-50%, 0.222 top-6-now); bye odds no better than flat 2/12; more shrinkage scored better in-sample (k 20: 0.128). Revisit `shrink_weeks` after 2026's week 14 | `playoff-odds` |
| Past seasons 2020–2025 | Built and checked (17 of 17 in every season) | `past-seasons` |
| History section | Built; wording approved | `past-seasons` |
| Playoff bracket view (Playoffs section) | Built; wording approved | `bracket-view` |

**Merging** (in this order; never merge with an unchecked run or unapproved wording):
1. After the Tue Oct 6 run succeeds (and its actor is checked, section 7): `git switch main`, `git pull`, `git merge playoff-odds`. The bot's week 4 commit will conflict on `data/processed/*.csv`: take either side (`git checkout --theirs data/processed/`), run `.venv\Scripts\python.exe -m sleeper_dash.pipeline` (16 of 16 checks; week 4 odds appear), run all tests (467), commit, push. Check the page at 360, 390, 1024 and 1280px, light and dark. The Thursday Oct 8 run publishes it (or run Weekly refresh by hand).
2. Right after step 1 (History wording approved 2026-10-05): `git merge past-seasons` into `main` the same way (conflicts again only in tables; pipeline 17 of 17 in every season; 489 tests). The first GitHub run afterwards takes about 4 minutes (RUNBOOK.md says so); watch it once with `gh run watch`.
3. Right after step 2 (Playoffs wording approved 2026-10-05): `git merge bracket-view` the same way (no table changes of its own; 515 tests). Must be on `main` before the Tue Dec 22 run.
4. Update this file, `CLAUDE.md` "Current status", and the memory note after each merge.

**Playoff bracket view: built 2026-10-05** on `bracket-view` (stacked on `past-seasons`, because History was still unmerged), as the owner asked (build now). The Playoffs section (UI_GUIDE.md "Playoffs") shows Sleeper's winners bracket in playoff weeks, each week as of that week, in the odds' place after the ladder. Tested on all six finished brackets (2020–2025), a provisional bracket with no results, 2025's page week by week, and the fake `PlayoffLeague`; checked in the browser at 360, 390, 1024 and 1280px, light and dark. Before building: all 42 games of 2020–2025 have the bracket's winner outscoring its opponent that week. Wording approved as drafted (2026-10-05); merge after `past-seasons`.

**Remaining extras** (ask the owner to order them; recommendations in brackets):
- **Weekly league-chat post** (high value; see the note in section 1 before raising it).
- **Boom/bust display** (low effort; data and copy already exist).
- **Season rollover** (required before the 2027 preseason, about August 2027): what the page shows between rollover and week 1 (the build stops on a season with no completed week, section 7), then the checklist in section 7a. With past seasons in the pipeline, 2026 simply becomes a past season: move `season` and `league_id` to 2027 and add its start date; `history_from` stays.
- Smaller, any time: self-host the fonts (risk 8); the "Final rankings" line immediately after the season instead of after 8 days (one line; owner chose 8 days).

**December, already scheduled:** Tue Dec 22 2:00 PM ET, `sleeper-week15-playoff-checks` (section 7): verifies the playoff assumptions on week 15, restores the strict standings checks if they hold, and reports on branch `playoff-week15-checks` without merging. It expects the bracket view to be on `main` by then and reports if it isn't.
## 10. Commit history

Phase 1 ends at `1ad16d1`; Phase 2 ends at `38eba07 Phase 2: metrics`; Phase 3 runs from `487e76c` (season-to-date lineup efficiency) to `8966259 Phase 3: dashboard`; Phase 4 runs from `8dee0e8` (season start date in config) to `df8f4cf Phase 4: automation`; follow-ups `e8a3260` (playoff tests against 2025 behaviour), `86c1486` (either standings standard in playoff weeks), `38e081c` (workflow reconfirmed), `5cc0180` (handoff), `cbd13c7` (run summary), `6a70578` (status bar and stale-data line), `e7534e2` ("Final rankings"), `817c342` (rollback and 90-day retention), `8c9be5e` (runbook), and a second commit named "Phase 4: automation" that closes the phase (docs). From Phase 4 on, `github-actions[bot]` commits refreshed tables ("Weekly refresh: tables through week N"). Phase 5 so far: `90c3190` (playoff odds spec, on `main`); on `playoff-odds`: `15727ea` (playoff odds and winners bracket), `cccbb28` (calibration notebook), `9c3a8de` (page section), `bc995c6` (wording approved), `e600246` (December plan); on `past-seasons`: `8f51743` (seasons 2020–2025), `145f01a` (History section), `03fbd78` (handoff), `bfbdc54` (History wording approved); on `bracket-view`: the Playoffs section. Use `git log --oneline` for the full list.

## 11. First steps for the new session

1. **Before switching branches, read this file from `past-seasons`** (the local checkout is there): `git fetch`, then `git show origin/past-seasons:docs/HANDOFF.md` if you're elsewhere. `main`'s copy predates Phase 5.
2. Read `CLAUDE.md`, `docs/CODEBASE.md`, `docs/METRICS_SPEC.md` and `docs/UI_GUIDE.md` from the same branch. Skim `docs/RUNBOOK.md`: it's what the owner follows, so match its wording when talking about runs.
3. Check the weekly job: `gh run list --workflow weekly.yml --limit 5`. Any failure comes first (section 7a, CLAUDE.md rule 13). **Tue Oct 6** should commit "Weekly refresh: tables through week 4"; check its actor is JonahT26 (`gh api repos/JonahT26/sleeper-dashboard/actions/runs/<id> --jq .actor.login`, risk 13). **Thu Oct 8** should report no new week.
4. Confirm the environment on each branch you touch: `.venv\Scripts\python.exe -m pytest -q` (**433** on `main`, **467** on `playoff-odds`, **489** on `past-seasons`; a `test_dependencies` failure means the environment drifted from the pins) and `git status` (clean, in sync).
5. If the Tue Oct 6 run passed: merge `playoff-odds` (section 9, "Merging", step 1) and check the page.
6. Merge `past-seasons` (step 2): the History wording is approved.
7. Merge `bracket-view` (step 3): the Playoffs wording is approved.
