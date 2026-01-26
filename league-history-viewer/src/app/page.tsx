"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

/* -------------------------------------------------------
   CSV utils
------------------------------------------------------- */
type CsvRow = Record<string, string>;

function parseCsv(text: string): CsvRow[] {
  const lines = text.trim().split(/\r?\n/);
  if (!lines.length) return [];
  const headers = lines[0].split(",").map((h) => h.trim());
  return lines.slice(1).map((line) => {
    const cols = line.split(","); // simple, no quoted commas expected
    const row: CsvRow = {};
    headers.forEach((h, i) => (row[h] = (cols[i] ?? "").trim()));
    return row;
  });
}

/* -------------------------------------------------------
   Countdown helpers
------------------------------------------------------- */
function weekdayIndexShort(wd: string) {
  const map: Record<string, number> = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
  return map[wd] ?? 0;
}

function londonOffsetForUTCDate(utcDate: Date) {
  const f = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    timeZoneName: "shortOffset",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  const parts = f.formatToParts(utcDate);
  const tz = parts.find((p) => p.type === "timeZoneName")?.value || "GMT+0";
  const m = tz.match(/GMT([+-]\d+)/);
  const hours = m ? parseInt(m[1], 10) : 0;
  const sign = hours >= 0 ? "+" : "-";
  const hh = Math.abs(hours).toString().padStart(2, "0");
  return `${sign}${hh}:00`;
}

function nextThursdayAt21London() {
  const now = new Date();

  const nowParts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    weekday: "short",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(now);

  const wdShort = nowParts.find((p) => p.type === "weekday")?.value || "Mon";
  const year = parseInt(nowParts.find((p) => p.type === "year")?.value ?? "1970", 10);
  const month = parseInt(nowParts.find((p) => p.type === "month")?.value ?? "01", 10);
  const day = parseInt(nowParts.find((p) => p.type === "day")?.value ?? "01", 10);
  const hour = parseInt(nowParts.find((p) => p.type === "hour")?.value ?? "00", 10);
  const minute = parseInt(nowParts.find((p) => p.type === "minute")?.value ?? "00", 10);

  const todayIdx = weekdayIndexShort(wdShort);
  const targetIdx = 3; // Thu

  let daysUntil = (targetIdx - todayIdx + 7) % 7;
  if (daysUntil === 0 && (hour > 21 || (hour === 21 && minute >= 0))) {
    daysUntil = 7;
  }

  const londonDate = new Date(Date.UTC(year, month - 1, day));
  londonDate.setUTCDate(londonDate.getUTCDate() + daysUntil);

  const tgtY = londonDate.getUTCFullYear();
  const tgtM = (londonDate.getUTCMonth() + 1).toString().padStart(2, "0");
  const tgtD = londonDate.getUTCDate().toString().padStart(2, "0");

  const probeUTCNoon = new Date(Date.UTC(londonDate.getUTCFullYear(), londonDate.getUTCMonth(), londonDate.getUTCDate(), 12, 0, 0));
  const offset = londonOffsetForUTCDate(probeUTCNoon);

  const iso = `${tgtY}-${tgtM}-${tgtD}T21:00:00${offset}`;
  return new Date(iso);
}

