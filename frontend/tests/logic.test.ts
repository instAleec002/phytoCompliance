import { describe, expect, it } from "vitest";

import { parsePastedMeasurements } from "@/features/lab/paste";
import { strictestMarket } from "@/features/limits/strictest";
import { buildTrack } from "@/features/limits/track";
import { applicationsToCsv, parseApplicationsCsv } from "@/features/program/csv";
import { importToDraft, needsReview, rowsToReview, type ImportResult, type ImportRow } from "@/features/program/fieldSheet";
import { graphRowsOf, rowLines, rowLink } from "@/features/assistant/graphRows";
import { findingsToCsv } from "@/features/program/report";
import { NO_FILTER, filterProducts, productsToCsv, type Product } from "@/features/registry/products";
import { draftProblems, emptyDraft, toProgramIn, type Draft } from "@/features/program/model";
import { buildTimeline } from "@/features/program/timeline";
import { toApiError } from "@/lib/api/errors";
import { addDays, daysBetween, fmtDate, fmtSnapshot, mgkg, percent, todayISO } from "@/lib/format";

describe("format", () => {
  it("writes figures with a decimal comma and no thousands separator", () => {
    expect(mgkg(4)).toBe("4");
    expect(mgkg(0.01)).toBe("0,01");
    expect(mgkg(1234.5)).toBe("1234,5");
    expect(mgkg(null)).toBe("—");
    expect(percent(243.06)).toBe("243,1 %");
  });

  it("handles ISO dates without time zone shifts", () => {
    expect(fmtDate("2026-10-28")).toBe("28/10/2026");
    expect(addDays("2026-12-28", 7)).toBe("2027-01-04");
    expect(daysBetween("2026-10-28", "2027-03-01")).toBe(124);
    expect(todayISO(new Date(2026, 9, 28, 23, 50))).toBe("2026-10-28");
    expect(fmtSnapshot("eu_mrl:2026-10-27")).toBe("eu_mrl · 27/10/2026");
  });
});

describe("program draft", () => {
  const base: Draft = {
    crop: "blueberry",
    blocks: [{ key: "A1", harvest_on: "2026-12-01", markets: ["EU", "US"] }],
    applications: [{ id: "x", block: "A1", pest: "000626", product_id: "P1", product_name: "ADIKO", phi_days: 14, applied_on: "2026-11-20" }],
  };

  it("converts to the API body", () => {
    expect(toProgramIn(base)).toEqual({
      crop: "blueberry",
      blocks: [{ key: "A1", harvest_on: "2026-12-01", markets: ["EU", "US"] }],
      applications: [{ block: "A1", product_id: "P1", applied_on: "2026-11-20", pest: "000626" }],
    });
  });

  it("reports what stops a validation before calling the API", () => {
    expect(draftProblems(base)).toEqual([]);
    const bad: Draft = { ...base, blocks: [...base.blocks, { key: "A1", harvest_on: "", markets: [] }] };
    expect(draftProblems(bad).map((p) => p.message)).toEqual(["Clave repetida", "Falta la fecha de cosecha", "Elija al menos un mercado"]);
    expect(draftProblems(emptyDraft("2026-10-28")).map((p) => p.message)).toEqual(["Elija el cultivo"]);
  });
});

describe("applications CSV", () => {
  it("reads semicolon files from spreadsheets, with either date format", () => {
    const { applications, errors } = parseApplicationsCsv("﻿bloque;plaga;producto;fecha\r\nA1;000626;001200500051;20/11/2026\r\nB2;;P9;2026-11-25\r\nmal;;\r\n");
    expect(applications.map((a) => [a.block, a.pest, a.product_id, a.applied_on])).toEqual([
      ["A1", "000626", "001200500051", "2026-11-20"],
      ["B2", "", "P9", "2026-11-25"],
    ]);
    expect(errors).toHaveLength(1);
  });

  it("round-trips", () => {
    const { applications } = parseApplicationsCsv("A1;000626;P1;2026-11-20");
    expect(parseApplicationsCsv(applicationsToCsv(applications)).applications.map((a) => a.product_id)).toEqual(["P1"]);
  });
});

describe("pasted lab results", () => {
  it("accepts tabs, semicolons, decimal commas and skips non-detects", () => {
    const { rows, skipped } = parsePastedMeasurements("Pyraclostrobin;0,12\nfludioxonil\t0.30\nboscalid;ND\nCaptan 0.5\n");
    expect(rows).toEqual([
      { ingredient: "pyraclostrobin", value: "0.12" },
      { ingredient: "fludioxonil", value: "0.30" },
      { ingredient: "captan", value: "0.5" },
    ]);
    expect(skipped).toEqual(["boscalid;ND"]);
  });
});

