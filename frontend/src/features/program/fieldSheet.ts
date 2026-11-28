// A field sheet (Excel or CSV as the farm writes it) sent to /api/programas/importar, and what comes back turned into
// the draft the editor works on. Rows that need a person stay out of the draft and are listed for review.

import type { Schemas } from "@/lib/api/client";

import { newId, type Draft } from "./model";

export type ImportResult = Schemas["ImportOut"];
export type ImportRow = Schemas["ImportRowOut"];

export const ROW_STATUS: Record<string, { label: string; tone: string }> = {
  resolved_by_trade_name: { label: "Por nombre comercial", tone: "ok" },
  resolved_by_ingredient: { label: "Por ingrediente", tone: "info" },
  not_a_pesticide: { label: "No es plaguicida", tone: "neutral" },
  needs_review: { label: "Revisar", tone: "risk" },
};

export const DOSE_STATUS: Record<string, { label: string; tone: string }> = {
  within: { label: "Dentro de lo registrado", tone: "ok" },
  outside_range: { label: "Fuera de lo registrado", tone: "risk" },
  not_comparable: { label: "No comparable", tone: "neutral" },
};

export const TARGET_STATUS: Record<string, { label: string; tone: string }> = {
  registered: { label: "Registrado para el objetivo", tone: "ok" },
  not_registered: { label: "Sin registro para el objetivo", tone: "risk" },
  unresolved: { label: "Objetivo no reconocido", tone: "neutral" },
};

/** What the row said, in one line: date or stage, product, ingredient and dose, as written. */
export function rowText(row: ImportRow): string {
  const o = row.original;
  return [o.fecha ?? o.momento, o.producto, o.ingrediente, o.dosis].filter(Boolean).join(" · ");
}

/** Rows a person should look at: unresolved, approximate dates, doses outside the registered range or targets the
 * product is not registered for. */
export function needsReview(r: ImportRow): boolean {
  return r.status === "needs_review" || r.approximate_date || r.dose?.status === "outside_range"
    || r.target_check === "not_registered" || !!r.mismatch;
}

export function rowsToReview(rows: ImportRow[]): ImportRow[] {
  return rows.filter(needsReview);
}

/** The imported program as a draft: its blocks and resolved applications, the crop of the import. */
export function importToDraft(result: ImportResult, crop: string, current: Draft): Draft {
  const program = result.program;
  if (!program) return { ...current, crop, blocks: current.blocks, applications: [] };
  const names = new Map(result.rows.filter((r) => r.product_id).map((r) => [r.product_id!, r.trade_name ?? ""]));
  return {
    ...current,
    crop,
    blocks: program.blocks.map((b) => ({ key: b.key, harvest_on: b.harvest_on, markets: b.markets })),
    applications: program.applications.map((a) => ({
      id: newId(),
      block: a.block,
      pest: a.pest ?? "",
      product_id: a.product_id,
      product_name: names.get(a.product_id) ?? "",
      phi_days: null,
      applied_on: a.applied_on,
    })),
    savedId: null,
    savedName: null,
  };
}

/** The file's bytes in base64, as the endpoint takes them. */
export async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}
