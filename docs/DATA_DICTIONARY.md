# Data dictionary: raw Sleeper responses

Field-level notes on every raw file in `data/raw/{season}/`, written from the first real pull (season 2026, weeks 1–3, profiled 2026-10-02 during NFL week 4). Transform code should rely on what is confirmed here, not on assumptions about the API.

- **% missing** counts a field as missing when the key is absent **or** its value is `null`, across all records of that file type.
- **Examples are anonymised.** Manager usernames, team names, user IDs, avatars, and nicknames are replaced with placeholders like `<user_id 2>` because this repo is public. NFL player names and IDs are left as-is.
- Meanings marked *(likely)* are inferred from the data rather than documented by Sleeper.

## Key findings

| # | Topic | What the data shows | What it means for us |
|---|---|---|---|
| 1 | `"0"` in `starters` | **None** in all 36 team-weeks so far. | Transform must still handle it (`is_empty_slot`), but no saved fixture contains one, so tests need a hand-made case. |
| 2 | `null` `matchup_id` | **None** in weeks 1–3. Every week has `matchup_id` 1–6, each exactly twice. | Expected only in playoff weeks (15+) for teams with no game. Re-check when week 15 is pulled. |
| 3 | Missing `owner_id` | **None.** All 12 rosters have an owner who appears in `users.json`; no user owns zero rosters. `co_owners` is `null` for all. | No orphaned teams to handle now; keep the null-safe join anyway. |
| 4 | `players` vs `players_points` | **Identical key sets** in all 36 team-weeks. `starters_points[i]` always equals `players_points[starters[i]]`, and `points` equals `sum(starters_points)` exactly. `custom_points` is always `null`. | Points are internally consistent. `players_points` is the single source for bench points. |
| 5 | `fpts` + `fpts_decimal` | **Season total = `fpts + fpts_decimal / 100`.** Matches the sum of weekly matchup `points` to the cent for all 12 teams. Same for `fpts_against`. `ppts` (+ `ppts_decimal`) is ≥ `fpts` for every team. | Use this as a reconciliation check. `ppts` is *(likely)* Sleeper's "max possible points", but our optimal lineups exceed it by 0.02–4.00 for 7 teams, so it is a soft check only (see Decisions made). |
| 6 | Injured reserve in matchups | **IR players are included** in matchup `players` and `players_points`: 27 team-weeks have 17 players (10 starters + 6 bench + 1 IR), and 9 have 16 (IR slot empty). **Nothing in a matchup marks which player was on IR.** `rosters.json` `reserve` is **today's** snapshot only: 5 of today's IR players were *starters* in earlier weeks. | We cannot tell from the API who was on IR in a past week. Decision: IR players count as bench (see Decisions made). |
| 7 | Team-defense IDs | The `DEF` slot always holds a team abbreviation (`"KC"`, `"PHI"`, …) instead of a number: 36 of 36 team-weeks, 17 distinct teams. They also appear in `adds`/`drops` and draft picks. | `player_id` must stay a string; never cast it to an integer. Join defenses to `players` by abbreviation. |
| 8 | Median game | Sleeper's `wins`/`losses` **include median games**: every team has W + L = 6 after 3 weeks. Roster `metadata.record` is two letters per week (head-to-head, then median), reproduced exactly for all 12 teams. The comparison is against the **median**, not the mean: a mean rule would score 2 team-weeks differently in week 2. | Reconciliation must compare our H2H + median results to Sleeper's totals. No team has scored exactly the median yet; ties are deliberately not handled (see Decisions made). |
| 9 | Transactions | 68 of 182 are `failed` (lost waiver claims). `leg` always equals the file's week. Week 1 contains everything from the draft (Aug 25) to Sep 15. Weeks turn over early Wednesday ET, when waivers run. | Keep `complete` only. Split preseason moves out of week 1 (see Decisions made). |
| 10 | Roster snapshot fields | `rosters.json` `starters`, `players`, `reserve`, and `metadata.record`/`streak` describe **now**, not any past week. | Weekly lineups come from matchups only. Rosters supply ownership and season totals. |
| 11 | Types | IDs are strings even when numeric. `roster_id` is an int. `season` is a **string** (`"2026"`) in the API but an int in `config.yaml`. Times are epoch milliseconds. League settings use 0/1 ints for yes/no; user metadata uses `"on"`/`"off"` strings. Some numbers arrive as strings (pick `metadata.years_exp`, `number`). | Cast deliberately in transform. Compare seasons as strings or convert explicitly. |
| 12 | Privacy | `users.json` holds notification preferences and custom mascot messages. `league.json` holds the last league-chat author and time; so far that author is Sleeper's system bot (`"sys"`) and the message text is `null`. | Raw files are kept off GitHub (owner decision, 2026-10-02). |

