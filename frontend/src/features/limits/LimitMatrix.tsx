"use client";

import { LimitStamp } from "@/components/ui/Stamp";
import { useLimit } from "@/lib/api/hooks";
import { fmtSnapshot, mgkg } from "@/lib/format";
import { MARKETS, MARKET_LABEL } from "@/lib/labels";

import styles from "./limits.module.css";

function Row({
  ingredient,
  crop,
  market,
  day,
  strictest,
  selected,
  onSelect,
}: {
  ingredient: string;
  crop: string;
  market: string;
  day: string;
  strictest: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const q = useLimit(ingredient, crop, market, day);
  const lim = q.data;
  return (
    <tr className={`${styles.selectRow} ${selected ? styles.selected : ""}`} onClick={onSelect}
      aria-selected={selected}>
      <td style={{ width: 170 }}>
        <div className={styles.market}>{MARKET_LABEL[market]}</div>
        <div className={styles.marketCode}>{market}</div>
      </td>
      <td style={{ width: 150 }}>{lim ? <LimitStamp status={lim.status} /> : <span className="muted small">{q.isError ? "error" : "…"}</span>}</td>
      <td style={{ width: 170 }}>
        {lim && (
          <>
            <div className={styles.value}>
              {lim.value_mg_kg === null ? "—" : mgkg(lim.value_mg_kg)}
              {lim.value_mg_kg !== null && <small>mg/kg</small>}
            </div>
            {lim.at_limit_of_determination && lim.status === "specific" && <div className="small muted">en el límite de determinación</div>}
            {strictest && <span className={styles.strictest}>más estricto</span>}
          </>
        )}
      </td>
      <td>
        {q.isError && <div className="notice" data-tone="blocking">{q.error.message}</div>}
        {lim && (
          <>
            <div className="cite">{lim.regulation ?? "—"}</div>
            {lim.residue && <div className="cite"><span className="src">residuo </span>{lim.residue}</div>}
            {lim.note && <div className={styles.note}>{lim.note.length > 320 ? `${lim.note.slice(0, 320)}…` : lim.note}</div>}
            {lim.ambiguous && <div className="small" style={{ color: "var(--risk)" }}>Varias definiciones de residuo posibles</div>}
          </>
        )}
      </td>
      <td style={{ width: 170 }} className="cite">{lim ? fmtSnapshot(lim.snapshot) : ""}</td>
    </tr>
  );
}

/** The limit of one ingredient and crop in every market, side by side, for the evaluation date. */
export function LimitMatrix({
  ingredient,
  crop,
  day,
  selected,
  onSelect,
  strictestMarket,
}: {
  ingredient: string;
  crop: string;
  day: string;
  selected: string;
  onSelect: (market: string) => void;
  strictestMarket: string | null;
}) {
  return (
    <table className={styles.matrix}>
      <thead>
        <tr>
          <th>Mercado</th>
          <th>Estado</th>
          <th>LMR</th>
          <th>Norma y nota</th>
          <th>Instantánea</th>
        </tr>
      </thead>
      <tbody>
        {MARKETS.map((m) => (
          <Row key={m} ingredient={ingredient} crop={crop} market={m} day={day} strictest={strictestMarket === m}
            selected={selected === m} onSelect={() => onSelect(m)} />
        ))}
      </tbody>
    </table>
  );
}
