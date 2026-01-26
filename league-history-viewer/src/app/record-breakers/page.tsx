"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

/** ---------- Types ---------- */
type StringMap = Record<string, string>;

interface RecordSection {
  section: string;
  headers: string[];
  rows: StringMap[];
}

interface YearData {
  head_to_head?: RecordSection[];
  team_points?: RecordSection[];
  team_stats?: RecordSection[];
}

interface RecordsData {
  years: Record<string, YearData>;
}

type SeasonalKey = "head_to_head" | "team_points" | "team_stats";
type Mode = "all_time" | SeasonalKey;

/** ---------- Global removals ---------- */
function shouldExcludeSection(sectionName: string): boolean {
  const s = sectionName.trim().toLowerCase();

  if (s.includes("points from draft players")) return true;
  if (s.includes("points from drafted players")) return true;

  if (
    (s.includes("points from waiver-wire pickups") || s.includes("points from waiver wire pickups")) &&
    s.includes("least")
  ) {
    return true;
  }

  if (s.includes("kicking points") && s.includes("least")) return true;
  if (s.includes("defensive points") && s.includes("least")) return true;
  if (s.includes("touchdowns") && s.includes("least")) return true;
  if (s.includes("passing yards") && s.includes("least")) return true;
  if (s.includes("rushing yards") && s.includes("least")) return true;
  if (s.includes("receiving yards") && s.includes("least")) return true;
  if (s.includes("field goals") && s.includes("least")) return true;
  if (s.includes("post-draft") && s.includes("least")) return true;

  if (s.includes("field goals") && s.includes("most")) return true;

  if (s.includes("margin of defeat")) return true;

  return false;
}

/** ---------- Helpers ---------- */
function hasAllTimeTag(row: StringMap): boolean {
  return Object.values(row).some((v) => v.toLowerCase().includes("all time"));
}

const seasonTagRe = /\s*(,|-)?\s*season\s+\d{4}\s*$/i;
const allTimeWordRe = /\ball\s*time\b/gi;
const multiSpaceRe = /\s+/g;
const dashRe = /[\u2012\u2013\u2014\u2212]/g;
const punctRe = /[‐-–—]+/g;

function normalizeCell(val: string): string {
  let s = (val ?? "").toLowerCase().trim();
  s = s.replace(dashRe, "-").replace(punctRe, "-");
  s = s.replace(allTimeWordRe, "");
  s = s.replace(seasonTagRe, "");
  s = s.replace(multiSpaceRe, " ").trim();
  return s;
}

function extractNumericSignature(headers: string[], row: StringMap): string {
  if (!headers.length) return "";
  const last = row[headers[headers.length - 1]] ?? "";
  const num = (last.match(/-?\d+(\.\d+)?/g) || [""]).join("|");
  return num;
}

function numericFromRow(headers: string[], row: StringMap): number | null {
  if (!headers.length) return null;
  const raw = row[headers[headers.length - 1]] ?? "";
  const m = raw.match(/-?\d+(\.\d+)?/);
  return m ? Number(m[0]) : null;
}

/** ---------- Section ordering ---------- */
const ORDER_PATTERNS: { tokens: string[] }[] = [
  { tokens: ["win"] },
  { tokens: ["loss"] },
  { tokens: ["team points", "most"] },
  { tokens: ["touchdowns", "most"] },
  { tokens: ["rushing", "most"] },
  { tokens: ["receiving", "most"] },
  { tokens: ["passing", "most"] },
  { tokens: ["offensive points", "most"] },
  { tokens: ["margin of victory", "largest"] },
  { tokens: ["strength of schedule", "hardest"] },
  { tokens: ["team points", "least"] },
  { tokens: ["offensive points", "least"] },
  { tokens: ["margin of victory", "smallest"] },
  { tokens: ["kicking points", "most"] },
  { tokens: ["defensive points", "most"] },
  { tokens: ["strength of schedule", "easiest"] },
];

function rankSection(title: string): number {
  const t = normalizeCell(title);
  for (let i = 0; i < ORDER_PATTERNS.length; i++) {
    const { tokens } = ORDER_PATTERNS[i];
    if (tokens.every((tok) => t.includes(tok))) {
      if (tokens.length === 1 && tokens[0] === "win" && t.includes("margin of victory")) continue;
      if (tokens.length === 1 && tokens[0] === "loss" && t.includes("margin of victory")) continue;
      return i;
    }
  }
  return 10_000;
}

