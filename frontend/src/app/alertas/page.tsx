"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ErrorNote, Loading, PageHead, Panel } from "@/components/ui/Page";
import { CropSelect, IngredientInput } from "@/components/ui/Pickers";
import { AlertsTable } from "@/features/alerts/AlertsTable";
import { PROGRAM_KEY, draftProblems, toProgramIn, type Draft } from "@/features/program/model";
import { useAlerts, useProgramAlerts } from "@/lib/api/hooks";
import { fmtDate } from "@/lib/format";
import { MARKETS, MARKET_LABEL } from "@/lib/labels";
import { useSettings } from "@/lib/settings";
import { readStored } from "@/lib/storage";

export default function AlertsPage() {
  const { evaluationDate, ready } = useSettings();
  const programAlerts = useProgramAlerts();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [ingredient, setIngredient] = useState("");
  const [crop, setCrop] = useState("");
  const [market, setMarket] = useState("EU");
  const single = useAlerts(ingredient, crop, market, evaluationDate);

  useEffect(() => {
    setDraft(readStored<Draft | null>(PROGRAM_KEY, null));
  }, []);

  const usable = draft && draft.applications.length > 0 && draftProblems(draft).length === 0;
  const { mutate } = programAlerts;
  useEffect(() => {
    if (ready && usable && draft) mutate({ program: toProgramIn(draft), day: evaluationDate });
  }, [ready, usable, draft, evaluationDate, mutate]);

  return (
    <div className="page">
      <PageHead
        index="05"
        title="Alertas de límites próximos"
        lead={<>Límites ya publicados que empiezan a aplicar después del <b className="mono">{fmtDate(evaluationDate)}</b>. Un cambio importa cuando aplica antes de la cosecha de un bloque que usa el ingrediente.</>}
      />
      <div className="stack">
        <Panel title="Programa guardado" aside={<Link prefetch={false} className="btn btn-quiet" href="/programa/">Abrir el programa</Link>} flush>
          {!draft || !draft.applications.length ? (
            <div className="empty">No hay un programa con aplicaciones en este dispositivo. Arme uno en Programa para ver sus alertas.</div>
          ) : !usable ? (
            <div className="empty">El programa tiene datos incompletos; complételo en Programa.</div>
          ) : programAlerts.isPending ? (
            <Loading what="las alertas del programa" />
          ) : programAlerts.isError ? (
            <div className="panel-body"><ErrorNote error={programAlerts.error} /></div>
          ) : (
            <AlertsTable alerts={programAlerts.data ?? []} />
          )}
        </Panel>

        <Panel title="Consulta por ingrediente">
          <div className="stack">
            <div className="row">
              <IngredientInput value={ingredient} onChange={setIngredient} crop={crop || undefined} />
              <div style={{ width: 200 }}><CropSelect value={crop} onChange={setCrop} /></div>
              <label className="field" style={{ width: 180 }}><span>Mercado</span>
                <select value={market} onChange={(e) => setMarket(e.target.value)}>
                  {MARKETS.map((m) => <option key={m} value={m}>{MARKET_LABEL[m]}</option>)}
                </select></label>
            </div>
            {ingredient.length > 1 && crop && (
              single.isPending ? <Loading what="alertas" /> : single.isError ? <ErrorNote error={single.error} /> : (
                <AlertsTable alerts={single.data ?? []} showBlocks={false} />
              )
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