describe("harvest timeline", () => {
  it("marks windows that end after the harvest and unknown intervals", () => {
    const t = buildTimeline({
      harvest_on: "2026-12-01",
      safe_from: "2026-12-04",
      applications: [
        { id: "1", label: "A", applied_on: "2026-11-01", phi_days: 14 },
        { id: "2", label: "B", applied_on: "2026-11-20", phi_days: 14 },
        { id: "3", label: "C", applied_on: "2026-11-10", phi_days: null },
      ],
    })!;
    expect(t.windows.map((w) => [w.label, w.ends, w.breach, w.x1 === null])).toEqual([
      ["A", "2026-11-15", false, false],
      ["C", null, false, true],
      ["B", "2026-12-04", true, false],
    ]);
    expect(t.safe! > t.harvest).toBe(true);
    expect(t.windows.every((w) => w.x0 >= 0 && w.x0 <= 1)).toBe(true);
  });

  it("keeps the last date away from the edge and puts late labels before their bar", () => {
    const t = buildTimeline({ harvest_on: "2026-12-05", safe_from: "2026-12-05",
      applications: [{ id: "1", label: "A", applied_on: "2026-11-02", phi_days: 14 }, { id: "2", label: "B", applied_on: "2026-11-28", phi_days: 7 }] })!;
    expect(t.harvest).toBeLessThan(0.9);
    expect(t.windows.map((w) => w.labelLeft)).toEqual([false, true]);
  });

  it("has nothing to draw without applications", () => {
    expect(buildTimeline({ harvest_on: "2026-12-01", safe_from: null, applications: [] })).toBeNull();
  });
});

describe("version track", () => {
  const v = (from: string, until: string | null, value: number) => ({
    applies_from: from, valid_until: until, value_mg_kg: value, value_text: String(value), regulation: "R", no_mrl_required: false,
  });

  it("places versions in time and flags the one in force and the future one", () => {
    const t = buildTrack([v("2026-02-11", "2027-03-01", 4), v("2008-09-01", "2017-04-26", 0.5), v("2027-03-01", null, 0.01)], "2026-10-28")!;
    expect(t.bars.map((b) => [b.version.value_mg_kg, b.inForce, b.future, b.open])).toEqual([
      [0.5, false, false, false],
      [4, true, false, false],
      [0.01, false, true, true],
    ]);
    expect(t.lanes).toEqual(["4", "0,5", "0,01"]);
    expect(t.bars.map((b) => b.lane)).toEqual([1, 0, 2]);
    expect(t.bars[0]!.x0).toBeLessThan(t.bars[1]!.x0);
    expect(t.cursor).toBeGreaterThan(t.bars[1]!.x0);
    expect(t.years.length).toBeGreaterThan(2);
  });
});

describe("API errors", () => {
  it("turns statuses into messages a user can act on", () => {
    expect(toApiError(0, null, "http://x").message).toContain("Sin conexión con la API en http://x");
    expect(toApiError(401, null, "u").message).toContain("Inicie sesión");
    expect(toApiError(401, { detail: "Correo o contraseña incorrectos" }, "u").message).toBe("Correo o contraseña incorrectos");
    expect(toApiError(403, null, "u").message).toContain("permiso");
    expect(toApiError(422, { detail: [{ loc: ["body", "blocks", 0, "key"], msg: "Field required" }] }, "u").message)
      .toBe("Datos no válidos: blocks.0.key: Field required");
    expect(toApiError(404, { detail: "Perfil x no configurado" }, "u").message).toBe("Perfil x no configurado");
  });
});

describe("strictest market", () => {
  const l = (market: string, value: number | null, status = "specific") => ({ market, value_mg_kg: value, status });
  it("is the one strictly below the others", () => {
    expect(strictestMarket([l("EU", 0.3), l("US", 2), l("CODEX", 2)])).toBe("EU");
    expect(strictestMarket([l("EU", 4), l("US", 4), l("CODEX", 4)])).toBeNull();
    expect(strictestMarket([l("EU", 0.01, "default"), l("US", null, "not_permitted"), undefined])).toBeNull();
  });
});

describe("password hints", () => {
  it("mirror the server policy before sending", async () => {
    const { passwordReady } = await import("@/components/ui/PasswordFields");
    expect(passwordReady("luz-de-campo-2026", "luz-de-campo-2026", "ana")).toBe(true);
    expect(passwordReady("corta", "corta")).toBe(false);
    expect(passwordReady("clave-de-andrea-1", "clave-de-andrea-1", "andrea")).toBe(false);
    expect(passwordReady("luz-de-campo-2026", "otra", "ana")).toBe(false);
  });
});