### Decisions made (2026-10-02), to carry into `METRICS_SPEC.md`

1. **Injured reserve: every non-starter in a week's matchup `players` counts as bench, IR included.** The owner delegated this call. Reasons:
   - Past-week IR status cannot be recovered from the API, so any exclusion rule would be a guess.
   - IR-eligible players are listed Out, so they almost always score 0 and rarely affect optimal lineups or bench points.
   - Checked against Sleeper's `ppts` (season max possible points) using optimal lineups over weeks 1–3:
     - **Including IR** matches `ppts` exactly for 5 teams and never comes out below it.
     - **Excluding today's `reserve` players** comes out *below* Sleeper for teams 8 and 10, so Sleeper itself counts them.
     - The other 7 teams sit 0.02–4.00 points above `ppts`. That includes team 12, which never had an IR player, and no single bench player explains any gap. So the gaps come from something other than IR, possibly stat-correction timing or eligibility rules. Investigate when building `lineup.py`.
   - Consequence: treat `ppts` as a **soft check**. Our optimal points should be ≥ `ppts`; a gap is a warning, not a failure.
2. **Median ties: not handled.** A team scoring exactly the median is very unlikely, so no tie rule is coded for now. If one happens, the validation step should stop the run so it gets noticed and decided then.
3. **Preseason transactions are kept separate from week 1.** Rule: a week 1 (`leg` 1) transaction is *preseason* if `created` is before `/state/nfl` `season_start_date` (2026-09-09 00:00 ET). This matches how Sleeper splits later weeks, where each new week's transactions begin with Wednesday's waiver run. In 2026: 19 preseason moves, then 23 completed and 16 failed in week 1 proper.

## Files

### `state.json` (from `/state/nfl`), 1 record

```json
{
  "week": 4,
  "leg": 4,
  "season": "2026",
  "season_type": "regular",
  "league_season": "2026",
  "previous_season": "2025",
  "season_start_date": "2026-09-09",
  "display_week": 4,
  "league_create_season": "2026",
  "season_has_scores": true
}
```

| Field | Type | Example | % missing | Meaning |
|---|---|---|---|---|
| week | int | `4` | 0 | Current NFL week, **in progress** during the regular season |
| leg | int | `4` | 0 | Same as `week` here; Sleeper's word for a scoring period |
| season | str | `"2026"` | 0 | Current NFL season |
| season_type | str | `"regular"` | 0 | `pre`, `regular`, `post`, or `off` |
| league_season | str | `"2026"` | 0 | Season new leagues are created for *(likely)* |
| previous_season | str | `"2025"` | 0 | Prior season |
| season_start_date | str | `"2026-09-09"` | 0 | Regular-season start date |
| display_week | int | `4` | 0 | Week the Sleeper app shows |
| league_create_season | str | `"2026"` | 0 | Season assigned to newly created leagues *(likely)* |
| season_has_scores | bool | `true` | 0 | Whether games have produced scores this season |

### `league.json` (from `/league/{league_id}`), 1 record

