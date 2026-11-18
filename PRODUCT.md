# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The 12 managers of one Sleeper redraft fantasy football league. Most open the page on a phone from a group-chat link, once or twice a week, usually right after the Tuesday update. Their job: find out who is actually good right now and who is just lucky, in under ten seconds, then dig into the deeper analysis if they care to.

The page is public and indexable, but outsiders are not a target audience.

## Product Purpose

A static weekly power-rankings and analytics page for the league. A scheduled job pulls league data from the Sleeper API, computes metrics in Python, validates them, and publishes the page to GitHub Pages every Tuesday and Thursday.

Success means the managers bookmark it, check it each week, and use its numbers to settle arguments in the group chat.

## Positioning

Luck versus skill, settled. Sleeper's app shows records and points. This page separates skill from luck: all-play expected wins, optimal lineups, consistency, strength of schedule, and a transparent power score whose every component is shown. Every definition was approved by the owner (`docs/METRICS_SPEC.md`), and every number passes reconciliation checks before it is published. Credibility is the product.

## Operating Context

- Readers arrive from the weekly GroupMe post (top 3, biggest riser and faller, two awards, the link) or from a bookmark.
- The first look happens on a phone in the first hour after an update. Desktop is secondary.
- One page with a week selector. Every completed week is embedded, so switching weeks needs no network call.
- The latest week is written into the HTML at build time, so it reads without JavaScript and in link previews.
- The page publishes only through GitHub Actions (`weekly.yml`, `rollback.yml`), never by hand. A failed run publishes nothing and leaves the last good page live.

## Capabilities and Constraints

- Sections: power rankings ladder (the hero, with a tap-to-expand breakdown), playoff odds (from week 3) or the playoff bracket in playoff weeks, weekly awards, five charts (luck, lineup efficiency, consistency, strength of schedule, rank history), Roster moves (pickups, FAAB, trades), History (every finished season since 2020), and "How this works".
- Stack: Python package (`src/sleeper_dash/`), Jinja2 template, Plotly charts, GSAP and Lenis motion bundled in `site/js/`, Pillow link-preview image, all pinned. Static output in `site/`.
- Network: no calls except Google Fonts and the Plotly CDN. Page budget: 1 MB compressed.
- League settings (scoring, roster slots, playoff start, median game) and the league name come from the Sleeper API at runtime and are never hardcoded.
- Sections whose metric isn't available yet are hidden, not shown empty.
- Terminology follows `docs/METRICS_SPEC.md`: "Power score", "Head-to-head wins", luck from all-play expected wins. The displayed record includes median games.

## Brand Commitments

- Voice: data-first and credible enough to settle arguments, with a little trash talk confined to the weekly awards.
- Usernames appear on the ladder and in History.
- Any wording change on the page, including "How this works", needs the owner's approval before it reaches `main`.
- The design system lives in `docs/UI_GUIDE.md`, and owner decisions in it are binding.

## Evidence on Hand

- Real league data: 18 processed tables in `data/processed/`, covering every season from 2020 to 2026.
- History: champions (including the 2022 title override by league ruling), all-time records, and the highest weekly scores.
- Owner-approved copy: "How this works", the stale-data line, and the chat-post template.
- No testimonials, outside endorsements, or usage analytics exist. Don't invent them.

## Product Principles

1. Rankings first. The answer to "who's good, who's lucky" is the first thing on screen, with no hero card in front of it.
2. Show the working. Every score can be broken down into its parts, so the numbers settle arguments instead of starting them.
3. Never publish a wrong number. Validation stops a run before anything goes live.
4. Phone first, glanceable in seconds, rewarding for anyone who scrolls.
5. Personality lives in the awards. Everything else stays sober.

## Accessibility & Inclusion

WCAG 2.2 AA. Contrast is checked for every token pairing, the light-mode orange accent is limited to large text and fills, and all motion is off when reduced motion is requested.
