# UI guide

How the dashboard looks, reads, and behaves. Follow this for every user-facing page and chart. If something here conflicts with a request from the owner, the owner wins; then update this file.

## The brief

- **Audience:** the 12 managers in our league. Most will open it on a phone from a group-chat link, once or twice a week.
- **Primary job:** answer "who's actually good right now, and who's just lucky?" in under ten seconds, then reward anyone who scrolls with deeper analysis.
- **Tone:** data-first and credible enough to settle arguments, with a little trash talk confined to the weekly awards.
- **Mobile first** (owner, 2026-10-02): design and check every component at phone width (390px) first, then adapt it for desktop.

## Design direction: "the sideline"

The look borrows from the physical game, not from SaaS dashboards: turf green, chalk white, yard-line rules, and an orange pylon as the single accent. The one bold element is the rankings ladder, whose rank numbers are set large in a condensed athletic face like jersey numbers. Everything around it stays quiet.

## Tokens

### Color

| Token | Light | Dark | Use |
|---|---|---|---|
| `--turf` | `#18392B` | `#0F1F17` | Dark-mode page background (and the turf green in light mode) |
| `--masthead` | `#18392B` | `#18392B` | Masthead band. The same in both modes, so in dark mode it stands out from the `#0F1F17` page (1.35:1 step; chalk text 10.7:1, muted text 5.4:1). Approved by the owner 2026-10-02 |
| `--chalk` | `#F6F8F4` | `#E8EDE9` | Light-mode page background; dark-mode text |
| `--ink` | `#15201A` | `#E8EDE9` | Body text |
| `--muted` | `#5B6B61` | `#9DADA3` | Secondary text, captions, axis labels |
| `--hash` | `#D5DDD7` | `#2A3D33` | Rules, gridlines, row dividers |
| `--pylon` | `#E8590C` | `#FF7A2E` | The single accent: #1 rank numeral, current-week marker, highlighted team in charts |
| `--up` | `#1D6FB8` | `#5AA2E0` | Rank rising |
| `--down` | `#B42318` | `#F07060` | Rank falling |
| `--bar` | `#9AA79F` | `#5E7066` | Default bars and points for "all other teams" |

Contrast notes, checked against WCAG: ink on chalk 15.7:1, chalk on turf 11.8:1, muted on chalk 5.3:1, up 4.9:1, down 6.2:1. **Light-mode pylon is 3.4:1, so use it only for large text (24px+ bold) and fills, never for small text.**

Define colors as CSS custom properties on `:root`, with a `@media (prefers-color-scheme: dark)` override.

### Type

- **Display and numerals:** Barlow Condensed, weights 600 and 700. Used for rank numerals, section headings, and big stat values.
- **Body and tables:** Barlow, weights 400 and 600.
- Load both from Google Fonts. Fallback stack: `"Arial Narrow", "Roboto Condensed", system-ui, sans-serif` for display; `system-ui, -apple-system, "Segoe UI", sans-serif` for body.
- Always set `font-variant-numeric: tabular-nums` on numbers so columns align.

Scale, in px: 13 (captions), 15 (body, mobile), 16 (body, desktop), 20 (subheads), 28 (section heads), 48 (ladder rank numerals). Body line-height 1.5; headings 1.15. Keep line length under 75 characters.

### Space and shape

- 4px base unit; use 8, 12, 16, 24, 40, and 64 for spacing.
- Border radius: 6px on the ladder rows and award tiles, 0 on charts and tables. Not everything gets the same radius.
- No drop shadows. Separation comes from `--hash` rules and spacing.

## Layout

A single page with a week selector. The default view is the latest completed week; all weeks' data is embedded in the page, so switching weeks needs no network call. The latest week is written into the HTML when the page is built, so it shows without JavaScript and in link previews; JavaScript only redraws the page when the viewer switches weeks (owner, 2026-10-02).

Section order, top to bottom:

