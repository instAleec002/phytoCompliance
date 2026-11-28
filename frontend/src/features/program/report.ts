// The validation report taken out of the app: findings as CSV for a spreadsheet (semicolon separated, as Excel in
// Spanish locales reads it); the printable report is the page itself with the editing controls hidden.

import type { Schemas } from "@/lib/api/client";
import { FINDING_TITLE, SEVERITY } from "@/lib/labels";

import type { Draft } from "./model";

type Finding = Schemas["FindingOut"];

const cell = (v: unknown) => {
  const t = v === null || v === undefined ? "" : String(v);
  return /[;"\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
};

export function findingsToCsv(findings: Finding[], draft: Draft, evaluationDate: string): string {
  const names = new Map(draft.applications.map((a) => [a.product_id, a.product_name || a.product_id]));
  const head = ["fecha_evaluacion", "cultivo", "severidad", "codigo", "hallazgo", "bloque", "producto", "ingrediente",
    "mercado", "detalle", "norma", "instantanea"];
  const rows = findings.map((f) => {
    const ev = (f.evidence ?? {}) as Record<string, unknown>;
    return [evaluationDate, draft.crop, SEVERITY[f.severity]?.label ?? f.severity, f.code, FINDING_TITLE[f.code] ?? f.code,
      f.block ?? "", f.product_id ? names.get(f.product_id) ?? f.product_id : "", f.ingredient ?? "", f.market ?? "",
      f.message, ev.regulation ?? "", ev.snapshot ?? ""];
  });
  return [head, ...rows].map((r) => r.map(cell).join(";")).join("\r\n") + "\r\n";
}