```json
{
  "league_id": "1369887235935059968",
  "name": "12 Supersexy Superflexy Hoekies",
  "season": "2026",
  "status": "in_season",
  "total_rosters": 12,
  "previous_league_id": "1243747994637963265",
  "draft_id": "1369887235939274752",
  "roster_positions": ["QB", "RB", "RB", "WR", "… 12 more"],
  "settings": {"num_teams": 12, "playoff_week_start": 15, "league_average_match": 1, "last_scored_leg": 3, "…": "45 more keys"},
  "scoring_settings": {"rec": 0.5, "bonus_rec_te": 0.5, "pass_td": 4.0, "…": "44 more keys"},
  "…": "chat, bracket, and avatar fields"
}
```

| Field | Type | Example | % missing | Meaning |
|---|---|---|---|---|
| league_id | str | `"1369887235935059968"` | 0 | League key |
| name | str | `"12 Supersexy Superflexy Hoekies"` | 0 | League name |
| season | str | `"2026"` | 0 | League season |
| season_type | str | `"regular"` | 0 | Season type the league plays |
| status | str | `"in_season"` | 0 | `pre_draft`, `drafting`, `in_season`, or `complete` |
| sport | str | `"nfl"` | 0 | Sport |
| total_rosters | int | `12` | 0 | Number of teams |
| roster_positions | list[str] | `["QB","RB","RB","WR","WR","FLEX","REC_FLEX","SUPER_FLEX","K","DEF","BN"×6]` | 0 | Lineup slots in order; the order matches matchup `starters` |
| scoring_settings | dict[str→float] | `{"rec": 0.5, …}` | 0 | 47 scoring rules (listed below) |
| previous_league_id | str | `"1243747994637963265"` | 0 | Last season's league, for history |
| draft_id | str | `"1369887235939274752"` | 0 | This season's draft |
| metadata.latest_league_winner_roster_id | str | `"2"` | 0 | Last season's champion roster *(likely)* |
| metadata.auto_continue, keeper_deadline | str | `"on"`, `"0"` | 0 | League admin flags; unused |
| last_message_id, last_message_time | str, int | `…`, `1790971715709` | 0 | Latest league-chat message ID and time (epoch ms) |
| last_author_display_name, last_author_id, last_author_is_bot | str, str, bool | `"sys"`, `…`, `true` | 0 | Who posted it; currently Sleeper's system bot |
| last_message_text_map, last_message_attachment, last_author_avatar, last_pinned_message_id, last_read_id | null | `null` | 100 | Chat details; always empty here |
| bracket_id, loser_bracket_id, bracket_overrides_id, loser_bracket_overrides_id | null | `null` | 100 | Playoff bracket IDs; *(likely)* filled once playoffs are set |
| company_id, group_id | null | `null` | 100 | Unused |
| avatar, shard | str, int | `<avatar id>`, `82` | 0 | League image; internal server shard |

**`settings`** (49 keys, all ints, none missing). The ones that matter:

| Key | Value | Meaning |
|---|---|---|
| num_teams | 12 | Teams |
| start_week | 1 | First fantasy week |
| playoff_week_start | 15 | First playoff week |
| playoff_teams | 6 | Playoff field size (6 teams → 3 rounds: weeks 15–17 *(likely)*) |
| playoff_round_type | 0 | One week per playoff round *(likely)* |
| league_average_match | 1 | **Weekly median game on** (confirmed against records) |
| last_scored_leg | 3 | Last week Sleeper has finished scoring; drives the completed-week rule |
| leg | 4 | League's current week |
| last_report | 3 | Last week with a league report *(likely)* |
| reserve_slots | 1 | One injured-reserve slot per team |
| reserve_allow_out, reserve_allow_cov | 1 | IR allowed for players listed Out or on the COVID list |
| taxi_slots | 0 | No taxi squad |
| type | 0 | Redraft league *(likely)* |
| waiver_type | 2 | FAAB bidding (consistent with `waiver_budget`) |
| waiver_budget | 100 | FAAB dollars per team |
| waiver_bid_min | 0 | $0 bids allowed (11 winning bids were $0) |
| waiver_day_of_week | 2 | Waiver day; claims are observed processing early Wednesday ET |
| trade_deadline | 99 | No trade deadline in practice *(likely)* |

