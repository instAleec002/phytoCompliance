"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ErrorNote, PageHead, Panel } from "@/components/ui/Page";
import { CropSelect } from "@/components/ui/Pickers";
import { applicationsToCsv, parseApplicationsCsv } from "@/features/program/csv";
import { FieldSheetImport } from "@/features/program/FieldSheetImport";
import { importToDraft, rowsToReview, type ImportResult } from "@/features/program/fieldSheet";
import { PROGRAM_KEY, draftProblems, emptyDraft, toProgramIn, type Draft } from "@/features/program/model";
import { ProgramEditor } from "@/features/program/ProgramEditor";
import styles from "@/features/program/program.module.css";
import { ProgramResults } from "@/features/program/ProgramResults";
import { useSaveProgram } from "@/lib/api/accounts";
import { useProgramAlerts, useValidate } from "@/lib/api/hooks";
import { fmtDate, todayISO } from "@/lib/format";
import { downloadCsv, downloadText } from "@/lib/download";
import { useSettings } from "@/lib/settings";
import { useStoredState } from "@/lib/storage";

export default function ProgramPage() {
  const { evaluationDate } = useSettings();
  const [draft, setDraft] = useStoredState<Draft>(PROGRAM_KEY, emptyDraft(todayISO()));
  const validate = useValidate();
  const alerts = useProgramAlerts();
  const saveRemote = useSaveProgram();
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [importNote, setImportNote] = useState<string[]>([]);
  const [showSheet, setShowSheet] = useState(false);
  const csvInput = useRef<HTMLInputElement>(null);
  const jsonInput = useRef<HTMLInputElement>(null);
  const problems = draftProblems(draft);

  const run = useCallback(() => {
    if (draftProblems(draft).length) return;
    const program = toProgramIn(draft);
    validate.mutate(program);
    alerts.mutate({ program, day: evaluationDate });
  }, [draft, evaluationDate, validate, alerts]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        run();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [run]);

  // a result describes the program it was computed for; editing makes it stale
  const [validatedFor, setValidatedFor] = useState<string | null>(null);
  const fingerprint = JSON.stringify(toProgramIn(draft)) + evaluationDate;
  useEffect(() => {
    if (validate.isSuccess) setValidatedFor(fingerprint);
  }, [validate.data]);
  const stale = validate.isSuccess && validatedFor !== null && validatedFor !== fingerprint;

  const saveToAccount = () => {
    const name = draft.savedName ?? window.prompt("Nombre del programa en su cuenta", `Programa ${draft.crop || ""} ${todayISO()}`)?.trim();
    if (!name) return;
    const { savedId, savedName, ...content } = draft;
    void savedName;
    saveRemote.mutate(
      { id: savedId ?? null, body: { nombre: name, cultivo: draft.crop, contenido: content as unknown as Record<string, unknown> } },
      {
        onSuccess: (p) => {
          setDraft((d) => ({ ...d, savedId: p.id, savedName: p.nombre }));
          setSavedAt(p.actualizado);
        },
      },
    );
  };

  const onCsv = async (file: File) => {
    const { applications, errors } = parseApplicationsCsv(await file.text());
    const missing = [...new Set(applications.map((a) => a.block))].filter((k) => !draft.blocks.some((b) => b.key === k));
    const last = draft.blocks.at(-1);
    setDraft({
      ...draft,
      blocks: [...draft.blocks, ...missing.map((key) => ({ key, harvest_on: last?.harvest_on ?? "", markets: last?.markets ?? ["EU"] }))],
      applications: [...draft.applications, ...applications],
    });
    setImportNote([
      `${applications.length} aplicaciones importadas de ${file.name}.`,
      ...(missing.length ? [`Bloques creados: ${missing.join(", ")}; revise su fecha de cosecha y mercados.`] : []),
      ...errors,
    ]);
  };

  const onSheet = (result: ImportResult, validateNow: boolean) => {
    if (draft.applications.length && !window.confirm("¿Reemplazar los bloques y aplicaciones del programa actual por los de la hoja?")) return;
    const next = importToDraft(result, draft.crop, draft);
    setDraft(next);
    setShowSheet(false);
    const review = rowsToReview(result.rows).length;
    const pending = result.rows.filter((r) => r.status === "needs_review").length;
    setImportNote([
      `${next.applications.length} aplicaciones cargadas de la hoja de campo.`,
      ...(pending ? [`${pending} filas sin resolver no se cargaron; agréguelas a mano si corresponde.`] : []),
      ...(review ? [`${review} filas tenían algo que revisar (fecha por etapa, dosis u objetivo).`] : []),
    ]);
    if (validateNow && next.applications.length && !draftProblems(next).length) {
      const program = toProgramIn(next);
      validate.mutate(program);
      alerts.mutate({ program, day: evaluationDate });
    }
  };

  const onJson = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text()) as Draft;
      if (!Array.isArray(parsed.blocks) || !Array.isArray(parsed.applications)) throw new Error();
      setDraft(parsed);
      setImportNote([`Programa cargado de ${file.name}.`]);
    } catch {
      setImportNote([`${file.name} no es un programa guardado por esta aplicación.`]);
    }
  };

  return (
    <div className="page">
      <PageHead
        index="03"
        title="Validación del programa"
        lead="Registro en SENASA, carencia frente a la cosecha, límite de cada ingrediente en cada mercado el día de la cosecha y rotación de modos de acción, por bloque."
        actions={
          <div className={`${styles.toolbar} no-print`}>
            <input ref={csvInput} type="file" accept=".csv,text/csv,.txt" hidden
              onChange={(e) => e.target.files?.[0] && onCsv(e.target.files[0]).finally(() => (e.target.value = ""))} />
            <input ref={jsonInput} type="file" accept=".json,application/json" hidden
              onChange={(e) => e.target.files?.[0] && onJson(e.target.files[0]).finally(() => (e.target.value = ""))} />
            <button type="button" className="btn btn-primary" onClick={() => setShowSheet(true)} disabled={showSheet}>Hoja de campo</button>
            <button type="button" className="btn" onClick={() => csvInput.current?.click()}>Importar CSV</button>
            <button type="button" className="btn" disabled={!draft.applications.length}
              onClick={() => downloadCsv("aplicaciones.csv", applicationsToCsv(draft.applications))}>Exportar CSV</button>
            <button type="button" className="btn" onClick={() => jsonInput.current?.click()}>Abrir archivo</button>
            <button type="button" className="btn"
              onClick={() => downloadText(`programa-${draft.crop || "cultivo"}-${todayISO()}.json`, JSON.stringify(draft, null, 1), "application/json")}>Descargar</button>
            <button type="button" className="btn btn-quiet"
              onClick={() => { if (window.confirm("¿Empezar un programa nuevo? Se pierde lo no guardado.")) { setDraft(emptyDraft(evaluationDate, draft.crop)); validate.reset(); alerts.reset(); setSavedAt(null); } }}>Nuevo</button>
          </div>
        }
      />

      <div className="stack">
        {showSheet && (
          <div className="no-print">
            <FieldSheetImport crop={draft.crop} harvest={draft.blocks[0]?.harvest_on ?? ""} onUse={onSheet}
              onClose={() => setShowSheet(false)} />
          </div>
        )}
        <div className="no-print">
        <Panel
          title={
            <div className="row" style={{ alignItems: "center" }}>
              <h2>Programa</h2>
              <div style={{ width: 200 }}>
                <CropSelect value={draft.crop} onChange={(crop) => setDraft((d) => ({ ...d, crop }))} label="" />
              </div>
            </div>
          }
          aside={
            <div className="row" style={{ alignItems: "center" }}>
              <span className="small muted">
                {draft.savedName ? <>Cuenta: <b>{draft.savedName}</b>{savedAt ? " · guardado" : ""}</> : "Borrador en este dispositivo"}
              </span>
              <button type="button" className="btn" onClick={saveToAccount} disabled={!draft.crop || saveRemote.isPending}>
                {saveRemote.isPending ? "Guardando…" : draft.savedId ? "Guardar cambios" : "Guardar en mi cuenta"}</button>
              <button type="button" className="btn btn-primary" onClick={run} disabled={problems.length > 0 || validate.isPending}>
                {validate.isPending ? "Validando…" : "Validar"} <kbd>Ctrl ↵</kbd>
              </button>
            </div>
          }
        >
          <div className="stack">
            {importNote.length > 0 && (
              <div className="notice" data-tone="info">
                {importNote.map((n, i) => <div key={i}>{n}</div>)}
              </div>
            )}
            <ProgramEditor draft={draft} onChange={setDraft} today={evaluationDate} />
            {problems.length > 0 && draft.applications.length > 0 && (
              <div className="notice" data-tone="risk">
                <ul className={styles.problems}>
                  {problems.map((p, i) => <li key={i}><b>{p.where}:</b> {p.message}</li>)}
                </ul>
              </div>
            )}
          </div>
        </Panel>
        </div>

        <ErrorNote error={validate.error ?? saveRemote.error} />
        {stale && (
          <div className="notice" data-tone="risk">
            El programa o la fecha cambiaron desde la última validación ({fmtDate(evaluationDate)}). Vuelva a validar.
          </div>
        )}
        {validate.data && (
          <ProgramResults report={validate.data} draft={draft} alerts={alerts.data} evaluationDate={evaluationDate} />
        )}
      </div>
    </div>
  );
}
