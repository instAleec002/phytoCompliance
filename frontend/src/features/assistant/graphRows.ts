// The exact-core rows an answer cites as [G1], [G2]…: which tool gave them, with which arguments, and what they say,
// written as short lines a technician can check against the official source.

import { fmtDate, mgkg } from "@/lib/format";

export interface GraphRow {
  id: string;
  herramienta: string;
  argumentos: Record<string, unknown>;
  resultado: Record<string, unknown>;
}

export const TOOL_LABEL: Record<string, string> = {
  limite_maximo: "Límite vigente",
  historial_limite: "Historial del límite",
  comparar_mercados: "Comparación de mercados",
  registro_producto: "Registro en SENASA",
  carencia: "Periodo de carencia",
  grupo_modo_accion: "Grupo de modo de acción",
  productos_para_plaga: "Productos para la plaga",
  ingredientes_sin_limite: "Ingredientes sin LMR vigente",
};

const ARG_LABEL: Record<string, string> = {
  ingrediente: "ingrediente", cultivo: "cultivo", mercado: "mercado", fecha: "fecha", producto: "producto",
  plaga: "plaga", carencia_maxima: "carencia máx.", excluir_grupo: "sin grupo",
};

type Obj = Record<string, unknown>;
const list = (v: unknown): Obj[] => (Array.isArray(v) ? (v as Obj[]) : []);
const str = (v: unknown): string => (v === null || v === undefined ? "" : String(v));

/** The rows the trace of a message carries (``traza.filas_grafo``), or none. */
export function graphRowsOf(trace: unknown): GraphRow[] {
  const rows = (trace as Obj | null)?.filas_grafo;
  return Array.isArray(rows) ? (rows as GraphRow[]).filter((r) => r && typeof r.id === "string") : [];
}

export function argsLine(row: GraphRow): string {
  return Object.entries(row.argumentos ?? {})
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${ARG_LABEL[k] ?? k}: ${str(v)}`)
    .join(" · ");
}

function version(v: Obj): string {
  const value = v.valor_mg_kg === null || v.valor_mg_kg === undefined ? str(v.texto_oficial) || "sin valor" : `${mgkg(v.valor_mg_kg as number)} mg/kg`;
  const loq = v.en_limite_de_determinacion ? " (límite de determinación)" : "";
  const since = v.aplica_desde ? ` desde ${fmtDate(str(v.aplica_desde))}` : "";
  const until = v.aplica_hasta ? ` hasta ${fmtDate(str(v.aplica_hasta))}` : "";
  return `${value}${loq}${since}${until}${v.norma ? ` · ${str(v.norma)}` : ""}`;
}

/** What the row says, in a few lines; a row with «error» or «sin_dato» says that. */
export function rowLines(row: GraphRow): string[] {
  const r = row.resultado ?? {};
  if (r.error) return [`Error: ${str(r.error)}`];
  if (r.sin_dato) return [`Sin dato: ${str(r.sin_dato)}`];
  switch (row.herramienta) {
    case "limite_maximo":
      return list(r.vigentes).map(version);
    case "historial_limite":
      return list(r.versiones).slice(0, 6).map(version);
    case "comparar_mercados": {
      const por = (r.por_mercado ?? {}) as Record<string, Obj>;
      return [...Object.entries(por).map(([m, v]) => `${m}: ${mgkg(v.valor_mg_kg as number)} mg/kg · ${str(v.norma)}`),
        `Más estricto: ${str(r.mas_estricto)}`];
    }
    case "registro_producto": {
      const plagas = Array.isArray(r.plagas_autorizadas_en_el_cultivo) ? (r.plagas_autorizadas_en_el_cultivo as string[]) : [];
      return [`${r.registrado ? "Registrado" : "No registrado"} para ${str(r.cultivo)}${r.numero_registro ? ` · ${str(r.numero_registro)}` : ""}`,
        ...(plagas.length ? [`Plagas: ${plagas.slice(0, 4).join("; ")}${plagas.length > 4 ? ` y ${plagas.length - 4} más` : ""}`] : [])];
    }
    case "carencia":
      return [`${str(r.dias)} días${Array.isArray(r.varios_valores) ? ` (el mayor de ${(r.varios_valores as number[]).join(", ")})` : ""}`];
    case "grupo_modo_accion":
      return list(r.grupos).map((g) => `${str(g.esquema)} ${str(g.grupo)}`);
    case "productos_para_plaga":
      return [`${str(r.total)} productos`,
        ...list(r.productos).slice(0, 5).map((p) => `${str(p.producto)} · carencia ${p.carencia_dias ?? "sin dato"} d`)];
    case "ingredientes_sin_limite":
      return [`${str(r.sin_lmr_vigente)} de ${str(r.ingredientes_registrados)} ingredientes sin LMR vigente en ${str(r.mercado)}`,
        ...(r.en_limite_de_determinacion ? [`${str(r.en_limite_de_determinacion)} en el límite de determinación`] : [])];
    default:
      return Object.entries(r).filter(([k]) => !["id", "fuente"].includes(k)).slice(0, 6)
        .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : str(v)}`);
  }
}

/** Where in the app the row can be looked at in full. */
export function rowLink(row: GraphRow): string | null {
  const r = row.resultado ?? {};
  const crop = str(r.cultivo);
  const ingredient = str(r.ingrediente);
  if (["limite_maximo", "historial_limite", "comparar_mercados"].includes(row.herramienta) && ingredient && crop)
    return `/lmr/?i=${encodeURIComponent(ingredient)}&c=${encodeURIComponent(crop)}`;
  if (["registro_producto", "productos_para_plaga"].includes(row.herramienta) && crop)
    return `/registro/?c=${encodeURIComponent(crop)}`;
  return null;
}