The other 31 keys cover vetoes, keepers, taxi rules, daily waivers, and other admin options we don't use.

**`scoring_settings`** (47 keys). Offense: `pass_yd` 0.04, `pass_td` 4, `pass_int` −2, `pass_2pt` 2, `rush_yd` 0.1, `rush_td` 6, `rush_2pt` 2, `rec` 0.5, `bonus_rec_te` 0.5, `rec_yd` 0.1, `rec_td` 6, `rec_2pt` 2, `fum_lost` −2, `fum` 0, `fum_rec_td` 6. Kicking: `fgm_0_19`/`20_29`/`30_39` 3, `fgm_40_49` 4, `fgm_50p` 5, `fgmiss_0_19`/`20_29`/`30_39` −1, `fgmiss` 0, `xpm` 1, `xpmiss` −1. Defense: `sack` 1, `int` 2, `fum_rec` 2, `ff` 0, `safe` 2, `blk_kick` 2, `def_td` 6, `def_4_and_stop` 1, `pts_allow_0` 10, `pts_allow_1_6` 7, `pts_allow_7_13` 4, `pts_allow_14_20` 1, `pts_allow_21_27` 0, `pts_allow_28_34` −1, `pts_allow_35p` −4. Special teams: `st_td` 6, `st_ff` 1, `st_fum_rec` 1, `def_st_td` 6, `def_st_ff` 1, `def_st_fum_rec` 1.

We never recompute points from these; Sleeper's `players_points` already applies them.

### `users.json` (from `/league/{id}/users`), 12 records

```json
{
  "avatar": "<avatar id>",
  "display_name": "<display name>",
  "is_bot": false,
  "is_owner": false,
  "league_id": "1369887235935059968",
  "metadata": {"team_name": "<team name>", "allow_pn": "on", "mascot_item_type_id_leg_1": "cyber-duck", "…": "27 more keys"},
  "settings": null,
  "user_id": "<user_id 1>"
}
```

| Field | Type | Example | % missing | Meaning |
|---|---|---|---|---|
| user_id | str | `<user_id 1>` | 0 | Manager key; equals roster `owner_id` |
| display_name | str | `<display name>` | 0 | Sleeper username |
| metadata.team_name | str | `<team name>` | 0 | Team name (all 12 set; 3 have leading or trailing spaces, so strip them) |
| is_owner | bool | `false` | 0 | League commissioner (exactly 1 user) |
| is_bot | bool | `false` | 0 | Bot account |
| avatar | str | `<avatar id>` | 8 | Avatar image ID; 1 user has none |
| metadata.avatar | str | `<avatar url>` | 25 | Custom team avatar URL |
| league_id | str | `"1369887235935059968"` | 0 | League |
| settings | null | `null` | 100 | Always empty |
| metadata.allow_pn, mention_pn, allow_sms, … | str | `"on"` | 0–83 | Notification preferences (12 keys); unused |
| metadata.mascot_item_type_id_leg_&lt;week&gt; | str | `"cyber-duck"` | 25 | Per-week app mascot; unused |
| metadata.mascot_message, mascot_message_emotion_leg_&lt;week&gt; | str | `<text>` | 25–58 | Mascot text and emotions; unused |
| metadata.archived, team_name_update, player_nickname_update, show_mascots | str | `"off"` | 58–83 | App flags; unused |

### `rosters.json` (from `/league/{id}/rosters`), 12 records

