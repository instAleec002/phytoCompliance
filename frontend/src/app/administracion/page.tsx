"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { ActivityTable } from "@/components/ui/ActivityTable";
import { ErrorNote, Loading, PageHead, Panel } from "@/components/ui/Page";
import styles from "@/features/admin/admin.module.css";
import { UsersPanel } from "@/features/admin/UsersPanel";
import { WorkPanel } from "@/features/admin/WorkPanel";
import { RightsAdminPanel } from "@/features/privacy/Privacy";
import { useAudit, useUsers } from "@/lib/api/accounts";
import { useSession } from "@/lib/session";

const VIEWS = [
  { key: "usuarios", label: "Usuarios" },
  { key: "actividad", label: "Actividad" },
  { key: "trabajo", label: "Trabajo de las cuentas" },
  { key: "derechos", label: "Derechos de los titulares" },
] as const;

function Activity() {
  const users = useUsers();
  const [userId, setUserId] = useState<number | null>(null);
  const audit = useAudit(userId);
  return (
    <Panel title="Registro de actividad"
      aside={
        <select value={userId ?? ""} style={{ width: 280 }} aria-label="Filtrar por cuenta"
          onChange={(e) => setUserId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">Todas las cuentas</option>
          {users.data?.map((u) => <option key={u.id} value={u.id}>{u.nombre} · {u.usuario}</option>)}
        </select>
      }
      flush>
      {audit.isPending ? <Loading what="actividad" /> : audit.isError ? <div className="panel-body"><ErrorNote error={audit.error} /></div> : (
        <ActivityTable rows={audit.data} showUser />
      )}
    </Panel>
  );
}

function Administration() {
  const params = useSearchParams();
  const router = useRouter();
  const { isAdmin } = useSession();
  const view = params.get("vista") ?? "usuarios";
  const num = (k: string) => (params.get(k) ? Number(params.get(k)) : null);

  const go = (next: Record<string, string | number | null | undefined>) => {
    const q = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(next)) {
      if (v === null || v === undefined || v === "") q.delete(k);
      else q.set(k, String(v));
    }
    router.replace(`/administracion/?${q.toString()}`, { scroll: false });
  };

  if (!isAdmin) {
    return <div className="page"><div className="notice" data-tone="blocking">Esta sección es solo para la administración.</div></div>;
  }

  return (
    <div className="page">
      <PageHead index="12" title="Administración" lead="Cuentas de usuario, enlaces de activación y restablecimiento, actividad de todas las cuentas y su trabajo, en solo lectura." />
      <div className={styles.tabs} role="tablist">
        {VIEWS.map((v) => (
          <button key={v.key} type="button" role="tab" className={styles.tab} aria-selected={view === v.key}
            onClick={() => go({ vista: v.key, u: v.key === "trabajo" ? num("u") : null, p: null, l: null })}>{v.label}</button>
        ))}
      </div>
      {view === "usuarios" && <UsersPanel onViewWork={(u) => go({ vista: "trabajo", u, p: null, l: null })} />}
      {view === "actividad" && <Activity />}
      {view === "derechos" && <RightsAdminPanel />}
      {view === "trabajo" && (
        <WorkPanel userId={num("u")} programId={num("p")} lotId={num("l")}
          onSelect={(next) => go(next)} />
      )}
    </div>
  );
}

export default function AdministrationPage() {
  return (
    <Suspense fallback={null}>
      <Administration />
    </Suspense>
  );
}
