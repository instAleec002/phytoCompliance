"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";

import { call, makeClient, type Schemas } from "./api/client";
import { SESSION_LOST } from "./api/errors";
import { useSettings } from "./settings";

// Who is signed in. The session token comes from /api/auth/iniciar-sesion and is kept on the device; the account
// behind it is read from /api/auth/yo. Signing out revokes the session on the server too.

export type Me = Schemas["UserOut"];

interface SessionValue {
  me: Me | null;
  status: "loading" | "signed-in" | "signed-out";
  isAdmin: boolean;
  signIn: (identifier: string, password: string) => Promise<Me>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const { connection, setToken, ready } = useSettings();
  const queries = useQueryClient();

  const me = useQuery({
    queryKey: [connection.apiUrl, "me", connection.token],
    queryFn: () => call(connection.apiUrl, () => makeClient(connection).GET("/api/auth/yo")),
    enabled: ready && !!connection.token,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const forget = useCallback(() => {
    setToken("");
    queries.clear();
  }, [setToken, queries]);

  useEffect(() => {
    window.addEventListener(SESSION_LOST, forget);
    return () => window.removeEventListener(SESSION_LOST, forget);
  }, [forget]);

  const signIn = useCallback(
    async (identifier: string, password: string) => {
      const client = makeClient({ apiUrl: connection.apiUrl, token: "" });
      const out = await call(connection.apiUrl, () =>
        client.POST("/api/auth/iniciar-sesion", { body: { identificador: identifier, contrasena: password } }),
      );
      queries.clear();
      setToken(out.token);
      queries.setQueryData([connection.apiUrl, "me", out.token], out.usuario);
      return out.usuario;
    },
    [connection.apiUrl, queries, setToken],
  );

  const signOut = useCallback(async () => {
    try {
      await call(connection.apiUrl, () => makeClient(connection).POST("/api/auth/cerrar-sesion"));
    } catch {
      // the session may already be gone; forgetting it locally is what matters
    }
    forget();
  }, [connection, forget]);

  const value = useMemo<SessionValue>(() => {
    const status = !ready || (connection.token && me.isPending) ? "loading" : me.data && connection.token ? "signed-in" : "signed-out";
    return { me: status === "signed-in" ? me.data! : null, status, isAdmin: me.data?.rol === "admin", signIn, signOut };
  }, [ready, connection.token, me.isPending, me.data, signIn, signOut]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession outside SessionProvider");
  return value;
}
