# Metrics specification

The source of truth for every metric. Code follows this file, not the other way round. Each definition here was proposed by Claude and confirmed or changed by the owner during the Phase 2 interview (started 2026-10-02). Any change to a definition needs the owner's approval and goes in this file first.

## Status

| # | Metric | Status |
|---|---|---|
| 1 | All-play record | **Confirmed** 2026-10-02 |
| 2 | Expected wins and luck | **Confirmed** 2026-10-02 |
| 3 | Lineup efficiency | **Confirmed** 2026-10-02 (one parameter pending) |
| 4 | Consistency | **Confirmed** 2026-10-02 |
| 5 | Strength of schedule | In interview |
| 6 | Power score | Not started |
| 7 | Weekly awards | Not started |

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

**Status:** confirmed by the owner, 2026-10-02.

**Meaning.** *Expected wins* is how many games your scores deserved to win against an average opponent. *Luck* is actual wins minus expected wins. Positive luck means your schedule handed you wins your scores didn't earn; negative means it took wins away.

**Formula.** For team *i* in regular-season week *w*:

| Quantity | Definition |
|---|---|
| Expected wins *xW₍ᵢ,w₎* | that week's all-play win % (metric 1) = (*W* + ½*T*) ÷ (*n₍w₎* − 1). This is the probability of beating an opponent drawn at random from that week's other teams |
| Actual wins *A₍ᵢ,w₎* | head-to-head result: 1 for a win, ½ for a tie, 0 for a loss |
| Luck *λ₍ᵢ,w₎* | *A₍ᵢ,w₎* − *xW₍ᵢ,w₎* |
| Season to date, through week *t* | Σ*xW*, Σ*A*, and Σ*λ* over regular-season weeks 1…*t* |

Example: the 4th-highest score of 12 beats 8 of the other 11 teams, so *xW* = 8/11 = 0.73. A loss that week gives luck −0.73; a win gives +0.27.

Display: expected wins to 1 decimal place (`UI_GUIDE.md`); luck as a signed number of wins, e.g. "+1.4".

**Record scale (owner decision).** Head-to-head only. The ladder shows the head-to-head record next to the all-play record ("4–1, all-play 41–14"), and actual wins, expected wins, and luck are all on the same scale of one game per week. This settles the Phase 1 open question about the ladder record. Sleeper's official record, which includes median games, is not shown on the ladder.

Why the median game doesn't change luck: a team's median-game result is fully determined by its own score (it wins exactly when all-play wins ≥ *N*/2), so its expected result always equals its actual result and its luck is always zero. Including median games would double the scale but leave luck unchanged.

**Model (owner decision).** All-play based, as above. The alternative, a score-distribution model of the probability of beating the actual opponent from each team's mean and SD, was rejected: it mixes team strength into luck, overlapping with the power score, and is unstable with few weeks of data.

**Inputs.** Metric 1 (weekly all-play *W*, *T*, and *n₍w₎*); `team_weeks`: `result`, `is_playoff`.

**Parameters.** None.

**Edge cases.**

| Case | Rule |
|---|---|
| Playoff weeks | **Excluded** (owner decision). Expected wins, actual wins, and luck cover the regular season only, because their job is to explain the regular-season standings. Weekly all-play values still exist for playoff weeks (metric 1). From week 15 on, season-to-date values stay at their end-of-regular-season totals |
| Head-to-head ties | ½ actual win, consistent with all-play ties |
| Median game | Not part of actual or expected wins (see Record scale) |
| Exact score ties with other teams | Handled through all-play ties (½ each) |
| Empty starting slots | No adjustment. The team's actual score stands |
| Players added mid-week | No adjustment. The team's actual score stands |
| Small early-season samples | No shrinkage. Luck describes results already banked rather than estimating talent, so it is valid from week 1 and simply starts close to zero |

**Expected range.**
- Weekly luck lies strictly between −1 and +1, and at most ±(*n₍w₎* − 2)/(*n₍w₎* − 1) = ±10/11, e.g. losing with the second-highest score.
- Season expected wins lie between 0 and the number of regular-season games played.
- The league's total luck is 0 every week, so the league average is 0.
- Weekly luck has a standard deviation of roughly 0.4 wins, so by the end of a 14-week regular season most teams should be within about ±3 wins.

**Sanity checks.**
1. In every regular-season week where all teams have a game, the league's luck sums to 0 (±0.000001), because total actual wins = *N*/2 = total expected wins.
2. 0 ≤ *xW₍ᵢ,w₎* ≤ 1 and −1 < *λ₍ᵢ,w₎* < 1 for every team-week.
3. A head-to-head win with the week's top score has *λ* = 0; a loss with the week's bottom score has *λ* = 0.
4. Season Σ*A* reproduces the head-to-head part of Sleeper's record: Sleeper's wins minus median wins (cross-check with `validate.py`).

---

## 3. Lineup efficiency

**Status:** confirmed by the owner, 2026-10-02. The soft-check warning threshold is still to be decided.

**Meaning.** *Optimal points* is the best score a team could have posted with hindsight, using only players on its roster that week. *Efficiency* is the share of that best score the team actually got. *Points left on the bench* is the gap between the two.

**Optimal lineup.** From the week's player pool, choose players to fill every starting slot in league settings `roster_positions` (every entry except `BN`), maximising total points, subject to:
- each player fills at most one slot;
- each player fills only slots his position allows (table below);
- every slot is filled whenever at least one unused eligible player is in the pool, even if all eligible players scored below zero.

Solved exactly as an assignment problem (slots × players).

| Slot | Eligible positions |
|---|---|
| QB, RB, WR, K, DEF | that position only |
| FLEX | RB, WR, TE |
| REC_FLEX | WR, TE |
| SUPER_FLEX | QB, RB, WR, TE |

The slot list is read from league settings each run. The eligibility table is Sleeper's rule, not a tunable parameter, so it is fixed in this spec. A slot name not in this table stops the run.

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
- `metrics.efficiency.ppts_warn_gap`: *pending owner decision*. The proposed warning threshold for the soft check against Sleeper's max points, in points per team-season.

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
