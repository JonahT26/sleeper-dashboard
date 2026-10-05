"""The History section (owner-approved design, 2026-10-05; UI_GUIDE.md "History"): champions, all-time records,
last season's luckiest and unluckiest teams, and the highest weekly score, from every finished season.

Pure: tables in, plain values and formatted strings out. A season counts once Sleeper's bracket names its
champion. Records are regular-season records including median games (the ladder's record); playoff results
count only as appearances (seeded 1-6 in the winners bracket) and titles (winner of the final).
Managers are matched across seasons by Sleeper owner ID (the managers table), never by team name.
"""

import pandas as pd

EN_DASH, MINUS = "–", "−"


def _signed(value):
    text = f"{abs(value):.1f}"
    return text if text == "0.0" else ("+" if value > 0 else MINUS) + text


def _record(wins, losses, ties):
    return EN_DASH.join(str(int(n)) for n in ((wins, losses, ties) if ties else (wins, losses)))


def _span(seasons):
    return str(seasons[0]) if len(seasons) == 1 else f"{seasons[0]}{EN_DASH}{seasons[-1]}"


def finished_seasons(bracket):
    """Seasons whose winners bracket names a champion, oldest first."""
    final = bracket[(bracket["place"] == 1) & bracket["winner_roster_id"].notna()]
    return sorted(int(s) for s in final["season"].unique())


def playoff_teams(bracket):
    """(season, roster_id) of every team seeded into the winners bracket: first-round teams plus the byes."""
    first_round = bracket[bracket["round"] == 1]
    byes = bracket[(bracket["round"] == 2) & bracket["t1_from"].isna() & bracket["t1_roster_id"].notna()]
    pairs = {(int(g.season), int(g.t1_roster_id)) for g in first_round.itertuples() if pd.notna(g.t1_roster_id)}
    pairs |= {(int(g.season), int(g.t2_roster_id)) for g in first_round.itertuples() if pd.notna(g.t2_roster_id)}
    pairs |= {(int(g.season), int(g.t1_roster_id)) for g in byes.itertuples()}
    return pairs


def history_view(tables, current_season):
    """Everything the History section shows, or None when no season has finished yet (the section is hidden)."""
    needed = ["teams", "managers", "metrics_season", "team_weeks", "winners_bracket"]
    if any(name not in tables for name in needed):
        return None
    bracket = tables["winners_bracket"]
    seasons = [s for s in finished_seasons(bracket) if s <= current_season]
    if not seasons:
        return None
    teams, managers = tables["teams"], tables["managers"].astype({"owner_id": str}).set_index("owner_id")
    owner = {(int(t.season), int(t.roster_id)): str(t.owner_id) for t in teams.itertuples()}
    name = managers["display_name"].to_dict()

    # Final regular-season standings of each finished season (metrics_season stops changing after the regular season).
    standings = tables["metrics_season"]
    standings = standings[standings["season"].isin(seasons)]
    final = standings[standings["through_week"] == standings.groupby("season")["through_week"].transform("max")].copy()
    final["owner_id"] = [owner[(int(s), int(r))] for s, r in zip(final["season"], final["roster_id"])]

    champions = bracket[(bracket["place"] == 1) & bracket["season"].isin(seasons)]
    champion_of = {int(g.season): owner[(int(g.season), int(g.winner_roster_id))] for g in champions.itertuples()}
    appearances = pd.Series([owner[p] for p in playoff_teams(bracket[bracket["season"].isin(seasons)])], dtype=object).value_counts()
    titles = pd.Series(list(champion_of.values()), dtype=object).value_counts()

    totals = final.groupby("owner_id").agg(seasons=("season", "nunique"), wins=("wins", "sum"), losses=("losses", "sum"),
                                           ties=("ties", "sum"))
    games = totals["wins"] + totals["losses"] + totals["ties"]
    totals["win_pct"] = (totals["wins"] + 0.5 * totals["ties"]) / games
    totals["playoffs"] = appearances.reindex(totals.index).fillna(0).astype(int)
    totals["titles"] = titles.reindex(totals.index).fillna(0).astype(int)
    totals = totals.reset_index().sort_values(["win_pct", "titles", "wins", "owner_id"], ascending=[False, False, False, True])

    current_teams = teams[teams["season"] == current_season].set_index(teams[teams["season"] == current_season]["owner_id"].astype(str))
    rows = {"current": [], "former": []}
    for t in totals.itertuples():
        group = "current" if t.owner_id in current_teams.index else "former"
        rows[group].append({
            "manager": name[t.owner_id], "team": current_teams.at[t.owner_id, "team_name"] if group == "current" else None,
            "seasons": int(t.seasons), "record": _record(t.wins, t.losses, t.ties),
            # Seasons share the name cell so the table fits a 360px phone (UI_GUIDE.md "History").
            "detail": (f"{int(t.seasons)} season{'s' if t.seasons != 1 else ''}"
                       + (f"; now {current_teams.at[t.owner_id, 'team_name']}" if group == "current" else "")),
            "win_pct": f"{round(t.win_pct * 100)}%", "playoffs": int(t.playoffs), "titles": int(t.titles),
        })

    last = seasons[-1]
    luck = final[final["season"] == last].sort_values(["luck", "roster_id"])

    def luck_line(row):
        return {"manager": name[row.owner_id], "record": _record(row.wins, row.losses, row.ties),
                "expected": f"{row.expected_wins:.1f}", "luck": _signed(row.luck)}

    weeks = tables["team_weeks"]
    weeks = weeks[weeks["season"].isin(seasons)]
    best = weeks.sort_values(["points", "season", "week", "roster_id"], ascending=[False, True, True, True]).iloc[0]

    return {
        "span": _span(seasons), "last_season": last,
        "champions": [{"season": s, "manager": name[champion_of[s]]} for s in reversed(seasons)],
        "current": rows["current"], "former": rows["former"],
        "luckiest": luck_line(luck.iloc[-1]), "unluckiest": luck_line(luck.iloc[0]),
        "high_score": {"points": f"{best['points']:.1f}", "manager": name[owner[(int(best['season']), int(best['roster_id']))]],
                       "week": int(best["week"]), "season": int(best["season"])},
    }
