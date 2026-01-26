#!/usr/bin/env python3
# tools/export_records.py
# Parse saved Yahoo Record Book HTMLs into records.json that the site reads.
#
# Expects files (any subset) under public/data:
#   recordbook_h2h_<YEAR>.html        -> head_to_head
#   recordbook_teampoints_<YEAR>.html -> team_points
#   recordbook_teamstats_<YEAR>.html  -> team_stats
#
# Output: public/data/records.json
# {
#   "years": {
#     "2024": {
#       "head_to_head": [ {section, headers, rows}, ... ],
#       "team_points":  [ ... ],
#       "team_stats":   [ ... ]
#     },
#     ...
#   }
# }

import os
import re
import json
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT, "public", "data")
OUT_PATH = os.path.join(DATA_DIR, "records.json")

# map filename kind -> JSON key
KIND_TO_KEY = {
    "h2h": "head_to_head",
    "teampoints": "team_points",
    "teamstats": "team_stats",
}

FILE_RE = re.compile(r"^recordbook_(h2h|teampoints|teamstats)_(\d{4})\.html$")

def discover_files() -> Dict[str, Dict[str, str]]:
    """
    Returns: {year: {kind: filepath, ...}, ...}
    where kind in {"h2h","teampoints","teamstats"}.
    """
    by_year: Dict[str, Dict[str, str]] = {}
    for name in os.listdir(DATA_DIR):
        m = FILE_RE.match(name)
        if not m:
            continue
        kind, year = m.group(1), m.group(2)
        by_year.setdefault(year, {})[kind] = os.path.join(DATA_DIR, name)
    return by_year

def text_clean(s: str) -> str:
    return " ".join((s or "").split())

def find_section_title(tbl: Any) -> str:
    """
    Try to infer a section title for a table:
    - <caption>
    - nearest previous heading (h1-h4)
    - data-section attr on table or parent
    - fallback: "Section"
    """
    # caption
    cap = tbl.find("caption")
    if cap:
        t = text_clean(cap.get_text(" ", strip=True))
        if t:
            return t

    # previous heading siblings
    prev = tbl
    for _ in range(20):  # avoid long walks
        prev = prev.find_previous_sibling()
        if prev is None:
            break
        if prev.name and prev.name.lower() in ("h1", "h2", "h3", "h4"):
            t = text_clean(prev.get_text(" ", strip=True))
            if t:
                return t

    # look on table or parent for data-section-ish attributes
    for node in (tbl, tbl.parent):
        if not node or not getattr(node, "attrs", None):
            continue
        for k, v in node.attrs.items():
            if "section" in k.lower():
                t = text_clean(v if isinstance(v, str) else " ".join(v))
                if t:
                    return t

    return "Section"

def parse_table(tbl: Any) -> Optional[Dict[str, Any]]:
    """
    Parse a single <table> into {section, headers, rows}.
    Headers from the first row with <th> (fallback to first row’s <td>).
    Rows are list of dicts keyed by headers.
    """
    # headers
    thead = tbl.find("thead")
    header_cells = None
    if thead:
        tr = thead.find("tr")
        if tr:
            header_cells = tr.find_all(["th", "td"])
    if not header_cells:
        # try first tr in tbody or table
        body = tbl.find("tbody") or tbl
        first_tr = body.find("tr") if body else None
        if first_tr:
            header_cells = first_tr.find_all(["th", "td"])
            # If we took first row for headers, skip it later
            header_from_first_row = True
        else:
            return None
    else:
        header_from_first_row = False

    headers = [text_clean(c.get_text(" ", strip=True)) for c in header_cells]
    headers = [h if h else f"Col{i+1}" for i, h in enumerate(headers)]

    # body rows
    body = tbl.find("tbody") or tbl
    trs = body.find_all("tr")
    rows: List[List[str]] = []
    started = False
    for tr in trs:
        tds = tr.find_all(["td", "th"])
        if not tds:
            continue
        # If we used first row as headers, skip it once
        if header_from_first_row and not started:
            started = True
            continue
        vals = [text_clean(td.get_text(" ", strip=True)) for td in tds]
        # normalize to headers length
        if len(vals) < len(headers):
            vals += [""] * (len(headers) - len(vals))
        elif len(vals) > len(headers):
            vals = vals[:len(headers)]
        rows.append(vals)

    # drop empty tables
    if not any(any(cell for cell in r) for r in rows):
        return None

    # map rows to dicts
    row_objs = [dict(zip(headers, r)) for r in rows]

    return {
        "section": find_section_title(tbl),
        "headers": headers,
        "rows": row_objs,
    }

def parse_html_file(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")

    # Heuristic: Yahoo pages tend to have multiple <table>s per section.
    # We’ll parse all tables and keep ones that have at least 2 columns
    # and 1+ non-empty rows.
    blocks: List[Dict[str, Any]] = []
    for tbl in soup.find_all("table"):
        blk = parse_table(tbl)
        if not blk:
            continue
        # filter out likely junk tables
        if len(blk["headers"]) < 2:
            continue
        if len(blk["rows"]) == 0:
            continue
        blocks.append(blk)

    # Deduplicate adjacent tables with identical section names by merging rows
    merged: List[Dict[str, Any]] = []
    for blk in blocks:
        if merged and merged[-1]["section"] == blk["section"] and merged[-1]["headers"] == blk["headers"]:
            merged[-1]["rows"].extend(blk["rows"])
        else:
            merged.append(blk)

    return merged

def main():
    files = discover_files()
    if not files:
        print("❌ No recordbook_*.html files found in public/data.")
        # still write an empty JSON so the app doesn’t crash
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump({"years": {}}, f, indent=2)
        return

    out: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    years_sorted = sorted(files.keys())  # ascending; UI will sort desc anyway

    for year in years_sorted:
        out[year] = {}
        kinds = files[year]
        for kind, path in kinds.items():
            key = KIND_TO_KEY.get(kind)
            if not key:
                continue
            try:
                blocks = parse_html_file(path)
                if blocks:
                    out[year][key] = blocks
                    print(f"• Parsed {year} {kind} -> {len(blocks)} block(s)")
                else:
                    print(f"• Parsed {year} {kind} -> 0 blocks (no usable tables)")
            except Exception as e:
                print(f"⚠️  Failed to parse {path}: {e}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"years": out}, f, indent=2)
    print(f"✔ Wrote {OUT_PATH}")

if __name__ == "__main__":
    main()
