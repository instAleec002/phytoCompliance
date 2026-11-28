"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ErrorNote, PageHead, Panel } from "@/components/ui/Page";
import { CropSelect, IngredientInput } from "@/components/ui/Pickers";
import styles from "@/features/lab/lab.module.css";
import { LabResults } from "@/features/lab/LabResults";
import { parsePastedMeasurements } from "@/features/lab/paste";
import { useLab, useProfiles } from "@/lib/api/hooks";
import { MARKETS, MARKET_LABEL } from "@/lib/labels";
import { useSettings } from "@/lib/settings";

interface Row {
  id: number;
  ingredient: string;
  value: string;
}

let seq = 0;
const row = (ingredient = "", value = ""): Row => ({ id: ++seq, ingredient, value });

export default function LabPage() {
  const { evaluationDate } = useSettings();
  const profiles = useProfiles();
  const lab = useLab();
  const [lot, setLot] = useState("");
  const [crop, setCrop] = useState("");
  const [market, setMarket] = useState("EU");
  const [sampledOn, setSampledOn] = useState(evaluationDate);
  const [profile, setProfile] = useState("lidl_2025");
  const [rows, setRows] = useState<Row[]>([row(), row()]);
  const [paste, setPaste] = useState("");
  const [pasteNote, setPasteNote] = useState<string | null>(null);

  useEffect(() => setSampledOn(evaluationDate), [evaluationDate]);

  const valid = rows.filter((r) => r.ingredient && /^\d*[.,]?\d+$/.test(r.value));
  const canRun = !!crop && valid.length > 0;
  const chosenProfile = profiles.data?.find((p) => p.key === profile) ?? null;

  const run = () =>
    lab.mutate({
      lot: lot || "sin código",
      crop,
      market,
      sampled_on: sampledOn,
      profile: profile || null,
      measurements: valid.map((r) => ({ ingredient: r.ingredient, value_mg_kg: Number(r.value.replace(",", ".")) })),
    });

  const applyPaste = () => {
    const { rows: pasted, skipped } = parsePastedMeasurements(paste);
    if (pasted.length) setRows([...rows.filter((r) => r.ingredient || r.value), ...pasted.map((p) => row(p.ingredient, p.value))]);
    setPasteNote(`${pasted.length} resultados agregados${skipped.length ? `; ${skipped.length} líneas sin valor numérico se omitieron (ND, <LOQ…)` : ""}.`);
    setPaste("");
  };

  return (
    <div className="page">
      <PageHead
        index="04"
        title="Resultados de laboratorio"
        lead="Cada residuo medido contra el LMR vigente el día del muestreo y, si se elige, contra el perfil del comprador: fracción del LMR, suma, número de residuos y exposición aguda frente a la ARfD."
      />
      {/* input sheet on top, report at full width below: the report has seven columns and needs the room */}
      <div className="stack">
        <div className="grid-2 no-print" style={{ alignItems: "start" }}>
          <Panel title="Lote">
            <div className="stack">
              <div className="grid-2">
                <label className="field"><span>Código del lote</span>
                  <input className="mono" value={lot} onChange={(e) => setLot(e.target.value)} placeholder="L-2026-114" /></label>
                <label className="field"><span>Fecha de muestreo</span>
                  <input type="date" value={sampledOn} onChange={(e) => setSampledOn(e.target.value)} /></label>
                <CropSelect value={crop} onChange={setCrop} />
                <label className="field"><span>Mercado</span>
                  <select value={market} onChange={(e) => setMarket(e.target.value)}>
                    {MARKETS.map((m) => <option key={m} value={m}>{MARKET_LABEL[m]}</option>)}
                  </select></label>
              </div>
              <label className="field"><span>Perfil del comprador</span>
                <select value={profile} onChange={(e) => setProfile(e.target.value)}>
                  <option value="">Solo límites legales</option>
                  {profiles.data?.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
                </select></label>
              {chosenProfile && (
                <div className="small muted mono">
                  ≤ {Math.round((chosenProfile.max_fraction_of_mrl_per_substance ?? 1) * 100)} % LMR por sustancia
                  {chosenProfile.max_sum_of_mrl_fractions != null && ` · suma ≤ ${Math.round(chosenProfile.max_sum_of_mrl_fractions * 100)} %`}
                  {chosenProfile.max_number_of_residues != null && ` · ≤ ${chosenProfile.max_number_of_residues} residuos`}
                  {chosenProfile.max_fraction_of_arfd != null && ` · ARfD ≤ ${Math.round(chosenProfile.max_fraction_of_arfd * 100)} %`}
                </div>
              )}
            </div>
          </Panel>

          <Panel title="Residuos" aside={<button type="button" className="btn btn-quiet" onClick={() => setRows([...rows, row()])}>+ Residuo</button>}>
            <div className="stack">
              {rows.map((r) => (
                <div key={r.id} className={styles.measure}>
                  <IngredientInput value={r.ingredient} crop={crop} label="Ingrediente" width="100%"
                    onChange={(v) => setRows(rows.map((x) => (x.id === r.id ? { ...x, ingredient: v } : x)))} />
                  <label className="field"><span>mg/kg</span>
                    <input inputMode="decimal" value={r.value} aria-invalid={!!r.value && !/^\d*[.,]?\d+$/.test(r.value)}
                      onChange={(e) => setRows(rows.map((x) => (x.id === r.id ? { ...x, value: e.target.value } : x)))} /></label>
                  <button type="button" className="btn btn-quiet" aria-label="Quitar el residuo"
                    onClick={() => setRows(rows.length > 1 ? rows.filter((x) => x.id !== r.id) : [row()])}>×</button>
                </div>
              ))}
              <details>
                <summary>Pegar desde el informe</summary>
                <div className="stack" style={{ marginTop: 8 }}>
                  <textarea rows={5} value={paste} onChange={(e) => setPaste(e.target.value)}
                    placeholder={"pyraclostrobin;0,12\nfludioxonil\t0.30\nboscalid;ND"} />
                  <div className="row"><button type="button" className="btn" onClick={applyPaste} disabled={!paste.trim()}>Agregar</button>
                    {pasteNote && <span className="small muted">{pasteNote}</span>}</div>
                </div>
              </details>
              <button type="button" className="btn btn-primary" onClick={run} disabled={!canRun || lab.isPending}>
                {lab.isPending ? "Evaluando…" : `Evaluar ${valid.length} residuo${valid.length === 1 ? "" : "s"}`}
              </button>
            </div>
          </Panel>
        </div>

        <div className="stack">
          <ErrorNote error={lab.error} />
          {lab.data?.lot_id && (
            <div className="notice no-print" data-tone="ok">
              Evaluación guardada en <Link prefetch={false} href={`/mis-lotes/?id=${lab.data.lot_id}`}>Mis lotes</Link>.
            </div>
          )}
          {lab.data ? (
            <LabResults report={lab.data} profile={chosenProfile} />
          ) : (
            <div className="empty">Ingrese los residuos detectados y evalúe el lote. Los no detectados no se ingresan.</div>
          )}
        </div>
      </div>
    </div>
  );
}
