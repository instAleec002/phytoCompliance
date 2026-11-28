// The program being edited, as kept on the device, and its conversion to what the API validates.

import type { Schemas } from "@/lib/api/client";
import { addDays } from "@/lib/format";

export const PROGRAM_KEY = "tp.program"; // localStorage key of the draft

export interface DraftBlock {
  key: string;
  harvest_on: string;
  markets: string[];
}

export interface DraftApplication {
  id: string;
  block: string;
  pest: string;
  product_id: string;
  product_name: string;
  phi_days: number | null; // as registered when chosen; the API recomputes it
  applied_on: string;
}

export interface Draft {
  crop: string;
  blocks: DraftBlock[];
  applications: DraftApplication[];
  savedId?: number | null; // the program in the account this draft was opened from or saved as
  savedName?: string | null;
}

let counter = 0;
export function newId(): string {
  counter += 1;
  return `a${Date.now().toString(36)}${counter}`;
}

export function emptyDraft(today: string, crop = ""): Draft {
  return {
    crop,
    blocks: [{ key: "A1", harvest_on: addDays(today, 30), markets: ["EU"] }],
    applications: [],
  };
}

export interface DraftProblem {
  where: string;
  message: string;
}

/** Problems that stop a validation before calling the API; the API checks the rest. */
export function draftProblems(d: Draft): DraftProblem[] {
  const out: DraftProblem[] = [];
  if (!d.crop) out.push({ where: "programa", message: "Elija el cultivo" });
  const keys = d.blocks.map((b) => b.key.trim());
  if (!d.blocks.length) out.push({ where: "bloques", message: "Agregue al menos un bloque" });
  d.blocks.forEach((b, i) => {
    if (!b.key.trim()) out.push({ where: `bloque ${i + 1}`, message: "Falta la clave" });
    else if (keys.indexOf(b.key.trim()) !== i) out.push({ where: `bloque ${b.key}`, message: "Clave repetida" });
    if (!b.harvest_on) out.push({ where: `bloque ${b.key || i + 1}`, message: "Falta la fecha de cosecha" });
    if (!b.markets.length) out.push({ where: `bloque ${b.key || i + 1}`, message: "Elija al menos un mercado" });
  });
  d.applications.forEach((a, i) => {
    const where = `aplicación ${i + 1}`;
    if (!keys.includes(a.block)) out.push({ where, message: "Bloque inexistente" });
    if (!a.product_id) out.push({ where, message: "Falta el producto" });
    if (!a.applied_on) out.push({ where, message: "Falta la fecha" });
  });
  return out;
}

export function toProgramIn(d: Draft): Schemas["ProgramIn"] {
  return {
    crop: d.crop,
    blocks: d.blocks.map((b) => ({ key: b.key.trim(), harvest_on: b.harvest_on, markets: b.markets })),
    applications: d.applications.map((a) => ({
      block: a.block,
      product_id: a.product_id,
      applied_on: a.applied_on,
      pest: a.pest || null,
    })),
  };
}
