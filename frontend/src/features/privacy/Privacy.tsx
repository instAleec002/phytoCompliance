"use client";

import Link from "next/link";
import { useState } from "react";

import { ErrorNote, Loading, Panel } from "@/components/ui/Page";
import { Stamp } from "@/components/ui/Stamp";
import {
  useAdminRights,
  useDownloadMyData,
  useMyRights,
  useNotice,
  useRequestRight,
  useResolveRight,
} from "@/lib/api/privacy";
import { fmtDateTime } from "@/lib/format";

export const RIGHT_LABEL: Record<string, string> = {
  acceso: "Acceso",
  rectificacion: "Rectificación",
  cancelacion: "Cancelación",
  oposicion: "Oposición",
};

const STATE: Record<string, { label: string; tone: "ok" | "info" | "neutral" }> = {
  pendiente: { label: "pendiente", tone: "info" },
  atendida: { label: "atendida", tone: "ok" },
  rechazada: { label: "rechazada", tone: "neutral" },
};

/** The notice text, as served by the API (one source for the activation page and /privacidad). */
export function NoticeBody({ compact = false }: { compact?: boolean }) {
  const notice = useNotice();
  if (notice.isPending) return <Loading what="el aviso de privacidad" />;
  if (notice.isError) return <ErrorNote error={notice.error} />;
  return (
    <div className="stack" style={{ gap: compact ? 8 : 12 }}>
      {notice.data.secciones.map((s) => (
        <section key={s.titulo}>
          <h3 style={{ margin: "0 0 2px", fontSize: compact ? 13.5 : 15 }}>{s.titulo}</h3>
          <p style={{ margin: 0, fontSize: compact ? 13 : 14, lineHeight: 1.55 }}>{s.texto}</p>
        </section>
      ))}
      <div className="small muted">Versión del aviso: {notice.data.version} · Ley N.° 29733, Ley de Protección de Datos Personales</div>
    </div>
  );
}

/** Mi cuenta: download one's data (access) and request rectification, cancellation or opposition. */
export function MyDataPanel() {
  const download = useDownloadMyData();
  const rights = useMyRights();
  const request = useRequestRight();
  const [tipo, setTipo] = useState("rectificacion");
  const [detalle, setDetalle] = useState("");
  return (
    <Panel title="Mis datos personales" aside={<Link prefetch={false} href="/privacidad/" className="small">Aviso de privacidad</Link>}>
      <div className="stack">
        <div className="stack" style={{ gap: 6 }}>
          <div><b>Acceso.</b> Descargue una copia de todo lo que el sistema guarda de su cuenta: perfil, sesiones, actividad, programas, lotes y conversaciones.</div>
          <div><button type="button" className="btn" onClick={() => download.mutate()} disabled={download.isPending}>Descargar mis datos (JSON)</button></div>
          <ErrorNote error={download.error} />
        </div>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); request.mutate({ tipo, detalle }, { onSuccess: () => setDetalle("") }); }}>
          <div><b>Rectificación, cancelación u oposición.</b> La administración responde por escrito y la respuesta queda aquí.</div>
          <label className="field"><span>Derecho</span>
            <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="rectificacion">Rectificación (corregir un dato)</option>
              <option value="cancelacion">Cancelación (eliminar la cuenta o un dato)</option>
              <option value="oposicion">Oposición (a un tratamiento)</option>
            </select>
          </label>
          <label className="field"><span>Qué dato o qué tratamiento</span>
            <textarea value={detalle} rows={3} onChange={(e) => setDetalle(e.target.value)}
              placeholder="Por ejemplo: mi nombre figura como «Ana Quispe»; debe decir «Ana María Quispe»." /></label>
          <ErrorNote error={request.error} />
          {request.isSuccess && <div className="notice" data-tone="ok">Solicitud registrada.</div>}
          <div><button type="submit" className="btn btn-primary" disabled={detalle.trim().length < 10 || request.isPending}>Enviar solicitud</button></div>
        </form>
        {rights.data && rights.data.length > 0 && (
          <table className="table">
            <thead><tr><th>Fecha</th><th>Derecho</th><th>Detalle</th><th>Estado</th><th>Respuesta</th></tr></thead>
            <tbody>
              {rights.data.map((r) => (
                <tr key={r.id}>
                  <td className="mono small">{fmtDateTime(r.creada)}</td>
                  <td>{RIGHT_LABEL[r.tipo] ?? r.tipo}</td>
                  <td className="small">{r.detalle}</td>
                  <td><Stamp tone={STATE[r.estado]?.tone ?? "neutral"}>{STATE[r.estado]?.label ?? r.estado}</Stamp></td>
                  <td className="small">{r.respuesta ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Panel>
  );
}

function Resolve({ id }: { id: number }) {
  const resolve = useResolveRight();
  const [text, setText] = useState("");
  return (
    <div className="stack" style={{ gap: 6 }}>
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} aria-label="Respuesta al titular"
        placeholder="Qué se hizo, o el motivo del rechazo" />
      <ErrorNote error={resolve.error} />
      <div style={{ display: "flex", gap: 6 }}>
        <button type="button" className="btn btn-primary" disabled={text.trim().length < 10 || resolve.isPending}
          onClick={() => resolve.mutate({ id, body: { estado: "atendida", respuesta: text } })}>Atendida</button>
        <button type="button" className="btn" disabled={text.trim().length < 10 || resolve.isPending}
          onClick={() => resolve.mutate({ id, body: { estado: "rechazada", respuesta: text } })}>Rechazar</button>
      </div>
    </div>
  );
}

/** Administración: requests from the account holders, answered in writing and kept in the activity log. */
export function RightsAdminPanel() {
  const rights = useAdminRights();
  return (
    <Panel title="Solicitudes de derechos" aside={<span className="small muted">Ley N.° 29733: rectificación, cancelación y oposición</span>} flush>
      {rights.isPending ? <Loading what="solicitudes" /> : rights.isError ? <div className="panel-body"><ErrorNote error={rights.error} /></div> :
        rights.data.length === 0 ? <div className="panel-body empty">No hay solicitudes.</div> : (
          <table className="table">
            <thead><tr><th>Fecha</th><th>Titular</th><th>Derecho</th><th>Detalle</th><th>Estado</th><th style={{ width: 300 }}>Respuesta</th></tr></thead>
            <tbody>
              {rights.data.map((r) => (
                <tr key={r.id}>
                  <td className="mono small">{fmtDateTime(r.creada)}</td>
                  <td>{r.nombre}<div className="small muted">{r.usuario}</div></td>
                  <td>{RIGHT_LABEL[r.tipo] ?? r.tipo}</td>
                  <td className="small">{r.detalle}</td>
                  <td><Stamp tone={STATE[r.estado]?.tone ?? "neutral"}>{STATE[r.estado]?.label ?? r.estado}</Stamp></td>
                  <td className="small">{r.estado === "pendiente" ? <Resolve id={r.id} /> : r.respuesta}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </Panel>
  );
}
