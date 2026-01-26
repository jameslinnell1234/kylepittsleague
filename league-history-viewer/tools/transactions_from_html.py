#!/usr/bin/env python3
# tools/transactions_from_html.py
#
# Parse one or more Yahoo Fantasy "Transactions" HTML pages (can be pasted back-to-back)
# and extract player add/drop/waiver/trade actions.
#
# Now supports incremental updates:
#   - You only need to paste the *latest* HTML page each time you run it.
#   - It automatically merges with prior results and removes duplicates.
#
# Outputs:
#   - public/data/waiver_transactions_2025.csv
#   - public/data/waiver_transactions_2025.json
#
# Requires: pip install beautifulsoup4
#
# ---------------------------------------------------------------------------

import os, csv, json, re, datetime
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(__file__)
OUT_DIR = os.path.join(ROOT, "..", "public", "data")
os.makedirs(OUT_DIR, exist_ok=True)

SEASON = 2025
HTML_FILE = os.path.join(OUT_DIR, "transactions_2025.html")

CSV_FIELDS = [
    "season", "date", "type", "player", "position", "nfl",
    "from_team", "to_team", "note"
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def txt(el) -> str:
    return " ".join((el.get_text(" ", strip=True) if el else "").split())

def extract_player_bits(s: str) -> Tuple[str, str, str]:
    """
    From 'Tyler Loop (K) Bal' or 'Tyler Loop Bal - K' -> (player, pos, nfl)
    """
    s = (s or "").strip()
    player, pos, nfl = s, "", ""

    # Try "Name (POS) TEAM"
    if "(" in s and ")" in s:
        try:
            before, after = s.split("(", 1)
            player = before.strip()
            inside, tail = after.split(")", 1)
            pos = inside.strip()
            tail = tail.strip()
            if tail:
                last = tail.split()[-1]
                nfl = last
        except Exception:
            pass
        return player, pos, nfl

    # Try "Team - POS" at end (e.g., "Bal - K")
    dash_idx = s.rfind(" - ")
    if dash_idx != -1:
        tail = s[dash_idx + 3:].strip()
        before = s[:dash_idx].strip()
        pos = tail
        parts = before.split()
        if len(parts) >= 2:
            nfl = parts[-1]
            player = " ".join(parts[:-1])
        else:
            player = before
        return player, pos, nfl

    return player, pos, nfl

def map_icon_title_to_type(title: str) -> str:
    t = (title or "").strip().lower()
    if "added" in t and "player" in t:
        return "add"
    if "dropped" in t and "player" in t:
        return "drop"
    if "waiver" in t:
        return "waiver"
    if "trade" in t:
        return "trade"
    return t or "transaction"

# ---------------------------------------------------------------------------
# Transaction row parsing
# ---------------------------------------------------------------------------

def parse_transaction_tr(tr) -> Optional[Dict[str, Any]]:
    """
    Parse a single <tr> from the Tst-transaction-table.
    """
    tds = tr.find_all("td")
    if not tds or len(tds) < 2:
        return None

    # Left icon/type (td[0])
    icon_td = tds[0]
    icon_span = icon_td.find("span")
    icon_title = icon_span["title"] if (icon_span and icon_span.has_attr("title")) else ""
    ttype = map_icon_title_to_type(icon_title)

    # Middle cell with player info
    mid_td = None
    for td in tds[1:]:
        if td.find("a", href=True) or td.find("span", class_=lambda c: c and "F-position" in c):
            mid_td = td
            break
    if mid_td is None:
        mid_td = tds[1]

    # Extract player + position
    player_link = mid_td.find("a", href=True)
    player_name = txt(player_link) if player_link else ""
    pos_span = mid_td.find("span", class_=lambda c: c and "F-position" in c)
    pos_blob = txt(pos_span)
    combined_player = f"{player_name} {pos_blob}".strip()
    player, position, nfl = extract_player_bits(combined_player)

    # Status / source
    status_h6 = mid_td.find("h6")
    status = txt(status_h6)

    # Right side: team + timestamp
    right_td = tds[-1]
    to_team_a = right_td.find("a", class_=lambda c: c and "Tst-team-name" in c)
    to_team = txt(to_team_a)
    timestamp_span = right_td.find("span", class_=lambda c: c and "F-timestamp" in c)
    date_str = txt(timestamp_span)

    # From team derivation
    from_team = ""
    s = status.lower()
    if "free agent" in s:
        from_team = "Free Agent"
    elif "waiver" in s:
        from_team = "Waivers"
    elif "dropped by" in s:
        m = re.search(r"dropped by\s+(.+)$", status, flags=re.I)
        if m:
            from_team = m.group(1).strip()

    row = {
        "season": SEASON,
        "date": date_str,
        "type": ttype,
        "player": player,
        "position": position,
        "nfl": nfl,
        "from_team": from_team,
        "to_team": to_team,
        "note": status,
    }

    if not (row["date"] or row["player"] or row["type"]):
        return None
    return row

def parse_tables_in_soup(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    tables = soup.find_all("table", class_=lambda c: c and "Tst-transaction-table" in c)
    for tbl in tables:
        for tr in tbl.find_all("tr"):
            row = parse_transaction_tr(tr)
            if row:
                out.append(row)
    return out

# ---------------------------------------------------------------------------
# Multi-HTML handling
# ---------------------------------------------------------------------------

HTML_SEG_RE = re.compile(r"(?is)<html\b.*?</html>")

def split_into_segments(html: str) -> List[str]:
    segs = HTML_SEG_RE.findall(html)
    return segs if segs else [html]

def parse_file_multi(html_path: str) -> List[Dict[str, Any]]:
    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        big = f.read()
    segments = split_into_segments(big)
    all_rows: List[Dict[str, Any]] = []
    for seg in segments:
        soup = BeautifulSoup(seg, "html.parser")
        all_rows.extend(parse_tables_in_soup(soup))
    return all_rows

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def load_existing_transactions(json_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rows", [])
    except Exception as e:
        print(f"⚠️ Couldn't load existing JSON: {e}")
        return []

def deduplicate_transactions(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate transactions.
    Two transactions are considered identical if they share:
      (season, date, type, player, to_team)
    """
    seen = set()
    unique = []
    for r in rows:
        key = (
            r.get("season"),
            r.get("date"),
            r.get("type"),
            r.get("player"),
            r.get("to_team"),
        )
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique

def write_csv(path: str, rows: List[Dict[str, Any]]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS})

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not os.path.exists(HTML_FILE):
        print(f"❌ HTML file not found: {HTML_FILE}")
        return

    csv_out = os.path.join(OUT_DIR, f"waiver_transactions_{SEASON}.csv")
    json_out = os.path.join(OUT_DIR, f"waiver_transactions_{SEASON}.json")

    # Step 1: Load existing transactions
    old_rows = load_existing_transactions(json_out)
    print(f"📦 Loaded {len(old_rows)} existing transactions")

    # Step 2: Parse new HTML
    new_rows = parse_file_multi(HTML_FILE)
    print(f"🆕 Parsed {len(new_rows)} new transactions from {HTML_FILE}")

    # Step 3: Merge & deduplicate
    all_rows = old_rows + new_rows
    all_rows = deduplicate_transactions(all_rows)

    # Step 4: Sort & save
    all_rows.sort(key=lambda r: (r.get("date", ""), r.get("player", "")))

    write_csv(csv_out, all_rows)
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(
            {
                "season": SEASON,
                "rows": all_rows,
                "updated_at": datetime.datetime.now(datetime.UTC).isoformat()
            },
            f, indent=2
        )

    print(f"✔ Total unique transactions: {len(all_rows)}")
    print(f"✔ Wrote {csv_out}")
    print(f"✔ Wrote {json_out}")

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
