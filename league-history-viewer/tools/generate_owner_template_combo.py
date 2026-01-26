# RUN THIS SCRIPT - IT PRODUCES OWNERS_TEMPLATE.JSON - THEN RUN SCAFFOLD_OWNERS_BY_SEASON.PY 
#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from yahoo_oauth import OAuth2
from yahoo_fantasy_api import Game

ANCHOR_LEAGUE_KEY = "461.l.54130"
OUT_DIR = Path("public/data")
TEMPLATE_JSON = OUT_DIR / "owners_template.json"

def load_oauth():
    sc = OAuth2(None, None, from_file="oauth2.json")
    if not sc.token_is_valid():
        sc.refresh_access_token()
    return sc

def league_key_from_renew_string(renew_str: str) -> str:
    try:
        gid, lid = renew_str.split("_", 1)
        return f"{gid}.l.{lid}"
    except Exception:
        return ""

def walk_chain(gm: Game, anchor: str) -> List[str]:
    seen, q, keys = set(), [anchor], set()
    while q:
        lid = q.pop()
        if not lid or lid in seen:
            continue
        seen.add(lid)
        try:
            lg = gm.to_league(lid)
            st = lg.settings()
        except Exception:
            continue
        keys.add(lid)
        prev = st.get("renew")
        if isinstance(prev, str):
            pk = league_key_from_renew_string(prev)
            if pk and pk not in seen:
                q.append(pk)
        nxt = st.get("renewed")
        if isinstance(nxt, str):
            nk = league_key_from_renew_string(nxt)
            if nk and nk not in seen:
                q.append(nk)

    def season_of(k: str) -> int:
        try:
            return int(gm.to_league(k).settings().get("season", 0))
        except Exception:
            return 0

    return sorted(keys, key=season_of)

def squash(node: Any) -> Dict[str, Any]:
    if isinstance(node, dict): return node
    if not isinstance(node, list): return {}
    out: Dict[str, Any] = {}
    for el in node:
        if isinstance(el, dict):
            out.update(el)
    return out

def normalize_from_team_node(node: Any) -> Tuple[str, str]:
    """Return (team_key, team_name) from any of Yahoo's 'team' shapes."""
    t = node
    if isinstance(t, list):
        t = squash(t)
    if isinstance(t, dict) and "team" in t:
        inner = t["team"]
        if isinstance(inner, list):
            inner = squash(inner)
        if isinstance(inner, dict):
            t = {**t, **inner}
    if not isinstance(t, dict):
        return "", ""

    team_key = str(t.get("team_key", "")).strip()
    team_name = str(t.get("name", "") or t.get("team_name", "")).strip()
    return team_key, team_name

def get_from_raw_teams(gm: Game, league_key: str) -> List[Dict[str, str]]:
    """Use league/{league_key}/teams (no ?format param)."""
    try:
        data = gm.yhandler.get(f"league/{league_key}/teams")
    except Exception as e:
        # write a small marker for debugging
        (OUT_DIR / f"_owntpl_raw_teams_error_{league_key.replace('.', '_')}.txt").write_text(str(e))
        return []

    # decode to dict if needed
    if isinstance(data, (bytes, str)):
        try:
            data = json.loads(data)
        except Exception:
            return []

    # dump raw for inspection
    (OUT_DIR / f"_owntpl_raw_teams_{league_key.replace('.', '_')}.json").write_text(json.dumps(data, indent=2))

    fc = data.get("fantasy_content")
    if not isinstance(fc, dict):
        return []

    league = fc.get("league")
    ln = None
    if isinstance(league, list):
        for item in league:
            if isinstance(item, dict) and "teams" in item:
                ln = item
                break
        if ln is None and len(league) >= 2 and isinstance(league[1], dict):
            ln = league[1]
    elif isinstance(league, dict):
        ln = league
    if not isinstance(ln, dict):
        return []

    teams_node = ln.get("teams")
    items: List[Any] = []
    if isinstance(teams_node, dict):
        if "team" in teams_node and isinstance(teams_node["team"], list):
            items = teams_node["team"]
        else:
            for v in teams_node.values():
                if isinstance(v, dict) and "team" in v:
                    items.append(v["team"])
    elif isinstance(teams_node, list):
        items = teams_node

    out: List[Dict[str, str]] = []
    for item in items:
        tk, tn = normalize_from_team_node(item)
        if tk:
            out.append({"team_key": tk, "team_name": tn})
    return out

