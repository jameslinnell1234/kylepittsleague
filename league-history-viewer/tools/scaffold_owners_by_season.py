#RUN THIS AFTER YOU HAVE RUN GENERATE_OWNER_TEMPLATE_COMBO.PY AND IT WILL CREATE OWNER_BY_SEASON.CSV THEN YOU ADD THE MANAGER NAMES (CHRIS, GRAHAM ETC) MANUALLY
#!/usr/bin/env python3
import json
from pathlib import Path
import pandas as pd

DATA = Path("public/data")
OWNERS_TEMPLATE = DATA / "owners_template.json"   # you already have this (season → [{team_key, team_name}])
OWNERS_BY_SEASON_CSV = DATA / "owners_by_season.csv"

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    if not OWNERS_TEMPLATE.exists():
        raise SystemExit(f"Missing {OWNERS_TEMPLATE}. Run your template generator first.")
    tmpl = json.loads(OWNERS_TEMPLATE.read_text())

    rows = []
    for season, teams in sorted(tmpl.items(), key=lambda kv: int(kv[0])):
        for t in teams:
            rows.append({
                "season": int(season),
                "team_key": t.get("team_key",""),
                "team_name": t.get("team_name",""),
                "manager": ""  # fill this once manually
            })
    df = pd.DataFrame(rows, columns=["season","team_key","team_name","manager"])
    df.to_csv(OWNERS_BY_SEASON_CSV, index=False)
    print(f"✔ Wrote {OWNERS_BY_SEASON_CSV} ({len(df)} rows).")
    print("→ Open it, fill 'manager' for each row (your preferred display). Save, then run the exporter.")
if __name__ == "__main__":
    main()
