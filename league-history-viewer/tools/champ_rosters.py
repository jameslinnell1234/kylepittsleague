#run this at the end of the season to generate the rosters of the champion

import csv
import json
import os
from datetime import datetime
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

# ---------- Configuration ----------
OAUTH2_FILE = os.path.join(os.path.dirname(__file__), "..", "oauth2.json")
STANDINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "public", "data", "finishes.csv")
OUTPUT_JSON = os.path.join(os.path.dirname(__file__), "..", "public", "data", "champion_rosters.json")
# -----------------------------------

def load_champions(standings_path: str):
    """
    Read finishes.csv and return a list of dicts
    for each season's 1st-place finisher with their team_key.
    """
    champs = []
    with open(standings_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("place") == "1":
                champs.append({
                    "season": int(row["season"]),
                    "manager": row["manager"],
                    "team_key": row["team_key"],
                    "team_name": row["team_name"],
                })
    return champs


def fetch_roster(oauth: OAuth2, team_key: str):
    """
    Fetch the final roster for a given team_key, including player positions only.
    """
    team = yfa.Team(oauth, team_key)
    roster = team.roster(week=None)  # final roster for the season
    players = []
    for p in roster:
        players.append({
            "name": p.get("name", ""),
            "position": ",".join(p.get("eligible_positions", []))  # convert list to string
        })
    return players


def main():
    oauth = OAuth2(None, None, from_file=OAUTH2_FILE)
    champs = load_champions(STANDINGS_FILE)

    result = {"updated_at": datetime.utcnow().isoformat(), "champions": []}

    for champ in champs:
        print(f"Fetching {champ['season']} champion roster: {champ['team_name']} ({champ['manager']})")
        try:
            roster = fetch_roster(oauth, champ["team_key"])
        except Exception as e:
            print(f"  ! Error fetching roster for {champ['team_key']}: {e}")
            roster = []
        result["champions"].append({
            "season": champ["season"],
            "manager": champ["manager"],
            "team_name": champ["team_name"],
            "roster": roster
        })

    with open(OUTPUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(f"✔ Champion rosters written to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
