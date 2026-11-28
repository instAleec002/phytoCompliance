"use client";

import { FindingsTable, SeverityCounts } from "@/components/findings/FindingsTable";
import { Panel } from "@/components/ui/Page";
import { Stamp, VerdictStamp } from "@/components/ui/Stamp";
import type { Schemas } from "@/lib/api/client";
import { daysBetween, fmtDate, mgkg } from "@/lib/format";
import { MARKET_SHORT } from "@/lib/labels";
import { downloadCsv } from "@/lib/download";

import { HarvestTimeline } from "./HarvestTimeline";
import type { Draft } from "./model";
import styles from "./program.module.css";
import { findingsToCsv } from "./report";

const VERDICT_TEXT: Record<string, string> = {
  blocking: "El programa incumple reglas: no puede ir como está",
  risk: "El programa puede incumplir según el residuo a la cosecha o datos faltantes",
  info: "Sin incumplimientos; hay observaciones",
};

export function ProgramResults({
  report,
  draft,
  alerts,
  evaluationDate,
}: {
  report: Schemas["ReportOut"];
  draft: Draft;
  alerts: Schemas["AlertOut"][] | undefined;
  evaluationDate: string;
}) {
  return (
    <div className="stack">
      <div className="print-only">
        <h2 style={{ margin: 0 }}>Informe de validación del programa</h2>
        <div className="small">
          Cultivo: {draft.crop} · Fecha de evaluación: {fmtDate(evaluationDate)} · {draft.blocks.length} bloques ·{" "}
          {draft.applications.length} aplicaciones
        </div>
      </div>
      <Panel>
        <div className={styles.verdict}>
          <VerdictStamp verdict={report.verdict} />
          <span className={styles.verdictTitle}>
            {report.verdict ? VERDICT_TEXT[report.verdict] : "El programa cumple todas las reglas verificadas"}
          </span>
          <span style={{ flex: 1 }} />
          <SeverityCounts findings={report.findings} />
          <span className="row no-print" style={{ gap: 6 }}>
            <button type="button" className="btn btn-quiet" disabled={!report.findings.length}
              onClick={() => downloadCsv(`hallazgos-${draft.crop || "programa"}-${evaluationDate}.csv`,
                findingsToCsv(report.findings, draft, evaluationDate))}>Exportar hallazgos</button>
            <button type="button" className="btn btn-quiet" onClick={() => window.print()}>Imprimir o guardar PDF</button>
          </span>
        </div>
      </Panel>

      <div className="print-only">
        <Panel title="Aplicaciones evaluadas" flush>
          <table className="table">
            <thead><tr><th>Bloque</th><th>Producto</th><th>Plaga</th><th>Fecha</th></tr></thead>
            <tbody>
              {draft.applications.map((a) => (
                <tr key={a.id}><td className="mono">{a.block}</td><td>{a.product_name || a.product_id}</td>
                  <td className="small">{a.pest || "—"}</td><td className="mono">{fmtDate(a.applied_on)}</td></tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>

      <Panel title="Cosecha segura por bloque" flush>
        <div className={styles.blocks}>
          {draft.blocks.map((b) => {
            const safe = report.safe_harvest.find((s) => s.block === b.key.trim());
            const late = safe?.safe_from && safe.safe_from > b.harvest_on;
            return (
              <div key={b.key} className={styles.blockRow}>
                <div className={styles.blockMeta}>
                  <span className={styles.blockKey}>{b.key}</span>
                  <span className="small muted">{b.markets.map((m) => MARKET_SHORT[m] ?? m).join(" · ")}</span>
                  <span className={styles.blockSafe}>
                    segura <b>{fmtDate(safe?.safe_from)}</b>
                  </span>
                  {late && <Stamp tone="blocking">+{daysBetween(b.harvest_on, safe!.safe_from!)} d</Stamp>}
                  {safe && safe.undetermined_by.length > 0 && <Stamp tone="risk">{safe.undetermined_by.length} sin carencia</Stamp>}
                </div>
                <div className={styles.chart}>
                  <HarvestTimeline
                    input={{
                      harvest_on: b.harvest_on,
                      safe_from: safe?.safe_from ?? null,
                      applications: draft.applications
                        .filter((a) => a.block === b.key)
                        .map((a) => ({ id: a.id, label: a.product_name || a.product_id, applied_on: a.applied_on, phi_days: a.phi_days })),
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel title="Hallazgos" aside={<span className="small muted">Ordenados por severidad, por bloque</span>} flush>
        <FindingsTable findings={report.findings} groupByBlock />
      </Panel>

      <Panel title="Límites que cambian" aside={<span className="small muted">Para los ingredientes del programa, desde el {fmtDate(evaluationDate)}</span>} flush>
        {!alerts ? (
          <div className="empty">Consultando…</div>
        ) : alerts.length === 0 ? (
          <div className="empty">Ningún límite publicado cambia para estos ingredientes.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Aplica desde</th>
                <th>Ingrediente</th>
                <th>Mercado</th>
                <th className="num">Actual</th>
                <th className="num">Nuevo</th>
                <th>Bloques afectados</th>
                <th>Norma</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a, i) => (
                <tr key={i}>
                  <td className="mono">{fmtDate(a.applies_from)} <span className="muted small">({a.days_left} d)</span></td>
                  <td className="mono">{a.ingredient}</td>
                  <td className="mono">{MARKET_SHORT[a.market] ?? a.market}</td>
                  <td className="num">{mgkg(a.current_mg_kg)}</td>
                  <td className="num">
                    {a.new_no_mrl_required ? "exento" : mgkg(a.new_mg_kg)} {a.stricter && <Stamp tone="risk">más estricto</Stamp>}
                  </td>
                  <td className="mono">{a.blocks_affected.length ? a.blocks_affected.join(", ") : <span className="muted">ninguno</span>}</td>
                  <td className="cite">{a.regulation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
