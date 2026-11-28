"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useSession } from "@/lib/session";

import { Rail } from "./Rail";
import styles from "./shell.module.css";
import { StatusBar } from "./StatusBar";

// Sign-in and activation have a bare frame; every other page needs a session. Ajustes is reachable signed out, so the
// API address can be fixed before signing in. The server checks every permission again: this only steers the user.
const BARE = ["/iniciar-sesion", "/activar"];
const OPEN = [...BARE, "/ajustes", "/privacidad"];

const startsWith = (path: string, list: string[]) => list.some((p) => path === p || path.startsWith(`${p}/`));

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname() ?? "/";
  const router = useRouter();
  const { status, me } = useSession();
  const open = startsWith(path, OPEN);

  useEffect(() => {
    if (status === "signed-out" && !open) {
      router.replace(`/iniciar-sesion/?siguiente=${encodeURIComponent(path)}`);
    }
  }, [status, open, path, router]);

  if (startsWith(path, BARE) || (open && status === "signed-out")) {
    return (
      <div className={styles.bare}>
        <div className={styles.bareMark}>
          <span className={styles.markCode}>TP202620505</span>
          <span className={styles.markName}>Cumplimiento fitosanitario</span>
        </div>
        <main id="contenido" className={styles.bareMain}>{children}</main>
        <div className={styles.bareFoot}>Cumplimiento con reglas exactas · consulta con fuentes citadas</div>
      </div>
    );
  }

  if (status !== "signed-in") {
    return <div className={styles.bare} aria-busy="true"><main className={styles.bareMain}><div className="empty">Verificando la sesión…</div></main></div>;
  }

  return (
    <div className={styles.app}>
      <Rail />
      <div className={styles.main}>
        <StatusBar />
        {me?.aviso_pendiente && !path.startsWith("/privacidad") && (
          <div className="notice" data-tone="info" role="status" style={{ margin: "12px 24px 0" }}>
            El aviso de privacidad es nuevo o cambió. <Link prefetch={false} href="/privacidad/">Léalo y acéptelo</Link> para seguir usando el sistema.
          </div>
        )}
        <main id="contenido">{children}</main>
      </div>
    </div>
  );
}