```json
{
  "roster_id": 1,
  "owner_id": "<user_id 2>",
  "co_owners": null,
  "players": ["10859", "11564", "11603", "11625", "… 13 more"],
  "starters": ["11564", "8151", "6790", "8112", "… 6 more"],
  "reserve": ["11625"],
  "taxi": null,
  "keepers": null,
  "player_map": null,
  "settings": {"wins": 3, "losses": 3, "ties": 0, "fpts": 438, "fpts_decimal": 78, "fpts_against": 354, "fpts_against_decimal": 84, "ppts": 462, "ppts_decimal": 88, "…": "3 more keys"},
  "metadata": {"record": "WWWLLL", "streak": "3L", "p_nick_5849": "<nickname>", "…": "84 more keys"},
  "league_id": "1369887235935059968"
}
```

| Field | Type | Example | % missing | Meaning |
|---|---|---|---|---|
| roster_id | int | `1` | 0 | Team key used everywhere (1–12) |
| owner_id | str | `<user_id 2>` | 0 | Manager; joins to `users.user_id` |
| co_owners | null | `null` | 100 | No co-owners |
| players | list[str] | 17 IDs | 0 | Everyone on the roster **today**, IR included (17 = 16 + 1 IR) |
| starters | list[str] | 10 IDs | 0 | **Current** lineup (week 4), in `roster_positions` order |
| reserve | list[str] | `["11625"]` | 0 | Players in the IR slot **today**; also listed in `players` |
| taxi, keepers, player_map | null | `null` | 100 | Unused in this league |
| settings.wins / losses / ties | int | `3` / `3` / `0` | 0 | Season record **including median games** |
| settings.fpts + fpts_decimal | int + int | `438` + `78` | 0 | Points for = 438.78 (`fpts + fpts_decimal/100`) |
| settings.fpts_against + fpts_against_decimal | int + int | `354` + `84` | 0 | Points against = 354.84 |
| settings.ppts + ppts_decimal | int + int | `462` + `88` | 0 | Max possible points = 462.88 *(likely)* |
| settings.waiver_budget_used | int | `32` | 0 | FAAB dollars spent |
| settings.waiver_position | int | `9` | 0 | Waiver priority (tiebreaker for equal bids) *(likely)* |
| settings.total_moves | int | `0` | 0 | **Not maintained:** 0 for all 12 rosters despite 3–23 completed moves each. Count moves from transactions instead |
| metadata.record | str | `"WWWLLL"` | 0 | Two letters per week: head-to-head result, then median result |
| metadata.streak | str | `"3L"` | 0 | Current streak, counting median games |
| metadata.p_nick_&lt;player_id&gt; | str | `<nickname>` | 0 | Manager-assigned player nicknames; unused |
| metadata.allow_pn_* | str | `"on"` | 25–67 | Notification preferences; unused |
| league_id | str | `"1369887235935059968"` | 0 | League |

### `drafts.json` (from `/league/{id}/drafts`), 1 record

```json
{
  "draft_id": "1369887235939274752",
  "type": "snake",
  "status": "complete",
  "season": "2026",
  "draft_order": {"<user_id 1>": 8, "<user_id 2>": 7, "…": "10 more keys"},
  "settings": {"rounds": 16, "teams": 12, "pick_timer": 90, "slots_qb": 1, "…": "19 more keys"},
  "metadata": {"scoring_type": "2qb", "name": "12 Supersexy Superflexy Hoekies", "…": "2 more keys"},
  "…": "timestamps and chat fields"
}
```

