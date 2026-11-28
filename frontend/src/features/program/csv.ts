// Applications exchanged as CSV with spreadsheets: semicolon separated (Excel in Spanish locales), one application per
// line: bloque;plaga;producto;fecha. Dates accepted as AAAA-MM-DD or DD/MM/AAAA.

import { newId, type DraftApplication } from "./model";

export const CSV_HEADER = "bloque;plaga;producto;fecha";

export interface CsvResult {
  applications: DraftApplication[];
  errors: string[];
}

function isoDate(text: string): string | null {
  const t = text.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return t;
  const m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!m) return null;
  return `${m[3]}-${m[2]!.padStart(2, "0")}-${m[1]!.padStart(2, "0")}`;
}

export function parseApplicationsCsv(text: string): CsvResult {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const applications: DraftApplication[] = [];
  const errors: string[] = [];
  lines.forEach((line, i) => {
    const cells = line.split(/[;\t,]/).map((c) => c.trim());
    if (i === 0 && cells[0]?.toLowerCase() === "bloque") return; // header
    const [block, pest, product, date] = cells;
    const iso = isoDate(date ?? "");
    if (!block || !product || !iso) {
      errors.push(`Línea ${i + 1}: se esperaba bloque;plaga;producto;fecha y se leyó «${line}»`);
      return;
    }
    applications.push({ id: newId(), block, pest: pest ?? "", product_id: product, product_name: "", phi_days: null, applied_on: iso });
  });
  return { applications, errors };
}

export function applicationsToCsv(apps: DraftApplication[]): string {
  return [CSV_HEADER, ...apps.map((a) => [a.block, a.pest, a.product_id, a.applied_on].join(";"))].join("\r\n") + "\r\n";
}