describe("field sheet import", () => {
  const row = (n: number, extra: Partial<ImportRow> = {}): ImportRow => ({
    n, original: { fecha: "11-sep", producto: "Adiko" }, status: "resolved_by_trade_name", block: "L1",
    product_id: "ADIKO", trade_name: "ADIKO SC", ingredients: ["pyraclostrobin"], candidates: 1,
    applied_on: "2026-09-11", approximate_date: false, pest: null, mismatch: null, notes: [], dose: null,
    target_pests: [], target_check: null, ...extra,
  });
  const result: ImportResult = {
    summary: { filas: 3 },
    rows: [row(1), row(2, { status: "needs_review", product_id: null, trade_name: null, applied_on: null }),
      row(3, { dose: { text: "1 lt/cil", status: "outside_range", reason: "fuera", registered: ["2–3 L/cilindro"] } })],
    program: { crop: "avocado", blocks: [{ key: "L1", harvest_on: "2027-05-15", markets: ["EU", "US"] }],
      applications: [{ block: "L1", product_id: "ADIKO", applied_on: "2026-09-11", pest: null }] },
  };

  it("flags unresolved rows and doses outside the registered range for review", () => {
    expect(needsReview(result.rows[0]!)).toBe(false);
    expect(rowsToReview(result.rows).map((r) => r.n)).toEqual([2, 3]);
  });

  it("turns the imported program into a draft, with the trade names and without the saved program", () => {
    const d = importToDraft(result, "avocado", { ...emptyDraft("2026-11-27"), savedId: 4, savedName: "viejo" });
    expect(d.blocks).toEqual([{ key: "L1", harvest_on: "2027-05-15", markets: ["EU", "US"] }]);
    expect(d.applications.map((a) => [a.product_id, a.product_name, a.applied_on])).toEqual([["ADIKO", "ADIKO SC", "2026-09-11"]]);
    expect([d.savedId, d.savedName]).toEqual([null, null]);
    expect(draftProblems(d)).toEqual([]);
  });
});

describe("registry filters", () => {
  const p = (id: string, phi: number | null, extra: Partial<Product> = {}): Product => ({
    product_id: id, trade_name: id, registration_number: `PQUA ${id}`, product_type: "QUIMICO",
    preharvest_interval_days: phi, preharvest_not_applicable: false, peru_mrl_mg_kg: null, ingredients: ["sulphur"],
    snapshot: "sigia:2026-10-28", ...extra,
  } as Product);
  const all = [p("ZETA", 14), p("ALFA", 3), p("BIO", null, { product_type: "BIOLOGICO", preharvest_not_applicable: true }), p("SIN", null)];

  it("keeps products within the interval, counting «no aplica» as 0 and leaving out unknown ones", () => {
    expect(filterProducts(all, { ...NO_FILTER, maxPhi: 7 }).map((x) => x.product_id)).toEqual(["ALFA", "BIO"]);
    expect(filterProducts(all, { ...NO_FILTER, type: "biological" }).map((x) => x.product_id)).toEqual(["BIO"]);
    expect(filterProducts(all, { ...NO_FILTER, text: "zéta" }).map((x) => x.product_id)).toEqual(["ZETA"]);
  });

  it("sorts by interval with unknown ones last, and exports semicolon CSV", () => {
    expect(filterProducts(all, NO_FILTER, "phi").map((x) => x.product_id)).toEqual(["BIO", "ALFA", "ZETA", "SIN"]);
    const csv = productsToCsv([all[0]!], "avocado", "Queresa");
    expect(csv.split("\r\n")[1]).toBe("avocado;Queresa;ZETA;PQUA ZETA;químico;14;;sulphur");
  });
});

describe("rows of the exact core in an answer", () => {
  const trace = { filas_grafo: [
    { id: "G1", herramienta: "limite_maximo", argumentos: { ingrediente: "fenhexamid", cultivo: "arándano", mercado: "UE" },
      resultado: { id: "G1", ingrediente: "fenhexamid", cultivo: "blueberry", vigentes: [
        { valor_mg_kg: 5, norma: "Reg. (EU) 2021/1807", aplica_desde: "2022-05-15", en_limite_de_determinacion: false }] } },
    { id: "G2", herramienta: "carencia", argumentos: { producto: "X" }, resultado: { id: "G2", sin_dato: "sin carencia" } },
  ] };

  it("reads the rows from the trace and writes what each says", () => {
    const rows = graphRowsOf(trace);
    expect(rows.map((r) => r.id)).toEqual(["G1", "G2"]);
    expect(rowLines(rows[0]!)).toEqual(["5 mg/kg desde 15/05/2022 · Reg. (EU) 2021/1807"]);
    expect(rowLines(rows[1]!)).toEqual(["Sin dato: sin carencia"]);
    expect(rowLink(rows[0]!)).toBe("/lmr/?i=fenhexamid&c=blueberry");
    expect(graphRowsOf({})).toEqual([]);
  });
});

describe("validation report", () => {
  it("writes the findings as CSV with the product names of the draft and the regulation of the evidence", () => {
    const d = { ...emptyDraft("2026-11-27", "blueberry"), applications: [
      { id: "a1", block: "A1", pest: "", product_id: "ADIKO", product_name: "ADIKO SC", phi_days: 14, applied_on: "2026-11-20" }] };
    const csv = findingsToCsv([{ code: "PHI_NOT_MET", severity: "blocking", message: "Faltan 3 días; carencia", block: "A1",
      product_id: "ADIKO", ingredient: null, market: null, evidence: { regulation: "SIGIA", snapshot: "sigia:2026-10-28" } }],
      d, "2026-11-27");
    const [head, row] = csv.split("\r\n");
    expect(head!.startsWith("fecha_evaluacion;cultivo;severidad;codigo")).toBe(true);
    expect(row).toContain("2026-11-27;blueberry;");
    expect(row).toContain(";PHI_NOT_MET;");
    expect(row).toContain(";A1;ADIKO SC;;;");
    expect(row!.endsWith(";SIGIA;sigia:2026-10-28")).toBe(true);
  });
});
