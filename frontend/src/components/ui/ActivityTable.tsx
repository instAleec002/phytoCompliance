"use client";

import type { Schemas } from "@/lib/api/client";
import { fmtDateTime } from "@/lib/format";
import { ACTION_LABEL, SEVERITY } from "@/lib/labels";

import { Stamp } from "./Stamp";

function detailText(action: string, d: Record<string, unknown>): string {
  if (action === "programa_validado") {
    const v = d.veredicto ? SEVERITY[String(d.veredicto)]?.label ?? d.veredicto : "sin hallazgos";
    return `${d.cultivo} · ${d.bloques} bloques · ${d.aplicaciones} aplicaciones · ${v}`;
  }
  if (action === "lote_evaluado") return `lote ${d.codigo} · ${d.veredicto ? SEVERITY[String(d.veredicto)]?.label ?? d.veredicto : "cumple"}`;
  if (action === "programa_guardado") return String(d.nombre ?? "");
  if (action === "usuario_invitado") return `${d.usuario} · ${d.rol}`;
  if (action === "usuario_actualizado") return [d.rol && `rol ${d.rol}`, d.estado && `estado ${d.estado}`].filter(Boolean).join(" · ");
  if (action === "enlace_emitido") return String(d.tipo ?? "");
  if (action === "ingreso_fallido") return d.bloqueada ? "cuenta bloqueada 15 min" : "";
  return "";
}

/** The activity log; with ``showUser`` it says who did each thing (administration). */
export function ActivityTable({ rows, showUser = false }: { rows: Schemas["ActivityOut"][]; showUser?: boolean }) {
  if (!rows.length) return <div className="empty">Sin actividad registrada.</div>;
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 150 }}>Fecha y hora</th>
            {showUser && <th>Cuenta</th>}
            <th>Acción</th>
            <th>Detalle</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <td className="mono small">{fmtDateTime(a.creado)}</td>
              {showUser && <td className="small">{a.nombre ?? "—"}<div className="muted mono">{a.email}</div></td>}
              <td>{a.accion === "ingreso_fallido" ? <Stamp tone="risk">{ACTION_LABEL[a.accion]}</Stamp> : ACTION_LABEL[a.accion] ?? a.accion}</td>
              <td className="small mono" style={{ color: "var(--ink-2)" }}>{detailText(a.accion, a.detalle as Record<string, unknown>)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
