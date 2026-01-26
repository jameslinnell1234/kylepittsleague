"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

type Txn = {
  season: number;
  date: string;
  type: string;
  player: string;
  position: string;
  nfl: string;
  from_team: string;
  to_team: string;
  note: string;
};

type TxnFile = {
  season: number;
  rows: Txn[];
  updated_at: string;
};

type DraftRow = {
  player: string;
  position: string;
  nfl: string;
  manager: string;
};

type OwnedTeam = { team: string; type: "drafted" | "waiver" | "trade" };

function classChip(color: "emerald" | "zinc" | "blue" | "red" = "emerald") {
  const base = "inline-flex items-center rounded-full px-2 py-0.5 text-xs";
  const map: Record<string, string> = {
    emerald:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
    zinc: "bg-zinc-100 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300",
    blue: "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300",
    red: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300",
  };
  return `${base} ${map[color]}`;
}

function parseCSV(text: string): DraftRow[] {
  const lines = text.trim().split(/\r?\n/);
  const headers = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const rows: DraftRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = lines[i].split(",").map((c) => c.trim());
    const obj: Record<string, string> = {};
    headers.forEach((h, idx) => (obj[h] = cells[idx] || ""));
    rows.push({
      player: obj.player || "",
      position: obj.position || "",
      nfl: obj.editorial_team_abbr || "",
      manager: obj.manager || "",
    });
  }
  return rows;
}

