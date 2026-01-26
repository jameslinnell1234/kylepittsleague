// Updated page with head-to-head styling applied exactly
// (No logic changes, only styling updated to match H2H page)
// standings.json must be done manually - json the final standings and insert into standings.json

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Player = {
  name: string;
  position: string;
  editorial_team_abbr?: string;
  team?: string;
};

type Champion = {
  season: number;
  manager: string;
  team_name: string;
  roster: Player[];
};

type TeamStanding = {
  rank: number;
  team: string;
  record: string;
  points_for: number;
  points_against: number;
  streak: string;
  waiver: number;
  moves: number;
  achievement?: string;
};

type SeasonStandings = {
  league: {
    season: number;
    standings: TeamStanding[];
  };
};

// Restored alternating white desktop rows (matching Head-to-Head page)
function rowBgClass(idx: number): string {
  return idx % 2 ? "bg-zinc-50 dark:bg-zinc-900/40" : "";
}

export default function ChampsRostersPage() {
  const [champions, setChampions] = useState<Champion[]>([]);
  const [standings, setStandings] = useState<SeasonStandings[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [rostersRes, standingsRes] = await Promise.all([
          fetch("/data/champion_rosters.json", { cache: "no-store" }),
          fetch("/data/standings.json", { cache: "no-store" }),
        ]);

        if (!rostersRes.ok || !standingsRes.ok)
          throw new Error("Failed to load data files.");

        const rostersRaw = await rostersRes.json();
        const standingsRaw = await standingsRes.json();

        const champs: Champion[] = Array.isArray(rostersRaw)
          ? rostersRaw
          : rostersRaw?.champions ?? [];

        const standingsData: SeasonStandings[] = Array.isArray(standingsRaw)
          ? standingsRaw
          : standingsRaw?.seasons
          ? standingsRaw.seasons
          : [standingsRaw];

        champs.sort((a, b) => b.season - a.season);
        standingsData.sort((a, b) => b.league.season - a.league.season);

        setChampions(champs);
        setStandings(standingsData);

        if (champs.length) setSelectedYear(champs[0].season);
      } catch (e: unknown) {
        setErr(e instanceof Error ? e.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="p-6 animate-pulse text-sm opacity-70">Loading data…</div>
    );
  }

  if (err) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-semibold mb-4">League Champions & Standings</h1>
        <div className="text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-xl p-3">
          {err}
        </div>
      </div>
    );
  }

  const currentStandings = standings.find(
    (s) => s.league.season === selectedYear
  );
  const currentChampion = champions.find((c) => c.season === selectedYear);

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
          href="/draft-history"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          Draft History
        </Link>
        <Link
          href="/waivers"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition"
        >
          {"Waiver 'Wonders'"}
        </Link>
      </div>

      <header>
        <h1 className="text-2xl font-semibold">
          {"League Standings & Champion's Rosters"}
        </h1>
      </header>

      {/* Year Selector */}
      <div className="flex flex-wrap gap-3 mt-4">
        <select
          value={selectedYear ?? ""}
          onChange={(e) => setSelectedYear(Number(e.target.value))}
          className="border rounded-xl px-3 py-2 bg-white dark:bg-zinc-900"
        >
          {standings.map((s) => (
            <option key={s.league.season} value={s.league.season}>
              {s.league.season}
            </option>
          ))}
        </select>
      </div>

      {/* Standings Table */}
      {currentStandings ? (
        <div className="overflow-x-auto border rounded-2xl shadow-sm">
          <table className="min-w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-900">
              <tr>
                {["Rank", "Team", "Record", "PF", "PA", "Streak", "Moves"].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-2 py-2 font-medium uppercase tracking-wide text-left"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {currentStandings.league.standings.map((team, i) => (
                <tr key={team.rank} className={rowBgClass(i)}>
                  <td className="px-2 py-2 whitespace-nowrap">{team.rank}</td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    {team.team}{" "}
                    {team.achievement && (
                      <span className="opacity-70">{team.achievement}</span>
                    )}
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">{team.record}</td>
                  <td className="px-2 py-2 whitespace-nowrap">{team.points_for}</td>
                  <td className="px-2 py-2 whitespace-nowrap">{team.points_against}</td>
                  <td className="px-2 py-2 whitespace-nowrap">{team.streak}</td>
                  <td className="px-2 py-2 whitespace-nowrap">{team.moves}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-xs opacity-60">No standings found for this season.</p>
      )}

      {/* Champion Roster */}
      {currentChampion && (
        <div className="overflow-x-auto border rounded-2xl shadow-sm mt-4">
          <table className="min-w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-900">
              <tr>
                {["Player", "Position"].map((h) => (
                  <th
                    key={h}
                    className="px-2 py-2 font-medium uppercase tracking-wide text-left"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {currentChampion.roster.map((p, i) => (
                <tr key={`${currentChampion.season}-${i}`} className={rowBgClass(i)}>
                  <td className="px-2 py-2 whitespace-nowrap">{p.name}</td>
                  <td className="px-2 py-2 whitespace-nowrap">{p.position}</td>
                </tr>
              ))}

              {!currentChampion.roster?.length && (
                <tr>
                  <td colSpan={3} className="px-2 py-2 opacity-60">
                    No roster data.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}