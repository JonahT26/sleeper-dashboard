# Metrics specification

The source of truth for every metric. Code follows this file, not the other way round. Each definition here was proposed by Claude and confirmed or changed by the owner during the Phase 2 interview (started 2026-10-02). Any change to a definition needs the owner's approval and goes in this file first.

## Status

| # | Metric | Status |
|---|---|---|
| 1 | All-play record | **Confirmed** 2026-10-02 |
| 2 | Expected wins and luck | **Confirmed** 2026-10-02 |
| 3 | Lineup efficiency | **Confirmed** 2026-10-02 |
| 4 | Consistency | **Confirmed** 2026-10-02 |
| 5 | Strength of schedule | **Confirmed** 2026-10-02 |
| 6 | Power score | **Confirmed** 2026-10-02 |
| 7 | Weekly awards | **Confirmed** 2026-10-02 |

All seven definitions are confirmed. Next: build them in the order of `docs/CODEBASE.md` "Adding a new metric" (pure function, invariant tests, pipeline wiring, docs update).

## Conventions that apply to every metric

- **Points** come from `team_weeks.points` and `player_weeks.points`, which are Sleeper's own scored values at 2 decimal places. Points are never recomputed from scoring settings. Comparisons of points (greater than, less than, equal) use these 2-decimal values.
- **League size *N*** and the playoff start week are read from league settings at runtime (`num_teams`, `playoff_week_start`), never hardcoded. In 2026, *N* = 12 and playoffs start in week 15.
- **Regular season** means weeks before `playoff_week_start`. **Playoff weeks** are `playoff_week_start` and later (`team_weeks.is_playoff`).
- **Completed weeks only.** Metrics are computed for weeks the pipeline has processed (see the completed-week rule in `docs/CODEBASE.md`). "Through week *t*" means weeks 1 to *t* inclusive.
- **Full refresh.** Every metric is recomputed for the whole season on every run, so Sleeper's stat corrections flow through.
- **Data rules carried over from Phase 1** (evidence in `docs/DATA_DICTIONARY.md`):
  - Injured-reserve players count as bench in past weeks.
  - A team scoring exactly the weekly median stops the run; no tie rule is defined.
  - Preseason transactions are kept separate from week 1.
- **Tunable parameters** (weights, thresholds, shrinkage) live in `config.yaml` under `metrics:` and are referenced here by their key, e.g. `metrics.power.weights`. A metric with no tunable parameters says so.

## Template

Each metric is recorded with the same fields: **Name**, **Meaning** (plain English), **Formula**, **Inputs**, **Parameters** (`config.yaml` keys), **Edge cases**, **Expected range**, and **Sanity checks** (each one becomes an automated test or validation check).

---

## 1. All-play record

**Status:** confirmed by the owner, 2026-10-02.

**Meaning.** Your record if you had played every other team every week. It measures how good your scores were, setting aside the luck of who you happened to face.

**Formula.** For team *i* in week *w*, with points *p₍ᵢ,w₎* and *n₍w₎* teams scored that week (normally *N*):

| Quantity | Definition |
|---|---|
| All-play wins *W₍ᵢ,w₎* | number of other teams *j* with *p₍ⱼ,w₎* < *p₍ᵢ,w₎* |
| All-play losses *L₍ᵢ,w₎* | number of other teams *j* with *p₍ⱼ,w₎* > *p₍ᵢ,w₎* |
| All-play ties *T₍ᵢ,w₎* | number of other teams *j* with *p₍ⱼ,w₎* = *p₍ᵢ,w₎* |
| All-play win % (week) | (*W* + ½*T*) ÷ (*n₍w₎* − 1) |
| Season to date, through week *t* | Σ*W*, Σ*L*, Σ*T* over weeks 1…*t*; win % = (Σ*W* + ½Σ*T*) ÷ (Σ*W* + Σ*L* + Σ*T*) |

Display: "all-play 41–14", with a third number only when ties exist ("41–13–1").

**Inputs.** `team_weeks`: `season`, `week`, `roster_id`, `points`. League settings: `num_teams`.

**Parameters.** None.

**Edge cases.**

| Case | Rule |
|---|---|
| Playoff weeks | **Included: every week, every team** (owner decision). Teams knocked out of the playoffs still count, both as the team being measured and as opponents. Owner's reasoning: the league has enough other penalties to discourage neglecting a lineup. Season-to-date totals therefore include playoff weeks |
| A team with no score in a week | Not expected: the validation step requires one row per team per completed week. If Sleeper ever omits a team (to verify at week 15), all-play uses the *n₍w₎* teams that scored, so the denominator stays *n₍w₎* − 1 |
| Exact score ties | Count as an all-play tie, worth half a win. None in weeks 1–3; the closest gap so far is 0.44 points |
| Median game | Ignored. All-play already contains it: beating the median is the same as all-play wins ≥ *N*/2 |
| Empty starting slots | No adjustment. The team's actual score is used. Empty slots are measured under lineup efficiency |
| Players added mid-week | No adjustment. A player's points count only if he was started, and they are already in the team score |
| Small early-season samples | No shrinkage. All-play is a count of results and already has 11 comparisons per week instead of 1 head-to-head game |