export default function TransactionsPage() {
  const [season] = useState<number>(2025);
  const [data, setData] = useState<TxnFile | null>(null);
  const [draft, setDraft] = useState<DraftRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const [query, setQuery] = useState<string>("");
  const [minPickups, setMinPickups] = useState<number>(2); // show 2+ ownerships

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setErr(null);

        const resTx = await fetch(`/data/waiver_transactions_${season}.json`, {
          cache: "no-store",
        });
        if (!resTx.ok) throw new Error("Failed to load waiver transactions");
        const txJson = (await resTx.json()) as TxnFile;

        const resDraft = await fetch(`/data/draft_results_${season}.csv`, {
          cache: "no-store",
        });
        let draftRows: DraftRow[] = [];
        if (resDraft.ok) {
          const csvText = await resDraft.text();
          draftRows = parseCSV(csvText);
        }

        setData(txJson);
        setDraft(draftRows);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    })();
  }, [season]);

  const leaderboard = useMemo(() => {
    if (!data) return [];

    type MapVal = {
      player: string;
      position: string;
      nfl: string;
      drafted: number;
      adds: number;
      total: number;
      owned: OwnedTeam[];
    };

    const map = new Map<string, MapVal>();

    // Drafted first
    for (const d of draft) {
      const key = d.player.trim();
      if (!key) continue;
      const existing = map.get(key) ?? {
        player: key,
        position: d.position || "",
        nfl: d.nfl || "",
        drafted: 0,
        adds: 0,
        total: 0,
        owned: [],
      };
      existing.drafted += 1;
      existing.total += 1;
      existing.position = existing.position || d.position || "";
      existing.nfl = existing.nfl || d.nfl || "";
      if (d.manager?.trim()) {
        existing.owned.unshift({ team: d.manager.trim(), type: "drafted" });
      }
      map.set(key, existing);
    }

    // Adds (waiver, free agent, and trades), sorted chronologically
    const adds = data.rows
      .filter((r) => r.player && r.type === "add" && r.to_team?.trim())
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

    for (const r of adds) {
      const key = r.player.trim();
      if (!key) continue;
      const existing = map.get(key) ?? {
        player: key,
        position: r.position || "",
        nfl: r.nfl || "",
        drafted: 0,
        adds: 0,
        total: 0,
        owned: [],
      };
      existing.adds += 1;
      existing.total += 1;
      existing.position = existing.position || r.position || "";
      existing.nfl = existing.nfl || r.nfl || "";

      const type: OwnedTeam["type"] =
        r.note === "Trade" ? "trade" : "waiver";
      existing.owned.push({ team: r.to_team.trim(), type });
      map.set(key, existing);
    }

    return Array.from(map.values())
      .filter((x) => x.total >= minPickups) // filter 2+ ownerships
      .filter(
        (x) =>
          !query.trim() ||
          x.player.toLowerCase().includes(query.toLowerCase()) ||
          x.owned.some((o) => o.team.toLowerCase().includes(query.toLowerCase()))
      )
      .sort((a, b) => b.total - a.total || a.player.localeCompare(b.player));
  }, [data, draft, query, minPickups]);

  return (
  <div className="p-6 space-y-6">
    <div className="flex flex-wrap justify-end gap-3 mb-2">
      {[
        { href: "/", label: "News & Notes" },
        { href: "/head-to-head", label: "H2H Record" },
        { href: "/record-breakers", label: "Record Breakers" },
        { href: "/roll-of-honour", label: "Roll of Honour" },
        { href: "/draft-history", label: "Draft History" },
        { href: "/league-finishes", label: "League Finishes" },
      ].map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          {link.label}
        </Link>
      ))}
    </div>

    <header className="flex items-center justify-between">
      <h1 className="text-2xl font-semibold">
        Player Ownership (Draft + Adds + Trades) – {season}
      </h1>
    </header>

    <div className="flex flex-wrap items-center gap-3">
      <input
        type="search"
        placeholder="Search player / team / pos / NFL…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="border rounded-xl px-3 py-2 bg-white dark:bg-zinc-900 w-64"
      />
      <label className="text-sm opacity-80">
        Min total ownerships:
        <input
          type="number"
          min={2}
          value={minPickups}
          onChange={(e) =>
            setMinPickups(Math.max(2, Number(e.target.value) || 2))
          }
          className="border rounded-xl px-2 py-1 bg-white dark:bg-zinc-900 ml-2 w-20"
        />
      </label>
    </div>

    {err && (
      <div className="text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-xl p-3">
        {err}
      </div>
    )}

    {loading ? (
      <div className="animate-pulse text-sm opacity-70">Loading…</div>
    ) : (
      <section className="rounded-2xl border shadow-sm p-4 bg-white/70 dark:bg-zinc-900/40">
        <h2 className="text-lg font-semibold mb-3">Ownership Breakdown</h2>

        <div className="overflow-x-auto rounded-xl border">
          <table className="min-w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-900">
              <tr>
                <th className="px-3 py-2 text-left font-medium uppercase tracking-wide">#</th>
                <th className="px-3 py-2 text-left font-medium uppercase tracking-wide">Player</th>
                <th className="px-3 py-2 text-left font-medium uppercase tracking-wide">Pos</th>
                <th className="px-3 py-2 text-left font-medium uppercase tracking-wide">NFL</th>
                <th className="px-3 py-2 text-center font-medium uppercase tracking-wide">Total</th>

                {/* Hide owners header on mobile but show on md+ */}
                <th className="px-3 py-2 text-left font-medium uppercase tracking-wide hidden md:table-cell">
                  Owned By
                </th>
              </tr>
            </thead>

            <tbody>
              {leaderboard.map((row, i) => {
                const mainKey = `${row.player}-${i}`;
                const ownersKey = `${row.player}-${i}-owners`;

                return [
                  // MAIN ROW (always visible)
                  <tr key={mainKey} className={i % 2 ? "bg-zinc-50 dark:bg-zinc-900/40" : ""}>
                    <td className="px-3 py-2">{i + 1}</td>
                    <td className="px-3 py-2 font-medium">{row.player}</td>
                    <td className="px-3 py-2">{row.position || "—"}</td>
                    <td className="px-3 py-2">{row.nfl || "—"}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={classChip("blue")}>{row.total}</span>
                    </td>

                    {/* DESKTOP owners cell */}
                    <td className="px-3 py-2 hidden md:table-cell">
                      <div className="flex flex-wrap gap-1">
                        {row.owned.length > 0 ? (
                          row.owned.map((o, idx) => (
                            <span
                              key={`${o.team}-${idx}`}
                              className={classChip(
                                o.type === "drafted" ? "emerald" : o.type === "trade" ? "red" : "zinc"
                              )}
                            >
                              {o.team}
                            </span>
                          ))
                        ) : (
                          <span className="opacity-60">—</span>
                        )}
                      </div>
                    </td>
                  </tr>,

                  // MOBILE-ONLY OWNERS ROW (visible only under md)
                  <tr key={ownersKey} className={`md:hidden ${i % 2 ? "bg-zinc-50 dark:bg-zinc-900/40" : ""}`}>
                    <td colSpan={5} className="px-3 pb-4">
                      <div className="text-xs opacity-60 mb-1">Owned By</div>
                      <div className="flex flex-wrap gap-1">
                        {row.owned.length > 0 ? (
                          row.owned.map((o, idx) => (
                            <span
                              key={`${o.team}-m-${idx}`}
                              className={classChip(
                                o.type === "drafted" ? "emerald" : o.type === "trade" ? "red" : "zinc"
                              )}
                            >
                              {o.team}
                            </span>
                          ))
                        ) : (
                          <span className="opacity-60">—</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ];
              })}

              {!leaderboard.length && (
                <tr>
                  <td className="px-3 py-3 opacity-60" colSpan={6}>
                    No data found for these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    )}
  </div>
);




}
