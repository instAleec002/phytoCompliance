"use client";

import { useHealth, useMarkets } from "@/lib/api/hooks";
import { fmtDate, todayISO } from "@/lib/format";
import { MARKET_SHORT } from "@/lib/labels";
import { useSettings } from "@/lib/settings";
import {
  showApiAddress, showConnectionDot, showEvaluationDate, showMarketFreshness,
} from "@/styles/ui.config";

import styles from "./shell.module.css";
import { UserMenu } from "./UserMenu";

export function StatusBar() {
  const { connection, evaluationDate, setEvaluationDate } = useSettings();
  const health = useHealth();
  const markets = useMarkets();
  const state = health.isPending ? "wait" : health.isSuccess ? "ok" : "error";
  const today = todayISO();
  const moved = evaluationDate !== today;

  return (
    <header className={`${styles.bar} no-print`}>
      {(showConnectionDot || showApiAddress) && (
        <div className={styles.barGroup} title={health.error?.message ?? connection.apiUrl}>
          {showConnectionDot && <span className={styles.dot} data-state={state} aria-hidden />}
          <span className="sr-only">{state === "ok" ? "API conectada" : state === "wait" ? "Conectando" : "Sin conexión"}</span>
          {showApiAddress && <span className={styles.host}>{connection.apiUrl.replace(/^https?:\/\//, "")}</span>}
        </div>
      )}

      {showMarketFreshness && markets.data && (
        <div className={styles.fresh} aria-label="Vigencia de los datos por mercado">
          {markets.data.map((m) => (
            <span key={m.key}>
              <b>{MARKET_SHORT[m.key] ?? m.key}</b> {m.known_from ? `desde ${fmtDate(m.known_from)}` : "historial completo"}
            </span>
          ))}
        </div>
      )}

      <div className={styles.barSpacer} />

      {showEvaluationDate && (
      <label className={styles.dateBox} data-moved={moved}>
        <span className="label">Fecha de evaluación</span>
        <input
          type="date"
          value={evaluationDate}
          onChange={(e) => e.target.value && setEvaluationDate(e.target.value)}
          aria-describedby="fecha-ayuda"
        />
        {moved && (
          <button type="button" className="btn btn-quiet" onClick={() => setEvaluationDate(today)}>
            Hoy
          </button>
        )}
        <span id="fecha-ayuda" className="sr-only">
          Todos los límites, validaciones y alertas se calculan para esta fecha.
        </span>
      </label>
      )}

      <UserMenu />
    </header>
  );
}
