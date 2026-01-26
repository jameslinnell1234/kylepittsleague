"use client";

import { useEffect, useMemo, useState, Fragment } from "react";
import Link from "next/link";

type Row = Record<string, string>;

function parseCsv(text: string): Row[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length === 0) return [];
  const headers = lines[0].split(",").map((h) => h.trim());
  return lines.slice(1).map((line) => {
    const cols = line.split(","); // simple CSV (no quoted commas)
    const row: Row = {};
    headers.forEach((h, i) => (row[h] = (cols[i] ?? "").trim()));
    return row;
  });
}

type SeasonLink = { year: number; draft: string };
type Manifest = { seasons: SeasonLink[] };

// Round tint (single-season only)
function roundBgClass(round: number): string {
  const palette = [
    "bg-rose-50 dark:bg-rose-950/30",
    "bg-orange-50 dark:bg-orange-950/30",
    "bg-amber-50 dark:bg-amber-950/30",
    "bg-lime-50 dark:bg-lime-950/30",
    "bg-emerald-50 dark:bg-emerald-950/30",
    "bg-teal-50 dark:bg-teal-950/30",
    "bg-cyan-50 dark:bg-cyan-950/30",
    "bg-sky-50 dark:bg-sky-950/30",
    "bg-indigo-50 dark:bg-indigo-950/30",
    "bg-fuchsia-50 dark:bg-fuchsia-950/30",
  ];
  const idx = Math.max(0, (Math.floor(round) - 1) % palette.length);
  return palette[idx];
}

function renderHeader(c: string) {
  switch (c) {
    case "round":
      return "R";
    case "pick":
      return "P";
    case "position":
      return "Pos";
    case "editorial_team_abbr":
      return "Team";
    case "adp":
      return "ADP";
    case "adp_diff":
      return "Δ ADP";
    default:
      return c.replaceAll("_", " ");
  }
}

function colClass(c: string) {
  switch (c) {
    case "round":
    case "pick":
      return "w-12 text-center";
    case "position":
    case "adp":
      return "w-16 text-center";
    case "adp_diff":
      return "w-20 text-center";
    default:
      return "";
  }
}

function renderCell(c: string, v: string) {
  let val = v ?? "";
  if (c === "adp" && val) {
    const num = Number(val);
    if (!Number.isNaN(num)) val = num.toFixed(1);
  }
  if (c === "adp_diff" && val !== "") {
    const num = Number(val);
    if (!Number.isNaN(num)) {
      const chip = "inline-flex items-center rounded-full px-2 py-0.5 text-xs";
      const style =
        num > 0
          ? "bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300"
          : "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300";
      return (
        <span className={`${chip} ${style}`}>
          {num > 0 ? "+" : ""}
          {num.toFixed(1)}
        </span>
      );
    }
  }
  return val;
}

