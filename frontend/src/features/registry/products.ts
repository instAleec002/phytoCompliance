// The products registered for a crop and a pest, filtered and sorted as a technician narrows them down: by name or
// ingredient, by the longest pre-harvest interval that still fits the harvest, and by chemical or biological type.

import type { Schemas } from "@/lib/api/client";

export type Product = Schemas["ProductOut"];

export interface ProductFilter {
  text: string;
  maxPhi: number | null;          // days; products without a registered interval are left out when it is set
  type: "all" | "chemical" | "biological";
}

export type SortKey = "name" | "phi";

export const NO_FILTER: ProductFilter = { text: "", maxPhi: null, type: "all" };

function norm(text: string): string {
  return text.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

export function productName(p: Product): string {
  return p.trade_name || p.product_id;
}

export function isBiological(p: Product): boolean {
  return p.product_type === "BIOLOGICO";
}

/** The interval a product counts with when filtering: 0 when SENASA says none applies, null when unknown. */
export function phiDays(p: Product): number | null {
  if (p.preharvest_not_applicable) return 0;
  return p.preharvest_interval_days ?? null;
}

export function filterProducts(products: Product[], f: ProductFilter, sort: SortKey = "name"): Product[] {
  const q = norm(f.text.trim());
  const out = products.filter((p) => {
    if (q && !norm(`${productName(p)} ${p.ingredients.join(" ")} ${p.registration_number ?? ""}`).includes(q)) return false;
    if (f.type === "chemical" && isBiological(p)) return false;
    if (f.type === "biological" && !isBiological(p)) return false;
    if (f.maxPhi !== null) {
      const d = phiDays(p);
      if (d === null || d > f.maxPhi) return false;
    }
    return true;
  });
  return out.sort((a, b) => {
    if (sort === "phi") {
      const da = phiDays(a) ?? Number.POSITIVE_INFINITY;
      const db = phiDays(b) ?? Number.POSITIVE_INFINITY;
      if (da !== db) return da - db;
    }
    return productName(a).localeCompare(productName(b), "es");
  });
}

/** The shown products as CSV for a spreadsheet (semicolon separated, as Excel in Spanish locales reads it). */
export function productsToCsv(products: Product[], crop: string, pest: string): string {
  const cell = (v: unknown) => {
    const t = v === null || v === undefined ? "" : String(v);
    return /[;"\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
  };
  const head = ["cultivo", "plaga", "producto", "registro", "tipo", "carencia_dias", "lmr_peru_mg_kg", "ingredientes"];
  const rows = products.map((p) => [crop, pest, productName(p), p.registration_number ?? "", isBiological(p) ? "biológico" : "químico",
    p.preharvest_not_applicable ? "no aplica" : p.preharvest_interval_days ?? "", p.peru_mrl_mg_kg ?? "", p.ingredients.join(" + ")]);
  return [head, ...rows].map((r) => r.map(cell).join(";")).join("\r\n") + "\r\n";
}
