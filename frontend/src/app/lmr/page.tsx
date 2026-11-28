"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Loading, PageHead, Panel } from "@/components/ui/Page";
import { CropSelect, IngredientInput } from "@/components/ui/Pickers";
import { LimitMatrix } from "@/features/limits/LimitMatrix";
import styles from "@/features/limits/limits.module.css";
import { strictestMarket } from "@/features/limits/strictest";
import { VersionTrack } from "@/features/limits/VersionTrack";
import { useLimit, useVersions } from "@/lib/api/hooks";
import { fmtDate, fmtSnapshot, mgkg } from "@/lib/format";
import { MARKETS, MARKET_LABEL, MARKET_SHORT } from "@/lib/labels";
import { useSettings } from "@/lib/settings";

function useStrictest(ingredient: string, crop: string, day: string): string | null {
  // fixed number of hooks: one per market, sharing the cache with the matrix rows
  const eu = useLimit(ingredient, crop, "EU", day).data;
  const us = useLimit(ingredient, crop, "US", day).data;
  const cx = useLimit(ingredient, crop, "CODEX", day).data;
  return strictestMarket([eu, us, cx]);
}

function LimitsView() {
  const params = useSearchParams();
  const router = useRouter();
  const { evaluationDate } = useSettings();
  const [ingredient, setIngredient] = useState(params.get("i") ?? "");
  const [crop, setCrop] = useState(params.get("c") ?? "");
  const [market, setMarket] = useState("EU");

  useEffect(() => {
    const q = new URLSearchParams();
    if (ingredient) q.set("i", ingredient);
    if (crop) q.set("c", crop);
    router.replace(`/lmr/?${q.toString()}`, { scroll: false });
  }, [ingredient, crop, router]);

  const strictest = useStrictest(ingredient, crop, evaluationDate);
  const versions = useVersions(ingredient, crop, market);
  const ready = ingredient.length > 1 && !!crop;

  return (
    <div className="page">
      <PageHead
        index="02"
        title="Límites máximos de residuos"
        lead={<>El límite vigente el <b className="mono">{fmtDate(evaluationDate)}</b> en cada mercado, con la norma que lo fija y la instantánea de la fuente.</>}
      />
      <div className="stack">
        <Panel>
          <div className="row">
            <IngredientInput value={ingredient} onChange={setIngredient} crop={crop || undefined} />
            <div style={{ width: 200 }}>
              <CropSelect value={crop} onChange={setCrop} />
            </div>
          </div>
        </Panel>

        {!ready ? (
          <div className="empty">Escriba un ingrediente activo (nombre ISO o como figura en SIGIA) y elija el cultivo.</div>
        ) : (
          <>
            <Panel title="Comparación por mercado" aside={<span className="small muted">Elija un mercado para ver su historial</span>} flush>
              <LimitMatrix ingredient={ingredient} crop={crop} day={evaluationDate} selected={market} onSelect={setMarket}
                strictestMarket={strictest} />
            </Panel>

            <Panel
              title={`Historial · ${MARKET_LABEL[market]}`}
              aside={
                <div className={styles.tabs} role="tablist" aria-label="Mercado del historial">
                  {MARKETS.map((m) => (
                    <button key={m} type="button" role="tab" className={styles.tab} aria-selected={market === m}
                      onClick={() => setMarket(m)}>
                      {MARKET_SHORT[m]}
                    </button>
                  ))}
                </div>
              }
            >
              {versions.isPending ? (
                <Loading what="versiones" />
              ) : versions.isError ? (
                <div className="notice" data-tone="blocking">{versions.error.message}</div>
              ) : (
                <div className="stack">
                  <VersionTrack versions={versions.data} evaluationDate={evaluationDate} />
                  <div className="small muted">
                    Intenso: vigente en la fecha de evaluación · azul: aprobada, aún no aplica · gris: reemplazada.
                    {market !== "EU" && " Este mercado solo publica el estado vigente; su historial empieza en la instantánea."}
                  </div>
                  {versions.data.length > 0 && (
                    <div className="table-scroll" style={{ maxHeight: 320 }}>
                      <table className="table">
                        <thead>
                          <tr>
                            <th className="num">LMR mg/kg</th>
                            <th>Desde</th>
                            <th>Hasta</th>
                            <th>Residuo</th>
                            <th>Norma</th>
                            <th>Instantánea</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[...versions.data].reverse().map((v, i) => (
                            <tr key={i}>
                              <td className="num">{v.no_mrl_required ? "exento" : v.value_mg_kg === null ? v.value_text || "—" : mgkg(v.value_mg_kg)}</td>
                              <td className="mono">{fmtDate(v.applies_from)}</td>
                              <td className="mono">{v.valid_until ? fmtDate(v.valid_until) : <span className="muted">vigente</span>}</td>
                              <td className="small">{v.residue}</td>
                              <td className="cite">{v.regulation}</td>
                              <td className="cite">{fmtSnapshot(v.snapshot)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </Panel>
          </>
        )}
      </div>
    </div>
  );
}

export default function LimitsPage() {
  return (
    <Suspense fallback={<div className="page"><Loading what="la página" /></div>}>
      <LimitsView />
    </Suspense>
  );
}
