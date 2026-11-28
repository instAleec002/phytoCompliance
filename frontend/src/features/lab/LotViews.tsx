"use client";

import { VerdictStamp } from "@/components/ui/Stamp";
import type { Schemas } from "@/lib/api/client";
import { useCrops, useProfiles } from "@/lib/api/hooks";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { MARKET_SHORT, cropLabel } from "@/lib/labels";

import { LabResults } from "./LabResults";

// A list of evaluated lots and the saved result of one; used in Mis lotes and, read only, in Administración.

export function LotsTable({ lots, onOpen }: { lots: Schemas["LotSummaryOut"][]; onOpen: (id: number) => void }) {
  const crops = useCrops();
  if (!lots.length) return <div className="empty">Sin lotes evaluados.</div>;
  return (
    <table className="table">
      <thead>
        <tr><th>Lote</th><th>Resultado</th><th>Cultivo</th><th>Mercado</th><th>Muestreo</th><th>Perfil</th><th className="num">Residuos</th><th>Evaluado</th><th /></tr>
      </thead>
      <tbody>
        {lots.map((l) => (
          <tr key={l.id}>
            <td className="mono" style={{ fontWeight: 500 }}>{l.codigo}</td>
            <td><VerdictStamp verdict={l.veredicto} /></td>
            <td>{cropLabel(crops.data, l.cultivo)}</td>
            <td className="mono">{MARKET_SHORT[l.mercado] ?? l.mercado}</td>
            <td className="mono">{fmtDate(l.muestreo)}</td>
            <td className="small">{l.perfil ?? "solo legal"}</td>
            <td className="num">{l.residuos ?? "—"}</td>
            <td className="mono small">{fmtDateTime(l.creado)}</td>
            <td style={{ textAlign: "right" }}><button type="button" className="btn" onClick={() => onOpen(l.id)}>Ver</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function LotDetail({ lot }: { lot: Schemas["LotOut"] }) {
  const profiles = useProfiles();
  const profile = profiles.data?.find((p) => p.key === lot.perfil) ?? null;
  return (
    <div className="stack">
      <div className="notice" data-tone="info">
        Resultado guardado el {fmtDateTime(lot.creado)}: refleja los límites vigentes el {fmtDate(lot.muestreo)} con las instantáneas de ese momento.
      </div>
      <LabResults report={lot.resultado as unknown as Schemas["LabReportOut"]} profile={profile} />
    </div>
  );
}
