"use client";

import { useEffect, useState } from "react";

import { PageHead, Panel } from "@/components/ui/Page";
import { Stamp } from "@/components/ui/Stamp";
import { call, makeClient } from "@/lib/api/client";
import { DEFAULT_API_URL, useSettings } from "@/lib/settings";

type Test = { state: "idle" } | { state: "running" } | { state: "ok" } | { state: "error"; detail: string };

export default function SettingsPage() {
  const { connection, setApiUrl } = useSettings();
  const [apiUrl, setUrl] = useState(connection.apiUrl);
  const [test, setTest] = useState<Test>({ state: "idle" });

  useEffect(() => setUrl(connection.apiUrl), [connection.apiUrl]);
  const dirty = apiUrl.trim() !== connection.apiUrl;

  const runTest = async () => {
    setTest({ state: "running" });
    try {
      await call(apiUrl, () => makeClient({ apiUrl, token: "" }).GET("/api/salud"));
      setTest({ state: "ok" });
    } catch (e) {
      setTest({ state: "error", detail: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <div className="page">
      <PageHead index="11" title="Ajustes" lead="Dirección de la API. La web y la aplicación de escritorio usan el mismo backend; el acceso es con su cuenta." />
      <div style={{ maxWidth: 720 }}>
        <Panel title="Conexión con la API">
          <form className="stack" onSubmit={(e) => { e.preventDefault(); setApiUrl(apiUrl.trim()); }}>
            <label className="field"><span>Dirección de la API</span>
              <input className="mono" value={apiUrl} onChange={(e) => setUrl(e.target.value)} placeholder={DEFAULT_API_URL} /></label>
            <div className="small muted">Cambiarla cierra la sesión en este dispositivo: cada API tiene sus propias cuentas.</div>
            <div className="row">
              <button type="button" className="btn" onClick={runTest} disabled={test.state === "running" || !apiUrl}>
                {test.state === "running" ? "Probando…" : "Probar conexión"}</button>
              <button type="submit" className="btn btn-primary" disabled={!dirty}>Guardar</button>
              {test.state === "ok" && <Stamp tone="ok">la API responde</Stamp>}
              {test.state === "error" && <Stamp tone="blocking">falló</Stamp>}
            </div>
            {test.state === "error" && <div className="notice" data-tone="blocking">{test.detail}</div>}
          </form>
        </Panel>
      </div>
    </div>
  );
}
