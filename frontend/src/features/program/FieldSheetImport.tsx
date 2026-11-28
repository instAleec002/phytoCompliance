"use client";

import { useEffect, useRef, useState } from "react";

import { ErrorNote, Panel } from "@/components/ui/Page";
import { MarketChecks } from "@/components/ui/Pickers";
import { useImportProgram } from "@/lib/api/hooks";
import { fmtDate } from "@/lib/format";

import {
  DOSE_STATUS,
  ROW_STATUS,
  TARGET_STATUS,
  fileToBase64,
  needsReview,
  rowText,
  rowsToReview,
  type ImportResult,
} from "./fieldSheet";
import styles from "./program.module.css";

function Stamp({ map, value }: { map: Record<string, { label: string; tone: string }>; value: string | null | undefined }) {
  if (!value) return <span className="muted">—</span>;
  const s = map[value] ?? { label: value, tone: "neutral" };
  return <span className="stamp" data-tone={s.tone}>{s.label}</span>;
}

/** Import of a field sheet in three steps: the file and what the sheet does not say (harvest, markets, the program's
 * pest); the rows as the system resolved them, filtered by default to those a person should look at; and loading the
 * result into the editor, or loading and validating it at once. */
export function FieldSheetImport({
  crop,
  harvest,
  onUse,
  onClose,
}: {
  crop: string;
  harvest: string;
  onUse: (result: ImportResult, validateNow: boolean) => void;
  onClose: () => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [harvestOn, setHarvestOn] = useState(harvest);
  const [markets, setMarkets] = useState<string[]>(["EU"]);
  const [pest, setPest] = useState("");
  const [onlyReview, setOnlyReview] = useState(true);
  const importer = useImportProgram();
  const result = importer.data;
  const review = result ? rowsToReview(result.rows) : [];
  // a new result opens on the rows to review, or on all of them when none needs it
  useEffect(() => setOnlyReview(review.length > 0), [result]);
  const shown = result ? (onlyReview ? review : result.rows) : [];
  const ready = !!file && !!crop && !!harvestOn && markets.length > 0;

  const send = async () => {
    if (!ready || !file) return;
    importer.mutate({
      name: file.name, crop, markets, harvest_on: harvestOn, pest_text: pest.trim() || null,
      file_name: file.name, file_base64: await fileToBase64(file),
    });
  };

  const s = result?.summary as Record<string, number> | undefined;
  return (
    <Panel
      title={<h2>Hoja de campo</h2>}
      aside={<button type="button" className="btn btn-quiet" onClick={onClose}>Cerrar</button>}
    >
      <div className="stack">
        <ol className={styles.steps}>
          <li data-done={!!result}>Leer la hoja</li>
          <li data-done={!!result && !review.length}>Revisar las filas</li>
          <li>Cargar en el programa y validar</li>
        </ol>
        <p className="small muted" style={{ margin: 0 }}>
          Excel o CSV tal como lo lleva el campo; las columnas se reconocen por su nombre (fecha o etapa, producto,
          ingrediente, dosis, lote, plaga u objetivo). Cada fila se resuelve en un producto registrado y una fecha. Lo que
          no se puede resolver queda para revisar y nunca se reemplaza por otro producto.
        </p>
        {!crop && <div className="notice" data-tone="risk">Elija primero el cultivo del programa.</div>}

        <div className={styles.importForm}>
          <div className="field">
            <span>Hoja</span>
            <input ref={fileInput} type="file" accept=".xlsx,.xlsm,.csv,.txt" hidden
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); importer.reset(); }} />
            <button type="button" className="btn" onClick={() => fileInput.current?.click()}>
              {file ? file.name : "Elegir archivo…"}
            </button>
          </div>
          <label className="field">
            <span>Cosecha planificada</span>
            <input type="date" value={harvestOn} onChange={(e) => setHarvestOn(e.target.value)} />
          </label>
          <div className="field">
            <span>Mercados de destino</span>
            <MarketChecks value={markets} onChange={setMarkets} />
          </div>
          <label className="field">
            <span>Plaga de todo el programa <span className="muted">(opcional)</span></span>
            <input type="text" value={pest} placeholder="p. ej. oídio" onChange={(e) => setPest(e.target.value)} />
          </label>
          <button type="button" className="btn btn-primary" onClick={send} disabled={!ready || importer.isPending}>
            {importer.isPending ? "Leyendo…" : "Leer hoja"}
          </button>
        </div>
        <ErrorNote error={importer.error} />

        {result && s && (
          <>
            <div className={styles.importSummary}>
              <span className="stamp" data-tone="ok">{s.resueltas_por_nombre} por nombre</span>
              <span className="stamp" data-tone="info">{s.resueltas_por_ingrediente} por ingrediente</span>
              <span className="stamp" data-tone={s.necesitan_persona ? "risk" : "neutral"}>{s.necesitan_persona} sin resolver</span>
              <span className="stamp" data-tone={s.dosis_fuera_de_rango ? "risk" : "neutral"}>{s.dosis_fuera_de_rango} dosis fuera</span>
              <span className="stamp" data-tone={s.objetivo_no_registrado ? "risk" : "neutral"}>{s.objetivo_no_registrado} sin registro para el objetivo</span>
              <span className="stamp" data-tone="neutral">{s.fechas_aproximadas} fechas por etapa</span>
              <label className="check" style={{ marginLeft: "auto" }}>
                <input type="checkbox" checked={onlyReview} onChange={(e) => setOnlyReview(e.target.checked)} />
                <span>Solo lo que hay que revisar ({review.length} de {result.rows.length})</span>
              </label>
            </div>
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th className="num">N.°</th><th>En la hoja</th><th>Resolución</th><th>Producto</th><th>Fecha</th>
                    <th>Dosis</th><th>Objetivo</th><th>Notas</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={r.n} data-review={needsReview(r) || undefined} className={needsReview(r) ? styles.reviewRow : undefined}>
                      <td className="num">{r.n}</td>
                      <td>{rowText(r)}</td>
                      <td><Stamp map={ROW_STATUS} value={r.status} /></td>
                      <td>{r.trade_name ?? "—"}{r.candidates > 1 ? <div className="small muted">{r.candidates} productos posibles</div> : null}</td>
                      <td>{r.applied_on ? fmtDate(r.applied_on) : "—"}{r.approximate_date ? <div className="small muted">por etapa</div> : null}</td>
                      <td>
                        <Stamp map={DOSE_STATUS} value={r.dose?.status} />
                        {r.dose?.status === "outside_range" && r.dose.registered?.length
                          ? <div className="small muted">SIGIA: {r.dose.registered.slice(0, 2).join("; ")}</div> : null}
                      </td>
                      <td><Stamp map={TARGET_STATUS} value={r.target_check} /></td>
                      <td className="small">{[r.mismatch, ...r.notes].filter(Boolean).join("; ") || "—"}</td>
                    </tr>
                  ))}
                  {shown.length === 0 && (
                    <tr><td colSpan={8} className="muted">Ninguna fila necesita revisión.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
              <span className="small muted" style={{ marginRight: "auto" }}>
                Reemplaza los bloques y aplicaciones del programa actual; las filas sin resolver no se cargan.
              </span>
              <button type="button" className="btn" disabled={!result.program} onClick={() => onUse(result, false)}>
                Cargar en el editor
              </button>
              <button type="button" className="btn btn-primary" disabled={!result.program} onClick={() => onUse(result, true)}>
                Cargar y validar ({result.program?.applications.length ?? 0} aplicaciones)
              </button>
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}
