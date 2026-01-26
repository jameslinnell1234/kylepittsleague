#!/usr/bin/env python3
# tools/h2h_builder.py
#
# Build manager-vs-manager head-to-head JSON for your site:
#   public/data/h2h.json
#
# Data sources / priorities:
#  1) public/data/owners_by_season.csv  (season,team_key,team_name,manager)
#  2) public/data/owners.json           ({ team_keys: [{team_key,name}, ...] })
#  3) Yahoo team display name (fallback)
#
# Notes:
#  - Counts only finished games ("postevent").
#  - Tie detection: check Yahoo "is_tied" first, else exact points equality (to 2 dp).
#  - Excludes consolation bracket by default to reflect "official" H2H perception.

from __future__ import annotations

import csv
import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa


# ───────────────────────────── Config ─────────────────────────────

# OAuth file (relative to /tools)
OAUTH2_FILE = os.path.join(os.path.dirname(__file__), "..", "oauth2.json")

# Output JSON
OUTPUT_JSON = os.path.join(os.path.dirname(__file__), "..", "public", "data", "h2h.json")

# Owners mapping (primary per-season CSV + fallback JSON)
OWNERS_BY_SEASON_CSV = os.path.join(os.path.dirname(__file__), "..", "public", "data", "owners_by_season.csv")
OWNERS_JSON = os.path.join(os.path.dirname(__file__), "..", "public", "data", "owners.json")

# Your current league (anchor for renew chain discovery)
ANCHOR_LEAGUE_KEY = "461.l.54130"

# Optional: explicitly pin a league key for a season if needed
LEAGUE_OVERRIDES: Dict[int, str] = {
    # example: 2023: "423.l.39167"
}

# Which games to count
INCLUDE_PLAYOFFS = True
INCLUDE_CONSOLATION = False  # recommended False — avoids inflating H2H

# Debug toggles
DEBUG_PRINT_MATCHUPS = False  # per-matchup log
DEBUG_DUMP_EMPTY_WEEKS = True  # write raw payloads when parsing yields nothing


# ───────────────────────────── Helpers ─────────────────────────────

def _normalize_league_key(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = str(s).strip()
    if ".l." in s:
        return s
    m = re.match(r"^(\d+)[\._](\d+)$", s)
    if m:
        return f"{m.group(1)}.l.{m.group(2)}"
    if "_" in s:
        a, b = s.split("_", 1)
        if a.isdigit() and b.isdigit():
            return f"{a}.l.{b}"
    return s


def _to_float(x: Any) -> float:
    try:
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, str):
            s = x.strip()
            if s in ("", "-"):
                return 0.0
            return float(s)
        if isinstance(x, dict):
            if "total" in x:
                return _to_float(x["total"])
            if "value" in x:
                return _to_float(x["value"])
            for v in x.values():
                try:
                    return float(v)
                except Exception:
                    pass
    except Exception:
        return 0.0
    return 0.0


def _team_key_from_any(node: Any) -> Optional[str]:
    if isinstance(node, str):
        return node if ".l." in node and ".t." in node else None
    if isinstance(node, dict):
        if isinstance(node.get("team_key"), str):
            return node["team_key"]
        t = node.get("team")
        if isinstance(t, dict) and isinstance(t.get("team_key"), str):
            return t["team_key"]
        if isinstance(t, list):
            for e in t:
                if isinstance(e, dict) and isinstance(e.get("team_key"), str):
                    return e["team_key"]
    if isinstance(node, list):
        for e in node:
            tk = _team_key_from_any(e)
            if tk:
                return tk
    return None


def _points_from_any(node: Any) -> float:
    if isinstance(node, dict):
        for k in ("team_points", "points", "team_points_total"):
            if k in node:
                return _to_float(node[k])
        for v in node.values():
            if isinstance(v, dict):
                for k in ("team_points", "points", "team_points_total"):
                    if k in v:
                        return _to_float(v[k])
    return 0.0


