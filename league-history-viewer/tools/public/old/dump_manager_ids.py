#!/usr/bin/env python3
# tools/dump_manager_ids.py
# Deep-scan Yahoo's teams payload and print ONE clean row per team (team_key, team_name, guid, name, nickname, email).

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json, os
from typing import Any, Dict, List, Tuple

ANCHOR_LEAGUE_ID = "461.l.54130"

def to_list(x):
    if x is None: return []
    if isinstance(x, list): return x
    if isinstance(x, dict) and "count" in x:
        try: n = int(x.get("count", 0))
        except Exception: n = 0
        return [x.get(str(i)) for i in range(n)]
    return [x]

def first_manager(managers_obj: Any) -> Dict[str, Any]:
    for cand in to_list(managers_obj):
        if not isinstance(cand, dict):
            continue
        inner = cand.get("manager") if isinstance(cand.get("manager"), dict) else cand
        if isinstance(inner, dict):
            return inner
    return {}

def extract_team_tuple(node: Any) -> Tuple[str, str, Dict[str, Any]] | None:
    if not isinstance(node, (dict, list)):
        return None

    # Node is already a team dict
    if isinstance(node, dict) and ("team_key" in node or "managers" in node):
        tkey = node.get("team_key")
        tname = node.get("name")
        if isinstance(tname, dict):
            tname = tname.get("full") or tname.get("first")
        mgr = first_manager(node.get("managers"))
        if tkey or mgr:
            return (tkey, tname, mgr)

    # Node has "team" child (dict or list)
    if isinstance(node, dict) and "team" in node:
        t = node["team"]
        if isinstance(t, dict):
            tkey = t.get("team_key")
            tname = t.get("name")
            if isinstance(tname, dict):
                tname = tname.get("full") or tname.get("first")
            mgr = first_manager(t.get("managers"))
            return (tkey, tname, mgr)
        if isinstance(t, list):
            tkey, tname, managers = None, None, None
            for e in t:
                if not isinstance(e, dict):
                    continue
                if "team_key" in e and not tkey:
                    tkey = e.get("team_key")
                if "name" in e and tname is None:
                    n = e.get("name")
                    tname = (n.get("full") if isinstance(n, dict) else n)
                if "managers" in e and managers is None:
                    managers = e["managers"]
            return (tkey, tname, first_manager(managers))

    # Node is a list of potential fields
    if isinstance(node, list):
        tkey, tname, managers = None, None, None
        for e in node:
            if not isinstance(e, dict):
                continue
            if "team_key" in e and not tkey:
                tkey = e.get("team_key")
            if "name" in e and tname is None:
                n = e.get("name")
                tname = (n.get("full") if isinstance(n, dict) else n)
            if "managers" in e and managers is None:
                managers = e["managers"]
        if tkey or managers:
            return (tkey, tname, first_manager(managers))

    return None

def deep_find_teams(obj: Any) -> List[Dict[str, Any]]:
    found = []
    def walk(x):
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
    """
    Consolidate to one row per team_key.
    Preference:
      - team_name: prefer non-empty latest seen
      - manager: prefer row with GUID; if multiple, keep the one with name>nickname>email
    """
    by_team: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        tkey = e.get("team_key") or ""
        if not tkey:
            continue
        cur = by_team.get(tkey, {"team_key": tkey, "team_name": "" , "manager_guid": "", "manager_name": "", "manager_nickname": "", "manager_email": ""})
        # team name
        if e.get("team_name"):
            cur["team_name"] = e["team_name"]
        # manager GUID wins
        def score(x):
            # higher is better
            return (
                1 if (x.get("manager_guid") or "") else 0,
                1 if (x.get("manager_name") or "") else 0,
                1 if (x.get("manager_nickname") or "") else 0,
                1 if (x.get("manager_email") or "") else 0,
            )
        if score(e) > score(cur):
            cur["manager_guid"] = e.get("manager_guid") or cur["manager_guid"]
            cur["manager_name"] = e.get("manager_name") or cur["manager_name"]
            cur["manager_nickname"] = e.get("manager_nickname") or cur["manager_nickname"]
            cur["manager_email"] = e.get("manager_email") or cur["manager_email"]
        by_team[tkey] = cur
    # return sorted by team_key
    return [by_team[k] for k in sorted(by_team.keys())]

def main():
    sc = OAuth2(None, None, from_file="oauth2.json")
    gm = yfa.Game(sc, "nfl")
    lg = gm.to_league(ANCHOR_LEAGUE_ID)

    raw = lg.yhandler.get(f"league/{ANCHOR_LEAGUE_ID}/teams")
    os.makedirs("public/data", exist_ok=True)
    with open("public/data/_raw_teams.json", "w") as f:
        json.dump(raw, f, indent=2)
    print("• Wrote public/data/_raw_teams.json")

    entries = deep_find_teams(raw)
    clean = consolidate(entries)
    print(json.dumps(clean, indent=2))

if __name__ == "__main__":
    main()