**Expected range.** Weekly all-play wins 0 to *N* − 1 (0–11). Season all-play % from 0 to 1. The league-average all-play % is exactly 0.500 in every week.

**Sanity checks.**
1. *W* + *L* + *T* = *n₍w₎* − 1 for every team-week.
2. In each week, the league's total of *W* + ½*T* = *n₍w₎*(*n₍w₎* − 1) / 2 (66 when all 12 teams score).
3. The week's highest scorer has *L* = 0, and the lowest scorer has *W* = 0.
4. Ordering: if *p₍ᵢ,w₎* > *p₍ⱼ,w₎*, then *W₍ᵢ,w₎* > *W₍ⱼ,w₎*.
5. **Median cross-check (regular-season weeks with a median game):** `median_result` = W exactly when *W₍ᵢ,w₎* ≥ *N*/2. This checks the all-play table and `team_weeks` against each other.

---

## 2. Expected wins and luck

**Status:** confirmed by the owner, 2026-10-02; record scale changed by the owner the same day (see Record scale).

**Meaning.** *Expected wins* is how many games your scores deserved to win. *Luck* is actual wins minus expected wins. Positive luck means your schedule handed you wins your scores didn't earn; negative means it took wins away.

**Formula.** For team *i* in regular-season week *w*, with *M₍ᵢ,w₎* the weekly median-game result (1 for a win, 0 for a loss; 0 in a week without a median game):

| Quantity | Definition |
|---|---|
| Head-to-head actual wins *H₍ᵢ,w₎* | 1 for a win, ½ for a tie, 0 for a loss |
| Actual wins *A₍ᵢ,w₎* | *H₍ᵢ,w₎* + *M₍ᵢ,w₎*: head-to-head plus median game, 0 to 2 per week. Matches Sleeper's official record |
| Expected wins *xW₍ᵢ,w₎* | that week's all-play win % (metric 1) + *M₍ᵢ,w₎*. The all-play % is the probability of beating an opponent drawn at random from that week's other teams; the median game's expected result equals its actual result, because it is decided by the team's own score alone |
| Luck *λ₍ᵢ,w₎* | *A₍ᵢ,w₎* − *xW₍ᵢ,w₎* = *H₍ᵢ,w₎* − all-play % |
| Season to date, through week *t* | Σ*xW*, Σ*A*, and Σ*λ* over regular-season weeks 1…*t* |

Example: the 4th-highest score of 12 beats 8 of the other 11 teams, so the all-play % is 8/11 = 0.73, and the team also wins the median game (top 6), so *xW* = 1.73. A head-to-head loss that week gives *A* = 1 and luck −0.73; a win gives *A* = 2 and luck +0.27.

Display: the record as overall wins–losses, with ties only when there are any ("6–0", "5–0–1"); expected wins to 1 decimal place (`UI_GUIDE.md`); luck as a signed number of wins, e.g. "+1.4".

**Record scale (owner decision, changed 2026-10-02).** **Overall: head-to-head plus median games**, the same as Sleeper's official standings. The ladder shows this record next to the all-play record ("8–2, all-play 41–14"), with no head-to-head/median split anywhere on the dashboard (owner decision), with one exception: the power score breakdown names its results component "Head-to-head wins" and gives the head-to-head record behind it ("Won 1 of 3"), so it does not appear to contradict the overall record (owner decision, 2026-10-02 prototype review). Actual and expected wins use the same scale, so the luck chart reads against the record league members see.

History: during the interview the owner first chose head-to-head only; after seeing the first season table, the owner changed it to the overall record. Luck values are identical under both scales: a team's median-game result is fully determined by its own score (it wins exactly when all-play wins ≥ *N*/2), so its expected result always equals its actual result and the median game adds no luck. The power score's results component stays head-to-head only (section 6).

**Model (owner decision).** All-play based, as above. The alternative, a score-distribution model of the probability of beating the actual opponent from each team's mean and SD, was rejected: it mixes team strength into luck, overlapping with the power score, and is unstable with few weeks of data.

**Inputs.** Metric 1 (weekly all-play *W*, *T*, and *n₍w₎*); `team_weeks`: `result`, `median_result` (present when the league plays a median game), `is_playoff`.

**Parameters.** None.

**Edge cases.**

