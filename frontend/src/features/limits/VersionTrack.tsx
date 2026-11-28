"use client";

import { fmtDate } from "@/lib/format";

import styles from "./limits.module.css";
import { buildTrack, laneLabel, type TrackVersion } from "./track";

const LANE = 26;
const LEFT = 92; // lane labels
const TOP = 20;

/** Every version of a limit on one time axis, one lane per value; the dashed line is the evaluation date. */
export function VersionTrack({ versions, evaluationDate }: { versions: TrackVersion[]; evaluationDate: string }) {
  const track = buildTrack(versions, evaluationDate);
  if (!track) return <div className="empty">El mercado no lista versiones de este límite para el cultivo.</div>;
  const width = 900;
  const inner = width - LEFT - 16;
  const height = TOP + track.lanes.length * LANE + 18;
  const px = (x: number) => LEFT + x * inner;
  const cursorRight = track.cursor > 0.85;

  return (
    <svg className={styles.track} viewBox={`0 0 ${width} ${height}`} role="img"
      aria-label={`Historial: ${track.bars.length} versiones en ${track.lanes.length} valores distintos`}>
      {track.years.map((y) => (
        <g key={y.label}>
          <line className={styles.trackRule} x1={px(y.x)} x2={px(y.x)} y1={TOP - 4} y2={height - 16} />
          <text className={styles.trackLabel} x={px(y.x) + 3} y={12}>{y.label}</text>
        </g>
      ))}
      {track.lanes.map((label, i) => (
        <g key={label}>
          <line className={styles.trackRule} x1={LEFT} x2={width - 8} y1={TOP + i * LANE + LANE / 2} y2={TOP + i * LANE + LANE / 2} />
          <text className={styles.trackValue} x={LEFT - 10} y={TOP + i * LANE + LANE / 2 + 4} textAnchor="end">
            {label}{label !== "exento" && label !== "sin valor" ? " mg/kg" : ""}
          </text>
        </g>
      ))}
      {track.bars.map((b, i) => {
        const y = TOP + b.lane * LANE + LANE / 2 - 6;
        const cls = b.inForce ? styles.barInForce : b.future ? styles.barFuture : styles.bar;
        return (
          <g key={i}>
            <title>
              {`${laneLabel(b.version)} · desde ${fmtDate(b.version.applies_from)}${b.version.valid_until ? ` hasta ${fmtDate(b.version.valid_until)}` : ""} · ${b.version.regulation}`}
            </title>
            {/* a 1px gap between consecutive versions keeps each regulation visible on a shared lane */}
            <rect className={cls} x={px(b.x0) + 1} y={y} width={Math.max(2, px(b.x1) - px(b.x0) - 1)} height={12} />
            {b.open && <path className={cls} d={`M ${px(b.x1)} ${y - 2} l 7 8 l -7 8 z`} />}
          </g>
        );
      })}
      <line className={styles.cursor} x1={px(track.cursor)} x2={px(track.cursor)} y1={TOP - 6} y2={height - 14} />
      <text className={styles.cursorLabel} x={px(track.cursor) + (cursorRight ? -4 : 4)} y={height - 3}
        textAnchor={cursorRight ? "end" : "start"}>{fmtDate(evaluationDate)}</text>
    </svg>
  );
}
