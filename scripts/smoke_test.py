"""One-off Phase 0 check: can we reach Sleeper, and what are the league's settings?

Run with:  python scripts/smoke_test.py
Makes two read-only API calls and saves nothing.
"""

import requests

from sleeper_dash.config import load_config

BASE_URL = "https://api.sleeper.app/v1"

# Scoring keys worth eyeballing, with plain-language labels.
KEY_SCORING = {
    "rec": "Points per reception (PPR)",
    "bonus_rec_te": "Extra points per TE reception",
    "pass_yd": "Points per passing yard",
    "pass_td": "Points per passing TD",
    "pass_int": "Points per interception thrown",
    "rush_yd": "Points per rushing yard",
    "rush_td": "Points per rushing TD",
    "rec_yd": "Points per receiving yard",
    "rec_td": "Points per receiving TD",
    "fum_lost": "Points per fumble lost",
}


def get(path):
    response = requests.get(f"{BASE_URL}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def main():
    config = load_config()
    league = get(f"/league/{config.league_id}")
    state = get("/state/nfl")

    settings = league.get("settings", {})
    scoring = league.get("scoring_settings", {})

    print("LEAGUE")
    print(f"  Name:                {league.get('name')}")
    print(f"  Season:              {league.get('season')}")
    print(f"  Teams:               {settings.get('num_teams', league.get('total_rosters'))}")
    print(f"  Status:              {league.get('status')}")
    print(f"  Playoff start week:  {settings.get('playoff_week_start')}")
    median = settings.get("league_average_match")
    print(f"  Weekly median game:  {'yes' if median == 1 else 'no'} (league_average_match = {median})")
    print(f"  Previous league ID:  {league.get('previous_league_id')}")

    print()
    print("ROSTER POSITIONS")
    positions = league.get("roster_positions", [])
    print(f"  {', '.join(positions)}")
    starters = [p for p in positions if p != "BN"]
    print(f"  ({len(starters)} starters, {positions.count('BN')} bench, {len(positions)} total)")

    print()
    print("KEY SCORING SETTINGS")
    for key, label in KEY_SCORING.items():
        value = scoring.get(key, "not set")
        print(f"  {label:<33} {key:<13} {value}")
    print(f"  ({len(scoring)} scoring settings in total)")

    print()
    print("NFL STATE")
    print(f"  Season:              {state.get('season')}")
    print(f"  Season type:         {state.get('season_type')}")
    print(f"  Week:                {state.get('week')}")


if __name__ == "__main__":
    main()
