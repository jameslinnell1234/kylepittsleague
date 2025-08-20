# tools/export_drafts.py
# Export Yahoo Fantasy NFL draft results for your recurring league (one CSV per season).
# Robust: prefers player_id, falls back to player_key, and recursively flattens Yahoo's nested player payloads.

import os, json
import pandas as pd
from collections import Counter
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

OUT_DIR = "public/data"
MANIFEST_PATH = os.path.join(OUT_DIR, "manifest.json")

# Optionally lock to an exact league name (case-sensitive). Leave None to auto-detect.
PREFERRED_LEAGUE_NAME = None  # e.g., "Kyle Pitts League"

def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

def build_team_maps(lg):
    name_by_key, mgr_by_key = {}, {}
    # standings usually cleanest
    try:
        for t in lg.standings() or []:
            if isinstance(t, dict):
                tk = t.get("team_key")
                if tk:
                    name_by_key[tk] = t.get("name", tk)
                    mgrs = t.get("managers") or []
                    nick = ""
                    if isinstance(mgrs, list) and mgrs and isinstance(mgrs[0], dict):
                        nick = mgrs[0].get("nickname", "") or mgrs[0].get("name", "")
                    mgr_by_key[tk] = nick
    except Exception:
        pass
    # teams() fallback
    try:
        for t in lg.teams() or []:
            if isinstance(t, dict):
                tk = t.get("team_key")
                if tk:
                    name_by_key.setdefault(tk, t.get("name", tk))
                    mgrs = t.get("managers") or []
                    if isinstance(mgrs, list) and mgrs and isinstance(mgrs[0], dict):
                        mgr_by_key.setdefault(tk, mgrs[0].get("nickname", "") or mgrs[0].get("name", ""))
            elif isinstance(t, str):
                name_by_key.setdefault(t, t); mgr_by_key.setdefault(t, "")
    except Exception:
        pass
    return name_by_key, mgr_by_key

# --------- NEW: deep flattener for Yahoo's nested player payloads ----------
def _flatten_player_node(node) -> dict:
    """
    Yahoo often returns: {'player': [ [ {...},{...},... ], {'player_stats':...} ]}
    Recursively walk lists/dicts to produce a flat dict with keys like
    player_id, player_key, name (dict), primary_position, editorial_team_abbr, etc.
    """
    flat = {}

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("player_stats", "player_points"):
                    # we don't need scoring for identity; still walk in case keys appear inside
                    walk(v)
                    continue
                if k == "name" and isinstance(v, dict):
                    flat["name"] = v
                elif isinstance(v, (list, dict)):
                    walk(v)
                else:
                    flat[k] = v
        elif isinstance(x, list):
            for item in x:
                walk(item)

    # node may be {'player': ...} or already inside that
    if isinstance(node, dict) and "player" in node:
        walk(node["player"])
    else:
        walk(node)
    return flat
# --------------------------------------------------------------------------

def fetch_players_via_yhandler(lg, player_ids, year_for_debug=None):
    """
    Directly call:
      league/{league_id}/players;player_keys=GAMEID.p.<pid>,...
    Build two dicts:
      id_map:  player_id -> {player, position, editorial_team_abbr}
      key_map: player_key -> same (fallback)
    """
    id_map, key_map = {}, {}
    if not player_ids:
        return id_map, key_map

    lid = lg.league_id                  # e.g., "449.l.453482"
    game_id = lid.split(".")[0]         # e.g., "449"
    keys = [f"{game_id}.p.{pid}" for pid in player_ids if str(pid).strip()]

    wrote_debug = False
    for batch in chunked(keys, 24):
        key_str = ",".join(batch)
        path = f"league/{lid}/players;player_keys={key_str}/stats"
        try:
            data = lg.yhandler.get(path)
        except Exception as e:
            print("WARN fetch error:", e)
            continue

        if (not wrote_debug) and year_for_debug:
            try:
                with open(os.path.join(OUT_DIR, f"_raw_players_{year_for_debug}.json"), "w") as f:
                    json.dump(data, f, indent=2)
                wrote_debug = True
                print(f"DEBUG wrote raw response: public/data/_raw_players_{year_for_debug}.json")
            except Exception:
                pass

        try:
            fc = data.get("fantasy_content", {})
            league = fc.get("league")
            players = None
            if isinstance(league, list):
                for item in league:
                    if isinstance(item, dict) and "players" in item:
                        players = item["players"]; break
            elif isinstance(league, dict) and "players" in league:
                players = league["players"]
            if players is None:
                players = fc.get("players")

            if isinstance(players, dict):
                count = int(players.get("count", 0))
                for i in range(count):
                    node = players.get(str(i))
                    if not isinstance(node, dict):
                        continue
                    p = _flatten_player_node(node)

                    pid = str(p.get("player_id", "")).strip()
                    pkey = p.get("player_key", "")
                    # name
                    name = ""
                    nm = p.get("name")
                    if isinstance(nm, dict):
                        name = nm.get("full") or nm.get("first") or ""
                    elif isinstance(nm, str):
                        name = nm
                    pos = p.get("primary_position") or p.get("display_position") or ""
                    nfl = p.get("editorial_team_abbr") or p.get("editorial_team_key") or ""

                    row = {"player": name, "position": pos, "editorial_team_abbr": nfl}
                    if pid:
                        id_map[pid] = row
                    if pkey:
                        key_map[pkey] = row
            else:
                print("WARN: unexpected players payload shape")
        except Exception as e:
            print("WARN parse error:", e)

    return id_map, key_map