function compareSections(a: RecordSection, b: RecordSection): number {
  const ra = rankSection(a.section);
  const rb = rankSection(b.section);
  if (ra !== rb) return ra - rb;
  return a.section.localeCompare(b.section);
}

/** ---------- Component ---------- */
export default function RecordBreakersPage() {
  const [data, setData] = useState<RecordsData | null>(null);
  const [mode, setMode] = useState<Mode>("all_time");
  const [year, setYear] = useState<string>("");

  useEffect(() => {
    (async () => {
      const res = await fetch("/data/records.json", { cache: "no-store" });
      const json: RecordsData = await res.json();
      const years = Object.keys(json.years).sort();
      setYear(years[years.length - 1] ?? "");
      setData(json);
    })();
  }, []);

  /** ---------- All-Time aggregation ---------- */
  const allTimeSections = useMemo<RecordSection[]>(() => {
    if (!data) return [];
    const bySection = new Map<string, { headers: string[]; rows: StringMap[] }>();

    const push = (title: string, headers: string[], row: StringMap) => {
      if (!bySection.has(title)) bySection.set(title, { headers: [...headers], rows: [] });
      bySection.get(title)!.rows.push(row);
    };

    for (const yd of Object.values(data.years)) {
      (["head_to_head", "team_points", "team_stats"] as SeasonalKey[]).forEach((key) => {
        const sections = yd[key];
        if (!sections) return;
        for (const sec of sections) {
          if (shouldExcludeSection(sec.section)) continue;
          // ONLY include All Time rows
          sec.rows.filter(hasAllTimeTag).forEach((r) => push(sec.section, sec.headers, r));
        }
      });
    }

    const out: RecordSection[] = [];

    for (const [title, { headers, rows }] of bySection.entries()) {
      const secNorm = normalizeCell(title);
      const keepMin =
        secNorm.includes("least") || secNorm.includes("easiest") || secNorm.includes("smallest");
      const keepMax = !keepMin;

      const byRecord = new Map<string, { row: StringMap; val: number }>();

      for (const r of rows) {
        const team = normalizeCell(r[headers[0]] ?? r["Record"] ?? "");
        const valRaw = numericFromRow(headers, r);
        if (valRaw == null || Number.isNaN(valRaw)) continue;

        const key = secNorm + "::" + team;
        const current = byRecord.get(key);

        if (!current || current.val == null) {
          byRecord.set(key, { row: r, val: valRaw });
          continue;
        }

        const better = (keepMax && valRaw > current.val) || (keepMin && valRaw < current.val);
        if (better) byRecord.set(key, { row: r, val: valRaw });
      }

      const deduped = Array.from(byRecord.values()).map((v) => v.row);
      if (deduped.length) out.push({ section: title, headers, rows: deduped });
    }

    out.sort(compareSections);
    return out;
  }, [data]);

  /** ---------- Seasonal sections ---------- */
  const seasonalSections = useMemo<RecordSection[]>(() => {
    if (!data || mode === "all_time" || !year) return [];
    const yd = data.years[year];
    if (!yd) return [];

    const secs = yd[mode] ?? [];
    const out: RecordSection[] = [];

    for (const sec of secs) {
      if (shouldExcludeSection(sec.section)) continue;
      const rows = sec.rows.filter((r) => !hasAllTimeTag(r));
      if (!rows.length) continue;

      const seen = new Set<string>();
      const keep: StringMap[] = [];
      for (const r of rows) {
        const sig =
          normalizeCell(sec.section) +
          " :: " +
          normalizeCell(r[sec.headers[0]] ?? r["Record"] ?? "") +
          " :: " +
          extractNumericSignature(sec.headers, r) +
          " :: " +
          normalizeCell(
            r[sec.headers.find((h) => h.toLowerCase().includes("holder")) ?? "Record Holder"] ?? ""
          );
        if (seen.has(sig)) continue;
        seen.add(sig);
        keep.push(r);
      }

      out.push({ section: sec.section, headers: sec.headers, rows: keep });
    }

    out.sort(compareSections);
    return out;
  }, [data, mode, year]);

  /** ---------- Extra Team Points tables ---------- */
  const teamPointsExtraTables = useMemo<RecordSection[]>(() => {
    if (!data || !year) return [];
    if (mode !== "team_points") return [];

    const yd = data.years[year];
    const secs = yd?.team_points ?? [];
    if (!secs.length) return [];

    const isPostDraftMost = (title: string) => {
      const t = normalizeCell(title);
      return t.includes("points from waiver-wire pickups") && t.includes("most");
    };
    const isDraftPlayersMost = (title: string) => {
      const t = normalizeCell(title);
      const draftWord = t.includes("points from draft players") || t.includes("points from drafted players");
      return draftWord && t.includes("most");
    };

    const wanted: RecordSection[] = [];

    for (const sec of secs) {
      if (!(isPostDraftMost(sec.section) || isDraftPlayersMost(sec.section))) continue;

      const rows = sec.rows.filter((r) => !hasAllTimeTag(r));
      if (!rows.length) continue;

      const seen = new Set<string>();
      const keep: StringMap[] = [];
      for (const r of rows) {
        const sig =
          normalizeCell(sec.section) +
          " :: " +
          normalizeCell(r[sec.headers[0]] ?? r["Record"] ?? "") +
          " :: " +
          extractNumericSignature(sec.headers, r) +
          " :: " +
          normalizeCell(
            r[sec.headers.find((h) => h.toLowerCase().includes("holder")) ?? "Record Holder"] ?? ""
          );
        if (seen.has(sig)) continue;
        seen.add(sig);
        keep.push(r);
      }

      wanted.push({ section: sec.section, headers: sec.headers, rows: keep });
    }

    wanted.sort((a, b) => {
      const aPost = isPostDraftMost(a.section) ? 0 : 1;
      const bPost = isPostDraftMost(b.section) ? 0 : 1;
      if (aPost !== bPost) return aPost - bPost;
      return a.section.localeCompare(b.section);
    });

    return wanted;
  }, [data, mode, year]);

  if (!data) return <div className="p-6">Loading…</div>;
  const yearsList = Object.keys(data.years).sort();

  const renderSection = (sec: RecordSection, keyPrefix: string) => (
    <div
      key={`${keyPrefix}-${sec.section}`}
      className="rounded-2xl border shadow-sm p-4 bg-white/70 dark:bg-zinc-900/40 mb-6"
    >
      <h3 className="text-lg font-semibold mb-2">{sec.section}</h3>
      <div className="overflow-x-auto rounded-xl border">
        <table className="min-w-full text-sm">
          <thead className="bg-zinc-50 dark:bg-zinc-900">
            <tr>
              {sec.headers.map((h) => (
                <th key={h} className="px-3 py-2 text-left font-medium uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sec.rows.map((row, i) => (
              <tr
                key={`${keyPrefix}-${sec.section}-${i}`}
                className={i % 2 ? "bg-zinc-50 dark:bg-zinc-900/40" : ""}
              >
                {sec.headers.map((h) => (
                  <td key={h} className="px-3 py-2 whitespace-pre-wrap">
                    {row[h] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
            {!sec.rows.length && (
              <tr>
                <td colSpan={sec.headers.length} className="px-3 py-3 opacity-60">
                  No records.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div className="p-6 space-y-8">
      {/* Nav */}
      <div className="flex flex-wrap justify-end gap-3">
        <Link href="/" className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          News &amp; Notes
        </Link>
        <Link href="/head-to-head" className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          H2H Record
        </Link>
        <Link href="/roll-of-honour" className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          Roll of Honour
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

      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Record Breakers</h1>
        <div className="flex gap-3">
          <select className="border rounded-xl px-3 py-2 bg-white dark:bg-zinc-900" value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
            <option value="all_time">All-Time</option>
            <option value="head_to_head">Head to Head</option>
            <option value="team_points">Team Points</option>
            <option value="team_stats">Team Stats</option>
          </select>
          <select className="border rounded-xl px-3 py-2 bg-white dark:bg-zinc-900 disabled:opacity-50" value={year} onChange={(e) => setYear(e.target.value)} disabled={mode === "all_time"}>
            {yearsList.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
      </header>

      {mode === "all_time" && (
        <section>
          <h2 className="text-xl font-semibold mb-3">🏆 All-Time Records</h2>
          {allTimeSections.map((sec) => renderSection(sec, "alltime"))}
          {!allTimeSections.length && <p className="text-sm opacity-70">No all-time records found.</p>}
        </section>
      )}

      {mode !== "all_time" && (
        <section>
          <h2 className="text-xl font-semibold mb-3">
            📅 {year} – {mode === "head_to_head" ? "Head to Head" : mode === "team_points" ? "Team Points" : "Team Stats"}
          </h2>

          {seasonalSections.map((sec) => renderSection(sec, `${mode}-${year}`))}
          {!seasonalSections.length && <p className="text-sm opacity-70">No records for this selection.</p>}

          {mode === "team_points" &&
            teamPointsExtraTables.map((sec) => renderSection(sec, `extra-team-points-${year}`))}
        </section>
      )}
    </div>
  );
}
