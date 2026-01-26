# THIS WILL GENERATE A NEW DRAFT_RESULT_2026.CSV FILE AND LEAVE THE PREVIOUS SEASONS DATA UNTOUCHED
# !/usr/bin/env python3
# tools/export_drafts.py
# Export all seasons; Manager names taken from owners_by_season.csv (priority),
# then owners.json team_keys (fallback), then Yahoo deep scan (last resort).
# Adds ADP (average draft position) + adp_diff (pick - adp).
# CSV columns: round,pick,manager,player,position,editorial_team_abbr,adp,adp_diff

import os, json, math
import pandas as pd
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
from typing import Any, Dict, List, Tuple, Iterable, Optional

OUT_DIR = "public/data"
OWNERS_JSON_PATH = os.path.join(OUT_DIR, "owners.json")
OWNERS_BY_SEASON_CSV = os.path.join(OUT_DIR, "owners_by_season.csv")
ANCHOR_LEAGUE_ID = "461.l.54130"  # your anchor
os.makedirs(OUT_DIR, exist_ok=True)

# ---------- small utils ----------
def chunked(seq: Iterable[Any], n: int) -> Iterable[List[Any]]:
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

def to_list(x: Any) -> List[Any]:
    if x is None: return []
    if isinstance(x, list): return x
    if isinstance(x, dict) and "count" in x:
        try: n = int(x.get("count", 0))
        except Exception: n = 0
        return [x.get(str(i)) for i in range(n)]
    return [x]

# ---------- load owner mappings (PRIORITY) ----------
def load_owners_by_season() -> Dict[int, Dict[str, str]]:
    """
    Reads public/data/owners_by_season.csv with columns:
      season,team_key,team_name,manager
    Returns: { season -> { team_key -> manager } }
    """
    out: Dict[int, Dict[str, str]] = {}
    if not os.path.exists(OWNERS_BY_SEASON_CSV):
        return out
    try:
        df = pd.read_csv(OWNERS_BY_SEASON_CSV, dtype=str).fillna("")
        for _, row in df.iterrows():
            try:
                season = int(str(row.get("season", "")).strip())
            except Exception:
                continue
            team_key = str(row.get("team_key", "")).strip()
            manager = str(row.get("manager", "")).strip()
            if not season or not team_key or not manager:
                continue
            out.setdefault(season, {})[team_key] = manager
    except Exception as e:
        print(f"• WARN: failed to read owners_by_season.csv: {e}")
    return out

def load_teamkey_overrides_from_owners_json() -> Dict[str, str]:
    """
    owners.json (if present) may include a 'team_keys' array:
      { "team_key": "<league_key.t.x>", "name": "<Manager Name>" }
    Returns team_key -> preferred manager display.
    """
    mapping: Dict[str, str] = {}
    if not os.path.exists(OWNERS_JSON_PATH):
        return mapping
    try:
        data = json.loads(open(OWNERS_JSON_PATH, "r").read() or "{}")
        for it in (data.get("team_keys") or []):
            tk = str(it.get("team_key", "")).strip()
            nm = str(it.get("name", "")).strip()
            if tk and nm:
                mapping[tk] = nm
    except Exception as e:
        print(f"• WARN: could not parse owners.json team_keys: {e}")
    return mapping

# ---------- deep team/manager scan (only as a last resort) ----------
def first_manager(managers_obj: Any) -> Dict[str, Any]:
    for cand in to_list(managers_obj):
        if not isinstance(cand, dict): continue
        inner = cand.get("manager") if isinstance(cand.get("manager"), dict) else cand
        if isinstance(inner, dict): return inner
    return {}

def deep_flatten_player(node: Any) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    def walk(x: Any):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("player_stats","player_points"): continue
                if k == "name" and isinstance(v, dict): flat["name"] = v
                elif isinstance(v, (list, dict)): walk(v)
                else: flat[k] = v
        elif isinstance(x, list):
            for it in x: walk(it)
    if isinstance(node, dict) and "player" in node: walk(node["player"])
    else: walk(node)
    return flat

