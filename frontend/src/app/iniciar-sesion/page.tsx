"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ErrorNote } from "@/components/ui/Page";
import { useSession } from "@/lib/session";

function SignInForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { signIn, status } = useSession();
  const [identifier, setIdentifier] = useState(params.get("usuario") ?? "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const next = params.get("siguiente");
  const target = next && next.startsWith("/") && !next.startsWith("//") ? next : "/lmr/";

  useEffect(() => {
    if (status === "signed-in") router.replace(target);
  }, [status, router, target]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(identifier.trim(), password);
      router.replace(target);
    } catch (err) {
      setError(err);
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <div>
        <div className="label">Acceso</div>
        <h1 style={{ marginTop: 4 }}>Iniciar sesión</h1>
      </div>
      <form className="panel" onSubmit={submit}>
        <div className="panel-body stack">
          <label className="field"><span>Usuario o correo</span>
            <input className="mono" value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username"
              autoFocus required spellCheck={false} /></label>
          <label className="field"><span>Contraseña</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password"
              required /></label>
          <ErrorNote error={error} />
          <button type="submit" className="btn btn-primary" disabled={busy || !identifier || !password}
            style={{ justifyContent: "center" }}>{busy ? "Verificando…" : "Entrar"}</button>
        </div>
      </form>
      <div className="small muted">
        Las cuentas las crea el administrador. Si olvidó su contraseña, pídale un enlace de restablecimiento.
        La dirección de la API se cambia en <Link prefetch={false} href="/ajustes/">Ajustes</Link>.
      </div>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={null}>
      <SignInForm />
    </Suspense>
  );
}
