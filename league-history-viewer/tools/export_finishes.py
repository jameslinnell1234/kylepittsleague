#!/usr/bin/env python3
import json, sys
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd
from yahoo_oauth import OAuth2
from yahoo_fantasy_api import Game

# ---------------- CONFIG ----------------
ANCHOR_LEAGUE_KEY = "461.l.54130"
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "public" / "data"
OWNERS_BY_SEASON_CSV = DATA / "owners_by_season.csv"
FINISHES_CSV = DATA / "finishes.csv"
DEBUG_DUMPS = True
PRINT_SANITY = True   # extra checks so we know mapping is actually used
# ----------------------------------------

def load_oauth():
    oauth_path = Path(__file__).resolve().parents[1] / "oauth2.json"
    if not oauth_path.exists():
        raise SystemExit(f"Missing OAuth file: {oauth_path}")
    sc = OAuth2(None, None, from_file=str(oauth_path))
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
        if not lid or lid in seen: continue
        seen.add(lid)
        try:
            lg = gm.to_league(lid); st = lg.settings()
        except Exception:
            continue
        keys.add(lid)
        prev, nxt = st.get("renew"), st.get("renewed")
        if isinstance(prev, str):
            pk = league_key_from_renew_string(prev)
            if pk: q.append(pk)
        if isinstance(nxt, str):
            nk = league_key_from_renew_string(nxt)
            if nk: q.append(nk)
    def season_of(k: str) -> int:
        try: return int(gm.to_league(k).settings().get("season",0))
        except Exception: return 0
    return sorted(keys, key=season_of)

def squash(node: Any) -> Dict[str, Any]:
    if isinstance(node, dict): return node
    if not isinstance(node, list): return {}
    out: Dict[str, Any] = {}
    for el in node:
        if isinstance(el, dict): out.update(el)
    return out

def normalize_team(node: Any) -> Dict[str, Any]:
    t = node
    if isinstance(t, list): t = squash(t)
    if isinstance(t, dict) and "team" in t:
        inner = t["team"]
        if isinstance(inner, list): inner = squash(inner)
        if isinstance(inner, dict): t = {**t, **inner}
    if not isinstance(t, dict): return {}
    rank = t.get("rank")
    if rank in (None, "", []):
        ts = t.get("team_standings")
        if isinstance(ts, list): ts = squash(ts)
        if isinstance(ts, dict): rank = ts.get("rank")
    try: rank_val = int(str(rank).strip())
    except Exception: rank_val = 9999
    return {
        "team_key": str(t.get("team_key","")).strip(),
        "team_name": str(t.get("name","") or t.get("team_name","")).strip(),
        "rank": rank_val
    }

def get_ranked_standings(lg, league_key: str) -> List[Dict[str, Any]]:
    # raw first
    try:
        data = lg.yhandler.get(f"league/{league_key}/standings")
    except Exception:
        data = None
    rows: List[Dict[str, Any]] = []
    if isinstance(data, (bytes, str)):
        try: data = json.loads(data)
        except Exception: data = None
    if isinstance(data, dict):
        if DEBUG_DUMPS:
            (DATA / f"_fin_raw_standings_{lg.settings().get('season',0)}.json").write_text(json.dumps(data, indent=2))
        fc = data.get("fantasy_content"); league = fc.get("league") if isinstance(fc, dict) else None
        ln = None
        if isinstance(league, list):
            for item in league:
                if isinstance(item, dict) and "standings" in item:
                    ln = item; break
            if ln is None and len(league) >= 2 and isinstance(league[1], dict):
                ln = league[1]
        elif isinstance(league, dict):
            ln = league
        if isinstance(ln, dict):
            st = ln.get("standings"); tn = st.get("teams") if isinstance(st, dict) else None
            items: List[Any] = []
            if isinstance(tn, dict):
                if "team" in tn and isinstance(tn["team"], list):
                    items = tn["team"]
                else:
                    for v in tn.values():
                        if isinstance(v, dict) and "team" in v:
                            items.append(v["team"])
            elif isinstance(tn, list):
                items = tn
            for it in items:
                nt = normalize_team(it)
                if nt.get("team_key"):
                    rows.append(nt)
    # fallback
    if not rows:
        try: lib_rows = lg.standings()
        except Exception: lib_rows = []
        if DEBUG_DUMPS:
            (DATA / f"_fin_lib_standings_{lg.settings().get('season',0)}.json").write_text(json.dumps(lib_rows, indent=2))
        for it in lib_rows or []:
            nt = normalize_team(it)
            if nt.get("team_key"):
                rows.append(nt)
    rows.sort(key=lambda r: r["rank"])
    return rows