function breakdown(ms: number) {
  const clamped = Math.max(0, ms);
  const s = Math.floor(clamped / 1000);
  const days = Math.floor(s / 86400);
  const hrs = Math.floor((s % 86400) / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  return { days, hrs, mins, secs };
}

/* -------------------------------------------------------
   Page
------------------------------------------------------- */
type DraftOrderRow = {
  pick: number;
  manager: string;
  draftGrade: string;
  projectedWins: string; // keep as "10-5"
  record: string;    // NEW
};

export default function HomePage() {
  // countdown
  const [target, setTarget] = useState(() => nextThursdayAt21London());
  const [now, setNow] = useState(() => new Date());
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    timerRef.current = setInterval(() => setNow(new Date()), 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (now.getTime() >= target.getTime()) {
      setTarget(nextThursdayAt21London());
    }
  }, [now, target]);

  const remaining = target.getTime() - now.getTime();
  const { days, hrs, mins, secs } = breakdown(remaining);

  const londonWhen = useMemo(
    () =>
      new Intl.DateTimeFormat("en-GB", {
        timeZone: "Europe/London",
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(target),
    [target]
  );

  // draft order
  const [doRows, setDoRows] = useState<DraftOrderRow[]>([]);
  const [doErr, setDoErr] = useState<string | null>(null);
  const [doLoading, setDoLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setDoLoading(true);
        const res = await fetch("/data/draftorder2025.csv", { cache: "no-store" });
        if (!res.ok) throw new Error("draftorder2025.csv not found");
        const text = await res.text();
        const raw = parseCsv(text);
        const typed: DraftOrderRow[] = raw
          .map((r) => {
            const pickStr = r.pick ?? "";
            return {
              pick: Number(pickStr),
              manager: (r.manager ?? "").trim(),
              draftGrade: (r.draft_grade ?? "").trim(),
              projectedWins: (r.projected_wins ?? "").trim(), // keep full "10-5"
              // accept common header variants
              record:
                (r.record ?? r.record ?? r["Record"] ?? r["record"] ?? "").trim(),
            };
          })
          .filter((r) => Number.isFinite(r.pick) && r.manager.length > 0)
          .sort((a, b) => a.pick - b.pick);
        setDoRows(typed);
      } catch (e) {
        setDoErr(e instanceof Error ? e.message : "Failed to load draft order");
      } finally {
        setDoLoading(false);
      }
    })();
  }, []);

  return (
    <div className="p-6 space-y-8">
      {/* Top-right navigation */}
      <div className="flex flex-wrap justify-end gap-3 mb-2">
        <Link
          href="/head-to-head"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          H2H Record
        </Link>
        <Link
          href="/record-breakers"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          Record Breakers
        </Link>
        <Link
          href="/roll-of-honour"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          Roll of Honour
        </Link>
        <Link
          href="/draft-history"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          Draft History
        </Link>
        <Link
          href="/league-finishes"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          League Finishes
        </Link>
        <Link
          href="/waivers"
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium shadow hover:bg-blue-700 transition">
          {"Waiver 'Wonders'"}
        </Link>
      </div>

      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">News &amp; Notes</h1>
        {/* Notes placeholder */}
        <section className="rounded-2xl border shadow-sm p-4 bg-white/70 dark:bg-zinc-900/40">
          <h2 className="font-semibold mb-2">League Notes</h2>
          
          <h2 className="font-semibold mb-1">New</h2>
          <h3 className="text-sm opacity-70">2025 Champion - {"PAT's the way uh-hu I like it."}</h3>
        
          
          <h3 className="font-semibold mt-4 mb-1">Mini Bowls</h3>
          <p className="text-sm opacity-70">Whitton Bowl - Week 1 - Winner - {"PAT's the way uh-hu I like it."}</p>
          <p className="text-sm opacity-70">Godfather Bowl - Week 3 - Winner - Drake it til you make it. </p>            
          <p className="text-sm opacity-70">Linnell Bowl - Week 8 - Winner - Whole lotta Hurts.</p>
          <p className="text-sm opacity-70">Shepperson Bowl - Week 11 - Winner - Never Starting Najee</p>
          <p className="text-sm opacity-70">Godfather Bowl II - Week 14 - Winner - San Franshelfo 49ers  </p>  
          
          <h3 className="font-semibold mt-4 mb-1">Old</h3>
          <p className="text-sm opacity-70">Shall we change to decimal points for kickers next season?</p>
          <p className="text-sm opacity-70">2025 draft - record time of 52 mins!</p>
          
            
        </section>
      </header>

      

      {/* 2025 Draft Order */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">2025 Draft Order</h2>
          {doLoading && <span className="text-sm opacity-70">Loading…</span>}
        </div>

        {doErr ? (
          <div className="text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-xl p-3">
            {doErr}
          </div>
        ) : (
          <div className="overflow-x-auto border rounded-2xl shadow-sm">
            <table className="min-w-full text-sm">
              <thead className="bg-zinc-50 dark:bg-zinc-900">
                <tr>
                  <th className="px-3 py-2 text-left font-medium uppercase tracking-wide w-16">Pick</th>
                  <th className="px-3 py-2 text-left font-medium uppercase tracking-wide">Manager</th>
                  <th className="px-3 py-2 text-left font-medium uppercase tracking-wide">Draft Grade</th>
                  <th className="px-3 py-2 text-left font-medium uppercase tracking-wide">Projected Wins</th>
                  <th className="px-3 py-2 text-left font-medium uppercase tracking-wide">Record</th>{/* NEW */}
                </tr>
              </thead>
              <tbody>
                {doRows.map((r, i) => (
                  <tr key={r.pick} className={i % 2 ? "bg-zinc-50 dark:bg-zinc-900/40" : ""}>
                    <td className="px-3 py-2 tabular-nums">{r.pick}</td>
                    <td className="px-3 py-2 font-medium">{r.manager}</td>
                    <td className="px-3 py-2">{r.draftGrade || "—"}</td>
                    <td className="px-3 py-2">{r.projectedWins || "—"}</td>
                    <td className="px-3 py-2">{r.record || "—"}</td>{/* NEW */}
                  </tr>
                ))}
                {!doRows.length && !doLoading && (
                  <tr>
                    <td colSpan={5} className="px-3 py-4 text-sm opacity-70">
                      No draft order found in <code>/public/data/draftorder2025.csv</code>.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Countdown card (kept commented out exactly as before) */}
      {/*<section className="rounded-2xl border shadow-sm p-6 bg-white/70 dark:bg-zinc-900/40">
        <div className="text-sm opacity-70 mb-2">
          Countdown to draft time: <span className="font-medium">{londonWhen}</span>
        </div>

        <div className="grid grid-cols-4 gap-3 max-w-xl">
          <div className="text-center rounded-xl border p-4 bg-zinc-50 dark:bg-zinc-900">
            <div className="text-3xl font-bold tabular-nums">{days}</div>
            <div className="text-xs mt-1 uppercase tracking-wide">Days</div>
          </div>
          <div className="text-center rounded-xl border p-4 bg-zinc-50 dark:bg-zinc-900">
            <div className="text-3xl font-bold tabular-nums">{hrs.toString().padStart(2, "0")}</div>
            <div className="text-xs mt-1 uppercase tracking-wide">Hours</div>
          </div>
          <div className="text-center rounded-xl border p-4 bg-zinc-50 dark:bg-zinc-900">
            <div className="text-3xl font-bold tabular-nums">{mins.toString().padStart(2, "0")}</div>
            <div className="text-xs mt-1 uppercase tracking-wide">Min</div>
          </div>
          <div className="text-center rounded-xl border p-4 bg-zinc-50 dark:bg-zinc-900">
            <div className="text-3xl font-bold tabular-nums">{secs.toString().padStart(2, "0")}</div>
            <div className="text-xs mt-1 uppercase tracking-wide">Sec</div>
          </div>
        </div>

        {remaining <= 0 && (
          <p className="mt-4 text-emerald-600 dark:text-emerald-400 font-medium">It’s draft time! 🎉</p>
        )}
      </section>*/}
    </div>
  );
}
