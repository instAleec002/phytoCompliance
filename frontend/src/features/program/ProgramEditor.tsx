"use client";

import { MarketChecks } from "@/components/ui/Pickers";
import { usePests, useProducts } from "@/lib/api/hooks";
import { addDays } from "@/lib/format";

import { newId, type Draft, type DraftApplication, type DraftBlock } from "./model";
import styles from "./program.module.css";

function ApplicationRow({
  app,
  crop,
  blocks,
  index,
  onChange,
  onRemove,
}: {
  app: DraftApplication;
  crop: string;
  blocks: DraftBlock[];
  index: number;
  onChange: (a: DraftApplication) => void;
  onRemove: () => void;
}) {
  const pests = usePests(crop || null);
  const products = useProducts(crop || null, app.pest || null);
  const chosen = products.data?.find((p) => p.product_id === app.product_id);
  const phi = chosen
    ? chosen.preharvest_not_applicable
      ? "no aplica"
      : chosen.preharvest_interval_days ?? "sin dato"
    : app.phi_days ?? "—";

  return (
    <tr>
      <td className="mono muted small">{String(index + 1).padStart(2, "0")}</td>
      <td style={{ width: 90 }}>
        <select value={app.block} onChange={(e) => onChange({ ...app, block: e.target.value })} aria-label="Bloque">
          {!blocks.some((b) => b.key === app.block) && <option value={app.block}>{app.block || "—"}</option>}
          {blocks.map((b) => (
            <option key={b.key} value={b.key}>{b.key}</option>
          ))}
        </select>
      </td>
      <td style={{ minWidth: 200 }}>
        <select
          value={app.pest}
          aria-label="Plaga u otro uso"
          onChange={(e) => onChange({ ...app, pest: e.target.value, product_id: "", product_name: "", phi_days: null })}
          disabled={!pests.data}
        >
          <option value="">— plaga —</option>
          {pests.data?.map((p) => (
            <option key={p.key} value={p.key}>
              {p.other_use ? "Otro uso · " : ""}
              {p.common_name || p.scientific_name || p.key}
            </option>
          ))}
        </select>
      </td>
      <td style={{ minWidth: 240 }}>
        {app.pest ? (
          <select
            value={app.product_id}
            aria-label="Producto"
            disabled={!products.data}
            onChange={(e) => {
              const p = products.data?.find((x) => x.product_id === e.target.value);
              onChange({
                ...app,
                product_id: e.target.value,
                product_name: p?.trade_name ?? "",
                phi_days: p?.preharvest_not_applicable ? 0 : p?.preharvest_interval_days ?? null,
              });
            }}
          >
            <option value="">{products.isPending ? "Cargando…" : "— producto —"}</option>
            {!chosen && app.product_id && <option value={app.product_id}>{app.product_name || app.product_id}</option>}
            {products.data?.map((p) => (
              <option key={p.product_id} value={p.product_id}>
                {p.trade_name} · {p.ingredients.join(" + ")}
              </option>
            ))}
          </select>
        ) : (
          <input
            className="mono"
            value={app.product_id}
            placeholder="ID SIGIA, o elija la plaga"
            aria-label="Identificador del producto en SIGIA"
            onChange={(e) => onChange({ ...app, product_id: e.target.value.trim(), product_name: "" })}
          />
        )}
      </td>
      <td className="num" style={{ width: 80 }}>{phi}</td>
      <td style={{ width: 150 }}>
        <input type="date" value={app.applied_on} aria-label="Fecha de aplicación"
          onChange={(e) => onChange({ ...app, applied_on: e.target.value })} />
      </td>
      <td style={{ width: 40 }}>
        <button type="button" className="btn btn-quiet" onClick={onRemove} aria-label={`Quitar la aplicación ${index + 1}`}>×</button>
      </td>
    </tr>
  );
}

export function ProgramEditor({ draft, onChange, today }: { draft: Draft; onChange: (d: Draft) => void; today: string }) {
  const setBlock = (i: number, b: DraftBlock) => {
    const old = draft.blocks[i]!;
    const blocks = draft.blocks.map((x, j) => (j === i ? b : x));
    // renaming a block carries its applications along
    const applications = old.key !== b.key
      ? draft.applications.map((a) => (a.block === old.key ? { ...a, block: b.key } : a))
      : draft.applications;
    onChange({ ...draft, blocks, applications });
  };
  const addBlock = () => {
    const n = draft.blocks.length + 1;
    let key = `A${n}`;
    while (draft.blocks.some((b) => b.key === key)) key = `${key}'`;
    const last = draft.blocks.at(-1);
    onChange({ ...draft, blocks: [...draft.blocks, { key, harvest_on: last?.harvest_on ?? addDays(today, 30), markets: last?.markets ?? ["EU"] }] });
  };
  const addApplication = () => {
    const last = draft.applications.at(-1);
    onChange({
      ...draft,
      applications: [
        ...draft.applications,
        { id: newId(), block: last?.block ?? draft.blocks[0]?.key ?? "", pest: last?.pest ?? "", product_id: "", product_name: "",
          phi_days: null, applied_on: last ? addDays(last.applied_on, 7) : today },
      ],
    });
  };

  return (
    <div className="stack">
      <section>
        <div className={styles.subhead}>
          <span className="label">Bloques · {draft.blocks.length}</span>
          <button type="button" className="btn btn-quiet" onClick={addBlock}>+ Bloque</button>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 110 }}>Clave</th>
              <th style={{ width: 160 }}>Cosecha planificada</th>
              <th>Mercados de destino</th>
              <th style={{ width: 40 }} />
            </tr>
          </thead>
          <tbody>
            {draft.blocks.map((b, i) => (
              <tr key={i}>
                <td>
                  <input className="mono" value={b.key} aria-label="Clave del bloque" aria-invalid={!b.key.trim()}
                    onChange={(e) => setBlock(i, { ...b, key: e.target.value })} />
                </td>
                <td>
                  <input type="date" value={b.harvest_on} aria-label="Fecha de cosecha" aria-invalid={!b.harvest_on}
                    onChange={(e) => setBlock(i, { ...b, harvest_on: e.target.value })} />
                </td>
                <td><MarketChecks value={b.markets} onChange={(markets) => setBlock(i, { ...b, markets })} /></td>
                <td>
                  <button type="button" className="btn btn-quiet" aria-label={`Quitar el bloque ${b.key}`}
                    disabled={draft.blocks.length === 1}
                    onClick={() => onChange({ ...draft, blocks: draft.blocks.filter((_, j) => j !== i) })}>×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <div className={styles.subhead}>
          <span className="label">Aplicaciones · {draft.applications.length}</span>
          <button type="button" className="btn btn-quiet" onClick={addApplication} disabled={!draft.blocks.length}>+ Aplicación</button>
        </div>
        {draft.applications.length === 0 ? (
          <div className="empty">Sin aplicaciones. Agréguelas una por una o importe un CSV (bloque;plaga;producto;fecha).</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 32 }}>#</th>
                <th>Bloque</th>
                <th>Plaga u otro uso</th>
                <th>Producto registrado</th>
                <th className="num">Carencia d</th>
                <th>Fecha</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {draft.applications.map((a, i) => (
                <ApplicationRow key={a.id} app={a} crop={draft.crop} blocks={draft.blocks} index={i}
                  onChange={(next) => onChange({ ...draft, applications: draft.applications.map((x) => (x.id === a.id ? next : x)) })}
                  onRemove={() => onChange({ ...draft, applications: draft.applications.filter((x) => x.id !== a.id) })} />
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
