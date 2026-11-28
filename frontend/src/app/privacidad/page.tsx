"use client";

import Link from "next/link";

import { ErrorNote } from "@/components/ui/Page";
import { NoticeBody } from "@/features/privacy/Privacy";
import { useAcceptNotice, useNotice } from "@/lib/api/privacy";
import { useSession } from "@/lib/session";

/** The privacy notice, readable without a session. A signed-in account that has not accepted the current version
 *  accepts it here. */
export default function PrivacyPage() {
  const { me, status } = useSession();
  const notice = useNotice();
  const accept = useAcceptNotice();
  const pending = status === "signed-in" && me?.aviso_pendiente;
  return (
    <div className="page" style={{ maxWidth: 820 }}>
      <h1>Aviso de privacidad</h1>
      {pending && (
        <div className="notice" data-tone="info" style={{ marginBottom: 12 }}>
          El aviso es nuevo o cambió desde la última vez que lo aceptó. Léalo y acéptelo para seguir usando el sistema.
        </div>
      )}
      <div className="panel"><div className="panel-body"><NoticeBody /></div></div>
      <div style={{ display: "flex", gap: 10, marginTop: 12, alignItems: "center" }}>
        {pending && notice.data && (
          <button type="button" className="btn btn-primary" disabled={accept.isPending}
            onClick={() => accept.mutate(notice.data.version)}>He leído y acepto el aviso</button>
        )}
        {status === "signed-in" && !pending && <span className="small muted">Usted aceptó la versión {me?.aviso_version}.</span>}
        {status === "signed-in" && <Link prefetch={false} href="/mi-cuenta/" className="small">Mis datos y derechos</Link>}
      </div>
      <ErrorNote error={accept.error} />
    </div>
  );
}