1. **Masthead:** league name, "Week 5 power rankings", and the week selector, then the **status bar**: "Updated Tue Oct 6, 9:00 AM ET", pinned to the top of the screen while scrolling, and the stale-data line when it applies (Components, "Status bar"). "Updated" is the time the pipeline ran, which the pipeline records; never a file date.
2. **Power rankings ladder:** the hero. No separate hero card above it; the rankings are the first thing anyone sees.
3. **Playoff odds** (Phase 5): from `metrics.playoff_odds.min_weeks` (week 3) to the last regular-season week (Components, "Playoff odds")
4. **Weekly awards**
5. **Luck:** actual wins vs expected wins
6. **Lineup efficiency:** actual vs optimal points
7. **Consistency:** weekly score spread per team
8. **Strength of schedule:** played and remaining
9. **Rank history:** bump chart across weeks
10. **How this works:** plain-language explanation of each metric and the power score, with every weight shown. Trust depends on this section. **The owner reviews this copy before it is published** (decision 2026-10-02). Approved with no edits on 2026-10-02; the text lives in `dashboard/explainer.py` with every number filled in from `config.yaml`, so any wording change needs the owner's approval again. One section for the whole page (not per week), after the charts, in a reading column under 75 characters.


### Mobile (360–430px)

```
┌────────────────────────────────┐
│ League Name           Week 5 ▾ │  ← masthead band
│ Week 5 power rankings          │
│ Updated Tue Oct 6, 9:00 AM ET  │  ← status bar, pinned to the top
├────────────────────────────────┤     while scrolling
│  1  Team Name              ▲2  │
│     user   8–2, all-play 41–14 │
│     ───────┼████──────   57.8  │
├────────────────────────────────┤
│  2  Team Name              ▼1  │
│     ...                        │
└────────────────────────────────┘
  Weekly awards (2-column tiles)
  Charts stacked, full width; height to suit the chart (luck is square;
  one-row-per-team charts about 30px a row)
```

### Desktop (1024px+)

```
┌──────────────────────────────────────────────────────────────┐
│ League Name   Week 5 power rankings            Week 5 ▾       │
│ Updated Tue Oct 6, 9:00 AM ET          (status bar, pinned)   │
├──────────────────────────────────┬───────────────────────────┤
│ Rankings ladder (12 rows)         │ Weekly awards (stacked)   │
│                                   │                           │
│ Playoff odds (table)              │                           │
├──────────────────────────────────┴───────────────────────────┤
│ Luck chart                     │ Efficiency chart             │
├────────────────────────────────┼──────────────────────────────┤
│ Consistency chart              │ Schedule chart               │
├────────────────────────────────┴──────────────────────────────┤
│ Rank history (full width)                                      │
└────────────────────────────────────────────────────────────────┘
```

Max content width 1200px, centred on wider screens (owner, 2026-10-02); left-aligned text throughout. Reading text ("How this works", chart subtitles) is held to about 72 characters a line (`31em`). Numbers right-aligned in tables.

## Components

### Ladder row

Settled in the prototype review with the owner, 2026-10-02.