def extract_team_tuple(node: Any):
    if not isinstance(node, (dict, list)): return None
    if isinstance(node, dict) and ("team_key" in node or "managers" in node):
        tkey = node.get("team_key"); tname = node.get("name")
        if isinstance(tname, dict): tname = tname.get("full") or tname.get("first")
        mgr = first_manager(node.get("managers"))
        if tkey or mgr: return (tkey, tname, mgr)
    if isinstance(node, dict) and "team" in node:
        t = node["team"]
        if isinstance(t, dict):
            tkey = t.get("team_key"); tname = t.get("name")
            if isinstance(tname, dict): tname = tname.get("full") or tname.get("first")
            mgr = first_manager(t.get("managers"))
            return (tkey, tname, mgr)
        if isinstance(t, list):
            tkey, tname, managers = None, None, None
            for e in t:
                if not isinstance(e, dict): continue
                if "team_key" in e and not tkey: tkey = e.get("team_key")
                if "name" in e and tname is None:
                    n = e.get("name"); tname = (n.get("full") if isinstance(n, dict) else n)
                if "managers" in e and managers is None: managers = e["managers"]
            return (tkey, tname, first_manager(managers))
    if isinstance(node, list):
        tkey, tname, managers = None, None, None
        for e in node:
            if not isinstance(e, dict): continue
            if "team_key" in e and not tkey: tkey = e.get("team_key")
            if "name" in e and tname is None:
                n = e.get("name"); tname = (n.get("full") if isinstance(n, dict) else n)
            if "managers" in e and managers is None: managers = e["managers"]
        if tkey or managers: return (tkey, tname, first_manager(managers))
    return None

def deep_find_teams(obj: Any) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    def walk(x: Any):
        res = extract_team_tuple(x)
        if res:
            tkey, tname, mgr = res
            found.append({
                "team_key": tkey or "",
                "team_name": tname or "",
                "manager_guid": (mgr.get("guid") or ""),
                "manager_name": (mgr.get("name") or ""),
                "manager_nickname": (mgr.get("nickname") or ""),
                "manager_email": (mgr.get("email") or "")
            })
        if isinstance(x, dict):
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(obj)
    return found