| Field | Type | Example | % missing | Meaning |
|---|---|---|---|---|
| draft_id | str | `"1369887235939274752"` | 0 | Draft key; matches `league.draft_id` |
| type | str | `"snake"` | 0 | Snake draft |
| status | str | `"complete"` | 0 | Draft finished |
| season, season_type, sport, league_id | str | `"2026"` | 0 | Context |
| draft_order | dict[str→int] | `{"<user_id 1>": 8}` | 0 | Draft slot per **user**. There is no `slot_to_roster_id` field; use `roster_id` on each pick instead |
| settings.rounds / teams | int | `16` / `12` | 0 | 16 rounds × 12 teams = 192 picks |
| settings.slots_* | int | `slots_qb` 1 | 0 | Roster slots at draft time (match `roster_positions`) |
| settings.reversal_round | int | `0` | 0 | No third-round reversal |
| settings (timers, autopause, cpu_autopick, …) | int | `90` | 0 | Draft-room settings; unused |
| metadata.scoring_type | str | `"2qb"` | 0 | Sleeper's label for superflex scoring |
| metadata.name, description, show_team_names | str | `""` | 0 | Display fields |
| creators | list[str] | `[<user_id 2>]` | 0 | Who created the draft |
| created, start_time, last_picked | int | `1787702421917` | 0 | Epoch ms |
| last_message_id, last_message_time | str, int | `…` | 0 | Draft-room chat |

### `picks/draft_{draft_id}.json` (from `/draft/{draft_id}/picks`), 192 records

```json
{
  "pick_no": 1,
  "round": 1,
  "draft_slot": 1,
  "roster_id": 4,
  "picked_by": "<user_id 6>",
  "player_id": "9221",
  "is_keeper": null,
  "reactions": null,
  "draft_id": "1369887235939274752",
  "metadata": {"first_name": "Jahmyr", "last_name": "Gibbs", "position": "RB", "team": "DET", "years_exp": "3", "…": "8 more keys"}
}
```

| Field | Type | Example | % missing | Meaning |
|---|---|---|---|---|
| pick_no | int | `1` | 0 | Overall pick 1–192 (unique) |
| round | int | `1` | 0 | Round 1–16 |
| draft_slot | int | `1` | 0 | Position in the round order; maps one-to-one to `roster_id` |
| roster_id | int | `4` | 0 | Team that made the pick |
| picked_by | str | `<user_id 6>` | 0 | User who picked; matches today's roster owner for all 192 |
| player_id | str | `"9221"` | 0 | Player drafted (unique); 10 picks are team defenses like `"PHI"` |
| metadata.first_name, last_name, position, team | str | `"Gibbs"`, `"RB"`, `"DET"` | 0 | Player details **as of the draft** |
| metadata.years_exp, number, news_updated | str | `"3"` | 0 | Numbers stored as strings |
| metadata.status, injury_status, team_abbr, team_changed_at, sport, player_id | str | `"Active"`, `""` | 0 | Player status at draft time; empty string means none |
| is_keeper, reactions | null | `null` | 100 | Unused |
| draft_id | str | `"1369887235939274752"` | 0 | Draft |

Positions drafted: WR 66, RB 56, QB 33, TE 18, DEF 10, K 9. Not every team drafted a kicker or defense.

### `matchups/week_XX.json` (from `/league/{id}/matchups/{week}`), 12 records per week, 36 total

```json
{
  "roster_id": 1,
  "matchup_id": 6,
  "points": 195.12,
  "custom_points": null,
  "starters": ["11564", "8151", "6790", "12514", "… 6 more"],
  "starters_points": [9.82, 32.6, 31.9, 8.8, "… 6 more"],
  "players": ["10859", "11564", "12474", "12514", "… 12 more"],
  "players_points": {"10859": 9.8, "11564": 9.82, "12474": 4.5, "…": "13 more keys"}
}
```

| Field | Type | Example | % missing | Meaning |
|---|---|---|---|---|
| roster_id | int | `1` | 0 | Team |
| matchup_id | int | `6` | 0 | Game ID within the week; the two teams sharing it played each other |
| points | float | `195.12` | 0 | Team score = `sum(starters_points)` exactly, 2 dp |
| custom_points | null | `null` | 100 | Commissioner score override; never used so far |
| starters | list[str] | 10 IDs | 0 | Lineup in `roster_positions` order; `"0"` would mean an empty slot (none seen); `DEF` slot holds team abbreviations |
| starters_points | list[float] | `[9.82, 32.6, …]` | 0 | Points per starter, same order as `starters` |
| players | list[str] | 16–17 IDs | 0 | Every rostered player that week: starters, bench, **and IR** |
| players_points | dict[str→float] | `{"10859": 9.8}` | 0 | Points for every player in `players` (same keys exactly) |

