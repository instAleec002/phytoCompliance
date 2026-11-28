"use client";

import { Stamp } from "@/components/ui/Stamp";
import type { Schemas } from "@/lib/api/client";
import { fmtDate, mgkg } from "@/lib/format";
import { MARKET_SHORT } from "@/lib/labels";

/** Upcoming limits, soonest first, with how many days remain and whether the change tightens the limit. */
export function AlertsTable({ alerts, showBlocks = true }: { alerts: Schemas["AlertOut"][]; showBlocks?: boolean }) {
  if (!alerts.length) return <div className="empty">Ningún límite publicado cambia para estos ingredientes.</div>;
  const sorted = [...alerts].sort((a, b) => a.applies_from.localeCompare(b.applies_from));
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th className="num">Faltan</th>
            <th>Aplica desde</th>
            <th>Ingrediente</th>
            <th>Mercado</th>
            <th className="num">Actual mg/kg</th>
            <th className="num">Nuevo mg/kg</th>
            <th>Cambio</th>
            {showBlocks && <th>Bloques cosechados después</th>}
            <th>Norma</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((a, i) => (
            <tr key={i}>
              <td className="num">
                <Stamp tone={a.days_left <= 30 ? "blocking" : a.days_left <= 90 ? "risk" : "neutral"}>{a.days_left} d</Stamp>
              </td>
              <td className="mono">{fmtDate(a.applies_from)}</td>
              <td className="mono">{a.ingredient}</td>
              <td className="mono">{MARKET_SHORT[a.market] ?? a.market}</td>
              <td className="num">{mgkg(a.current_mg_kg)}</td>
              <td className="num">{a.new_no_mrl_required ? "exento" : mgkg(a.new_mg_kg)}</td>
              <td>
                {a.stricter ? <Stamp tone="risk">más estricto</Stamp> : a.new_mg_kg === a.current_mg_kg ? <span className="small muted">mismo valor, nueva norma</span> : <span className="small muted">se relaja</span>}
              </td>
              {showBlocks && <td className="mono">{a.blocks_affected.length ? a.blocks_affected.join(", ") : <span className="muted">ninguno</span>}</td>}
              <td className="cite">{a.regulation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