def load_owners_by_season_csv() -> Dict[str, Dict[str, str]]:
    if not OWNERS_BY_SEASON_CSV.exists():
        raise SystemExit(f"Missing {OWNERS_BY_SEASON_CSV}. Run scaffold and fill managers first.")
    df = pd.read_csv(
        OWNERS_BY_SEASON_CSV,
        dtype={"season":str, "team_key":str, "team_name":str, "manager":str},
        keep_default_na=False
    )
    # normalize
    df["season"] = df["season"].str.strip()
    df["team_key"] = df["team_key"].str.strip()
    df["manager"] = df["manager"].str.strip()
    mapping: Dict[str, Dict[str, str]] = {}
    for season, sub in df.groupby("season", sort=False):
        inner: Dict[str, str] = {}
        for _, row in sub.iterrows():
            tk = row["team_key"]
            nm = row["manager"]
            if tk:
                inner[tk] = nm  # may be blank; exporter will warn if blank
        mapping[str(season)] = inner
    print(f"USING owners_by_season.csv ONLY — seasons loaded: {sorted(mapping.keys())}")
    if PRINT_SANITY:
        # sanity: print a couple of known keys if present
        samp = [
            ("2020","399.l.857293.t.5"),
            ("2020","399.l.857293.t.3"),
            ("2022","414.l.336160.t.10")
        ]
        for s, tk in samp:
            nm = mapping.get(s, {}).get(tk, "<missing>")
            print(f"SANITY owners_by_season[{s}][{tk}] = {nm}")
    return mapping

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    sc = load_oauth(); gm = Game(sc, "nfl")

    owners_map = load_owners_by_season_csv()  # <<< ONLY SOURCE OF NAMES

    chain = walk_chain(gm, ANCHOR_LEAGUE_KEY)
    if not chain:
        print("No leagues found in chain."); return

    records: List[Dict[str, Any]] = []

    for lid in chain:
        lg = gm.to_league(lid)
        season = str(int(lg.settings().get("season",0)))
        ranked = get_ranked_standings(lg, lid)
        tk2name = owners_map.get(season, {})

        print(f"Processing league: {lid}, season: {season}, teams in owners_map: {len(tk2name)}")

        detail_rows: List[Dict[str, Any]] = []
        for r in ranked:
            tk = r["team_key"]; tn = r["team_name"]; place = r["rank"]
            mgr = tk2name.get(tk, "")
            src = "owners_by_season.csv"
            detail_rows.append({
                "rank": place,
                "manager": mgr,
                "name_source": src,
                "team_name": tn,
                "team_key": tk
            })
            records.append({
                "season": int(season),
                "manager": mgr,
                "place": place,
                "team_key": tk,
                "team_name": tn,
                "name_source": src
            })

        pd.DataFrame(detail_rows, columns=["rank","manager","name_source","team_name","team_key"]).to_csv(
            DATA / f"finishes_detail_{season}.csv", index=False
        )

    if not records:
        print("No data."); return
    df = pd.DataFrame(records).sort_values(by=["season","place"], ascending=[False,True])
    df.to_csv(FINISHES_CSV, index=False)
    print(f"✔ Wrote {FINISHES_CSV} ({len(df)} rows)")
    # warn blanks
    blanks = df[(df["name_source"]=="owners_by_season.csv") & (df["manager"].astype(str).str.strip()=="")]
    if not blanks.empty:
        print("\n⚠️ Blank manager values in owners_by_season.csv for these rows:")
        print(blanks[["season","place","team_key","team_name"]].to_string(index=False))

if __name__ == "__main__":
    main()
