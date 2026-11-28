// Geometry of the version track: one lane per distinct value of the limit, and each version a segment on its lane
// from the day it applies to the day it was replaced (open to the right while in force). Twenty versions with two
// values read as two lanes and a visible step. Pure function, so it can be tested without rendering.

import { addDays, daysBetween, mgkg } from "@/lib/format";

export interface TrackVersion {
  applies_from: string | null;
  valid_until: string | null;
  value_mg_kg: number | null;
  value_text: string;
  regulation: string;
  no_mrl_required: boolean;
}

export interface TrackBar {
  version: TrackVersion;
  lane: number;
  x0: number; // 0..1
  x1: number; // 0..1
  open: boolean; // still in force at the end of the axis
  inForce: boolean; // in force on the evaluation date
  future: boolean; // applies after the evaluation date
}

export interface Track {
  start: string;
  end: string;
  lanes: string[];
  bars: TrackBar[];
  cursor: number; // evaluation date, 0..1
  years: { label: string; x: number }[];
}

export function laneLabel(v: TrackVersion): string {
  if (v.no_mrl_required) return "exento";
  if (v.value_mg_kg === null) return "sin valor";
  return mgkg(v.value_mg_kg);
}

function laneOrder(v: TrackVersion): number {
  if (v.no_mrl_required) return -1;
  if (v.value_mg_kg === null) return -2;
  return v.value_mg_kg;
}

export function buildTrack(versions: TrackVersion[], evaluationDate: string): Track | null {
  const dated = versions.filter((v) => v.applies_from).sort((a, b) => a.applies_from!.localeCompare(b.applies_from!));
  if (!dated.length) return null;
  const first = dated[0]!.applies_from!;
  const lastEdge = [evaluationDate, ...dated.map((v) => v.valid_until ?? v.applies_from!)].sort().at(-1)!;
  const start = addDays(first, -60);
  const end = addDays(lastEdge, 365);
  const span = Math.max(1, daysBetween(start, end));
  const x = (iso: string) => Math.min(1, Math.max(0, daysBetween(start, iso) / span));

  // lanes from the highest value down; exemptions and versions without value at the bottom
  const order = new Map<string, number>();
  for (const v of dated) {
    const label = laneLabel(v);
    order.set(label, Math.max(order.get(label) ?? -Infinity, laneOrder(v)));
  }
  const lanes = [...order.entries()].sort((a, b) => b[1] - a[1]).map(([label]) => label);

  const bars = dated.map((v) => {
    const until = v.valid_until;
    return {
      version: v,
      lane: lanes.indexOf(laneLabel(v)),
      x0: x(v.applies_from!),
      x1: until ? x(until) : 1,
      open: !until,
      inForce: v.applies_from! <= evaluationDate && (!until || until > evaluationDate),
      future: v.applies_from! > evaluationDate,
    };
  });

  const years: { label: string; x: number }[] = [];
  const y0 = Number(start.slice(0, 4)) + 1;
  const y1 = Number(end.slice(0, 4));
  const step = y1 - y0 > 12 ? 4 : y1 - y0 > 6 ? 2 : 1;
  for (let y = y0; y <= y1; y += step) years.push({ label: String(y), x: x(`${y}-01-01`) });

  return { start, end, lanes, bars, cursor: x(evaluationDate), years };
}