def get_league_meta(lg, lid):
    s = lg.settings()
    return int(s.get("season")), (s.get("name") or f"league-{lid}")

def export_one_league(lg, lid, year):
    draft = lg.draft_results() or []
    if not draft:
        return None

    df = pd.DataFrame(draft)
    for c in ["round","pick","team_key","player_id","player_key","player_name","cost"]:
        if c not in df.columns: df[c] = ""

    # team/manager names
    team_name_by_key, mgr_name_by_key = build_team_maps(lg)
    df["team"] = df["team_key"].map(lambda k: team_name_by_key.get(k, k))
    df["manager"] = df["team_key"].map(lambda k: mgr_name_by_key.get(k, ""))

    # Prefer **player_id**; if missing, derive from player_key
    df["player_id_norm"] = df["player_id"].astype(str).str.strip()
    missing_pid = df["player_id_norm"].eq("") & df["player_key"].astype(str).str.contains(r"\.p\.", na=False)
    df.loc[missing_pid, "player_id_norm"] = df.loc[missing_pid, "player_key"].astype(str).str.split(".p.", n=1).str[-1]
    unique_pids = sorted(set(pid for pid in df["player_id_norm"].tolist() if pid))

    # Fetch maps
    id_map, key_map = fetch_players_via_yhandler(lg, unique_pids, year_for_debug=year)

    # Fill from id_map first, then key_map, then draft-supplied player_name
    def map_name(row):
        pid = row["player_id_norm"]; k = row.get("player_key")
        return id_map.get(pid, {}).get("player") or (key_map.get(str(k), {}).get("player") if k else "") or str(row.get("player_name") or "")

    def map_pos(row):
        pid = row["player_id_norm"]; k = row.get("player_key")
        return id_map.get(pid, {}).get("position") or (key_map.get(str(k), {}).get("position") if k else "") or ""

    def map_nfl(row):
        pid = row["player_id_norm"]; k = row.get("player_key")
        return id_map.get(pid, {}).get("editorial_team_abbr") or (key_map.get(str(k), {}).get("editorial_team_abbr") if k else "") or ""

    df["player"] = df.apply(map_name, axis=1)
    df["position"] = df.apply(map_pos, axis=1)
    df["editorial_team_abbr"] = df.apply(map_nfl, axis=1)

    filled = int((df["player"].astype(str) != "").sum())
    print(f"DEBUG {year}: filled names {filled}/{len(df)}")

    out_cols = ["round","pick","team","manager","player","position","editorial_team_abbr","cost"]
    return df[out_cols]

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    sc = OAuth2(None, None, from_file="oauth2.json")
    gm = yfa.Game(sc, "nfl")
    league_ids = gm.league_ids()

    # Find your recurring league across seasons
    meta = []
    for lid in league_ids:
        lg = gm.to_league(lid)
        try:
            y, name = get_league_meta(lg, lid)
            meta.append((lid, y, name))
        except Exception:
            continue
    if not meta:
        print("No leagues found."); return

    if PREFERRED_LEAGUE_NAME:
        target_name = PREFERRED_LEAGUE_NAME
    else:
        target_name, _ = Counter(name for _,_,name in meta).most_common(1)[0]
        print(f"Using detected recurring league: {target_name}")

    target = [(lid, y) for (lid, y, name) in meta if name == target_name]
    target.sort(key=lambda t: t[1])  # oldest → newest

    seasons = []
    for lid, year in target:
        lg = gm.to_league(lid)
        out_df = export_one_league(lg, lid, year)
        if out_df is None:
            print(f"ℹ️  No draft data for {year} (league {lid})"); continue
        csv_path = f"{OUT_DIR}/draft_results_{year}.csv"
        out_df.to_csv(csv_path, index=False)
        seasons.append({"year": year, "draft": f"/data/{os.path.basename(csv_path)}"})
        print(f"✔ Saved {csv_path} ({len(out_df)} rows)")

    seasons.sort(key=lambda x: x["year"], reverse=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump({"seasons": seasons}, f, indent=2)
    print(f"✔ Updated {MANIFEST_PATH}")

if __name__ == "__main__":
    main()
