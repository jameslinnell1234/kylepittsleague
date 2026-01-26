"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

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

type Row = {
  opponent: string;
  wins: number;
  losses: number;
  ties: number;
  pf: number;
  pa: number;
  winPct: number;
};

// Managers to hide from UI but include in stats
const HIDDEN = new Set(["Brendan"]);

export default function HeadToHeadPage() {
  const [data, setData] = useState<H2H | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [manager, setManager] = useState<string>("");

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/data/h2h.json", { cache: "no-store" });
        if (!res.ok) throw new Error("Failed to load h2h.json");
        const json: H2H = await res.json();
        setData(json);

        // Pick first non-hidden manager as default
        if (json.managers?.length && !manager) {
          const firstVisible = json.managers.find((m) => !HIDDEN.has(m));
          if (firstVisible) setManager(firstVisible);
        }
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Failed to load head-to-head data";
        setErr(message);
      }
    })();
    // We intentionally don't include `manager` here to avoid resetting selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Build the full table (includes hidden opponents so totals & win% are correct)
  const table: Row[] = useMemo(() => {
    if (!data || !manager) return [];
    const rows: Row[] = [];
    const oppSet = new Set<string>(data.managers.filter((m) => m !== manager));

    for (const p of data.pairs) {
      if (p.a === manager) {
        const opp = p.b;
        if (!oppSet.has(opp)) continue;
        const wins = p.a_wins;
        const losses = p.b_wins;
        const ties = p.ties;
        const pf = p.a_points_for;
        const pa = p.b_points_for;
        const games = wins + losses + ties;
        const winPct = games ? (wins + 0.5 * ties) / games : 0;
        rows.push({ opponent: opp, wins, losses, ties, pf, pa, winPct });
      } else if (p.b === manager) {
        const opp = p.a;
        if (!oppSet.has(opp)) continue;
        const wins = p.b_wins;
        const losses = p.a_wins;
        const ties = p.ties;
        const pf = p.b_points_for;
        const pa = p.a_points_for;
        const games = wins + losses + ties;
        const winPct = games ? (wins + 0.5 * ties) / games : 0;
        rows.push({ opponent: opp, wins, losses, ties, pf, pa, winPct });
      }
    }

    rows.sort((a, b) => {
      if (b.winPct !== a.winPct) return b.winPct - a.winPct;
      const gA = a.wins + a.losses + a.ties;
      const gB = b.wins + b.losses + b.ties;
      if (gB !== gA) return gB - gA; // more history first
      return a.opponent.localeCompare(b.opponent);
    });

    return rows;
  }, [data, manager]);

  // What we actually render in the table (hide Brendan from view only)
  const visibleTable: Row[] = useMemo(() => {
    if (!manager) return [];
    return table.filter((r) => !HIDDEN.has(r.opponent));
  }, [table, manager]);

  if (err) {
    return (
      <div className="p-6">
        <div className="text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-xl p-3">
          {err}
        </div>
      </div>
    );
  }

  if (!data) return <div className="p-6">Loading…</div>;

  return (
    <div className="p-6 space-y-8">
      {/* Nav (matches your site) */}
      <div className="flex flex-wrap justify-end gap-3">
        <Link
          href="/"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          News &amp; Notes
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
          href="/draft-history"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          Draft History
        </Link>
        <Link
          href="/league-finishes"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          League Finishes
        </Link>
        <Link
          href="/waivers"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          {"Waiver 'Wonders'"}
        </Link>
      </div>

      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Head-to-Head</h1>
        <div className="flex gap-3">
          <select
            className="border rounded-xl px-3 py-2 bg-white dark:bg-zinc-900"
            value={manager}
            onChange={(e) => setManager(e.target.value)}
          >
            {data.managers
              .filter((m) => !HIDDEN.has(m)) // hide Brendan from dropdown
              .map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
          </select>
        </div>
      </header>

      <section>
        <div className="rounded-2xl border shadow-sm p-4 bg-white/70 dark:bg-zinc-900/40">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">{manager} vs League</h2>
           </div>

          {/* Totals summary — computed from FULL table (includes Brendan) */}
          {table.length > 0 && (
            <div className="mt-3 text-sm opacity-80">
              {(() => {
                const totW = table.reduce((a, r) => a + r.wins, 0);
                const totL = table.reduce((a, r) => a + r.losses, 0);
                const totT = table.reduce((a, r) => a + r.ties, 0);
                const pf = table.reduce((a, r) => a + r.pf, 0);
                const pa = table.reduce((a, r) => a + r.pa, 0);
                const gp = totW + totL + totT;
                const wp = gp ? ((totW + 0.5 * totT) / gp) : 0;
                return (
                  <span>
                    Overall:{" "}
                    <span className="font-semibold">
                      {totW}-{totL}
                      {totT ? `-${totT}` : ""}
                    </span>{" "}
                    &middot; PF {pf.toFixed(1)} / PA {pa.toFixed(1)} &middot; PCT {" "}
                    {wp.toFixed(3)}
                  </span>
                );
              })()}
            </div>
          )}

          <div className="overflow-x-auto mt-3 rounded-xl border">
            <table className="min-w-full text-sm">
              <thead className="bg-zinc-50 dark:bg-zinc-900">
                <tr>
                  <th className="px-3 py-2 text-left font-medium uppercase tracking-wide">
                    Opponent
                  </th>
                  <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-24">
                    W
                  </th>
                  <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-24">
                    L
                  </th>
                  <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-24">
                    T
                  </th>
                  <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-28">
                    PF
                  </th>
                  <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-28">
                    PA
                  </th>
                  <th className="px-3 py-2 text-center font-medium uppercase tracking-wide w-28">
                    PCT
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleTable.map((r, i) => (
                  <tr
                    key={r.opponent}
                    className={i % 2 ? "bg-zinc-50 dark:bg-zinc-900/40" : ""}
                  >
                    <td className="px-3 py-2 font-medium">{r.opponent}</td>
                    <td className="px-3 py-2 text-center">{r.wins}</td>
                    <td className="px-3 py-2 text-center">{r.losses}</td>
                    <td className="px-3 py-2 text-center">{r.ties}</td>
                    <td className="px-3 py-2 text-center">{r.pf.toFixed(2)}</td>
                    <td className="px-3 py-2 text-center">{r.pa.toFixed(2)}</td>
                    <td className="px-3 py-2 text-center">
                      {(r.winPct).toFixed(3)}
                    </td>
                  </tr>
                ))}
                {!visibleTable.length && (
                  <tr>
                    <td colSpan={7} className="px-3 py-4 text-sm opacity-70">
                      No head-to-head results for {manager}.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
