"use client";

import { useState } from "react";

import { ErrorNote, Loading, Panel } from "@/components/ui/Page";
import { Stamp } from "@/components/ui/Stamp";
import { useInvite, useNewLink, useUpdateUser, useUsers } from "@/lib/api/accounts";
import type { Schemas } from "@/lib/api/client";
import { fmtDateTime } from "@/lib/format";
import { ACCOUNT_STATE } from "@/lib/labels";
import { useSession } from "@/lib/session";

import styles from "./admin.module.css";
import { LinkBox } from "./LinkBox";

const EMPTY = { email: "", usuario: "", nombre: "", rol: "usuario" };

export function UsersPanel({ onViewWork }: { onViewWork: (userId: number) => void }) {
  const { me } = useSession();
  const users = useUsers();
  const invite = useInvite();
  const update = useUpdateUser();
  const newLink = useNewLink();
  const [form, setForm] = useState(EMPTY);
  const [link, setLink] = useState<Schemas["LinkOut"] | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    invite.mutate(form, { onSuccess: (out) => { setLink(out); setForm(EMPTY); } });
  };
  const usernameOk = /^[a-z0-9._-]{3,32}$/.test(form.usuario);

  return (
    <div className="stack">
      <Panel title="Invitar usuario" aside={<span className="small muted">No hay registro público: las cuentas nacen aquí</span>}>
        <form className={styles.inviteGrid} onSubmit={submit}>
          <label className="field"><span>Nombre</span>
            <input value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required /></label>
          <label className="field"><span>Usuario</span>
            <input className="mono" value={form.usuario} aria-invalid={!!form.usuario && !usernameOk} spellCheck={false}
              onChange={(e) => setForm({ ...form, usuario: e.target.value.toLowerCase().replace(/\s/g, "") })}
              placeholder="a-z 0-9 . _ -" required /></label>
          <label className="field"><span>Correo</span>
            <input className="mono" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label>
          <label className="field"><span>Rol</span>
            <select value={form.rol} onChange={(e) => setForm({ ...form, rol: e.target.value })}>
              <option value="usuario">Usuario</option>
              <option value="admin">Administración</option>
            </select></label>
          <button type="submit" className="btn btn-primary" disabled={!usernameOk || !form.email || !form.nombre || invite.isPending}>
            Invitar</button>
        </form>
        <div style={{ marginTop: 10 }}><ErrorNote error={invite.error} /></div>
      </Panel>

      {link && <LinkBox link={link} onClose={() => setLink(null)} />}
      <ErrorNote error={update.error ?? newLink.error} />

      <Panel title="Cuentas" aside={users.data ? <span className="small muted mono">{users.data.length} cuentas</span> : null} flush>
        {users.isPending ? <Loading what="cuentas" /> : users.isError ? <div className="panel-body"><ErrorNote error={users.error} /></div> : (
          <table className="table">
            <thead>
              <tr><th>Cuenta</th><th>Correo</th><th>Rol</th><th>Estado</th><th>Último ingreso</th><th /></tr>
            </thead>
            <tbody>
              {users.data.map((u) => {
                const self = u.id === me?.id;
                const state = ACCOUNT_STATE[u.estado] ?? { label: u.estado, tone: "neutral" as const };
                return (
                  <tr key={u.id} className={self ? styles.selfRow : undefined}>
                    <td><div style={{ fontWeight: 500 }}>{u.nombre} {self && <span className="small muted">(usted)</span>}</div>
                      <div className="mono small muted">{u.usuario}</div></td>
                    <td className="mono small">{u.email}</td>
                    <td style={{ width: 170 }}>
                      <select value={u.rol} disabled={self || update.isPending} aria-label={`Rol de ${u.usuario}`}
                        onChange={(e) => update.mutate({ id: u.id, body: { rol: e.target.value } })}>
                        <option value="usuario">Usuario</option>
                        <option value="admin">Administración</option>
                      </select>
                    </td>
                    <td><Stamp tone={state.tone}>{state.label}</Stamp></td>
                    <td className="mono small">{fmtDateTime(u.ultimo_ingreso)}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {u.estado !== "desactivado" && !self && (
                        <button type="button" className="btn btn-quiet" disabled={newLink.isPending}
                          onClick={() => newLink.mutate(u.id, { onSuccess: setLink })}>
                          {u.estado === "invitado" ? "Nuevo enlace" : "Restablecer"}</button>
                      )}
                      {!self && u.estado === "activo" && (
                        <button type="button" className="btn btn-quiet"
                          onClick={() => window.confirm(`¿Desactivar a ${u.usuario}? Sus sesiones se cierran al instante.`) &&
                            update.mutate({ id: u.id, body: { estado: "desactivado" } })}>Desactivar</button>
                      )}
                      {u.estado === "desactivado" && (
                        <button type="button" className="btn btn-quiet" onClick={() => update.mutate({ id: u.id, body: { estado: "activo" } })}>
                          Reactivar</button>
                      )}
                      <button type="button" className="btn" onClick={() => onViewWork(u.id)}>Ver trabajo</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