def consolidate(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def score(x):
        return (
            1 if (x.get("manager_guid") or "") else 0,
            1 if (x.get("manager_name") or "") else 0,
            1 if (x.get("manager_nickname") or "") else 0,
            1 if (x.get("manager_email") or "") else 0,
        )
    by_team: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        tkey = e.get("team_key") or ""
        if not tkey: continue
        cur = by_team.get(tkey, {"team_key": tkey, "team_name": "", "manager_guid": "", "manager_name": "", "manager_nickname": "", "manager_email": ""})
        if e.get("team_name"): cur["team_name"] = e["team_name"]
        if score(e) > score(cur):
            cur["manager_guid"] = e.get("manager_guid") or cur["manager_guid"]
            cur["manager_name"] = e.get("manager_name") or cur["manager_name"]
            cur["manager_nickname"] = e.get("manager_nickname") or cur["manager_nickname"]
            cur["manager_email"] = e.get("manager_email") or cur["manager_email"]
        by_team[tkey] = cur
    return [by_team[k] for k in sorted(by_team.keys())]

# ---------- players (name/pos/team) ----------
def fetch_players_via_yhandler(lg, player_ids: List[str]) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    id_map: Dict[str, Dict[str, str]] = {}
    key_map: Dict[str, Dict[str, str]] = {}
    if not player_ids: return id_map, key_map
    lid = lg.league_id
    game_id = lid.split(".")[0]
    keys = [f"{game_id}.p.{pid}" for pid in player_ids if str(pid).strip()]
    for batch in chunked(keys, 24):
        path = f"league/{lid}/players;player_keys={','.join(batch)}/stats"
        try:
            data = lg.yhandler.get(path)
        except Exception as e:
            print(f"• WARN: player fetch error for {lid}: {e}"); continue
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
            if players is None: players = fc.get("players")
            if isinstance(players, dict):
                try: count = int(players.get("count", 0))
                except Exception: count = 0
                for i in range(count):
                    node = players.get(str(i))
                    if not isinstance(node, dict): continue
                    p = deep_flatten_player(node)
                    pid = str(p.get("player_id", "")).strip()
                    pkey = p.get("player_key", "")
                    nm = p.get("name")
                    if isinstance(nm, dict): name = nm.get("full") or nm.get("first") or ""
                    elif isinstance(nm, str): name = nm
                    else: name = ""
                    pos = p.get("primary_position") or p.get("display_position") or ""
                    nfl = p.get("editorial_team_abbr") or p.get("editorial_team_key") or ""
                    row = {"player": name, "position": pos, "editorial_team_abbr": nfl}
                    if pid: id_map[pid] = row
                    if pkey: key_map[pkey] = row
        except Exception as e:
            print(f"• WARN: player payload parse error for {lid}: {e}")
    return id_map, key_map

# ---------- ADP (draft_analysis via PLAYERS endpoint) ----------
def _extract_avg_pick_from_da(da: Any) -> Optional[float]:
    def to_float(val):
        try:
            if val is None: return None
            if isinstance(val, (int, float)): return float(val)
            if isinstance(val, str):
                s = val.strip()
                if s in ("-", ""): return None
                return float(s)
            if isinstance(val, dict) and "value" in val:
                return to_float(val["value"])
        except Exception:
            return None
        return None

    if isinstance(da, dict):
        for key in ("average_pick", "avg_pick", "avg"):
            if key in da:
                v = to_float(da.get(key))
                if v is not None: return v
        for key in ("preseason_average_pick", "preseason_avg_pick", "preseason_avg"):
            if key in da:
                v = to_float(da.get(key))
                if v is not None: return v
        for v in da.values():
            got = _extract_avg_pick_from_da(v)
            if got is not None: return got
        return None

    if isinstance(da, list):
        for item in da:
            if isinstance(item, dict):
                for key in ("average_pick", "avg_pick", "avg"):
                    if key in item:
                        v = to_float(item.get(key))
                        if v is not None: return v
        for item in da:
            if isinstance(item, dict):
                for key in ("preseason_average_pick", "preseason_avg_pick", "preseason_avg"):
                    if key in item:
                        v = to_float(item.get(key))
                        if v is not None: return v
        for item in da:
            got = _extract_avg_pick_from_da(item)
            if got is not None: return got

    return None

def _extract_player_id_and_adp(player_node: Any) -> Optional[Tuple[str, float]]:
    pid, adp = None, None
    def walk(x):
        nonlocal pid, adp
        if isinstance(x, dict):
            if "player_id" in x and pid is None:
                pid = str(x.get("player_id")).strip()
            if "draft_analysis" in x and adp is None:
                adp = _extract_avg_pick_from_da(x["draft_analysis"])
            for v in x.values():
                if isinstance(v, (dict, list)): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)

    if isinstance(player_node, dict) and "player" in player_node:
        walk(player_node["player"])
    else:
        walk(player_node)
    if pid and (adp is not None):
        return (pid, adp)
    return None

