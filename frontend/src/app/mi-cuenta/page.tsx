"use client";

import { useState } from "react";

import { ActivityTable } from "@/components/ui/ActivityTable";
import { ErrorNote, Loading, PageHead, Panel } from "@/components/ui/Page";
import { PasswordFields, passwordReady } from "@/components/ui/PasswordFields";
import { Stamp } from "@/components/ui/Stamp";
import { MyDataPanel } from "@/features/privacy/Privacy";
import { useChangePassword, useMyActivity, useMySessions, useRevokeSession } from "@/lib/api/accounts";
import { fmtDateTime } from "@/lib/format";
import { deviceLabel } from "@/lib/labels";
import { useSession } from "@/lib/session";

export default function AccountPage() {
  const { me } = useSession();
  const sessions = useMySessions();
  const revoke = useRevokeSession();
  const activity = useMyActivity();
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  if (!me) return null;

  return (
    <div className="page">
      <PageHead index="10" title="Mi cuenta" lead="Sus datos, su contraseña, los dispositivos con sesión abierta y lo que hizo en el sistema." />
      <div className="stack">
        <div className="grid-2" style={{ alignItems: "start" }}>
          <Panel title="Datos">
            <dl className="evidence" style={{ fontSize: 13 }}>
              <dt>nombre</dt><dd>{me.nombre}</dd>
              <dt>usuario</dt><dd>{me.usuario}</dd>
              <dt>correo</dt><dd>{me.email}</dd>
              <dt>rol</dt><dd>{me.rol === "admin" ? "administración" : "usuario"}</dd>
              <dt>último ingreso</dt><dd>{fmtDateTime(me.ultimo_ingreso)}</dd>
              <dt>cuenta creada</dt><dd>{fmtDateTime(me.creado)}</dd>
            </dl>
            <div className="small muted" style={{ marginTop: 10 }}>El correo y el usuario los cambia el administrador.</div>
          </Panel>

          <Panel title="Cambiar contraseña">
            <form className="stack" onSubmit={(e) => {
              e.preventDefault();
              change.mutate({ actual: current, nueva: password }, { onSuccess: () => { setCurrent(""); setPassword(""); setConfirm(""); } });
            }}>
              <label className="field"><span>Contraseña actual</span>
                <input type="password" value={current} autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} /></label>
              <PasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} username={me.usuario} />
              <ErrorNote error={change.error} />
              {change.isSuccess && <div className="notice" data-tone="ok">Contraseña cambiada. Las sesiones de otros dispositivos se cerraron.</div>}
              <div><button type="submit" className="btn btn-primary" disabled={!current || !passwordReady(password, confirm, me.usuario) || change.isPending}>
                Cambiar contraseña</button></div>
            </form>
          </Panel>
        </div>

        <Panel title="Sesiones abiertas" aside={<span className="small muted">Cierre las de equipos que ya no usa</span>} flush>
          {sessions.isPending ? <Loading what="sesiones" /> : sessions.isError ? <div className="panel-body"><ErrorNote error={sessions.error} /></div> : (
            <table className="table">
              <thead><tr><th>Dispositivo</th><th>Inicio</th><th>Última actividad</th><th>Vence a más tardar</th><th /></tr></thead>
              <tbody>
                {sessions.data.map((s) => (
                  <tr key={s.id}>
                    <td>{deviceLabel(s.agente)} {s.actual && <Stamp tone="ok">esta sesión</Stamp>}</td>
                    <td className="mono small">{fmtDateTime(s.creada)}</td>
                    <td className="mono small">{fmtDateTime(s.ultima_actividad)}</td>
                    <td className="mono small">{fmtDateTime(s.expira)}</td>
                    <td style={{ textAlign: "right" }}>
                      {!s.actual && <button type="button" className="btn btn-quiet" onClick={() => revoke.mutate(s.id)}>Cerrar</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <MyDataPanel />

        <Panel title="Mi actividad" flush>
          {activity.isPending ? <Loading what="actividad" /> : activity.isError ? <div className="panel-body"><ErrorNote error={activity.error} /></div> : (
            <ActivityTable rows={activity.data} />
          )}
        </Panel>
      </div>
    </div>
  );
}
