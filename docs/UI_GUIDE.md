# UI guide

How the dashboard looks, reads, and behaves. Follow this for every user-facing page and chart. If something here conflicts with a request from the owner, the owner wins; then update this file.

## The brief

- **Audience:** the 12 managers in our league. Most will open it on a phone from a group-chat link, once or twice a week.
- **Primary job:** answer "who's actually good right now, and who's just lucky?" in under ten seconds, then reward anyone who scrolls with deeper analysis.
- **Tone:** data-first and credible enough to settle arguments, with a little trash talk confined to the weekly awards.

## Design direction: "the sideline"

The look borrows from the physical game, not from SaaS dashboards: turf green, chalk white, yard-line rules, and an orange pylon as the single accent. The one bold element is the rankings ladder, whose rank numbers are set large in a condensed athletic face like jersey numbers. Everything around it stays quiet.

## Tokens

### Color

| Token | Light | Dark | Use |
|---|---|---|---|
| `--turf` | `#18392B` | `#0F1F17` | Masthead band; dark-mode page background |
| `--chalk` | `#F6F8F4` | `#E8EDE9` | Light-mode page background; dark-mode text |
| `--ink` | `#15201A` | `#E8EDE9` | Body text |
| `--muted` | `#5B6B61` | `#9DADA3` | Secondary text, captions, axis labels |
| `--hash` | `#D5DDD7` | `#2A3D33` | Rules, gridlines, row dividers |
| `--pylon` | `#E8590C` | `#FF7A2E` | The single accent: #1 rank numeral, current-week marker, highlighted team in charts |
| `--up` | `#1D6FB8` | `#5AA2E0` | Rank rising |
| `--down` | `#B42318` | `#F07060` | Rank falling |
| `--bar` | `#9AA79F` | `#5E7066` | Default bars and points for "all other teams" |

Contrast notes, checked against WCAG: ink on chalk 15.7:1, chalk on turf 11.9:1, muted on chalk 5.3:1, up 4.9:1, down 6.2:1. **Light-mode pylon is 3.4:1, so use it only for large text (24px+ bold) and fills, never for small text.**

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

A single page with a week selector. The default view is the latest completed week; all weeks' data is embedded in the page, so switching weeks needs no network call.

Section order, top to bottom:

1. **Masthead:** league name, "Week 5 power rankings", "Updated Tue Oct 6, 9:00 AM ET", and the week selector.
2. **Power rankings ladder:** the hero. No separate hero card above it; the rankings are the first thing anyone sees.
3. **Weekly awards**
4. **Luck:** actual wins vs expected wins
5. **Lineup efficiency:** actual vs optimal points
6. **Consistency:** weekly score spread per team
7. **Strength of schedule:** played and remaining
8. **Rank history:** bump chart across weeks
9. **How this works:** plain-language explanation of each metric and the power score, with every weight shown. Trust depends on this section.

Phase 5 adds a **Playoff odds** section after the ladder.

### Mobile (360–430px)

```
┌────────────────────────────────┐
│ League Name             Wk 5 ▾ │  ← turf band
│ Week 5 power rankings          │
│ Updated Tue Oct 6, 9:00 AM ET  │
├────────────────────────────────┤
│  1  Team Name         ▲2       │
│     8–2, all-play 41–14        │
│     ████████████████░░  118.4  │
├────────────────────────────────┤
│  2  Team Name         ▼1       │
│     ...                        │
└────────────────────────────────┘
  Weekly awards (2-column tiles)
  Charts stacked, full width, 320px tall
```

### Desktop (1024px+)

```
┌──────────────────────────────────────────────────────────────┐
│ League Name   Week 5 power rankings            Week 5 ▾       │
├──────────────────────────────────┬───────────────────────────┤
│ Rankings ladder (12 rows)         │ Weekly awards (stacked)   │
│                                   │                           │
├──────────────────────────────────┴───────────────────────────┤
│ Luck chart                     │ Efficiency chart             │
├────────────────────────────────┼──────────────────────────────┤
│ Consistency chart              │ Schedule chart               │
├────────────────────────────────┴──────────────────────────────┤
│ Rank history (full width)                                      │
└────────────────────────────────────────────────────────────────┘
```