def fetch_adp_via_yhandler(lg, player_ids: List[str], year: int) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not player_ids: return out

    game_id = lg.league_id.split(".")[0]
    keys = [f"{game_id}.p.{pid}" for pid in player_ids if str(pid).strip()]

    raw_collect = []  # debug

    for batch in chunked(keys, 24):
        path = f"players;player_keys={','.join(batch)}/draft_analysis"
        try:
            data = lg.yhandler.get(path)
        except Exception as e:
            print(f"• WARN: draft_analysis fetch error: {e}")
            continue

        raw_collect.append(data)

        try:
            fc = data.get("fantasy_content", {})
            players = fc.get("players")
            if players is None and isinstance(fc.get("player"), dict):
                players = {"count": 1, "0": {"player": fc.get("player")}}

            if isinstance(players, dict):
                try: count = int(players.get("count", 0))
                except Exception: count = 0
                for i in range(count):
                    node = players.get(str(i))
                    if not isinstance(node, dict): continue
                    pair = _extract_player_id_and_adp(node)
                    if pair:
                        pid, adp = pair
                        out[pid] = adp
        except Exception as e:
            print(f"• WARN: draft_analysis parse error: {e}")

    # debug dump
    try:
        with open(os.path.join(OUT_DIR, f"_raw_draft_analysis_{year}.json"), "w") as f:
            json.dump(raw_collect, f, indent=2)
        print(f"• Wrote {OUT_DIR}/_raw_draft_analysis_{year}.json  (ADP matches: {len(out)})")
    except Exception:
        pass

    return out

# ---------- league chain ----------
def collect_renew_chain(gm, anchor_lid: str) -> List[Tuple[int, str, str]]:
    visited=set(); chain=[]
    def walk(lid, direction):
        if lid in visited: return
        visited.add(lid)
        try:
            lg = gm.to_league(lid); s = lg.settings()
            season = int(s.get("season")); name = s.get("name")
            chain.append((season, lid, name))
            if direction in ("backward","both") and s.get("renew"):
                walk(s["renew"].replace("_", ".l."), "backward")
            if direction in ("forward","both") and s.get("renewed"):
                walk(s["renewed"].replace("_", ".l."), "forward")
        except Exception as e:
            print(f"• WARN: failed to read settings for {lid}: {e}")
    walk(anchor_lid, "both")
    return sorted(chain, key=lambda x: x[0])

