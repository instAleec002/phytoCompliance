"use client";

import { fmtDate } from "@/lib/format";

import styles from "./program.module.css";
import { buildTimeline, type TimelineInput } from "./timeline";

const ROW = 18;
const TOP = 16;

/** One block: each application with its pre-harvest window, the planned harvest (solid) and the safe date (dashed). */
export function HarvestTimeline({ input }: { input: TimelineInput }) {
  const t = buildTimeline(input);
  if (!t) return <div className="small muted" style={{ padding: "10px 0" }}>Sin aplicaciones en este bloque.</div>;
  const width = 860;
  const left = 8;
  const inner = width - 16;
  const height = TOP + t.windows.length * ROW + 20;
  const px = (x: number) => left + x * inner;

  return (
    <svg className={styles.svg} viewBox={`0 0 ${width} ${height}`} role="img"
      aria-label={`Carencias de ${t.windows.length} aplicaciones; cosecha el ${fmtDate(input.harvest_on)}`}>
      {t.ticks.map((k) => (
        <g key={k.label + k.x}>
          <line className={styles.axis} x1={px(k.x)} x2={px(k.x)} y1={TOP - 4} y2={height - 14} />
          <text className={styles.tick} x={px(k.x) + 2} y={10}>{k.label}</text>
        </g>
      ))}
      {t.windows.map((w, i) => {
        const y = TOP + i * ROW;
        return (
          <g key={w.id}>
            <title>{`${w.label} · ventana hasta ${w.ends ? fmtDate(w.ends) : "carencia desconocida"}`}</title>
            {w.x1 === null ? (
              <rect className={styles.windowUnknown} x={px(w.x0)} y={y + 3} width={Math.max(24, inner * 0.06)} height={8} />
            ) : (
              <rect className={w.breach ? styles.windowBreach : styles.window} x={px(w.x0)} y={y + 3}
                width={Math.max(2, px(w.x1) - px(w.x0))} height={8} />
            )}
            <rect className={styles.appMark} x={px(w.x0) - 1} y={y} width={3} height={14} />
            <text className={styles.appLabel} x={w.labelLeft ? px(w.x0) - 6 : px(w.x1 ?? w.x0) + 6} y={y + 11}
              textAnchor={w.labelLeft ? "end" : "start"}>{w.label}</text>
          </g>
        );
      })}
      <line className={styles.harvest} x1={px(t.harvest)} x2={px(t.harvest)} y1={TOP - 6} y2={height - 12} />
      {(() => {
        // labels at the foot, on opposite sides of their lines so they never overlap
        const safeAfter = t.safe !== null && t.safe > t.harvest;
        const showSafe = t.safe !== null && Math.abs(t.safe - t.harvest) > 0.002;
        return (
          <>
            <text className={styles.harvestLabel} x={px(t.harvest) + (safeAfter ? -3 : 3)} y={height - 2}
              textAnchor={safeAfter ? "end" : "start"}>cosecha {fmtDate(input.harvest_on)}</text>
            {showSafe && (
              <>
                <line className={styles.safe} x1={px(t.safe!)} x2={px(t.safe!)} y1={TOP - 6} y2={height - 12} />
                <text className={styles.safeLabel} x={px(t.safe!) + (safeAfter ? 3 : -3)} y={height - 2}
                  textAnchor={safeAfter ? "start" : "end"}>segura {fmtDate(input.safe_from)}</text>
              </>
            )}
          </>
        );
      })()}
    </svg>
  );
}
