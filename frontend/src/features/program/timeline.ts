// Geometry of a block's harvest timeline: each application opens its pre-harvest window (application date plus the
// registered interval); the safe harvest is the end of the last window. A window that ends after the planned harvest
// is a breach. Pure function, tested without rendering.

import { addDays, daysBetween } from "@/lib/format";

export interface TimelineInput {
  harvest_on: string;
  safe_from: string | null;
  applications: { id: string; label: string; applied_on: string; phi_days: number | null }[];
}

export interface TimelineWindow {
  id: string;
  label: string;
  x0: number;
  x1: number | null; // null: unknown interval
  ends: string | null;
  breach: boolean;
  labelLeft: boolean; // the label goes before the bar when the bar reaches the right part of the axis
}

export interface Timeline {
  start: string;
  end: string;
  windows: TimelineWindow[];
  harvest: number;
  safe: number | null;
  ticks: { label: string; x: number }[];
}

export function buildTimeline(input: TimelineInput): Timeline | null {
  const apps = [...input.applications].sort((a, b) => a.applied_on.localeCompare(b.applied_on));
  if (!apps.length) return null;
  const ends = apps.map((a) => (a.phi_days === null ? null : addDays(a.applied_on, a.phi_days)));
  const edges = [input.harvest_on, input.safe_from, ...apps.map((a) => a.applied_on), ...ends].filter(Boolean) as string[];
  edges.sort();
  const raw = Math.max(1, daysBetween(edges[0]!, edges.at(-1)!));
  // margins proportional to the span, so the last date never sits on the edge with its label cut
  const start = addDays(edges[0]!, -Math.max(3, Math.round(raw * 0.05)));
  const end = addDays(edges.at(-1)!, Math.max(5, Math.round(raw * 0.16)));
  const span = Math.max(1, daysBetween(start, end));
  const x = (iso: string) => daysBetween(start, iso) / span;

  const windows = apps.map((a, i) => {
    const e = ends[i] ?? null;
    const x1 = e ? x(e) : null;
    return { id: a.id, label: a.label, x0: x(a.applied_on), x1, ends: e, breach: !!e && e > input.harvest_on,
      labelLeft: (x1 ?? x(a.applied_on)) > 0.62 };
  });

  const ticks: { label: string; x: number }[] = [];
  const stepDays = span > 120 ? 30 : span > 45 ? 14 : 7;
  for (let d = 0; d <= span; d += stepDays) {
    const iso = addDays(start, d);
    ticks.push({ label: `${iso.slice(8, 10)}/${iso.slice(5, 7)}`, x: d / span });
  }

  return { start, end, windows, harvest: x(input.harvest_on), safe: input.safe_from ? x(input.safe_from) : null, ticks };
}