export default function DraftHistoryPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [year, setYear] = useState<number | null>(null);

  const [rows, setRows] = useState<Row[]>([]);
  const [allRowsByYear, setAllRowsByYear] = useState<Record<number, Row[]>>({});
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [managerFilter, setManagerFilter] = useState<string>("");
  const [playerQuery, setPlayerQuery] = useState("");

  // Load manifest
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/data/manifest.json", { cache: "no-store" });
        const data = (await res.json()) as Manifest;
        setManifest(data);
        if (data.seasons?.length) setYear(data.seasons[0].year);
      } catch {
        setErr("Failed to load manifest.json");
      }
    })();
  }, []);

  // Load selected season
  useEffect(() => {
    (async () => {
      if (!manifest || year == null) return;
      const entry = manifest.seasons.find((s) => s.year === year);
      if (!entry) return;
      setLoading(true);
      setErr(null);
      try {
        const res = await fetch(entry.draft, { cache: "no-store" });
        const text = await res.text();
        setRows(parseCsv(text));
      } catch {
        setErr("Failed to load draft CSV");
      } finally {
        setLoading(false);
      }
    })();
  }, [manifest, year]);

  // Load all seasons
  useEffect(() => {
    (async () => {
      if (!manifest) return;
      const results: Array<[number, Row[]]> = await Promise.all(
        manifest.seasons.map(async (s): Promise<[number, Row[]]> => {
          try {
            const res = await fetch(s.draft, { cache: "no-store" });
            const text = await res.text();
            return [s.year, parseCsv(text)];
          } catch {
            return [s.year, [] as Row[]];
          }
        })
      );
      const map: Record<number, Row[]> = {};
      for (const [yr, arr] of results) map[yr] = arr;
      setAllRowsByYear(map);
    })();
  }, [manifest]);

  // Managers list
  const allManagers = useMemo(() => {
    const s = new Set<string>();
    for (const arr of Object.values(allRowsByYear)) {
      for (const r of arr) {
        const m = (r.manager ?? "").trim();
        if (m) s.add(m);
      }
    }
    return Array.from(s).sort();
  }, [allRowsByYear]);

  // Group by round
  const groupedByRoundSingle = useMemo(() => {
    const map = new Map<number, Row[]>();
    for (const r of rows) {
      const rn = Number(r.round);
      const key = Number.isFinite(rn) ? rn : 0;
      map.set(key, [...(map.get(key) ?? []), r]);
    }
    return Array.from(map.entries()).sort((a, b) => a[0] - b[0]);
  }, [rows]);

  // Manager rows
  const managerRowsFlat = useMemo(() => {
    if (!managerFilter) return [];
    const out: (Row & { season: string })[] = [];
    const years = Object.keys(allRowsByYear).map(Number).sort((a, b) => b - a);

    for (const y of years) {
      for (const r of allRowsByYear[y] ?? []) {
        if ((r.manager ?? "") === managerFilter)
          out.push({ ...r, season: String(y) });
      }
    }

    out.sort((a, b) => {
      const ay = Number(a.season),
        by = Number(b.season);
      if (ay !== by) return by - ay;
      const ar = Number(a.round),
        br = Number(b.round);
      if (ar !== br) return ar - br;
      return Number(a.pick) - Number(b.pick);
    });

    return out;
  }, [managerFilter, allRowsByYear]);

  // Player search
  const playerSearchResults = useMemo(() => {
    if (!playerQuery.trim()) return [];
    const q = playerQuery.trim().toLowerCase();
    const results: Array<Row & { season: string }> = [];

    for (const [yr, arr] of Object.entries(allRowsByYear)) {
      for (const r of arr) {
        if ((r.player ?? "").toLowerCase().includes(q)) {
          results.push({ ...r, season: yr });
        }
      }
    }

    results.sort((a, b) => {
      const ay = Number(a.season),
        by = Number(b.season);
      if (ay !== by) return by - ay;
      const ar = Number(a.round),
        br = Number(b.round);
      if (ar !== br) return ar - br;
      return Number(a.pick) - Number(b.pick);
    });

    return results;
  }, [playerQuery, allRowsByYear]);

  // Columns
  const columns = useMemo(() => {
    if (managerFilter || playerQuery) {
      return [
        "round",
        "pick",
        "player",
        "manager",
        "adp",
        "adp_diff",
        "position",
        "editorial_team_abbr",
      ];
    }
    if (!rows.length) return [];
    return [
      "round",
      "pick",
      "manager",
      "player",
      "adp",
      "adp_diff",
      "position",
      "editorial_team_abbr",
    ];
  }, [rows, managerFilter, playerQuery]);

  return (
    <div className="p-6 space-y-6">
      {/* Navigation */}
      <div className="flex flex-wrap justify-end gap-3 mb-2">
        <Link
          href="/"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          News &amp; Notes
        </Link>
        <Link
          href="/head-to-head"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          H2H Record
        </Link>
        <Link
          href="/record-breakers"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          Record Breakers
        </Link>
        <Link
          href="/roll-of-honour"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          Roll of Honour
        </Link>
        <Link
          href="/league-finishes"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          League Finishes
        </Link>
        <Link
          href="/waivers"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          {"Waiver 'Wonders'"}
        </Link>
      </div>

      <header>
        <h1 className="text-2xl font-semibold">Draft History</h1>
      </header>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mt-4">
        <select
          disabled={!!managerFilter || !!playerQuery}
          value={year ?? ""}
          onChange={(e) => setYear(Number(e.target.value))}
          className="border rounded-xl px-3 py-2 bg-white dark:bg-zinc-900 disabled:opacity-50"
        >
          {(manifest?.seasons ?? []).map((s) => (
            <option key={s.year} value={s.year}>
              {s.year}
            </option>
          ))}
        </select>

        <select
          disabled={!!playerQuery}
          value={managerFilter}
          onChange={(e) => setManagerFilter(e.target.value)}
          className="border rounded-xl px-3 py-2 bg-white dark:bg-zinc-900 disabled:opacity-50"
        >
          <option value="">All managers</option>
          {allManagers.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>

        {/* Player Search */}
        <input
          type="search"
          placeholder="Search player / team / pos / NFL…"
          value={playerQuery}
          onChange={(e) => setPlayerQuery(e.target.value)}
          className="border rounded-xl px-3 py-2 bg-white dark:bg-zinc-900 w-64"
        />
      </div>

      {err && (
        <div className="text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-xl p-3">
          {err}
        </div>
      )}

      {loading && !managerFilter && !playerQuery ? (
        <div className="animate-pulse text-sm opacity-70">Loading…</div>
      ) : (
        <div className="overflow-x-auto border rounded-2xl shadow-sm">
          <table className="min-w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-900">
              <tr>
                {columns.map((c) => (
                  <th
                    key={c}
                    className={`px-2 py-2 font-medium uppercase tracking-wide ${colClass(
                      c
                    )} text-left`}
                  >
                    {renderHeader(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* Player search takes priority */}
              {playerQuery ? (
                playerSearchResults.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="px-3 py-3 opacity-70">
                      No players found.
                    </td>
                  </tr>
                ) : (
                  playerSearchResults.map((r, i, arr) => {
                    const prevSeason = i > 0 ? arr[i - 1].season : null;
                    const newSeason = prevSeason !== r.season;
                    return (
                      <Fragment key={i}>
                        {newSeason && (
                          <tr className="bg-zinc-200/70 dark:bg-zinc-800/60">
                            <td
                              colSpan={columns.length}
                              className="px-3 py-2 font-semibold"
                            >
                              Season {r.season}
                            </td>
                          </tr>
                        )}
                        <tr>
                          {columns.map((c) => (
                            <td
                              key={c}
                              className={`px-2 py-2 whitespace-nowrap ${colClass(
                                c
                              )}`}
                            >
                              {renderCell(c, r[c] ?? "")}
                            </td>
                          ))}
                        </tr>
                      </Fragment>
                    );
                  })
                )
              ) : !managerFilter ? (
                // Single-season view
                groupedByRoundSingle.map(([roundNum, roundRows]) => (
                  <Fragment key={roundNum}>
                    <tr className="bg-zinc-100/70 dark:bg-zinc-900/60">
                      <td
                        colSpan={columns.length}
                        className="px-3 py-2 font-semibold"
                      >
                        Round {roundNum}
                      </td>
                    </tr>
                    {roundRows.map((r, i) => (
                      <tr key={i} className={roundBgClass(Number(r.round))}>
                        {columns.map((c) => (
                          <td
                            key={c}
                            className={`px-2 py-2 whitespace-nowrap ${colClass(
                              c
                            )}`}
                          >
                            {renderCell(c, r[c] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </Fragment>
                ))
              ) : (
                // Manager view
                managerRowsFlat.map((r, i, arr) => {
                  const prevSeason = i > 0 ? arr[i - 1].season : null;
                  const newSeason = prevSeason !== r.season;
                  return (
                    <Fragment key={i}>
                      {newSeason && (
                        <tr className="bg-zinc-200/70 dark:bg-zinc-800/60">
                          <td
                            colSpan={columns.length}
                            className="px-3 py-2 font-semibold"
                          >
                            Season {r.season}
                          </td>
                        </tr>
                      )}
                      <tr>
                        {columns.map((c) => (
                          <td
                            key={c}
                            className={`px-2 py-2 whitespace-nowrap ${colClass(
                              c
                            )}`}
                          >
                            {renderCell(c, r[c] ?? "")}
                          </td>
                        ))}
                      </tr>
                    </Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs opacity-60">
        ADP Diff = Actual Pick − ADP (positive = picked earlier; negative = value).
      </p>
    </div>
  );
}
