"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

// --- H2H types (logic only, no UI impact) ---
type Pair = {
  a: string;
  b: string;
  a_wins: number;
  b_wins: number;
  ties: number;
  a_points_for: number;
  b_points_for: number;
};

type H2H = {
  managers: string[];
  pairs: Pair[];
  updated_at?: string;
};

// --- CSV parsing ---
type Row = Record<string, string>;
function parseCsv(text: string): Row[] {
  const lines = text.trim().split(/\r?\n/);
  if (!lines.length) return [];
  const headers = lines[0].split(",").map((h) => h.trim());
  return lines.slice(1).map((line) => {
    const cols = line.split(",");
    const row: Row = {};
    headers.forEach((h, i) => (row[h] = (cols[i] ?? "").trim()));
    return row;
  });
}

// --- Totals type ---
type Totals = {
  manager: string;
  seasons: number;
  gold: number;
  silver: number;
  bronze: number;
  podiums: number;
  points: number;
  avgFinish: number;
  playoffsMade: number;
  winPct: number;
};

const MIN_SEASONS_FOR_AVG = 3;

export default function HomePage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // --- load finishes CSV ---
  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const res = await fetch("/data/finishes.csv", { cache: "no-store" });
        if (!res.ok) throw new Error("finishes.csv not found");
        const text = await res.text();
        setRows(parseCsv(text));
      } catch (e: unknown) {
        if (e instanceof Error) setErr(e.message);
        else setErr("Failed to load finishes.csv");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // --- load H2H JSON ---
  const [h2hData, setH2hData] = useState<H2H | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/data/h2h.json", { cache: "no-store" });
        if (!res.ok) throw new Error("Failed to load h2h.json");
        const json: H2H = await res.json();
        setH2hData(json);
      } catch (err) {
        console.error(err);
      }
    })();
  }, []);

  // --- aggregate per manager ---
  const table: Totals[] = useMemo(() => {
    const byMgr = new Map<string, Totals>();
    const bestByMgrSeason = new Map<string, Map<string, number>>();

    for (const r of rows) {
      const mgr = (r.manager ?? "").trim();
      const season = (r.season ?? "").trim();
      const placeNum = Number(r.place);

      if (!mgr || !season || !Number.isFinite(placeNum) || placeNum <= 0 || placeNum >= 9000)
        continue;

      if (!byMgr.has(mgr)) {
        byMgr.set(mgr, {
          manager: mgr,
          seasons: 0,
          gold: 0,
          silver: 0,
          bronze: 0,
          podiums: 0,
          points: 0,
          avgFinish: 0,
          playoffsMade: 0,
          winPct: 0,
        });
        bestByMgrSeason.set(mgr, new Map<string, number>());
      }

      const t = byMgr.get(mgr)!;

      if (placeNum === 1) {
        t.gold += 1;
        t.points += 3;
      } else if (placeNum === 2) {
        t.silver += 1;
        t.points += 2;
      } else if (placeNum === 3) {
        t.bronze += 1;
        t.points += 1;
      }

      t.podiums = t.gold + t.silver + t.bronze;

      const m = bestByMgrSeason.get(mgr)!;
      const prev = m.get(season);
      if (prev == null || placeNum < prev) m.set(season, placeNum);
    }

    // --- finalize per-manager stats ---
    for (const [mgr, t] of byMgr.entries()) {
      const seasonBest = Array.from(
        (bestByMgrSeason.get(mgr) ?? new Map()).values()
      );

      t.seasons = seasonBest.length;
      t.avgFinish = t.seasons
        ? seasonBest.reduce((a, n) => a + n, 0) / t.seasons
        : 0;

      t.playoffsMade = seasonBest.filter((n) => n <= 4).length;

      // ✅ win percentage from h2h.json
      t.winPct = 0;
      if (h2hData) {
        let wins = 0;
        let losses = 0;
        let ties = 0;

        for (const p of h2hData.pairs) {
          if (p.a === mgr) {
            wins += p.a_wins;
            losses += p.b_wins;
            ties += p.ties;
          } else if (p.b === mgr) {
            wins += p.b_wins;
            losses += p.a_wins;
            ties += p.ties;
          }
        }

        const games = wins + losses + ties;
        t.winPct = games ? (wins + 0.5 * ties) / games : 0;
      }
    }

    const arr = Array.from(byMgr.values());
    arr.sort((a, b) => {
      if (b.points !== a.points) return b.points - a.points;
      if (b.gold !== a.gold) return b.gold - a.gold;
      if (a.avgFinish !== b.avgFinish) return a.avgFinish - b.avgFinish;
      return a.manager.localeCompare(b.manager);
    });

    return arr;
  }, [rows, h2hData]);

  // --- Hall of Fame ---
  const hallOfFame = useMemo(() => {
    if (!table.length) return { titles: [] as Totals[], bestAvg: [] as Totals[] };

    const titles = table
      .filter((t) => t.gold > 0)
      .sort((a, b) => {
        if (b.gold !== a.gold) return b.gold - a.gold;
        if (b.points !== a.points) return b.points - a.points;
        return a.manager.localeCompare(b.manager);
      });

    const eligible = table.filter((t) => t.seasons >= MIN_SEASONS_FOR_AVG);
    const bestAvg = eligible
      .sort((a, b) => {
        if (a.avgFinish !== b.avgFinish) return a.avgFinish - b.avgFinish;
        return a.manager.localeCompare(b.manager);
      })
      .slice(0, 5);

    return { titles, bestAvg };
  }, [table]);

  return (
    <div className="p-6 space-y-8">
      {/* Top-right navigation */}
      <div className="flex flex-wrap justify-end gap-3 mb-2">
        <Link href="/" className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          News &amp; Notes
        </Link>
        <Link href="/head-to-head" className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          H2H Record
        </Link>
        <Link href="/record-breakers" className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          Record Breakers
        </Link>
        <Link href="/draft-history" className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          Draft History
        </Link>
        <Link href="/league-finishes" className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          League Finishes
        </Link>
        <Link
          href="/waivers"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          {"Waiver 'Wonders'"}
        </Link>
      </div>

      <header>
        <h1 className="text-2xl font-semibold">Championship Roll of Honour</h1>
      </header>

      {/* Hall of Fame */}
      <section className="grid gap-4 md:grid-cols-2">
        {/* Titles */}
        <div className="rounded-2xl border shadow-sm p-4 bg-white/70 dark:bg-zinc-900/40">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">🏆 Championship Winners</h2>
            <span className="text-xs opacity-60">All champions</span>
          </div>
          {hallOfFame.titles.length ? (
            <ul className="mt-3 space-y-2">
              {hallOfFame.titles.map((t) => (
                <li
                  key={`titles-${t.manager}`}
                  className="flex items-center justify-between"
                >
                  <span className="font-medium">{t.manager}</span>
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs bg-yellow-100 text-yellow-800 dark:bg-yellow-950/40 dark:text-yellow-300">
                    {t.gold}×
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm opacity-70">No champions yet.</p>
          )}
        </div>

        {/* Best Average Finish (Top 5) */}
        <div className="rounded-2xl border shadow-sm p-4 bg-white/70 dark:bg-zinc-900/40">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">📈 Best Average Finish</h2>
            <span className="text-xs opacity-60">
              min {MIN_SEASONS_FOR_AVG} seasons (Top 5)
            </span>
          </div>
          {hallOfFame.bestAvg.length ? (
            <ul className="mt-3 space-y-2">
              {hallOfFame.bestAvg.map((t) => (
                <li
                  key={`avg-${t.manager}`}
                  className="flex items-center justify-between"
                >
                  <span className="font-medium">{t.manager}</span>
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
                    {t.avgFinish.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm opacity-70">Not enough seasons yet.</p>
          )}
        </div>
      </section>

      {/* Errors / Loading */}
      {err && (
        <div className="text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-2xl p-3">
          {err}
        </div>
      )}

      {/* Full table */}
      {loading ? (
        <div className="animate-pulse text-sm opacity-70">Loading…</div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border shadow-sm">
          <table className="min-w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-900">
              <tr>
                <th className="px-3 py-2 text-left font-medium uppercase tracking-wide w-10">
                  #
                </th>
                <th className="px-3 py-2 text-left font-medium uppercase tracking-wide">
                  Manager
                </th>
                <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-16">
                  🥇
                </th>
                <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-16">
                  🥈
                </th>
                <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-16">
                  🥉
                </th>
                <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-20">
                  Podiums
                </th>
                <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-20">
                  Seasons
                </th>
                {/* NEW column */}
                <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-28">
                  Playoffs Made
                </th>
                <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-20">
                  Points
                </th>
                <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-24">
                  Avg Finish
                </th>
                <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-24">
                  Win pct
                </th>
              </tr>
            </thead>
            <tbody>
              {table.map((t, i) => (
                <tr
                  key={t.manager}
                  className={i % 2 ? "bg-zinc-50 dark:bg-zinc-900/40" : ""}
                >
                  <td className="px-3 py-2 text-zinc-500">{i + 1}</td>
                  <td className="px-3 py-2 font-medium">{t.manager}</td>
                  <td className="px-3 py-2 text-center">{t.gold}</td>
                  <td className="px-3 py-2 text-center">{t.silver}</td>
                  <td className="px-3 py-2 text-center">{t.bronze}</td>
                  <td className="px-3 py-2 text-center">{t.podiums}</td>
                  <td className="px-3 py-2 text-center">{t.seasons}</td>
                  <td className="px-3 py-2 text-center">{t.playoffsMade}</td>
                  <td className="px-3 py-2 text-center font-semibold">{t.points}</td>
                  <td className="px-3 py-2 text-center">{t.avgFinish ? t.avgFinish.toFixed(2) : "—"}</td>
                  <td className="px-3 py-2 text-center">{t.winPct ?  t.winPct.toFixed(3) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs opacity-60">
        Points = 3 for 🥇, 2 for 🥈, 1 for 🥉. Lowest average finish is better. Playoffs Made = seasons with best finish ≤ 4.
      </p>
    </div>
  );
}