def _extract_from_matchups_api(m: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(m, dict):
        return None
    teams = m.get("teams")
    if not isinstance(teams, list) or len(teams) != 2:
        return None
    norm_teams: List[Dict[str, Any]] = []
    for t in teams:
        tk = _team_key_from_any(t)
        if not tk:
            return None
        norm_teams.append({"team_key": tk, "points": _points_from_any(t)})
    status = str(m.get("status") or "")
    is_tied = m.get("is_tied")
    try:
        is_tied = int(is_tied) if is_tied is not None else None
    except Exception:
        is_tied = None
    winner_team_key = m.get("winner_team_key") if isinstance(m.get("winner_team_key"), str) else None
    is_playoffs = str(m.get("is_playoffs", "0"))
    is_consolation = str(m.get("is_consolation", "0"))
    return {
        "teams": norm_teams,
        "status": status,
        "is_tied": is_tied,
        "winner_team_key": winner_team_key,
        "is_playoffs": is_playoffs,
        "is_consolation": is_consolation,
    }


def _extract_from_scoreboard_node(node: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(node, dict):
        return None
    meta = node.get("matchup") if isinstance(node.get("matchup"), dict) else node
    status = str(meta.get("status") or "")
    is_playoffs = str(meta.get("is_playoffs", "0"))
    is_consolation = str(meta.get("is_consolation", "0"))
    is_tied = meta.get("is_tied")
    try:
        is_tied = int(is_tied) if is_tied is not None else None
    except Exception:
        is_tied = None
    winner_team_key = meta.get("winner_team_key") if isinstance(meta.get("winner_team_key"), str) else None

    # teams may be under "0" → "teams" or directly "teams"
    if "0" in meta and isinstance(meta["0"], dict) and "teams" in meta["0"]:
        teams_block = meta["0"]["teams"]
    else:
        teams_block = meta.get("teams")

    def pull_team(block: Any) -> Optional[Dict[str, Any]]:
        tk = _team_key_from_any(block)
        pts = _points_from_any(block)
        if tk:
            return {"team_key": tk, "points": pts}
        if isinstance(block, dict) and isinstance(block.get("team"), list):
            parts = block["team"]
            tk2 = _team_key_from_any(parts)
            pts2 = 0.0
            for p in parts:
                if isinstance(p, dict) and ("team_points" in p or "points" in p):
                    pts2 = _points_from_any(p)
            if tk2:
                return {"team_key": tk2, "points": pts2}
        return None

    teams_norm: List[Dict[str, Any]] = []
    if isinstance(teams_block, dict):
        try:
            cnt = int(teams_block.get("count", 0))
        except Exception:
            cnt = 0
        for i in range(cnt):
            tnode = teams_block.get(str(i))
            if not isinstance(tnode, dict):
                continue
            row = pull_team(tnode)
            if row:
                teams_norm.append(row)
    elif isinstance(teams_block, list) and len(teams_block) == 2:
        for t in teams_block:
            row = pull_team(t)
            if row:
                teams_norm.append(row)

    if len(teams_norm) != 2:
        return None

    return {
        "teams": teams_norm,
        "status": status,
        "is_tied": is_tied,
        "winner_team_key": winner_team_key,
        "is_playoffs": is_playoffs,
        "is_consolation": is_consolation,
    }


def _fetch_matchups_for_week(lg, week: int, season: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    # 1) matchups()
    lst = []
    try:
        lst = lg.matchups(week) or []
        for m in lst:
            norm = _extract_from_matchups_api(m)
            if norm:
                out.append(norm)
    except Exception:
        pass

    # 2) raw scoreboard fallback
    if not out:
        try:
            lid = lg.league_id
            raw = lg.yhandler.get(f"league/{lid}/scoreboard;week={week}")
            fc = raw.get("fantasy_content", {})
            league = fc.get("league")
            scoreboard = None
            if isinstance(league, list):
                for item in league:
                    if isinstance(item, dict) and "scoreboard" in item:
                        scoreboard = item["scoreboard"]
                        break
            elif isinstance(league, dict):
                scoreboard = league.get("scoreboard")
            matchups_node = None
            if isinstance(scoreboard, dict):
                matchups_node = scoreboard.get("matchups") or scoreboard.get("0", {}).get("matchups")
            if isinstance(matchups_node, dict):
                try:
                    cnt = int(matchups_node.get("count", 0))
                except Exception:
                    cnt = 0
                for i in range(cnt):
                    node = matchups_node.get(str(i))
                    norm = _extract_from_scoreboard_node(node) if isinstance(node, dict) else None
                    if norm:
                        out.append(norm)
            if DEBUG_DUMP_EMPTY_WEEKS and not out:
                dbg_dir = os.path.join(os.path.dirname(__file__), "..", "public", "data", "_debug")
                os.makedirs(dbg_dir, exist_ok=True)
                with open(os.path.join(dbg_dir, f"scoreboard_raw_{season}_w{week}.json"), "w", encoding="utf-8") as f:
                    json.dump(raw, f, ensure_ascii=False, indent=2)
                with open(os.path.join(dbg_dir, f"matchups_api_{season}_w{week}.json"), "w", encoding="utf-8") as f:
                    json.dump(lst, f, ensure_ascii=False, indent=2)
                print(f"• DEBUG: wrote raw dumps for {season} w{week} (no parsed matchups).")
        except Exception as e:
            print(f"• WARN: scoreboard fetch failed (season {season} w{week}): {e}")

    return out


def _week_range(lg) -> Tuple[int, int]:
    st = lg.settings()
    start = int(st.get("start_week", 1) or 1)
    end = st.get("end_week") or st.get("playoff_last_week") or st.get("current_week") or start
    end = int(end or start)
    if end < start:
        end = start
    return start, end


def _collect_yahoo_team_names(lg) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        for t in lg.teams() or []:
            if isinstance(t, dict):
                tk = t.get("team_key")
                nm = t.get("name")
                if tk and nm:
                    out[tk] = str(nm)
    except Exception:
        pass
    return out


def load_owners_by_season() -> Dict[int, Dict[str, str]]:
    out: Dict[int, Dict[str, str]] = {}
    if not os.path.exists(OWNERS_BY_SEASON_CSV):
        return out
    with open(OWNERS_BY_SEASON_CSV, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                season = int(str(row.get("season", "")).strip())
            except Exception:
                continue
            tk = (row.get("team_key") or "").strip()
            mgr = (row.get("manager") or "").strip()
            if season and tk and mgr:
                out.setdefault(season, {})[tk] = mgr
    return out


def load_owner_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    try:
        with open(OWNERS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("team_keys", []):
            tk = str(item.get("team_key", "")).strip()
            nm = str(item.get("name", "")).strip()
            if tk and nm:
                mapping[tk] = nm
    except Exception as e:
        print(f"• WARN: could not load owners.json: {e}")
    return mapping


def collect_renew_chain(gm: yfa.Game, anchor_key: str) -> List[Tuple[int, str, str]]:
    visited: Set[str] = set()
    out: List[Tuple[int, str, str]] = []
    def walk(key: Optional[str], dirn: str):
        key = _normalize_league_key(key)
        if not key or key in visited:
            return
        visited.add(key)
        try:
            lg = gm.to_league(key)
            st = lg.settings()
            season_raw = st.get("season")
            season = int(season_raw) if str(season_raw).isdigit() else None
            name = st.get("name") or ""
            if season is not None:
                out.append((season, key, name))
            if dirn in ("backward", "both"):
                walk(st.get("renew"), "backward")
            if dirn in ("forward", "both"):
                walk(st.get("renewed"), "forward")
        except Exception as e:
            print(f"• WARN: failed to read settings for {key}: {e}")
    walk(anchor_key, "both")
    out.sort(key=lambda x: x[0])
    return out


# ───────────────────────────── Builder ─────────────────────────────

def main() -> Dict[str, Any]:
    if not os.path.exists(OAUTH2_FILE):
        raise SystemExit(f"oauth2.json not found at {OAUTH2_FILE}")

    sc = OAuth2(None, None, from_file=OAUTH2_FILE)
    if not sc.token_is_valid():
        sc.refresh_access_token()

    gm = yfa.Game(sc, "nfl")

    owners_by_season = load_owners_by_season()
    owners_fallback = load_owner_map()

    def resolve_manager(season: int, team_key: str, yahoo_names: Dict[str, str]) -> str:
        m = owners_by_season.get(season, {}).get(team_key)
        if m:
            return m
        m = owners_fallback.get(team_key)
        if m:
            return m
        m = yahoo_names.get(team_key)
        if m:
            return m
        return team_key

    chain = collect_renew_chain(gm, ANCHOR_LEAGUE_KEY)
    if not chain:
        raise RuntimeError("No leagues found from anchor league key")

    print("H2H will be built from this league lineage:")
    for season, lid, name in chain:
        print(f"  • {season}: {name} [{lid}]")

    # Aggregation
    results: Dict[Tuple[str, str], Dict[str, Any]] = {}
    managers: Set[str] = set()
    unmapped: Set[Tuple[int, str]] = set()

    for season, lid, name in chain:
        lkey = LEAGUE_OVERRIDES.get(season, lid)
        lg = gm.to_league(lkey)
        w_start, w_end = _week_range(lg)
        print(f"  · {season}: weeks {w_start}–{w_end} ({name})")

        yahoo_names = _collect_yahoo_team_names(lg)

        # de-dup per (season, week, sorted team keys, phase)
        seen: Set[Tuple[int, int, str, str, str]] = set()

        for week in range(w_start, w_end + 1):
            matchups = _fetch_matchups_for_week(lg, week, season)
            if not matchups:
                continue

            for mu in matchups:
                status = str(mu.get("status") or "").lower()
                if status != "postevent":
                    continue  # only final games

                is_playoffs = str(mu.get("is_playoffs", "0")) == "1"
                is_consolation = str(mu.get("is_consolation", "0")) == "1"
                if is_playoffs and not INCLUDE_PLAYOFFS:
                    continue
                if is_consolation and not INCLUDE_CONSOLATION:
                    continue

                teams = mu.get("teams") or []
                if not (isinstance(teams, list) and len(teams) == 2):
                    continue

                tk0, pts0 = teams[0]["team_key"], float(teams[0]["points"])
                tk1, pts1 = teams[1]["team_key"], float(teams[1]["points"])

                # de-dup key (include phase to keep playoff rematches separate)
                a_tk, b_tk = sorted([tk0, tk1])
                phase_sig = ("P" if is_playoffs else "R") + ("C" if is_consolation else "")
                uniq = (season, week, a_tk, b_tk, phase_sig)
                if uniq in seen:
                    continue
                seen.add(uniq)

                n0 = resolve_manager(season, tk0, yahoo_names)
                n1 = resolve_manager(season, tk1, yahoo_names)

                if n0 == tk0:
                    unmapped.add((season, tk0))
                if n1 == tk1:
                    unmapped.add((season, tk1))

                managers.update([n0, n1])

                # stable pair ordering by manager name
                if n0 <= n1:
                    a_name, b_name = n0, n1
                    a_pts, b_pts = pts0, pts1
                    a_side_tk = tk0
                else:
                    a_name, b_name = n1, n0
                    a_pts, b_pts = pts1, pts0
                    a_side_tk = tk1

                rec = results.setdefault(
                    (a_name, b_name),
                    {"a": a_name, "b": b_name, "a_wins": 0, "b_wins": 0, "ties": 0,
                     "a_points_for": 0.0, "b_points_for": 0.0}
                )

                # accumulate points
                rec["a_points_for"] += a_pts
                rec["b_points_for"] += b_pts

                # outcome
                is_tied_flag = mu.get("is_tied")
                try:
                    is_tied_flag = int(is_tied_flag) if is_tied_flag is not None else None
                except Exception:
                    is_tied_flag = None

                winner_team_key = mu.get("winner_team_key") if isinstance(mu.get("winner_team_key"), str) else None

                # Ties first
                if is_tied_flag == 1:
                    if DEBUG_PRINT_MATCHUPS:
                        print(f"{season} w{week}: {a_name} vs {b_name} -> TIE  (playoffs={is_playoffs}, cons={is_consolation})")
                    rec["ties"] += 1
                    continue

                # Winner flag
                if winner_team_key in (tk0, tk1):
                    a_won = (winner_team_key == a_side_tk)
                    if DEBUG_PRINT_MATCHUPS:
                        who = a_name if a_won else b_name
                        print(f"{season} w{week}: {a_name} vs {b_name} -> WINNER {who}  (playoffs={is_playoffs}, cons={is_consolation})")
                    if a_won:
                        rec["a_wins"] += 1
                    else:
                        rec["b_wins"] += 1
                    continue

                # Final fallback: finished but no winner flag → exact 2dp comparison
                if round(a_pts, 2) == round(b_pts, 2):
                    if DEBUG_PRINT_MATCHUPS:
                        print(f"{season} w{week}: {a_name} vs {b_name} -> TIE-by-points  (playoffs={is_playoffs}, cons={is_consolation})")
                    rec["ties"] += 1
                elif a_pts > b_pts:
                    if DEBUG_PRINT_MATCHUPS:
                        print(f"{season} w{week}: {a_name} vs {b_name} -> WINNER {a_name}  (playoffs={is_playoffs}, cons={is_consolation})")
                    rec["a_wins"] += 1
                else:
                    if DEBUG_PRINT_MATCHUPS:
                        print(f"{season} w{week}: {a_name} vs {b_name} -> WINNER {b_name}  (playoffs={is_playoffs}, cons={is_consolation})")
                    rec["b_wins"] += 1

    # sanity
    if unmapped:
        print("• WARN: Unmapped team_keys (add to owners_by_season.csv):")
        for s, tk in sorted(unmapped):
            print(f"   - {s}: {tk}")

    # Prepare output
    pairs = sorted(results.values(), key=lambda r: (r["a"], r["b"]))
    try:
        from datetime import datetime, timezone
        updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        updated_at = ""

    out = {
        "managers": sorted(managers),
        "pairs": pairs,
        "updated_at": updated_at,
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # quick tie summary
    ties = [(p["a"], p["b"], p["ties"]) for p in pairs if p.get("ties", 0) > 0]
    if ties:
        print("• Tie summary:")
        for a, b, t in ties:
            print(f"   - {a} vs {b}: {t} tie(s)")
    else:
        print("• No ties found.")

    print(f"✔ Wrote {OUTPUT_JSON} with {len(out['managers'])} managers and {len(out['pairs'])} pairs.")
    return out


if __name__ == "__main__":
    main()
