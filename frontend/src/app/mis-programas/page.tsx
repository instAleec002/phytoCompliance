"use client";

import { useRouter } from "next/navigation";

import { ErrorNote, Loading, PageHead, Panel } from "@/components/ui/Page";
import { PROGRAM_KEY, type Draft } from "@/features/program/model";
import { useDeleteProgram, useLoadProgram, useMyPrograms, useSaveProgram } from "@/lib/api/accounts";
import { useCrops } from "@/lib/api/hooks";
import { fmtDateTime } from "@/lib/format";
import { cropLabel } from "@/lib/labels";
import { writeStored } from "@/lib/storage";

export default function MyProgramsPage() {
  const router = useRouter();
  const programs = useMyPrograms();
  const crops = useCrops();
  const load = useLoadProgram();
  const save = useSaveProgram();
  const remove = useDeleteProgram();

  const open = (id: number) =>
    load.mutate(id, {
      onSuccess: (p) => {
        // the editor works on the local draft; it remembers which saved program it came from
        writeStored<Draft>(PROGRAM_KEY, { ...(p.contenido as unknown as Draft), savedId: p.id, savedName: p.nombre });
        router.push("/programa/");
      },
    });

  const duplicate = (id: number) =>
    load.mutate(id, {
      onSuccess: (p) => save.mutate({ id: null, body: { nombre: `${p.nombre} (copia)`, cultivo: p.cultivo, contenido: p.contenido } }),
    });

  const rename = (id: number, current: string) => {
    const name = window.prompt("Nuevo nombre del programa", current)?.trim();
    if (!name || name === current) return;
    load.mutate(id, { onSuccess: (p) => save.mutate({ id, body: { nombre: name, cultivo: p.cultivo, contenido: p.contenido } }) });
  };

  return (
    <div className="page">
      <PageHead index="06" title="Mis programas"
        lead="Programas guardados en su cuenta: disponibles en la web y en la aplicación de escritorio. Abrir uno lo carga en el editor de Programa." />
      <Panel flush>
        <ErrorNote error={load.error ?? save.error ?? remove.error} />
        {programs.isPending ? <Loading what="programas" /> : programs.isError ? <div className="panel-body"><ErrorNote error={programs.error} /></div> :
          programs.data.length === 0 ? (
            <div className="empty">Aún no guardó programas. En Programa use «Guardar en mi cuenta».</div>
          ) : (
            <table className="table">
              <thead>
                <tr><th>Nombre</th><th>Cultivo</th><th className="num">Bloques</th><th className="num">Aplicaciones</th><th>Actualizado</th><th /></tr>
              </thead>
              <tbody>
                {programs.data.map((p) => (
                  <tr key={p.id}>
                    <td style={{ fontWeight: 500 }}>{p.nombre}</td>
                    <td>{cropLabel(crops.data, p.cultivo)}</td>
                    <td className="num">{p.bloques ?? "—"}</td>
                    <td className="num">{p.aplicaciones ?? "—"}</td>
                    <td className="mono small">{fmtDateTime(p.actualizado)}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button type="button" className="btn" onClick={() => open(p.id)} disabled={load.isPending}>Abrir</button>{" "}
                      <button type="button" className="btn btn-quiet" onClick={() => rename(p.id, p.nombre)}>Renombrar</button>
                      <button type="button" className="btn btn-quiet" onClick={() => duplicate(p.id)}>Duplicar</button>
                      <button type="button" className="btn btn-quiet"
                        onClick={() => window.confirm(`¿Eliminar «${p.nombre}»? No se puede deshacer.`) && remove.mutate(p.id)}>Eliminar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </Panel>
    </div>
  );
}