- Rank numeral: Barlow Condensed 700, 48px, `--ink`, in a 52px column so two-digit ranks fit. The #1 numeral alone uses `--pylon`.
- Phone layout, three lines (about 85px a row, so 7 teams fit on the first screen): team name with movement on the right; the manager's display name (Sleeper username, `--muted`, cut short with an ellipsis if needed) with the record on the right; the power score bar with its value. When the ladder is at least 760px wide, everything goes on one row: rank, name over username, record, bar and value, movement. The switch depends on the ladder's own width, not the screen's: on a 1024px screen the awards sit beside the ladder, which is then about 580px wide and keeps the three-line layout (design review 2026-10-02). Owner confirmed 2026-10-02: usernames stay on the public page.
- Movement (16px, the team name's size): `▲2` in `--up`, `▼1` in `--down`, `–` in `--muted` for no change. Always arrow plus number; never color alone.
- Record and all-play record on one line, separated by a comma. The record is the overall one (head-to-head plus median games).
- **Power score bar measured from the league average** (owner decision 2026-10-02, replacing a 0–100 bar on which every team looked about half full): a thin bar running right (above average) or left (below average) from a centre line at 50, plus the value to 1 decimal place. `--bar`, with the #1 team in `--pylon`. One fixed axis for every week of the season: the largest gap from 50 in any week so far, rounded up to 5, 10, 15, 20, 25, 30, 40 or 50 points (±15 through week 3). A one-line key above the ladder reads "League average: 50" (owner wording, 2026-10-02). Two teams can show the same value (e.g. both 57.8); the order still follows the unrounded score, and no tie marker is shown (owner decision 2026-10-02).
- **Tapping a row expands its breakdown** (the one place an expand animation is used), a small table so anyone can see why a team ranks where it does:

  | Component (weight) | Score | vs average |
  |---|---|---|
  | Season scoring (35%), "141.9 points a week" | 20.1 | small bar from zero, then +2.6 |
  | Recent form (25%), "141.9 points a week, last 3 weeks" | 14.3 | +1.8 |
  | Roster strength (20%), "156.5 points a week with the best lineup" | 11.6 | +1.6 |
  | Head-to-head wins (20%), "Won 1 of 3" | 9.3 | −0.7 |
  | **Power score** | **55.3** | **+5.3** |

  Column order is fixed: Score comes before vs average (owner decision 2026-10-02).

  - "Score" is each component's contribution (weight × component score); the four add up to the power score. The owner keeps it as the transparent part of the scoring (decision 2026-10-02).
  - "vs average" is the contribution minus an average team's (50 × weight), with a sign, plus a small bar running left or right from zero. All components and teams share one fixed axis for the season (rounded up to 1, 2, 3, 4, 5, 6, 8, 10, 12, 15 or 20; ±6 through week 3), so bars compare across rows. The four add up to the power score minus 50. These replace the stacked bar first specified, whose segments were dominated by the weights and looked the same for every team (owner decision 2026-10-02).
  - The results component is named **Head-to-head wins**, and its detail line gives the head-to-head record ("Won 1 of 3"), because the ladder shows the overall record and a bare win percentage would contradict it (owner decision 2026-10-02).
- Built as a semantic `<ol>` (with `role="list"`) so screen readers announce ranks correctly. Each row is a native `<details>`/`<summary>`, so it is keyboard-operable and announces whether it is open; the movement arrows have text equivalents ("up 2", "no change").

### Award tile

Award name, team name, the number, and a one-line caption, e.g. "Left 38.4 points on the bench." Captions are where personality is allowed. Keep them factual and specific; the number does the joking. Nine awards are enabled (2026-10-02), so in the 2-column mobile grid the last tile sits alone on its row. Beside the ladder on desktop, each tile puts the award name and the number on one line, so the awards column is about as tall as the ladder.

### Status bar

Added 2026-10-03 (owner request: stale data must be impossible to mistake for fresh). The pinned bar and the wording below were approved by the owner as drafted, 2026-10-03; wording changes need approval again.

- The masthead's last line, in the masthead colour, separate from the masthead so it can stay pinned to the top of the screen (`position: sticky`) on every screen width. It always shows "Updated Tue Oct 6, 9:00 AM ET" (13px, `--on-mast-muted`). On a fresh page it takes the same space the "Updated" line took inside the masthead (7 teams still fit on a 390px screen).
- **Stale-data line:** when the last update is more than `dashboard.stale_after_days` (config.yaml, 8) days old on the viewer's own clock, a second line appears below it, 15px semibold `--on-mast` (10.7:1), held to the reading width:

  > The latest rankings are from week 3. Next update due Tue Oct 6, 12:17 PM ET.

  "Latest" because the viewer may be looking at an earlier week. The week is the latest completed week in the page. The due time is the first scheduled run still ahead of the viewer, from the cron lines in `.github/workflows/weekly.yml` (the page lists the scheduled runs in the 120 days after the update); the date and time never break across lines. If none of those is still ahead (a page months old), only the first sentence shows.
- **After the season** (Sleeper marks the league complete), the same line reads instead (owner, 2026-10-03):

  > Final rankings for the 2026 season.

  with no next update, since none will bring new data.
- Checked in the browser, not at build time, because a page that has stopped updating can't rebuild itself. Without JavaScript the line never shows; the "Updated" time always does.
- No pylon and no icon: the plain sentence in the masthead's brightest text is the warning (pylon stays the single accent for #1 and highlights).

### Playoff odds

Added 2026-10-05 (Phase 5; definitions in `METRICS_SPEC.md` section 8). **The section's wording and its "How this works" paragraph are drafts awaiting the owner's approval**; the layout follows this guide.

- A section after the ladder, titled "Playoff odds", with a one-line subtitle: "Chances from 10,000 simulations of the rest of the season. The top 6 make the playoffs, and the top 2 get a first-round bye." After the last regular-season week: "The regular season is over and the top 6 are in; the top 2 have a first-round bye. Title odds come from 10,000 simulations of the playoffs." Numbers come from `config.yaml` and the league settings.
- **A table, not a chart**, one row per team, the most likely playoff team first (playoff odds, then bye odds, then average final wins). Columns: Team, Projected record (average final record to 1 decimal, e.g. "16.2–11.8", head-to-head plus median games), Playoffs (bold, with a thin `--bar` bar from 0 to 100% under it on a `--hash` track), Bye, Title. Team names wrap; numbers right-aligned and tabular.
- **Percentages are whole numbers.** "Clinched" and "Out" replace the playoff number only when a bound proves them (never because the simulation happened to say 100% or 0%). Otherwise a value that rounds to 0% shows as "<1%" and one that rounds to 100% as ">99%". Values known for certain show plainly: bye and seed odds after the last regular-season week, and 0% for every column of a team that is Out.
- **"Chance of each seed"** sits below in a closed `<details>`: the same rows with seeds 1–6, each cell its percentage on a `--bar` tint whose strength follows the probability (at most 60%), so the numbers carry the meaning and the tint only helps scanning. It opens instantly: the ladder's breakdown stays the page's one expand animation.
- **Layout:** on phones it follows the ladder at full width; both tables fit at 360px (checked 2026-10-05), and a table scrolls sideways inside its own box if it ever has to. From 1024px it sits under the ladder in the left column while the awards column spans both.
- **Hidden** before `min_weeks` and in playoff weeks (the table ends with the regular season; the playoff bracket is a separate Phase 5 extra).

### Week selector

A native `<select>` styled with tokens. Keyboard-accessible, labeled "Week".

## Charts

All charts use Plotly with one shared theme defined in `dashboard/theme.py`. Never style charts one by one.

- **Highlight, don't rainbow.** Twelve team colors are unreadable. Draw all teams in `--bar` and highlight one team (the one being discussed, or the one the viewer taps) in `--pylon`.
- **Direct labels instead of legends** wherever possible.
- **Titles state what the chart shows; a subtitle says how to read it.** Example: title "Luck", subtitle "Above the line: more wins than your scores earned."
- Axis titles include units ("Points per week"). Bar charts start at zero. Bars that show a gap from the league average (the ladder and its breakdown) start at the average, which is their zero, and say so.
- Gridlines in `--hash`, thin, horizontal only. No chart borders or background fills.
- Tooltips show the team name and that point's formatted values (e.g. "3 wins, 2.8 expected, luck +0.2"), nothing else.
- Hide the Plotly mode bar (`displayModeBar: false`) and make charts responsive.
- Load Plotly from its CDN rather than embedding it, to keep the page small (`cdn.plot.ly`, the basic bundle, version matched to the Python `plotly` package).
- **Highlighted team** (Claude, 2026-10-02): each week's #1 by default, matching the pylon #1 on the ladder. Tapping a chart point, a team name in any chart, or opening a ladder row moves the highlight to that team in every chart, and it stays through week changes. A highlighted label is bold `--ink`, never pylon text (pylon fails contrast for small text in light mode).
- Every chart section has a text summary ("Luckiest: …, unluckiest: …") for screen readers, which also shows if Plotly can't load.
- Chart colours are design tokens (`@pylon`, `@bar`, …) filled in from the CSS custom properties, so charts follow light and dark mode.

Specific charts:

| Section | Chart | Notes |
|---|---|---|
| Luck | Scatter: expected wins (x) vs actual wins (y) | 45° reference line; label every point with team name. Equal scales on a square plot (0 to the most wins so far + 0.5). Labels are placed by the page so they don't collide, on a page-coloured background so the 45° line passes behind them, with a leader line when a label has to sit away from its point. Regular season only; from the playoffs on, the subtitle says so |
| Efficiency | Dot plot: actual and optimal points per team, connected by a line | Points per week through the selected week; solid dot = scored, open dot = best possible. Sorted by season-to-date efficiency (best on top), team name above each row and the efficiency % at its right. Taller than 320px (30px a row) so 12 rows stay readable on a phone |
| Consistency | Strip or box plot of weekly scores per team | League median as a reference line. Built as a strip plot: one row per team, each week's score a dot, a shaded bar from floor to ceiling, steadiest (lowest volatility) on top, ± volatility at the right; dotted line at the median of every score so far. Appears from `metrics.consistency.min_weeks` |
| Schedule | Diverging bar: opponents' average points vs league average | Played and remaining as two panels, side by side with one row per team (toughest played schedule on top), whole-number ticks. When every remaining value is 0.0 (this league's round-robin makes that happen in week 3), the remaining panel is replaced by one line in the subtitle; after the regular season only the played panel shows. Appears from `metrics.schedule.min_weeks` |
| Rank history | Bump chart, rank by week | All lines grey; tap a team to highlight. Full width; rank 1 at the top; team names at the end of each line (on phones, names longer than 14 characters are cut to 13 plus "…", owner 2026-10-02; the full name is in the tooltip); the highlighted line is drawn on top. Appears from week 2 |