| Case | Rule |
|---|---|
| Playoff weeks | **Excluded** (owner decision). Expected wins, actual wins, and luck cover the regular season only, because their job is to explain the regular-season standings. Weekly all-play values still exist for playoff weeks (metric 1). From week 15 on, season-to-date values stay at their end-of-regular-season totals |
| Head-to-head ties | ½ actual win, consistent with all-play ties. The displayed record counts the tie as a tie ("5–0–1") |
| Median game | Included in actual and expected wins with equal value, so it never changes luck. A score exactly at the median stops the run (Phase 1 rule) |
| League or week without a median game | *M* = 0: actual and expected wins fall back to head-to-head only |
| Exact score ties with other teams | Handled through all-play ties (½ each) |
| Empty starting slots | No adjustment. The team's actual score stands |
| Players added mid-week | No adjustment. The team's actual score stands |
| Small early-season samples | No shrinkage. Luck describes results already banked rather than estimating talent, so it is valid from week 1 and simply starts close to zero |

**Expected range.**
- Weekly actual and expected wins between 0 and 2 (between 0 and 1 without a median game).
- Weekly luck lies strictly between −1 and +1, and at most ±(*n₍w₎* − 2)/(*n₍w₎* − 1) = ±10/11, e.g. losing with the second-highest score.
- Season expected wins lie between 0 and the number of regular-season games played (head-to-head plus median).
- The league's total luck is 0 every week, so the league average is 0.
- Weekly luck has a standard deviation of roughly 0.4 wins, so by the end of a 14-week regular season most teams should be within about ±3 wins.

**Sanity checks.**
1. In every regular-season week where all teams have a game, the league's expected wins equal its actual wins and luck sums to 0 (±0.000001): head-to-head wins total *N*/2 = total all-play %, and median wins equal on both sides.
2. 0 ≤ *xW₍ᵢ,w₎* ≤ 2 and −1 < *λ₍ᵢ,w₎* < 1 for every team-week.
3. A head-to-head win with the week's top score has *λ* = 0; a loss with the week's bottom score has *λ* = 0.
4. Each team's regular-season overall wins, losses, and ties equal Sleeper's roster `wins`, `losses`, and `ties` (checked in `validate.py`).

---

## 3. Lineup efficiency

**Status:** confirmed by the owner, 2026-10-02.

**Meaning.** *Optimal points* is the best score a team could have posted with hindsight, using only players on its roster that week. *Efficiency* is the share of that best score the team actually got. *Points left on the bench* is the gap between the two.

**Optimal lineup.** From the week's player pool, choose players to fill every starting slot in league settings `roster_positions` (every entry except `BN`), maximising total points, subject to:
- each player fills at most one slot;
- each player fills only slots his position allows (table below);
- every slot is filled whenever at least one unused eligible player is in the pool, even if all eligible players scored below zero.

Solved exactly as an assignment problem (slots × players).

| Slot | Eligible positions |
|---|---|
| QB, RB, WR, TE, K, DEF | that position only |
| FLEX | RB, WR, TE |
| WRRB_FLEX | RB, WR |
| REC_FLEX | WR, TE |
| SUPER_FLEX | QB, RB, WR, TE |

This league uses QB, RB, WR, FLEX, REC_FLEX, SUPER_FLEX, K, and DEF. TE and WRRB_FLEX are Sleeper slots it doesn't use; they are listed so a settings change wouldn't stop the run. A player's positions are his `fantasy_positions` in the players cache (his primary `position` if that list is empty), and he may fill a slot if any of them is eligible. The slot list is read from league settings each run. The eligibility table is Sleeper's rule, not a tunable parameter, so it is fixed in this spec. A slot name not in this table stops the run.

**Formula.** For team *i* in week *w*:

| Quantity | Definition |
|---|---|
| Optimal points *O₍ᵢ,w₎* | total points of the optimal lineup |
| Actual points *P₍ᵢ,w₎* | `team_weeks.points` |
| Efficiency *E₍ᵢ,w₎* | *P₍ᵢ,w₎* ÷ *O₍ᵢ,w₎* |
| Points left on the bench *B₍ᵢ,w₎* | *O₍ᵢ,w₎* − *P₍ᵢ,w₎* |
| Season efficiency, through week *t* | Σ*P* ÷ Σ*O* over weeks 1…*t*. This weights each week by its optimal points; it is **not** the mean of weekly ratios (owner decision) |
| Season points left on the bench | Σ*B* over weeks 1…*t* |

Display: efficiency as a whole-number percentage ("87%"); points to 1 decimal place.

The players chosen by the optimal lineup are stored as well (one row per slot per team-week), so that awards can name specific start/sit mistakes.

**Inputs.** `player_weeks`: `season`, `week`, `roster_id`, `player_id`, `is_starter`, `is_empty_slot`, `points`, `position`. `team_weeks.points`. League settings: `roster_positions`. Sleeper's `ppts` + `ppts_decimal` from `rosters.json`, for the soft check only.

**Parameters.**
| Key | Default | Meaning |
|---|---|---|
| `metrics.efficiency.ppts_warn_gap` | 5.0 | Soft check: warn when a team's regular-season optimal points exceed Sleeper's `ppts` by more than this many points (owner decision). Falling below `ppts` always warns |

