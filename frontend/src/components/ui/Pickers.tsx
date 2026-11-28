"use client";

import { useEffect, useId, useState } from "react";

import { useCrops, useIngredients } from "@/lib/api/hooks";
import { MARKETS, MARKET_SHORT } from "@/lib/labels";

export function CropSelect({ value, onChange, label = "Cultivo" }: { value: string; onChange: (v: string) => void; label?: string }) {
  const crops = useCrops();
  useEffect(() => {
    if (!value && crops.data?.[0]) onChange(crops.data[0].key);
  }, [value, crops.data, onChange]);
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={!crops.data}>
        {!crops.data && <option value="">{crops.isError ? "Sin conexión" : "Cargando…"}</option>}
        {crops.data?.map((c) => (
          <option key={c.key} value={c.key}>
            {c.name_es ?? c.key}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Text input with the ingredient names of the graph as suggestions (native datalist: keyboard and screen readers). */
export function IngredientInput({
  value,
  onChange,
  crop,
  label = "Ingrediente activo",
  width = 260,
}: {
  value: string;
  onChange: (v: string) => void;
  crop?: string | null;
  label?: string;
  width?: number | string;
}) {
  const id = useId();
  const [query, setQuery] = useState(value);
  useEffect(() => setQuery(value), [value]);
  const suggestions = useIngredients(query, crop);
  return (
    <label className="field" style={{ width }}>
      <span>{label}</span>
      <input
        className="mono"
        list={id}
        value={query}
        placeholder="p. ej. pyraclostrobin"
        autoComplete="off"
        spellCheck={false}
        onChange={(e) => {
          setQuery(e.target.value);
          onChange(e.target.value.trim());
        }}
      />
      <datalist id={id}>
        {suggestions.data?.map((i) => (
          <option key={i.key} value={i.key}>
            {i.markets.length ? i.markets.map((m) => MARKET_SHORT[m] ?? m).join(" · ") : "sin residuo listado"}
          </option>
        ))}
      </datalist>
    </label>
  );
}

export function MarketChecks({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="checks" role="group" aria-label="Mercados de destino">
      {MARKETS.map((m) => (
        <label key={m} className="check">
          <input
            type="checkbox"
            checked={value.includes(m)}
            onChange={(e) => onChange(e.target.checked ? [...value, m] : value.filter((x) => x !== m))}
          />
          <span>{MARKET_SHORT[m]}</span>
        </label>
      ))}
    </div>
  );
}