## Numbers and copy

- Points: 1 decimal (`118.4`). Percentages: whole numbers (`87%`). Expected wins: 1 decimal.
- Records use an en dash: `8–2`. Show ties only if the league has had one: `8–1–1`. The record is the overall one, head-to-head plus median games, matching Sleeper's standings (owner decision, see `METRICS_SPEC.md` section 2).
- Dates: "Tue Oct 6, 9:00 AM ET".
- Sentence case everywhere. No all-caps labels or tracked-out eyebrow text above headings.
- Name things by what managers understand ("Points left on the bench"), not by how the code works ("bench_points_lost").
- Empty or missing data says what happened and when it'll resolve: "Week 6 results post Tuesday morning."
- **Sections whose metric isn't available yet are hidden entirely**, with no placeholder (owner decision 2026-10-02). With the current settings, Consistency and Strength of schedule appear from week 3 (`metrics.consistency.min_weeks`, `metrics.schedule.min_weeks`).

## Motion

One deliberate moment: on first load, the ladder's power-score bars grow out from the average line once. Everything else is static unless the viewer acts (expanding a row, switching weeks). Respect `prefers-reduced-motion` by disabling the grow-in.

## Quality floor

- Works from 360px wide upward; nothing scrolls sideways except wide tables inside their own container.
- Visible keyboard focus on every interactive element.
- WCAG AA contrast for all text.
- Meaning never carried by color alone.
- Page weight under 1 MB excluding the Plotly CDN script, counted as compressed bytes, i.e. what a visitor downloads (owner decision 2026-10-02; a full season is ~115 KB compressed, ~1.2 MB raw).

## Avoid

- A grid of identical rounded cards with soft shadows.
- A big-number "hero stat" card above the rankings.
- Rainbow team colors and 12-item legends.
- All-caps labels, decorative numbering, and meta strings joined with dots.
- Gradients, glassmorphism, and decorative animation.