**Edge cases.**

| Case | Rule |
|---|---|
| Hindsight | **Pure hindsight** (owner decision). Any player in the pool can fill any eligible slot, regardless of game-time locks. This matches Sleeper's max points |
| Player pool | Sleeper's matchup `players` list for the week: starters, bench, **and injured reserve** (Phase 1 decision) |
| Players added mid-week | Included if they are in that week's matchup `players` list. A player who scored from the bench and was then dropped before the week ended is not in the list, so is not in the pool |
| Negative scores | Slots are always filled when an eligible player is available, even if all options scored below zero. The optimal lineup never leaves a slot empty to gain points (owner decision) |
| Empty starting slot | Counts as 0 in actual points. If an eligible player was in the pool, the optimal lineup fills the slot, so the manager is penalised by that player's points |
| No eligible player rostered (e.g. no kicker) | The optimal lineup leaves the slot empty too, so there is no efficiency penalty: it is a roster decision, not a lineup decision |
| Optimal points of 0 or less | Efficiency is null (cannot occur in practice; listed so the code never divides by zero) |
| Equal-scoring alternatives | Optimal points are the same either way. For the stored player list, ties go to the player the manager actually started, so no award blames a manager for a pointless swap |
| Playoff weeks | **Included: every week, every team** (owner decision, consistent with all-play). Season totals include playoff weeks. The soft check against `ppts` uses regular-season weeks only, because `ppts` is assumed to be regular season only (verify at week 15) |
| Position eligibility | From the players cache, which describes players **today** (owner accepted). A player whose position changed mid-season is judged on his current position. In weeks 1–3, none of the 230 players used had more than one eligible position |
| Median game | Not relevant |
| Small early-season samples | No shrinkage. The metric is descriptive |

**Expected range.** Weekly efficiency between 0 and 100%, typically about 80–95%. Points left on the bench are ≥ 0, typically about 5–40 per week.

**Sanity checks.**
1. *O₍ᵢ,w₎* ≥ *P₍ᵢ,w₎* for every team-week (±0.01).
2. A team whose actual starters form an optimal lineup has *E* = 100% and *B* = 0.
3. Every optimal lineup obeys the eligibility table, uses each player at most once, and fills every slot that has an eligible player available.
4. Optimal points equal the sum of the stored optimal players' points (±0.01).
5. **Soft check:** each team's regular-season Σ*O* ≥ Sleeper's `ppts`. A team below `ppts`, or above it by more than `metrics.efficiency.ppts_warn_gap`, gets a printed warning, not a failure. Phase 1 found gaps of 0 to 4.00 points with IR players included.

---

## 4. Consistency

**Status:** confirmed by the owner, 2026-10-02.

**Meaning.** How predictable a team's scoring is: how much it swings from week to week relative to the league, what a bad week and a good week look like, and how often it blows up or collapses.