Max content width 1200px, left-aligned text throughout. Numbers right-aligned in tables.

## Components

### Ladder row

- Rank numeral: Barlow Condensed 700, 48px, `--ink`. The #1 numeral alone uses `--pylon`.
- Team name (600 weight) with the manager's display name below it in `--muted`.
- Movement: `▲2` in `--up`, `▼1` in `--down`, `–` in `--muted` for no change. Always arrow plus number; never color alone.
- Record and all-play record on one line, separated by a comma.
- Power score as a thin horizontal bar (`--bar`, with the #1 team in `--pylon`) plus the value.
- Tapping a row expands it to show each power score component's contribution as a small stacked bar, so anyone can see why a team ranks where it does. This is the one place an expand animation is used.
- Built as a semantic `<table>` or `<ol>` so screen readers announce ranks correctly.

### Award tile

Award name, team name, the number, and a one-line caption, e.g. "Left 38.4 points on the bench." Captions are where personality is allowed. Keep them factual and specific; the number does the joking.

### Week selector

A native `<select>` styled with tokens. Keyboard-accessible, labeled "Week".

## Charts

All charts use Plotly with one shared theme defined in `dashboard/theme.py`. Never style charts one by one.

- **Highlight, don't rainbow.** Twelve team colors are unreadable. Draw all teams in `--bar` and highlight one team (the one being discussed, or the one the viewer taps) in `--pylon`.
- **Direct labels instead of legends** wherever possible.
- **Titles state what the chart shows; a subtitle says how to read it.** Example: title "Luck", subtitle "Above the line: more wins than your scores earned."
- Axis titles include units ("Points per week"). Bar charts start at zero.
- Gridlines in `--hash`, thin, horizontal only. No chart borders or background fills.
- Tooltips show team name and the formatted value only.
- Hide the Plotly mode bar (`displayModeBar: false`) and make charts responsive.
- Load Plotly from its CDN rather than embedding it, to keep the page small.

Specific charts:

| Section | Chart | Notes |
|---|---|---|
| Luck | Scatter: expected wins (x) vs actual wins (y) | 45° reference line; label every point with team name |
| Efficiency | Dot plot: actual and optimal points per team, connected by a line | Sorted by efficiency |
| Consistency | Strip or box plot of weekly scores per team | League median as a reference line |
| Schedule | Diverging bar: opponents' average points vs league average | Played and remaining as two panels |
| Rank history | Bump chart, rank by week | All lines grey; tap a team to highlight |

## Numbers and copy

- Points: 1 decimal (`118.4`). Percentages: whole numbers (`87%`). Expected wins: 1 decimal.
- Records use an en dash: `8–2`. Show ties only if the league has had one: `8–1–1`. The record is the overall one, head-to-head plus median games, matching Sleeper's standings (owner decision, see `METRICS_SPEC.md` section 2).
- Dates: "Tue Oct 6, 9:00 AM ET".
- Sentence case everywhere. No all-caps labels or tracked-out eyebrow text above headings.
- Name things by what managers understand ("Points left on the bench"), not by how the code works ("bench_points_lost").
- Empty or missing data says what happened and when it'll resolve: "Week 6 results post Tuesday morning."

## Motion

One deliberate moment: on first load, the ladder's power-score bars grow in once. Everything else is static unless the viewer acts (expanding a row, switching weeks). Respect `prefers-reduced-motion` by disabling the grow-in.

## Quality floor

- Works from 360px wide upward; nothing scrolls sideways except wide tables inside their own container.
- Visible keyboard focus on every interactive element.
- WCAG AA contrast for all text.
- Meaning never carried by color alone.
- Page weight under 1 MB excluding the Plotly CDN script.

## Avoid

- A grid of identical rounded cards with soft shadows.
- A big-number "hero stat" card above the rankings.
- Rainbow team colors and 12-item legends.
- All-caps labels, decorative numbering, and meta strings joined with dots.
- Gradients, glassmorphism, and decorative animation.
