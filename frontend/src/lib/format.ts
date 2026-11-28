// Formats used across the interface. Dates travel as ISO strings (YYYY-MM-DD) and are never turned into Date objects
// at midnight UTC, which would shift the day in Peru (UTC-5).

const NUMBER = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 3, useGrouping: false });
const PERCENT = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1, useGrouping: false });

export function mgkg(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : NUMBER.format(value);
}

export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${PERCENT.format(value)} %`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

export function todayISO(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function toUTC(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1);
}

export function daysBetween(fromISO: string, toISO: string): number {
  return Math.round((toUTC(toISO) - toUTC(fromISO)) / 86_400_000);
}

export function addDays(iso: string, days: number): string {
  const t = new Date(toUTC(iso) + days * 86_400_000);
  return t.toISOString().slice(0, 10);
}

/** "eu_mrl:2026-10-27" -> "eu_mrl · 27/10/2026" */
export function fmtSnapshot(snapshot: string | null | undefined): string {
  if (!snapshot) return "—";
  const [source, day] = snapshot.split(":");
  return day ? `${source} · ${fmtDate(day)}` : snapshot;
}

/** Instant from the API (ISO with zone) in local time: "28/10/2026 18:13". */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