**Formula.** Let *m₍w₎* be the league median score in week *w* (the median of all teams' points that week), and *d₍ᵢ,w₎* = *p₍ᵢ,w₎* − *m₍w₎*, the team's score relative to the league that week. Removing *m₍w₎* strips out league-wide swings such as bye weeks or a high-scoring weekend (the weekly SD across teams was 33.6 in week 1 but about 17 in weeks 2–3). For team *i*, season to date through week *t*, over its *n* weeks:

| Quantity | Definition |
|---|---|
| Volatility | sample standard deviation (divisor *n* − 1) of *d₍ᵢ,1₎ … d₍ᵢ,t₎*, in points |
| Floor | the `floor_pct` percentile of the team's weekly **points** *p₍ᵢ,w₎*, linear interpolation |
| Ceiling | the `ceiling_pct` percentile of the team's weekly **points**, linear interpolation |
| Boom week | *d₍ᵢ,w₎* ≥ `boom_margin` |
| Bust week | *d₍ᵢ,w₎* ≤ −`bust_margin` |
| Boom rate, bust rate | boom weeks ÷ *n*, bust weeks ÷ *n* |

Floor and ceiling use raw points so they line up with the dashboard's strip plot of weekly scores. Volatility and boom/bust use *d* because they describe the team, not the week.

Owner decisions: volatility relative to the weekly median, not raw SD or coefficient of variation; floor and ceiling as the 10th and 90th percentiles, not min/max or mean ± SD; boom and bust as a fixed margin around the weekly median, not fixed scores, weekly ranks, or z-scores.

**Inputs.** `team_weeks`: `season`, `week`, `roster_id`, `points`.

**Parameters** (`config.yaml`):

| Key | Default | Meaning |
|---|---|---|
| `metrics.consistency.min_weeks` | 3 | Volatility, floor, and ceiling are null until a team has this many weeks |
| `metrics.consistency.floor_pct` | 0.10 | Percentile used as the floor |
| `metrics.consistency.ceiling_pct` | 0.90 | Percentile used as the ceiling |
| `metrics.consistency.boom_margin` | 20 | Points above the weekly league median that make a boom week |
| `metrics.consistency.bust_margin` | 20 | Points below the weekly league median that make a bust week |

Calibration (weeks 1–3, 36 team-weeks): *d* has SD 23.5 and ranges from −42.8 to +68.6. A margin of ±20 gives 7 booms and 4 busts (31% of team-weeks); ±25 would give 5 and 3.

**Edge cases.**

| Case | Rule |
|---|---|
| Playoff weeks | **Included: every week, every team** (owner decision, consistent with metrics 1 and 3). The weekly median *m₍w₎* uses every team that scored that week |
| Small early-season samples | Values are shown raw, with no shrinkage. Volatility, floor, and ceiling are null until the team has `min_weeks` weeks; boom and bust counts are shown from week 1. If consistency feeds the power score, any shrinkage is decided there |
| Score exactly on a threshold | Counts: *d* = `boom_margin` is a boom, *d* = −`bust_margin` is a bust |
| Median game | The median-game result is not used; only the median *score* is used, as the reference point. A team scoring exactly the median already stops the run (Phase 1 rule) |
| Empty starting slots | No adjustment. The team's actual score stands |
| Players added mid-week | No adjustment. The team's actual score stands |

**Expected range.** Volatility ≥ 0, typically 15–30 points. Floor ≤ ceiling. Boom and bust rates each between 0 and 1, about 15–20% league-wide at a margin of 20.

**Sanity checks.**
1. Floor ≤ the team's median weekly score ≤ ceiling.
2. A team scoring exactly *m₍w₎* every week has volatility 0, no booms, and no busts.
3. No week is both a boom and a bust (requires both margins > 0; the code must stop with a clear error if either is 0 or less).
4. Volatility is unchanged if every team's score in a week is shifted by the same amount.
5. Boom count + bust count ≤ *n* for every team.

---

## 5. Strength of schedule

**Status:** confirmed by the owner, 2026-10-02.

**Meaning.** How good the opponents a team has faced were, and how good the ones still ahead of it are, compared with an average schedule. Positive means a harder schedule.

**Formula.** Through week *t*:

| Quantity | Definition |
|---|---|
| Opponent strength *S₍ⱼ₎(t)* | team *j*'s mean points per week over all completed weeks 1…*t* |
| Baseline *B₍ᵢ₎(t)* | mean strength of the **other** teams: (Σ₍ⱼ₎ *S₍ⱼ₎(t)* − *S₍ᵢ₎(t)*) ÷ (*N* − 1) |
| SOS played | mean of *S₍opp₎(t)* over the regular-season opponents team *i* has played in weeks 1…*t*, each game counted once (an opponent faced twice counts twice), minus *B₍ᵢ₎(t)* |
| SOS remaining | mean of *S₍opp₎(t)* over team *i*'s remaining regular-season opponents (weeks *t*+1 … `playoff_week_start` − 1, from the published schedule), each game counted once, minus *B₍ᵢ₎(t)* |

Both are in points per week. Display: two panels, played and remaining, as diverging bars (`UI_GUIDE.md`), to 1 decimal place.

Owner decisions:
- Opponent strength is average points per week, not all-play % or the points opponents scored in their games against the team (which mostly duplicates luck).
- The baseline is the other *N* − 1 teams, because a team never plays itself. Against the plain league average, strong teams would look like they had easy schedules partly by construction.
- An opponent's games against team *i* are not removed from *S₍ⱼ₎*: in fantasy football, an opponent's score does not depend on who it plays.

**Inputs.** `team_weeks`: `season`, `week`, `roster_id`, `points`, `opponent_roster_id`, `is_playoff`. **New data needed:** the published schedule for future regular-season weeks. Sleeper's matchups endpoint already returns future weeks with pairings (`matchup_id`) and 0 points (checked 2026-10-02 for week 14). Building this metric requires extract to pull weeks *t*+1 … `playoff_week_start` − 1 (about 10 more API calls per run early in the season) into a new `schedule` table: season, week, roster_id, opponent_roster_id, is_completed.

**Parameters** (`config.yaml`):

| Key | Default | Meaning |
|---|---|---|
| `metrics.schedule.min_weeks` | 3 | Both SOS values are null until this many weeks are complete |

**Edge cases.**

| Case | Rule |
|---|---|
| Small early-season samples | **No shrinkage; hidden until `min_weeks`** (owner decision). Shrinking every team's average toward the league mean would not change the SOS ranking, because every team has played the same number of weeks; it would only scale all values by the same factor |
| Playoff weeks | **Regular-season schedule only** (owner decision). Playoff opponents come from the bracket, not the schedule. Played SOS covers regular-season games; remaining SOS is null after the last regular-season week. Opponent strength *S* still uses every completed week, including playoff weeks |
| Median game | Ignored. Its "opponent" is the league median for everyone, so it adds nothing to schedule difficulty |
| Head-to-head and score ties | Play no role |
| Empty starting slots, players added mid-week | No adjustment. Opponent strength uses actual scores |
| Schedule changes | The future schedule is re-read from Sleeper on every run (full refresh) |

**Expected range.** Roughly ±15 points per week early in the season, narrowing to about ±5 by the end of the regular season. Remaining SOS is null once the regular season is over.

**Schedule structure (found 2026-10-02).** This league's 14-week schedule is an 11-week round-robin, and weeks 12–14 repeat the pairings of weeks 1–3. Two consequences, both following from the definition rather than from a bug:
- **As of week 3, remaining SOS is exactly 0 for every team**: the 11 remaining games are one game against each other team, so their average strength equals the baseline. From week 4 on, remaining SOS differs between teams again.
- **By the end of the regular season, SOS played = (3/14) × (average strength of the three teams played twice − baseline)**, because everyone else is faced exactly once. Played SOS therefore shrinks toward a small number as the season goes on; early values mostly reflect *when* a team met strong opponents.

**Sanity checks.**
1. Number of opponents in SOS played = regular-season games played.
2. Games played + games remaining = number of regular-season weeks (14 in 2026) for every team.
3. The future schedule is symmetric (if A plays B in a week, B plays A) and each `matchup_id` appears exactly twice per week.
4. Pairings in the `schedule` table for completed weeks match `team_weeks.opponent_roster_id`.
5. If every team had the same mean points, every SOS value would be 0.

---

## 6. Power score

**Status:** confirmed by the owner, 2026-10-02.

**Meaning.** One score from 0 to 100 for how strong each team is right now, where 50 is league average. It blends four components. Every weight is shown on the dashboard, and each team's ladder row expands to show what each component contributed (`UI_GUIDE.md`).

**Components**, for team *i* through week *t* (owner approved the components and weights):

| Key | Component | Definition | Weight |
|---|---|---|---|
| `season_scoring` | Season scoring | mean points per week over all completed weeks 1…*t* | 0.35 |
| `recent_form` | Recent form | simple mean points over the last `recent_weeks` completed weeks (*t* − `recent_weeks` + 1 … *t*); all weeks so far when *t* < `recent_weeks` | 0.25 |
| `roster_strength` | Roster strength | mean **optimal** points per week (metric 3) over weeks 1…*t*: the talent on the roster, bench included | 0.20 |
| `results` | Results (displayed as "Head-to-head wins") | **head-to-head** win % = (W + ½T) ÷ games, regular-season head-to-head games through *t*. Median games are excluded (owner decision, 2026-10-02): a median win is decided by the team's own score, which season scoring and recent form already weigh at 0.60 | 0.20 |

Deliberately left out (owner approved): **efficiency** (already inside actual points; roster strength captures the upside), **consistency** (volatility hurts a good team and helps a bad one, so it has no clear direction), **all-play %** (almost the same as season scoring), and **strength of schedule** (a team's points don't depend on its opponent). In weeks 1–3, recent form equals season scoring, so the two act as one component weighted 0.60.

**Formula.** In week *t*, for each component *c*:

1. Standardise across the *N* teams: *z₍ᵢ,c₎* = (*x₍ᵢ,c₎* − mean₍c₎) ÷ SD₍c₎, using the population SD (divisor *N*). If SD₍c₎ = 0, every *z₍ᵢ,c₎* = 0.
2. Early-season factor: *f* = *t* ÷ (*t* + `shrink_weeks`), where *t* is the number of completed weeks.
3. Component score: *s₍ᵢ,c₎* = 50 + `scale` · *f* · *z₍ᵢ,c₎*.
4. Contribution: *w₍c₎* · *s₍ᵢ,c₎*.
5. **Power score** = Σ₍c₎ *w₍c₎* · *s₍ᵢ,c₎* = 50 + `scale` · *f* · Σ₍c₎ *w₍c₎ z₍ᵢ,c₎*.

**Rank** is by power score, highest first. **Rank change** = previous week's rank − this week's rank, so positive means the team moved up; null in week 1.

Why this scale (owner decision, over percentile ranks or min–max): with *N* teams, no |*z*| can exceed (*N* − 1) ÷ √*N* (3.18 for 12 teams). With `scale` 15, every component score and every power score therefore lies between 2.4 and 97.6, every contribution is positive (so the ladder's stacked bars work), and the league average is exactly 50. The code must stop with a clear error if `scale` · (*N* − 1) ÷ √*N* > 50, which could push scores outside 0–100.

**Early-season compression (owner decision).** Because *z*-scores ignore scale, shrinking components toward the league mean would not change the ranking. What *f* changes is how confident the spread looks: in week 1, every score lies within 50 ± 12; by week 9 the spread is 75% of full. **The ranking is unaffected.**

Display: power score to 1 decimal place, with a thin bar running left or right from the league average of 50; rank change as ▲/▼ with a number. The breakdown shows each component's contribution ("Score") and its gap from an average team's contribution, *w₍c₎* · (*s₍ᵢ,c₎* − 50) (`UI_GUIDE.md` Ladder row).

**Inputs.** `team_weeks`: `week`, `roster_id`, `points`, `result`, `is_playoff`. Metric 3: weekly optimal points. League settings: `num_teams`.

**Parameters** (`config.yaml`):

| Key | Default | Meaning |
|---|---|---|
| `metrics.power.weights.season_scoring` | 0.35 | Weight of season scoring |
| `metrics.power.weights.recent_form` | 0.25 | Weight of recent form |
| `metrics.power.weights.roster_strength` | 0.20 | Weight of roster strength |
| `metrics.power.weights.results` | 0.20 | Weight of results |
| `metrics.power.recent_weeks` | 3 | Window for recent form (simple mean, owner decision over an exponentially weighted mean) |
| `metrics.power.scale` | 15 | Points of score per standard deviation |
| `metrics.power.shrink_weeks` | 3 | *k* in the early-season factor *f* = *t* ÷ (*t* + *k*) |

The weights must be ≥ 0 and sum to 1 (±0.000001), or the run stops. They are a judgement call: three weeks of data cannot fit them. A possible later step (Phase 5) is to backtest them on last season by checking which weighting best predicts the following week's results.

**Edge cases.**

| Case | Rule |
|---|---|
| Stat corrections to past weeks | **Recompute everything every run** (owner decision, settling the Phase 1 open question). Rank change is measured against the recomputed previous week, so posted rankings can shift slightly after corrections, and the numbers are always internally consistent |
| Ties in power score | Broken by season scoring, then head-to-head win %, then lower `roster_id`. Every team gets a distinct rank |
| Playoff weeks | **Every week, every team** (owner decision). Results stay frozen at the end-of-regular-season win %; the other three components keep updating |
| Week 1 | Results are 0, ½, or 1 for every team; *f* = 0.25 keeps the spread small. Rank change is null |
| Median game | Not used: results are head-to-head only, even though the displayed record includes median games (owner decision, 2026-10-02) |
| Empty starting slots, players added mid-week | No adjustment. Season scoring and recent form use actual scores; roster strength uses the roster as Sleeper recorded it (metric 3 rules) |
| A component with no spread | *z* = 0 for every team, so it contributes exactly 50 × weight to everyone |

**Expected range.** Power score between 2.4 and 97.6 (with `scale` 15 and 12 teams), tighter early in the season. The league mean is exactly 50 every week.

**Sanity checks.**
1. The league's mean power score = 50.0 every week (±0.000001).
2. Each team's contributions sum to its power score (±0.000001).
3. Weights are ≥ 0 and sum to 1.
4. A team ranked first on every component is ranked first overall.
5. Setting a weight to 0 leaves that component with no effect on the ranking.
6. Ranks are 1…*N* with no duplicates, every week.
7. The ranking is identical for any `shrink_weeks` value.

---

## 7. Weekly awards

**Status:** confirmed by the owner, 2026-10-02.

**Meaning.** A handful of awards each week, where the dashboard's trash talk lives (`UI_GUIDE.md`). Each names a team, a number, and a one-line caption. Captions are factual and specific; the number does the joking.

**Formula.** Each award picks its winner from one week's data. A team can win several awards in the same week.

| Key | Award | Eligible teams | Winner | Value | Tiebreak | Caption pattern | Enabled |
|---|---|---|---|---|---|---|---|
| `top_score` | Top Score | all | highest `points` | points | co-winners | "Put up 168.4, the best of the week." | yes |
| `lowest_score` | Lowest Score | all | lowest `points` | points | co-winners | "Managed 84.1. Everyone else did better." | yes |
| `heartbreaker` | Heartbreaker | with a game | highest `points` among teams whose `result` is L | points | co-winners | "Scored 141.2, 3rd-best of the week, and still lost." | yes |
| `robbery` | Robbery | with a game | lowest `points` among teams whose `result` is W | points | co-winners | "Won with 101.3, the 10th-best score." | yes |
| `blowout` | Blowout | with a game | largest `margin` among winners | margin | co-winners | "Beat ‹opponent› by 72.4." | yes |
| `nail_biter` | Nail-Biter | with a game | smallest `margin` among winners | margin | co-winners | "Edged ‹opponent› by 0.4." | yes (added 2026-10-02) |
| `bench_blunder` | Bench Blunder | all | largest points left on the bench *B* (metric 3) | *B* | lower efficiency, then co-winners | "Left 38.4 points on the bench." | yes |
| `perfect_lineup` | Perfect Lineup | all | highest efficiency *E* (metric 3) | *E* | higher points, then co-winners | "Started the best possible lineup: 100%." | no |
| `mvp` | MVP | all | team of the week's highest-scoring starter | that player's points | co-winners | "‹Player› scored 42.3." | yes |
| `pickup_of_the_week` | Pickup of the Week | all | team of the highest-scoring starter whose **most recent acquisition by that team, in that week or earlier this season, was a `waiver` or `free_agent` add** | that player's points | co-winners | "‹Player›, added off waivers in week 2, scored 24.1." | yes |
| `asleep_at_the_wheel` | Asleep at the Wheel | all | most starters with exactly 0 points, empty slots included; **awarded only when at least one exists** | count | higher points left on the bench, then co-winners | "Started 2 players who scored 0." | no |

The owner chose the enabled awards: eight at first, then Nail-biter was switched on before Phase 3 (2026-10-02), making nine. The other two are defined so they can be switched on in `config.yaml` without a spec change.

Rules shared by every award:
- **Co-winners** means each tied team gets its own row with the same value. Exact ties are rare, except at 100% efficiency, which is why `perfect_lineup` has a tiebreak.
- If no team is eligible (e.g. no losing team in a week with no games), the award is skipped that week.
- Rankings in captions ("3rd-best") are by points among all teams that week.
- Numbers in captions use the display rules: points to 1 decimal place, percentages as whole numbers.
- Display names follow `UI_GUIDE.md` sentence case: Top score, Lowest score, Heartbreaker, Robbery, Blowout, Nail-biter, Bench blunder, Perfect lineup, MVP, Pickup of the week, Asleep at the wheel.
- Caption details not shown in the table: a Pickup of the week added before `season_start_date` reads "added … before the season"; a free-agent add reads "added as a free agent"; a Perfect lineup below 100% reads "Got 87% of the points the best lineup would have scored."; Asleep at the wheel uses "1 player" in the singular. If two players on the same team tie for MVP or Pickup of the week, the team gets one row naming both.

**Inputs.** `team_weeks`: `week`, `roster_id`, `points`, `opponent_roster_id`, `margin`, `result`. `player_weeks`: `player_id`, `full_name`, `is_starter`, `is_empty_slot`, `points`. `transactions`: `roster_id`, `player_id`, `action`, `type`, `week`, `created_at`. `teams`: `team_name`. Metric 3: *B* and *E* per team-week.

**Parameters** (`config.yaml`):

| Key | Default | Meaning |
|---|---|---|
| `metrics.awards.enabled` | `top_score`, `lowest_score`, `heartbreaker`, `robbery`, `blowout`, `nail_biter`, `bench_blunder`, `mvp`, `pickup_of_the_week` | Awards shown each week, in display order. An unknown key stops the run |

Pickup of the Week has **no recency limit** (owner decision): any waiver or free-agent pickup this season qualifies.

**Edge cases.**

| Case | Rule |
|---|---|
| Ties | Co-winners by default; tiebreaks as listed in the table (owner decision) |
| Playoff weeks | **Every week** (owner decision). Score and lineup awards consider every team; matchup awards (`heartbreaker`, `robbery`, `blowout`, `nail_biter`) consider only teams with a game that week. Consolation-bracket and placement games (e.g. 5th place) count as games, since Sleeper pairs them like any other (owner decision 2026-10-03) |
| Median game | Ignored. Heartbreaker and Robbery are head-to-head only |
| Empty starting slots | Their lost points show up in Bench Blunder through metric 3, and in Asleep at the Wheel if enabled |
| Perfect lineups and Bench blunder | A team that left 0 points on the bench is not eligible; if every lineup that week was perfect, the award is skipped (Claude's reading of "no team is eligible", 2026-10-02) |
| Players added mid-week | Count for Pickup of the Week: a player added on Saturday and started on Sunday qualifies, because the add is in that week's transactions. Preseason adds count too |
| Pickup history | Only the team's most recent acquisition of the player counts. A player added off waivers and later traded away and back counts as a trade, so he does not qualify. Drafted players never qualify |
| Head-to-head tie | A tied game is neither a win nor a loss, so neither team is eligible for Heartbreaker, Robbery, Blowout, or Nail-Biter that week |
| Small early-season samples | Not applicable: every award uses a single week. Season-long awards are a possible Phase 5 extra |

**Expected range.** One row per enabled award per week, more with co-winners and fewer when an award is skipped. Values lie within the ranges of their source metrics.

**Sanity checks.**
1. `top_score` value = that week's maximum `points`; `lowest_score` value = the minimum.
2. Every `heartbreaker` winner lost and every `robbery` winner won that week; the Heartbreaker's score ≥ every other loser's, and the Robbery winner's score ≤ every other winner's.
3. `blowout` value = the week's largest positive margin.
4. `bench_blunder` value equals metric 3's *B* for the winner.
5. The `mvp` player was a starter for the winning team that week, and no starter that week scored more.
6. The `pickup_of_the_week` player was a starter for the winning team, and that team's most recent add of him (at or before that week) was a `waiver` or `free_agent` transaction.
7. Every key in `metrics.awards.enabled` is one of the keys above.
