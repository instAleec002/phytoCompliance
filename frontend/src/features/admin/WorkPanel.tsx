"use client";

import { ErrorNote, Loading, Panel } from "@/components/ui/Page";
import { LotDetail, LotsTable } from "@/features/lab/LotViews";
import type { Draft } from "@/features/program/model";
import { useUserLot, useUserProgram, useUserWork, useUsers } from "@/lib/api/accounts";
import { useCrops } from "@/lib/api/hooks";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { MARKET_SHORT, cropLabel } from "@/lib/labels";

/** A saved program, read only: blocks and applications as the user left them. */
function ProgramReadOnly({ content }: { content: Draft }) {
  return (
    <div className="stack">
      <table className="table">
        <thead><tr><th>Bloque</th><th>Cosecha</th><th>Mercados</th></tr></thead>
        <tbody>
          {content.blocks.map((b) => (
            <tr key={b.key}><td className="mono">{b.key}</td><td className="mono">{fmtDate(b.harvest_on)}</td>
              <td className="mono">{b.markets.map((m) => MARKET_SHORT[m] ?? m).join(" · ")}</td></tr>
          ))}
        </tbody>
      </table>
      <table className="table">
        <thead><tr><th>Bloque</th><th>Producto</th><th>Plaga</th><th className="num">Carencia d</th><th>Fecha</th></tr></thead>
        <tbody>
          {content.applications.length === 0 && <tr><td colSpan={5} className="muted">Sin aplicaciones</td></tr>}
          {content.applications.map((a) => (
            <tr key={a.id}><td className="mono">{a.block}</td><td>{a.product_name || <span className="mono">{a.product_id}</span>}</td>
              <td className="mono small">{a.pest || "—"}</td><td className="num">{a.phi_days ?? "—"}</td>
              <td className="mono">{fmtDate(a.applied_on)}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function WorkPanel({
  userId,
  programId,
  lotId,
  onSelect,
}: {
  userId: number | null;
  programId: number | null;
  lotId: number | null;
  onSelect: (next: { u?: number | null; p?: number | null; l?: number | null }) => void;
}) {
  const users = useUsers();
  const crops = useCrops();
  const work = useUserWork(userId);
  const program = useUserProgram(userId, programId);
  const lot = useUserLot(userId, lotId);
  const user = users.data?.find((u) => u.id === userId);

  return (
    <div className="stack">
      <Panel>
        <div className="row" style={{ alignItems: "center" }}>
          <label className="field" style={{ width: 320 }}><span>Cuenta</span>
            <select value={userId ?? ""} onChange={(e) => onSelect({ u: e.target.value ? Number(e.target.value) : null, p: null, l: null })}>
              <option value="">— elija una cuenta —</option>
              {users.data?.map((u) => <option key={u.id} value={u.id}>{u.nombre} · {u.usuario}</option>)}
            </select></label>
          <span className="small muted" style={{ marginTop: 18 }}>Solo lectura: la administración ve el trabajo de cada cuenta, no lo modifica.</span>
        </div>
      </Panel>

      {userId === null ? <div className="empty">Elija una cuenta para ver sus programas y lotes.</div> : programId !== null ? (
        <Panel title={program.data ? `Programa · ${program.data.nombre}` : "Programa"}
          aside={<button type="button" className="btn" onClick={() => onSelect({ p: null })}>Volver</button>}>
          {program.isPending ? <Loading what="el programa" /> : program.isError ? <ErrorNote error={program.error} /> : (
            <div className="stack">
              <div className="small muted">{user?.nombre} · {cropLabel(crops.data, program.data.cultivo)} · actualizado {fmtDateTime(program.data.actualizado)}</div>
              <ProgramReadOnly content={program.data.contenido as unknown as Draft} />
            </div>
          )}
        </Panel>
      ) : lotId !== null ? (
        <div className="stack">
          <div><button type="button" className="btn" onClick={() => onSelect({ l: null })}>Volver</button></div>
          {lot.isPending ? <Loading what="el lote" /> : lot.isError ? <ErrorNote error={lot.error} /> : <LotDetail lot={lot.data} />}
        </div>
      ) : (
        <>
          <Panel title={`Programas de ${user?.nombre ?? ""}`} flush>
            {work.programs.isPending ? <Loading what="programas" /> : work.programs.isError ? <div className="panel-body"><ErrorNote error={work.programs.error} /></div> :
              work.programs.data.length === 0 ? <div className="empty">Sin programas guardados.</div> : (
                <table className="table">
                  <thead><tr><th>Nombre</th><th>Cultivo</th><th className="num">Bloques</th><th className="num">Aplicaciones</th><th>Actualizado</th><th /></tr></thead>
                  <tbody>
                    {work.programs.data.map((p) => (
                      <tr key={p.id}><td style={{ fontWeight: 500 }}>{p.nombre}</td><td>{cropLabel(crops.data, p.cultivo)}</td>
                        <td className="num">{p.bloques ?? "—"}</td><td className="num">{p.aplicaciones ?? "—"}</td>
                        <td className="mono small">{fmtDateTime(p.actualizado)}</td>
                        <td style={{ textAlign: "right" }}><button type="button" className="btn" onClick={() => onSelect({ p: p.id })}>Ver</button></td></tr>
                    ))}
                  </tbody>
                </table>
              )}
          </Panel>
          <Panel title={`Lotes de ${user?.nombre ?? ""}`} flush>
            {work.lots.isPending ? <Loading what="lotes" /> : work.lots.isError ? <div className="panel-body"><ErrorNote error={work.lots.error} /></div> : (
              <LotsTable lots={work.lots.data} onOpen={(id) => onSelect({ l: id })} />
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
