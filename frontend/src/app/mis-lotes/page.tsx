"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ErrorNote, Loading, PageHead, Panel } from "@/components/ui/Page";
import { LotDetail, LotsTable } from "@/features/lab/LotViews";
import { useMyLot, useMyLots } from "@/lib/api/accounts";

function MyLots() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id") ? Number(params.get("id")) : null;
  const lots = useMyLots();
  const lot = useMyLot(id);

  return (
    <div className="page">
      <PageHead index="07" title={id ? `Lote ${lot.data?.codigo ?? ""}` : "Mis lotes"}
        lead="Cada evaluación de Laboratorio queda guardada con lo que se ingresó y el resultado obtenido."
        actions={id ? <button type="button" className="btn" onClick={() => router.push("/mis-lotes/")}>Volver a la lista</button> : undefined} />
      {id ? (
        lot.isPending ? <Loading what="el lote" /> : lot.isError ? <ErrorNote error={lot.error} /> : <LotDetail lot={lot.data} />
      ) : (
        <Panel flush>
          {lots.isPending ? <Loading what="lotes" /> : lots.isError ? <div className="panel-body"><ErrorNote error={lots.error} /></div> : (
            <LotsTable lots={lots.data} onOpen={(lid) => router.push(`/mis-lotes/?id=${lid}`)} />
          )}
        </Panel>
      )}
    </div>
  );
}

export default function MyLotsPage() {
  return (
    <Suspense fallback={null}>
      <MyLots />
    </Suspense>
  );
}
