"use client";

import { FindingsTable, SeverityCounts } from "@/components/findings/FindingsTable";
import { Panel } from "@/components/ui/Page";
import { LimitStamp, Stamp, VerdictStamp } from "@/components/ui/Stamp";
import type { Schemas } from "@/lib/api/client";
import { mgkg, percent } from "@/lib/format";

import styles from "./lab.module.css";

type Profile = Schemas["ProfileOut"];

/** Share of the MRL as a gauge, with the profile threshold (dashed) and the MRL (solid) marked. */
function Gauge({ fraction, threshold }: { fraction: number; threshold: number | null }) {
  const max = Math.max(1.2, fraction * 1.08);
  const pos = (f: number) => `${Math.min(100, (f / max) * 100)}%`;
  const tone = fraction > 1 ? "blocking" : threshold !== null && fraction > threshold ? "risk" : undefined;
  return (
    <div>
      <div className={styles.gauge} role="meter" aria-valuenow={Math.round(fraction * 100)} aria-valuemin={0}
        aria-valuemax={Math.round(max * 100)} aria-label="Porcentaje del LMR">
        <div className={styles.fill} data-tone={tone} style={{ width: pos(fraction) }} />
        {threshold !== null && <div className={`${styles.mark} ${styles.markProfile}`} style={{ left: pos(threshold) }} />}
        <div className={styles.mark} style={{ left: pos(1) }} />
      </div>
      <div className={styles.gaugeScale}>
        {threshold !== null && <span style={{ left: pos(threshold) }}>{Math.round(threshold * 100)} %</span>}
        <span style={{ left: pos(1) }}>LMR</span>
      </div>
    </div>
  );
}

export function LabResults({ report, profile }: { report: Schemas["LabReportOut"]; profile: Profile | null }) {
  const rows = report.measurements;
  const detected = rows.filter((r) => r.measured_mg_kg > 0);
  const sum = detected.reduce((s, r) => s + (r.fraction_of_mrl ?? 0), 0);
  const worstArfd = Math.max(0, ...detected.map((r) => r.acute?.percent_of_arfd ?? 0));
  const threshold = profile?.max_fraction_of_mrl_per_substance ?? null;

  return (
    <div className="stack">
      <Panel>
        <div className="row" style={{ alignItems: "center", gap: 14 }}>
          <VerdictStamp verdict={report.verdict} />
          <span style={{ fontWeight: 600, fontSize: 16 }}>
            {report.verdict === "blocking" ? "El lote no cumple" : report.verdict ? "El lote cumple con observaciones" : "El lote cumple"}
            {profile ? ` · ${profile.name}` : " · solo límites legales"}
          </span>
          <span style={{ flex: 1 }} />
          <SeverityCounts findings={report.findings} />
          <button type="button" className="btn btn-quiet no-print" onClick={() => window.print()}>Imprimir o guardar PDF</button>
        </div>
      </Panel>

      <div className={styles.totals}>
        <div className={styles.total}>
          <span className="label">Suma de fracciones del LMR</span>
          <span className={styles.totalValue}
            data-tone={profile?.max_sum_of_mrl_fractions != null && sum > profile.max_sum_of_mrl_fractions ? "blocking" : "ok"}>
            {percent(sum * 100)}
          </span>
          <span className="small muted">{profile?.max_sum_of_mrl_fractions != null ? `límite del perfil ${percent(profile.max_sum_of_mrl_fractions * 100)}` : "sin límite de perfil"}</span>
        </div>
        <div className={styles.total}>
          <span className="label">Residuos detectados</span>
          <span className={styles.totalValue}
            data-tone={profile?.max_number_of_residues != null && detected.length > profile.max_number_of_residues ? "blocking" : "ok"}>
            {detected.length}
          </span>
          <span className="small muted">{profile?.max_number_of_residues != null ? `límite del perfil ${profile.max_number_of_residues}` : "sin límite de perfil"}</span>
        </div>
        <div className={styles.total}>
          <span className="label">Mayor exposición aguda</span>
          <span className={styles.totalValue}
            data-tone={profile?.max_fraction_of_arfd != null && worstArfd > profile.max_fraction_of_arfd * 100 ? "blocking" : "ok"}>
            {worstArfd ? percent(worstArfd) : "—"}
          </span>
          <span className="small muted">de la ARfD, población más crítica (EFSA PRIMo 3.1)</span>
        </div>
      </div>

      <Panel title="Residuos medidos" flush>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Ingrediente</th>
                <th className="num">Medido mg/kg</th>
                <th>Límite</th>
                <th className="num">LMR mg/kg</th>
                <th style={{ minWidth: 220 }}>Fracción del LMR</th>
                <th className="num">% ARfD</th>
                <th>Población</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="mono">{r.ingredient}</td>
                  <td className="num">{mgkg(r.measured_mg_kg)}</td>
                  <td><LimitStamp status={r.limit.status} /></td>
                  <td className="num">{mgkg(r.limit.value_mg_kg)}</td>
                  <td>
                    {r.fraction_of_mrl !== null && r.fraction_of_mrl !== undefined ? (
                      <div className="row" style={{ gap: 10, alignItems: "center", flexWrap: "nowrap" }}>
                        <div style={{ flex: 1 }}><Gauge fraction={r.fraction_of_mrl} threshold={threshold} /></div>
                        <span className="num" style={{ width: 64 }}>{percent(r.fraction_of_mrl * 100)}</span>
                      </div>
                    ) : (
                      <span className="small muted">{r.limit.note ?? "sin valor de referencia"}</span>
                    )}
                  </td>
                  <td className="num">
                    {r.acute ? (
                      <span style={{ color: r.acute.percent_of_arfd > 100 ? "var(--blocking)" : undefined }}>{percent(r.acute.percent_of_arfd)}</span>
                    ) : r.arfd_status === "not_needed" ? (
                      <Stamp tone="neutral" title="La EFSA juzgó innecesaria una ARfD">no necesaria</Stamp>
                    ) : r.arfd_status === "not_set" ? (
                      <Stamp tone="risk">sin ARfD</Stamp>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="small">{r.acute ? `${r.acute.population === "children" ? "niños" : "adultos"} · ${r.acute.diet}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Hallazgos" flush>
        <FindingsTable findings={report.findings} />
      </Panel>
    </div>
  );
}
