"""The "How this works" copy (docs/UI_GUIDE.md section 9), written for league members, not statisticians.

Run with:  python -m sleeper_dash.dashboard.explainer   (prints the draft as plain text)

Every weight and threshold is filled in from config.yaml (and league size, the median game, and the
playoff start from Sleeper's league settings) each time the copy is built, so the words can never
drift from the model. The owner approved this copy on 2026-10-02; any change to the wording needs
the owner's approval again before it is published.
"""

import math

WEIGHT_ORDER = ["season_scoring", "recent_form", "roster_strength", "results"]


def pct(fraction):
    """0.35 -> '35%'."""
    return f"{round(fraction * 100)}%"


def ordinal(n):
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def number(value):
    """20 -> '20', 2.5 -> '2.5'."""
    return f"{value:g}"


def share_of_weeks(fraction):
    """0.10 -> 'one week in ten'; other shares as a percentage of weeks."""
    return "one week in ten" if abs(fraction - 0.10) < 1e-9 else f"about {pct(fraction)} of weeks"


def sections(params, league):
    """The copy as a list of {heading, paragraphs}. params: config.yaml metrics. league: teams, median_game, playoff_week_start."""
    power, consistency = params["power"], params["consistency"]
    w = power["weights"]
    teams, others = league["teams"], league["teams"] - 1
    scale, shrink, recent = power["scale"], power["shrink_weeks"], power["recent_weeks"]
    reach = scale * (teams - 1) / math.sqrt(teams)             # the furthest a score can sit from 50
    low, high = 50 - reach, 50 + reach
    three_quarters = 3 * shrink                                 # t / (t + k) reaches 75% at t = 3k
    last_regular = league["playoff_week_start"] - 1
    top_half = teams // 2
    beaten = max(1, round(others * 8 / 11))                     # the all-play example: beat about 73% of the league
    efficiency_rule = "total points scored ÷ total best possible points"

    out = [
        {"heading": "How this works", "paragraphs": [
            "Everything on this page is calculated from Sleeper's own scores for our league. Nothing is projected, "
            "and nothing is adjusted by hand. Each update recalculates the whole season and checks that every record "
            "and every point total matches Sleeper's standings before anything is published.",
        ]},
        {"heading": "The power score", "paragraphs": [
            f"One number for how strong a team is right now. 50 is an exactly average team; higher is better. "
            f"With {teams} teams it can't go below {low:.1f} or above {high:.1f}, though in practice it stays much closer to 50.",
            "It blends four ingredients:",
            f"Season scoring ({pct(w['season_scoring'])}): average points a week this season.",
            f"Recent form ({pct(w['recent_form'])}): average points a week over the last {recent} weeks (every week so far, "
            f"until {recent} have been played), so a team that is heating up or falling off shows it sooner.",
            f"Roster strength ({pct(w['roster_strength'])}): average points a week the team's best possible lineup would have "
            "scored. It measures the talent on the roster, bench included, whether or not the manager started the right players.",
            f"Head-to-head wins ({pct(w['results'])}): the share of head-to-head games won in the regular season. "
            + ("The weekly median game is left out here: a median win depends only on a team's own score, which season scoring "
               f"and recent form already count ({pct(w['season_scoring'] + w['recent_form'])} between them)."
               if league["median_game"] else ""),
            "For each ingredient, a team is compared with the league average that week, measured in typical gaps between "
            f"teams (standard deviations). One typical gap above average is worth {number(scale)} points of power score. "
            "The four results are then blended using the weights above. Tap any team in the rankings to see exactly how much "
            "each ingredient added to its score.",
            f"Early in the season there is little data, so every score is pulled toward 50. In week 1 the spread is "
            f"{pct(1 / (1 + shrink))} of its full size, and it reaches 75% by week {three_quarters}. This only changes how "
            "spread out the scores look, never the order of the rankings.",
            "Ties are broken by season scoring, then head-to-head record.",
        ]},
    ]
    if league["median_game"]:
        out.append({"heading": "Records", "paragraphs": [
            f"Our league plays two games every week: one against your head-to-head opponent and one against the league median. "
            f"Score in the top {top_half} of {teams} and you win the median game too, so each week is worth up to two wins. "
            "The records on this page count both, exactly like Sleeper's standings.",
        ]})
    out += [
        {"heading": "All-play record", "paragraphs": [
            f"Your record if you had played every team every week. Each week you get a win for every team you outscored and a "
            f"loss for every team that outscored you, so the week's top score goes {others}–0 and the lowest goes 0–{others}. "
            "It shows how good your scores were, without the luck of who you happened to face.",
        ]},
        {"heading": "Expected wins and luck", "paragraphs": [
            f"Expected wins are the wins your scores deserved. Each week you earn your all-play share: beat {beaten} of the other "
            f"{others} teams and that week is worth {beaten / others:.2f} of a head-to-head win, the chance you would have beaten an "
            "opponent picked at random."
            + (" The median game is counted as earned, because it depends only on your own score." if league["median_game"] else ""),
            "Luck is actual wins minus expected wins. +1.5 means the schedule has handed you one and a half wins your scores "
            "didn't earn; −1.5 means it has taken that many away. Across the league, luck adds up to zero every week. "
            f"Luck covers the regular season (weeks 1–{last_regular}), the games that decide the standings.",
        ]},
        {"heading": "Lineup efficiency", "paragraphs": [
            "Your best possible lineup is the highest score you could have started that week, with hindsight, using only the "
            "players on your roster (bench and injured reserve included) and the league's lineup slots.",
            f"Efficiency is the points you actually scored as a share of that best possible score. Season efficiency is "
            f"{efficiency_rule}, so a big week counts for more than a quiet one. Points left on the bench are the gap.",
        ]},
        {"heading": "Consistency", "paragraphs": [
            "The ± number is how much a team's score swings from week to week. To allow for weeks when the whole league scores "
            "high or low, each score is first compared with that week's league median; the ± is the standard deviation of those "
            "differences. Lower means steadier.",
            f"A typical bad week is the {ordinal(consistency['floor_pct'] * 100)} percentile of a team's weekly scores and a typical "
            f"good week is the {ordinal(consistency['ceiling_pct'] * 100)}: roughly {share_of_weeks(consistency['floor_pct'])} falls below "
            f"the first, and {share_of_weeks(1 - consistency['ceiling_pct'])} goes above the second. A boom week is {number(consistency['boom_margin'])} or more points above that week's "
            f"league median; a bust week is {number(consistency['bust_margin'])} or more below.",
            f"Consistency appears once teams have played {consistency['min_weeks']} weeks.",
        ]},
        {"heading": "Strength of schedule", "paragraphs": [
            f"How strong your opponents are: the average points a week of the teams you play, compared with the average of the "
            f"other {others} teams. +5 means your opponents score 5 more points a week than average, a tougher road; −5 means an "
            "easier one.",
            "Each opponent is judged on its average over the whole season so far, not just the points it scored against you, "
            "because in fantasy football an opponent's score doesn't depend on who it plays. \"Remaining\" uses the teams still "
            f"on your regular-season schedule. Strength of schedule appears once {params['schedule']['min_weeks']} weeks are complete.",
        ]},
        {"heading": "Why past weeks can change", "paragraphs": [
            "Sleeper sometimes corrects player stats a few days after a game, for example when a catch is ruled a fumble on review. "
            "Every update recalculates the whole season from Sleeper's latest scores, so a correction can shift earlier numbers "
            "slightly, including last week's rankings, luck, and awards. The numbers on this page always match Sleeper's current scores.",
        ]},
    ]
    return out


def as_text(copy):
    blocks = []
    for section in copy:
        blocks.append(section["heading"])
        blocks += [p for p in section["paragraphs"] if p]
    return "\n\n".join(blocks)


def main():
    from sleeper_dash.config import load_config
    from sleeper_dash.pipeline import league_facts
    from sleeper_dash.transform import read_raw

    config = load_config()
    print(as_text(sections(config.metrics, league_facts(read_raw(config.season, "league.json")))))


if __name__ == "__main__":
    main()
