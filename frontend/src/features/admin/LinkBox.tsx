"use client";

import { useState } from "react";

import type { Schemas } from "@/lib/api/client";

import styles from "./admin.module.css";

/** A one-time link, shown once: the admin copies it and hands it over (no mail server). */
export function LinkBox({ link, onClose }: { link: Schemas["LinkOut"]; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link.enlace);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  const activation = link.usuario.estado === "invitado";
  return (
    <div className="notice" data-tone="info" role="status">
      <div className="stack" style={{ gap: 8 }}>
        <div>
          <b>{activation ? "Enlace de activación" : "Enlace de restablecimiento"}</b> para <span className="mono">{link.usuario.usuario}</span>{" "}
          ({link.usuario.email}). Vence en {link.expira_en_horas} h y sirve una sola vez. Cópielo ahora: no se vuelve a mostrar.
        </div>
        <div className={styles.linkBox}>
          <input readOnly value={link.enlace} onFocus={(e) => e.target.select()} aria-label="Enlace" />
          <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
            <button type="button" className="btn btn-primary" onClick={copy}>{copied ? "Copiado" : "Copiar"}</button>
            <button type="button" className="btn btn-quiet" onClick={onClose}>Listo</button>
          </div>
        </div>
      </div>
    </div>
  );
}