def get_from_raw_standings(gm: Game, league_key: str) -> List[Dict[str, str]]:
    """Use league/{league_key}/standings and extract team list."""
    try:
        data = gm.yhandler.get(f"league/{league_key}/standings")
    except Exception as e:
        (OUT_DIR / f"_owntpl_raw_standings_error_{league_key.replace('.', '_')}.txt").write_text(str(e))
        return []

    if isinstance(data, (bytes, str)):
        try:
            data = json.loads(data)
        except Exception:
            return []

    (OUT_DIR / f"_owntpl_raw_standings_{league_key.replace('.', '_')}.json").write_text(json.dumps(data, indent=2))

    fc = data.get("fantasy_content")
    if not isinstance(fc, dict):
        return []

    league = fc.get("league")
    ln = None
    if isinstance(league, list):
        for item in league:
            if isinstance(item, dict) and "standings" in item:
                ln = item
                break
        if ln is None and len(league) >= 2 and isinstance(league[1], dict):
            ln = league[1]
    elif isinstance(league, dict):
        ln = league
    if not isinstance(ln, dict):
        return []

    standings = ln.get("standings")
    if not isinstance(standings, dict):
        return []
    teams_node = standings.get("teams")

    items: List[Any] = []
    if isinstance(teams_node, dict):
        if "team" in teams_node and isinstance(teams_node["team"], list):
            items = teams_node["team"]
        else:
            for v in teams_node.values():
                if isinstance(v, dict) and "team" in v:
                    items.append(v["team"])
    elif isinstance(teams_node, list):
        items = teams_node

    out: List[Dict[str, str]] = []
    for item in items:
        tk, tn = normalize_from_team_node(item)
        if tk:
            out.append({"team_key": tk, "team_name": tn})
    return out

def get_from_wrapper_standings(lg) -> List[Dict[str, str]]:
    """Final fallback: yahoo_fantasy_api.League.standings() → normalize."""
    try:
        rows = lg.standings()
    except Exception:
        rows = []
    (OUT_DIR / f"_owntpl_lib_standings_dump_{lg.settings().get('season', 0)}.json").write_text(json.dumps(rows, indent=2))
    out: List[Dict[str, str]] = []
    for row in rows or []:
        tk, tn = normalize_from_team_node(row)
        if tk:
            out.append({"team_key": tk, "team_name": tn})
    return out

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sc = load_oauth()
    gm = Game(sc, "nfl")

    chain = walk_chain(gm, ANCHOR_LEAGUE_KEY)
    if not chain:
        print("No leagues found in chain; exiting.")
        return

    result: Dict[str, List[Dict[str, str]]] = {}
    for lid in chain:
        lg = gm.to_league(lid)
        season = int(lg.settings().get("season", 0))

        # Try 1: raw teams
        rows = get_from_raw_teams(gm, lid)
        source = "raw_teams"

        # Try 2: raw standings
        if not rows:
            rows = get_from_raw_standings(gm, lid)
            source = "raw_standings"

        # Try 3: wrapper standings
        if not rows:
            rows = get_from_wrapper_standings(lg)
            source = "wrapper_standings"

        rows = sorted(rows, key=lambda r: r["team_key"])
        result[str(season)] = rows
        print(f"DEBUG {season}: {len(rows)} teams via {source}")

    TEMPLATE_JSON.write_text(json.dumps(result, indent=2))
    print(f"✔ Wrote {TEMPLATE_JSON}")
    print("Inspect public/data/_owntpl_* debug files if any season still shows 0 teams.")

if __name__ == "__main__":
    main()
