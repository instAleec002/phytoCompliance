"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { ErrorNote, Loading } from "@/components/ui/Page";
import { PasswordFields, passwordReady } from "@/components/ui/PasswordFields";
import { NoticeBody } from "@/features/privacy/Privacy";
import { useLinkInfo, useRedeem } from "@/lib/api/accounts";
import { useNotice } from "@/lib/api/privacy";
import { fmtDate } from "@/lib/format";

function Activate() {
  const params = useSearchParams();
  const token = params.get("t");
  const info = useLinkInfo(token);
  const redeem = useRedeem();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [accepted, setAccepted] = useState(false);
  const notice = useNotice();
  const kind = info.data?.tipo === "restablecimiento" ? "restablecimiento" : "activacion";

  if (!token) return <div className="notice" data-tone="blocking">Falta el enlace. Ábralo tal como lo recibió del administrador.</div>;
  if (info.isPending) return <Loading what="el enlace" />;
  if (info.isError) return <ErrorNote error={info.error} />;
  const account = info.data!;

  if (redeem.isSuccess) {
    return (
      <div className="stack">
        <h1>{kind === "activacion" ? "Cuenta activada" : "Contraseña restablecida"}</h1>
        <div className="notice" data-tone="ok">Ya puede iniciar sesión como <b className="mono">{account.usuario}</b> o con su correo.</div>
        <Link prefetch={false} className="btn btn-primary" href={`/iniciar-sesion/?usuario=${encodeURIComponent(account.usuario)}`}
          style={{ justifyContent: "center" }}>Iniciar sesión</Link>
      </div>
    );
  }

  return (
    <div className="stack">
      <div>
        <div className="label">{kind === "activacion" ? "Activación de cuenta" : "Restablecimiento"}</div>
        <h1 style={{ marginTop: 4 }}>{kind === "activacion" ? `Hola, ${account.nombre}` : "Nueva contraseña"}</h1>
      </div>
      <form className="panel" onSubmit={(e) => {
        e.preventDefault();
        redeem.mutate({ token, contrasena: password, aviso_version: kind === "activacion" ? notice.data?.version : undefined });
      }}>
        <div className="panel-body stack">
          <dl className="evidence" style={{ fontSize: 12.5 }}>
            <dt>usuario</dt><dd>{account.usuario}</dd>
            <dt>correo</dt><dd>{account.email}</dd>
            <dt>enlace válido hasta</dt><dd>{fmtDate(account.expira.slice(0, 10))} {account.expira.slice(11, 16)} UTC</dd>
          </dl>
          <PasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} username={account.usuario} />
          {kind === "activacion" && (
            <div className="stack" style={{ gap: 6 }}>
              <details>
                <summary className="small">Leer el aviso de privacidad</summary>
                <div style={{ marginTop: 8, maxHeight: 260, overflow: "auto" }}><NoticeBody compact /></div>
              </details>
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} style={{ marginTop: 3 }} />
                <span className="small">He leído el aviso de privacidad y acepto el tratamiento de mis datos para usar el sistema (Ley N.° 29733).</span>
              </label>
            </div>
          )}
          <ErrorNote error={redeem.error} />
          <button type="submit" className="btn btn-primary"
            disabled={!passwordReady(password, confirm, account.usuario) || (kind === "activacion" && !accepted) || redeem.isPending}
            style={{ justifyContent: "center" }}>{kind === "activacion" ? "Activar la cuenta" : "Guardar la contraseña"}</button>
        </div>
      </form>
      <div className="small muted">El enlace sirve una sola vez. {kind === "restablecimiento" && "Al guardar, se cierran las sesiones abiertas de la cuenta."}</div>
    </div>
  );
}

export default function ActivatePage() {
  return (
    <Suspense fallback={null}>
      <Activate />
    </Suspense>
  );
}