### `transactions/week_XX.json` (from `/league/{id}/transactions/{week}`), 182 records across weeks 1–3

Waiver claim:
```json
{
  "transaction_id": "1408377422432231424",
  "type": "waiver",
  "status": "complete",
  "leg": 2,
  "created": 1790145853197,
  "status_updated": 1790147279624,
  "creator": "<user_id 6>",
  "roster_ids": [4],
  "consenter_ids": [4],
  "adds": {"NYG": 4},
  "drops": {"TB": 4},
  "settings": {"waiver_bid": 0, "priority": 13, "seq": 38},
  "metadata": {"notes": "Your waiver claim was processed successfully!"},
  "draft_picks": [],
  "waiver_budget": []
}
```

Trade:
```json
{
  "type": "trade",
  "status": "complete",
  "leg": 1,
  "roster_ids": [4, 12],
  "consenter_ids": [4, 12],
  "adds": {"8130": 4, "9224": 12},
  "drops": {"8130": 12, "9224": 4},
  "settings": null,
  "metadata": null,
  "draft_picks": [],
  "waiver_budget": []
}
```

| Field | Type | Example | % missing | Meaning |
|---|---|---|---|---|
| transaction_id | str | `"1408377422432231424"` | 0 | Transaction key |
| type | str | `"waiver"` | 0 | `waiver` (117), `free_agent` (62), or `trade` (3) |
| status | str | `"complete"` | 0 | `complete` (114) or `failed` (68, all lost waiver claims) |
| leg | int | `2` | 0 | Week; always equals the file's week |
| created | int | `1790145853197` | 0 | When submitted, epoch ms |
| status_updated | int | `1790147279624` | 0 | When processed, epoch ms |
| creator | str | `<user_id 6>` | 0 | User who submitted it |
| roster_ids | list[int] | `[4]` | 0 | Teams involved (2 for trades) |
| consenter_ids | list[int] | `[4]` | 0 | Teams that agreed (roster IDs, not user IDs) |
| adds | dict[str→int] | `{"NYG": 4}` | 10 | Player → roster receiving them; `null` (not `{}`) for drop-only moves |
| drops | dict[str→int] | `{"TB": 4}` | 52 | Player → roster releasing them; `null` for add-only moves |
| settings.waiver_bid | int | `0` | 36 | FAAB bid; present on all waiver claims, absent for free agents and trades. Winning bids range $0–56 (11 at $0) |
| settings.priority | int | `13` | 73 | Order of a manager's claims *(likely)*; on 49 of 117 waiver claims, both won and lost |
| settings.seq | int | `38` | 36 | Processing sequence *(likely)* |
| metadata.notes | str | `"Your waiver claim was processed successfully!"` | 36 | Sleeper's system message: success, "claimed by another owner", or "too many players" |
| draft_picks | list | `[]` | 0 | Picks traded; empty in all 3 trades (all were 1-for-1 player swaps) |
| waiver_budget | list | `[]` | 0 | FAAB traded; empty in all 3 trades |

Week boundaries in Eastern time: week 1 runs from Aug 25 (after the draft) to Sep 15; week 2 from Wed Sep 16 03:23 to Wed Sep 23; week 3 from Wed Sep 23 04:00 to Wed Sep 30.

## How these checks were run

The checks were one-off scripts run against `data/raw/2026/` on 2026-10-02. The confirmed rules (findings 4, 5, 7, 8, 9) should become permanent checks in `validate.py` during Phase 1, so they re-run on every pull.
