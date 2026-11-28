"use client";

import { ErrorNote, PageHead, Panel } from "@/components/ui/Page";
import { Stamp } from "@/components/ui/Stamp";
import { useCrops, useHealth, useMarkets } from "@/lib/api/hooks";
import { fmtDate } from "@/lib/format";
import { LIMIT_STATUS, MARKET_LABEL, SEVERITY } from "@/lib/labels";
import { useSettings } from "@/lib/settings";

const STATUS_MEANING: Record<string, string> = {
  specific: "La fuente fija un límite para este residuo y cultivo.",
  default: "UE sin límite específico: rige 0,01 mg/kg; cualquier residuo detectable lo incumple.",
  exempt: "No requiere límite (Anexo IV de la UE, exención de 40 CFR 180).",
  not_permitted: "EE. UU. sin tolerancia: el residuo no está permitido.",
  no_reference: "El Codex no fija límite: decide el país de destino.",
  without_value: "La fuente lista el residuo sin valor; la nota explica qué rige.",
  no_data: "El mercado no está cargado o no se conoce su estado en esa fecha.",
};
const SEVERITY_MEANING: Record<string, string> = {
  blocking: "Incumple una regla: el programa o el lote no puede ir como está.",
  risk: "Puede incumplir según el residuo a la cosecha o por datos faltantes.",
  info: "Para saber; no se incumple ninguna regla.",
};

export default function StatusPage() {
  const { connection } = useSettings();
  const health = useHealth();
  const markets = useMarkets();
  const crops = useCrops();

  return (
    <div className="page">
      <PageHead index="09" title="Estado de los datos"
        lead="De dónde sale cada cifra y desde cuándo se conoce. Todas las respuestas citan la norma y la instantánea descargada." />
      <div className="stack">
        <div className="grid-2">
          <Panel title="Conexión" aside={health.isSuccess ? <Stamp tone="ok">en línea</Stamp> : health.isPending ? <Stamp tone="neutral">conectando</Stamp> : <Stamp tone="blocking">sin conexión</Stamp>}>
            <div className="stack">
              <dl className="evidence" style={{ fontSize: 12.5 }}>
                <dt>API</dt><dd>{connection.apiUrl}</dd>
              </dl>
              <ErrorNote error={health.error ?? markets.error} />
            </div>
          </Panel>
          <Panel title="Cultivos">
            {crops.data ? (
              <table className="table">
                <thead><tr><th>Cultivo</th><th>Código UE</th><th>Grupo EE. UU.</th><th>SIGIA</th></tr></thead>
                <tbody>{crops.data.map((c) => (
                  <tr key={c.key}><td>{c.name_es}<div className="small muted"><i>{c.scientific_name}</i></div></td>
                    <td className="mono">{c.eu_code}</td><td className="mono">{c.us_crop_group}</td><td className="mono">{c.sigia_id}</td></tr>
                ))}</tbody>
              </table>
            ) : <div className="empty">{crops.isError ? "Sin datos" : "Consultando…"}</div>}
          </Panel>
        </div>

        <Panel title="Mercados" flush>
          {markets.data ? (
            <table className="table">
              <thead><tr><th>Mercado</th><th>Fuente</th><th>Estado conocido</th></tr></thead>
              <tbody>{markets.data.map((m) => (
                <tr key={m.key}>
                  <td><b>{MARKET_LABEL[m.key] ?? m.name}</b> <span className="mono small muted">{m.key}</span></td>
                  <td className="small">{m.source ?? (m.key === "EU" ? "EU Pesticides Database (DG SANTE), con historial de versiones" : "—")}</td>
                  <td className="mono">{m.known_from ? `desde ${fmtDate(m.known_from)}; antes: sin datos` : "historial completo"}</td>
                </tr>
              ))}</tbody>
            </table>
          ) : <div className="empty">{markets.isError ? "Sin datos" : "Consultando…"}</div>}
        </Panel>

        <div className="grid-2">
          <Panel title="Estados de un límite" flush>
            <table className="table"><tbody>
              {Object.entries(LIMIT_STATUS).map(([k, v]) => (
                <tr key={k}><td style={{ width: 150 }}><Stamp tone={v.tone}>{v.label}</Stamp></td><td className="small">{STATUS_MEANING[k]}</td></tr>
              ))}
            </tbody></table>
          </Panel>
          <Panel title="Severidad de un hallazgo" flush>
            <table className="table"><tbody>
              {Object.entries(SEVERITY).map(([k, v]) => (
                <tr key={k}><td style={{ width: 150 }}><Stamp tone={v.tone}>{v.label}</Stamp></td><td className="small">{SEVERITY_MEANING[k]}</td></tr>
              ))}
            </tbody></table>
          </Panel>
        </div>
      </div>
    </div>
  );
}
