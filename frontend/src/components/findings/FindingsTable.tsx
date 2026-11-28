"use client";

import { Fragment } from "react";

import type { Schemas } from "@/lib/api/client";
import { fmtSnapshot } from "@/lib/format";
import { FINDING_TITLE, MARKET_SHORT, SEVERITY } from "@/lib/labels";

import { SeverityStamp } from "../ui/Stamp";

type Finding = Schemas["FindingOut"];

export function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort(
    (a, b) => (SEVERITY[a.severity]?.rank ?? 9) - (SEVERITY[b.severity]?.rank ?? 9) || a.code.localeCompare(b.code),
  );
}

export function SeverityCounts({ findings }: { findings: Finding[] }) {
  const counts = { blocking: 0, risk: 0, info: 0 } as Record<string, number>;
  for (const f of findings) counts[f.severity] = (counts[f.severity] ?? 0) + 1;
  return (
    <span className="row" style={{ gap: 6 }}>
      {(["blocking", "risk", "info"] as const).map((s) => (
        <span key={s} className="stamp" data-tone={counts[s] ? SEVERITY[s]!.tone : "neutral"}>
          {counts[s]} {SEVERITY[s]!.label}
        </span>
      ))}
    </span>
  );
}

const EVIDENCE_LABEL: Record<string, string> = {
  status: "estado",
  value_mg_kg: "LMR (mg/kg)",
  measured_mg_kg: "medido (mg/kg)",
  regulation: "norma",
  residue: "residuo",
  snapshot: "instantánea",
  day: "fecha",
  interval_days: "carencia (días)",
  safe_from: "cosechar desde",
  fraction_of_mrl: "fracción del LMR",
  percent_of_arfd: "% ARfD",
  arfd_mg_kg_bw: "ARfD (mg/kg pc)",
  arfd_source: "fuente ARfD",
  population: "población",
  diet: "dieta",
  iesti_mg_kg_bw: "IESTI (mg/kg pc)",
  group: "grupo",
};

function Evidence({ evidence }: { evidence: Record<string, unknown> }) {
  const entries = Object.entries(evidence).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (!entries.length) return null;
  return (
    <details>
      <summary>Evidencia</summary>
      <dl className="evidence">
        {entries.map(([k, v]) => (
          <Fragment key={k}>
            <dt>{EVIDENCE_LABEL[k] ?? k}</dt>
            <dd>{k === "snapshot" ? fmtSnapshot(String(v)) : typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
          </Fragment>
        ))}
      </dl>
    </details>
  );
}

/** Identical findings (same rule, block, ingredient, market and message: the same product applied twice) as one row. */
export function collapseFindings(findings: Finding[]): { finding: Finding; count: number }[] {
  const seen = new Map<string, { finding: Finding; count: number }>();
  for (const f of findings) {
    const key = [f.code, f.block, f.ingredient, f.market, f.message].join("|");
    const hit = seen.get(key);
    if (hit) hit.count += 1;
    else seen.set(key, { finding: f, count: 1 });
  }
  return [...seen.values()];
}

/** Findings sorted by severity, optionally grouped by block. */
export function FindingsTable({ findings, groupByBlock = false }: { findings: Finding[]; groupByBlock?: boolean }) {
  if (!findings.length) return <div className="empty">Sin hallazgos: ninguna regla se incumple ni queda en riesgo.</div>;
  const groups = new Map<string, { finding: Finding; count: number }[]>();
  for (const item of collapseFindings(sortFindings(findings))) {
    const key = groupByBlock ? (item.finding.block ?? "Programa") : "";
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 96 }}>Severidad</th>
            <th>Hallazgo</th>
            <th style={{ width: 150 }}>Ingrediente</th>
            <th style={{ width: 70 }}>Mercado</th>
          </tr>
        </thead>
        <tbody>
          {[...groups.entries()].map(([group, items]) => (
            <Fragment key={group || "all"}>
              {groupByBlock && (
                <tr className="group">
                  <td colSpan={4}>
                    <span className="label" style={{ marginRight: 8 }}>Bloque</span>
                    <span className="mono">{group}</span>
                  </td>
                </tr>
              )}
              {items.map(({ finding: f, count }, i) => (
                <tr key={`${f.code}-${i}`}>
                  <td>
                    <SeverityStamp severity={f.severity} />
                  </td>
                  <td>
                    <div style={{ fontWeight: 500 }}>
                      {FINDING_TITLE[f.code] ?? f.code}
                      {count > 1 && <span className="mono small muted" title="Aparece en varias aplicaciones"> ×{count}</span>}
                    </div>
                    <div className="small" style={{ color: "var(--ink-2)" }}>{f.message}</div>
                    <Evidence evidence={f.evidence as Record<string, unknown>} />
                  </td>
                  <td className="mono small">{f.ingredient ?? "—"}</td>
                  <td className="mono small">{f.market ? MARKET_SHORT[f.market] ?? f.market : "—"}</td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