# ---------- team/manager maps (Yahoo scan as last resort) ----------
def build_team_and_manager_maps(lg) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Returns (team_name_by_key, manager_display_by_team_key) from Yahoo raw /teams.
    We will only use this if our curated sources do not have a mapping.
    """
    try:
        raw = lg.yhandler.get(f"league/{lg.league_id}/teams")
    except Exception as e:
        print(f"• WARN: failed to load raw teams: {e}")
        return {}, {}

    consolidated = consolidate(deep_find_teams(raw))
    name_by_key: Dict[str, str] = {}
    mgr_by_key: Dict[str, str] = {}
    for e in consolidated:
        tkey = e.get("team_key")
        if not tkey: continue
        name_by_key[tkey] = e.get("team_name") or tkey
        # DO NOT force nicknames; we only use Yahoo as a last resort anyway.
        # Prefer 'manager_name' if present; else nickname; else empty.
        real = (e.get("manager_name") or "").strip()
        nick = (e.get("manager_nickname") or "").strip()
        mgr_by_key[tkey] = real or nick or ""
    return name_by_key, mgr_by_key

# ---------- export ----------
def export_one_league(lg, lid: str, year: int,
                      owners_by_season: Dict[int, Dict[str, str]],
                      teamkey_overrides: Dict[str, str]) -> Optional[Dict[str, Any]]:
    draft = lg.draft_results() or []
    if not draft:
        print(f"• INFO: no draft data for {year} ({lid})"); return None

    # LAST RESORT map from Yahoo:
    _team_name_by_key, yahoo_mgr_by_key = build_team_and_manager_maps(lg)

    df = pd.DataFrame(draft)
    for c in ["round","pick","team_key","player_id","player_key","player_name","cost"]:
        if c not in df.columns: df[c] = ""

    # Normalize player id
    df["player_id_norm"] = df["player_id"].astype(str).str.strip()
    has_pkey = df["player_key"].astype(str).str.contains(r"\.p\.", na=False)
    missing_pid = df["player_id_norm"].eq("") & has_pkey
    df.loc[missing_pid, "player_id_norm"] = (
        df.loc[missing_pid, "player_key"].astype(str).str.split(".p.", n=1).str[-1]
    )

    # Manager mapping priority:
    # 1) owners_by_season[year][team_key]
    # 2) owners.json team_keys (team_key -> name)
    # 3) Yahoo scanned name (real/nickname)
    season_map = owners_by_season.get(year, {})  # team_key -> manager
    def resolve_manager(tk: str) -> str:
        tk = (tk or "").strip()
        if not tk: return ""
        if tk in season_map:
            return season_map[tk]
        if tk in teamkey_overrides:
            return teamkey_overrides[tk]
        return yahoo_mgr_by_key.get(tk, "")

    df["manager"] = df["team_key"].map(resolve_manager)

    # Enrich players (name/pos/nfl)
    unique_pids = sorted(pid for pid in set(df["player_id_norm"].tolist()) if pid)
    id_map, key_map = fetch_players_via_yhandler(lg, unique_pids)

    def map_name(row):
        pid, k = row["player_id_norm"], row.get("player_key")
        return id_map.get(pid, {}).get("player") or (key_map.get(str(k), {}).get("player") if k else "") or str(row.get("player_name") or "")
    def map_pos(row):
        pid, k = row["player_id_norm"], row.get("player_key")
        return id_map.get(pid, {}).get("position") or (key_map.get(str(k), {}).get("position") if k else "") or ""
    def map_nfl(row):
        pid, k = row["player_id_norm"], row.get("player_key")
        return id_map.get(pid, {}).get("editorial_team_abbr") or (key_map.get(str(k), {}).get("editorial_team_abbr") if k else "") or ""

    df["player"] = df.apply(map_name, axis=1)
    df["position"] = df.apply(map_pos, axis=1)
    df["editorial_team_abbr"] = df.apply(map_nfl, axis=1)

    # ---- ADP via PLAYERS endpoint ----
    adp_map = fetch_adp_via_yhandler(lg, unique_pids, year)  # pid -> adp
    df["adp"] = df["player_id_norm"].map(adp_map)

    # adp_diff = actual pick - adp (positive = earlier than ADP; negative = value)
    def safe_diff(pick, adp):
        try:
            if adp is None or (isinstance(adp, float) and math.isnan(adp)): return ""
            return round(float(pick) - float(adp), 1)
        except Exception:
            return ""
    df["adp_diff"] = [safe_diff(p, a) for p, a in zip(df["pick"], df["adp"])]

    # ---- OUTPUT ----
    out_cols = ["round","pick","manager","player","position","editorial_team_abbr","adp","adp_diff"]
    out_path = f"{OUT_DIR}/draft_results_{year}.csv"
    df[out_cols].to_csv(out_path, index=False)
    print(f"✔ Saved {out_path} ({len(df)} rows)  | ADP matched: {df['adp'].notna().sum()} of {len(df)}")
    return {"year": year, "draft": f"/data/draft_results_{year}.csv"}

def main():
    sc = OAuth2(None, None, from_file="oauth2.json")
    gm = yfa.Game(sc, "nfl")

    # Load curated mappings
    owners_by_season = load_owners_by_season()                 # season -> { team_key -> manager }
    teamkey_overrides = load_teamkey_overrides_from_owners_json()  # team_key -> manager

    chain = collect_renew_chain(gm, ANCHOR_LEAGUE_ID)
    if not chain:
        print("❌ No leagues found from the anchor. Check ANCHOR_LEAGUE_ID."); return

    print("Exporting draft history for league chain:")
    for season, lid, name in chain:
        print(f"  • {season}: {name}  [{lid}]")

    seasons = []
    for season, lid, name in chain:
        lg = gm.to_league(lid)
        res = export_one_league(lg, lid, season, owners_by_season, teamkey_overrides)
        if res: seasons.append(res)

    seasons.sort(key=lambda x: x["year"], reverse=True)
    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as f:
        json.dump({"seasons": seasons}, f, indent=2)
    print("✔ Updated public/data/manifest.json")

if __name__ == "__main__":
    main()
