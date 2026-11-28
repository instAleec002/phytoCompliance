"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { ErrorNote, Loading, PageHead, Panel } from "@/components/ui/Page";
import { CropSelect } from "@/components/ui/Pickers";
import { Stamp } from "@/components/ui/Stamp";
import {
  NO_FILTER,
  filterProducts,
  isBiological,
  productName,
  productsToCsv,
  type ProductFilter,
  type SortKey,
} from "@/features/registry/products";
import { usePests, useProducts } from "@/lib/api/hooks";
import { fmtSnapshot, mgkg, todayISO } from "@/lib/format";
import { downloadCsv } from "@/lib/download";

function RegistryView() {
  const params = useSearchParams();
  const router = useRouter();
  const [crop, setCrop] = useState(params.get("c") ?? "");
  const [pest, setPest] = useState<string | null>(params.get("p"));
  const [filter, setFilter] = useState("");
  const [products_, setProducts] = useState<ProductFilter>(NO_FILTER);
  const [sort, setSort] = useState<SortKey>("name");
  const pests = usePests(crop || null);
  const products = useProducts(crop || null, pest);

  // crop and pest live in the URL, so a view can be shared and the assistant can link to it
  useEffect(() => {
    const q = new URLSearchParams();
    if (crop) q.set("c", crop);
    if (pest) q.set("p", pest);
    router.replace(`/registro/?${q.toString()}`, { scroll: false });
  }, [crop, pest, router]);

  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (pests.data ?? []).filter(
      (p) => !q || `${p.common_name ?? ""} ${p.scientific_name ?? ""}`.toLowerCase().includes(q),
    );
  }, [pests.data, filter]);
  const chosen = pests.data?.find((p) => p.key === pest);
  const list = useMemo(() => filterProducts(products.data ?? [], products_, sort), [products.data, products_, sort]);
  const filtered = products.data ? products.data.length - list.length : 0;
  const pestName = chosen ? (chosen.common_name || chosen.scientific_name || chosen.key) : "";

  return (
    <div className="page">
      <PageHead index="08" title="Registro de SENASA"
        lead="Plagas y otros usos del cultivo y los productos registrados para cada uno, con su carencia y sus ingredientes. Un ingrediente abre su límite por mercado." />
      <div className="split">
        <Panel
          title={<div style={{ width: 200 }}><CropSelect value={crop} onChange={(c) => { setCrop(c); setPest(null); }} label="" /></div>}
          aside={<span className="small muted mono">{pests.data ? `${pests.data.length} entradas` : ""}</span>}
          flush
        >
          <div className="panel-body" style={{ paddingBottom: 8 }}>
            <input type="search" placeholder="Filtrar plagas…" value={filter} onChange={(e) => setFilter(e.target.value)}
              style={{ width: "100%" }} aria-label="Filtrar plagas" />
          </div>
          {!crop ? <div className="empty">Elija un cultivo.</div> : pests.isPending ? <Loading what="plagas" /> : pests.isError ? <div className="panel-body"><ErrorNote error={pests.error} /></div> : (
            <div className="table-scroll" style={{ maxHeight: 640 }}>
              <table className="table">
                <thead><tr><th>Plaga u otro uso</th><th className="num">Productos</th></tr></thead>
                <tbody>
                  {shown.map((p) => (
                    <tr key={p.key} aria-selected={pest === p.key}>
                      <td style={pest === p.key ? { boxShadow: "inset 3px 0 0 var(--accent)" } : undefined}>
                        <button type="button" style={{ all: "unset", cursor: "pointer", display: "block", width: "100%" }}
                          onClick={() => { setPest(p.key); setProducts(NO_FILTER); }}>
                          <div>{p.other_use && <Stamp tone="neutral">otro uso</Stamp>} {p.common_name || "—"}</div>
                          <div className="small muted"><i>{p.scientific_name}</i></div>
                        </button>
                      </td>
                      <td className="num">{p.products}</td>
                    </tr>
                  ))}
                  {shown.length === 0 && <tr><td colSpan={2} className="muted">Ninguna plaga coincide con el filtro.</td></tr>}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title={pestName || "Productos"}
          aside={products.data ? (
            <span className="row" style={{ alignItems: "center", gap: 8 }}>
              <span className="small muted mono">
                {filtered ? `${list.length} de ${products.data.length} productos` : `${products.data.length} productos`}
              </span>
              <button type="button" className="btn btn-quiet" disabled={!list.length}
                onClick={() => downloadCsv(`registro-${crop}-${pest}-${todayISO()}.csv`, productsToCsv(list, crop, pestName))}>
                Exportar CSV
              </button>
            </span>
          ) : null} flush>
          {!pest ? <div className="empty">Elija una plaga o un otro uso.</div> : products.isPending ? <Loading what="productos" /> :
            products.isError ? <div className="panel-body"><ErrorNote error={products.error} /></div> : (
              <>
                <div className="panel-body" style={{ paddingBottom: 8 }}>
                  <div className="row" style={{ alignItems: "flex-end", flexWrap: "wrap", gap: 12 }}>
                    <label className="field" style={{ flex: "1 1 200px" }}>
                      <span>Producto o ingrediente</span>
                      <input type="search" value={products_.text} placeholder="p. ej. azufre"
                        onChange={(e) => setProducts({ ...products_, text: e.target.value })} />
                    </label>
                    <label className="field" style={{ width: 150 }}>
                      <span>Carencia máxima (días)</span>
                      <input type="number" min={0} max={365} value={products_.maxPhi ?? ""} placeholder="cualquiera"
                        onChange={(e) => setProducts({ ...products_, maxPhi: e.target.value === "" ? null : Math.max(0, Number(e.target.value)) })} />
                    </label>
                    <label className="field" style={{ width: 150 }}>
                      <span>Tipo</span>
                      <select value={products_.type} onChange={(e) => setProducts({ ...products_, type: e.target.value as ProductFilter["type"] })}>
                        <option value="all">Todos</option>
                        <option value="chemical">Químicos</option>
                        <option value="biological">Biológicos</option>
                      </select>
                    </label>
                    {(products_.text || products_.maxPhi !== null || products_.type !== "all") && (
                      <button type="button" className="btn btn-quiet" onClick={() => setProducts(NO_FILTER)}>Quitar filtros</button>
                    )}
                  </div>
                  {products_.maxPhi !== null && (
                    <div className="small muted" style={{ marginTop: 6 }}>
                      Con carencia máxima se dejan fuera los productos sin carencia registrada; «no aplica» cuenta como 0 días.
                    </div>
                  )}
                </div>
                <div className="table-scroll" style={{ maxHeight: 640 }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th aria-sort={sort === "name" ? "ascending" : "none"}>
                          <button type="button" style={{ all: "unset", cursor: "pointer" }} onClick={() => setSort("name")}>
                            Producto{sort === "name" ? " ▲" : ""}</button>
                        </th>
                        <th>Registro</th>
                        <th>Tipo</th>
                        <th className="num" aria-sort={sort === "phi" ? "ascending" : "none"}>
                          <button type="button" style={{ all: "unset", cursor: "pointer" }} onClick={() => setSort("phi")}>
                            Carencia d{sort === "phi" ? " ▲" : ""}</button>
                        </th>
                        <th className="num">LMR Perú</th>
                        <th>Ingredientes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((p) => (
                        <tr key={p.product_id}>
                          <td><div style={{ fontWeight: 500 }}>{productName(p)}</div><div className="small muted mono">{p.product_id}</div></td>
                          <td className="mono small">{p.registration_number ?? "—"}</td>
                          <td>{isBiological(p) ? <Stamp tone="info">biológico</Stamp> : <span className="small">químico</span>}</td>
                          <td className="num">{p.preharvest_not_applicable ? <span className="small muted">no aplica</span> : p.preharvest_interval_days ?? <Stamp tone="risk">sin dato</Stamp>}</td>
                          <td className="num">{mgkg(p.peru_mrl_mg_kg)}</td>
                          <td>
                            {p.ingredients.map((i) => (
                              <div key={i}><Link prefetch={false} className="mono small" href={`/lmr/?i=${encodeURIComponent(i)}&c=${encodeURIComponent(crop)}`}>{i}</Link></div>
                            ))}
                          </td>
                        </tr>
                      ))}
                      {list.length === 0 && <tr><td colSpan={6} className="muted">Ningún producto cumple los filtros.</td></tr>}
                    </tbody>
                  </table>
                  <div className="panel-body cite">Fuente: SIGIA de SENASA · {fmtSnapshot(products.data[0]?.snapshot)}</div>
                </div>
              </>
            )}
        </Panel>
      </div>
    </div>
  );
}

export default function RegistryPage() {
  return (
    <Suspense fallback={<div className="page"><Loading what="la página" /></div>}>
      <RegistryView />
    </Suspense>
  );
}
