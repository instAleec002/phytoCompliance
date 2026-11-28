"use client";

import { createContext, useCallback, useMemo, useState, useContext, type ReactNode } from "react";

import { todayISO } from "./format";
import { useStoredState } from "./storage";

// Connection and session live on the device: the API address, and the session token obtained when signing in
// (never a password). The evaluation date is global: every limit, validation and alert is computed for it.

export const DEFAULT_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Connection {
  apiUrl: string;
  token: string; // session token; empty when signed out
}

interface SettingsValue {
  connection: Connection;
  setApiUrl: (url: string) => void;
  setToken: (token: string) => void;
  evaluationDate: string;
  setEvaluationDate: (iso: string) => void;
  ready: boolean;
}

const SettingsContext = createContext<SettingsValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [apiUrl, setApiUrlState, urlReady] = useStoredState<string>("tp.api", DEFAULT_API_URL);
  const [token, setTokenState, tokenReady] = useStoredState<string>("tp.session", "");
  const [evaluationDate, setEvaluationDate] = useState(todayISO());
  const setApiUrl = useCallback(
    (url: string) => {
      setApiUrlState(url);
      setTokenState("");
    },
    [setApiUrlState, setTokenState],
  );
  const setToken = useCallback((t: string) => setTokenState(t), [setTokenState]);
  const value = useMemo(
    () => ({
      connection: { apiUrl, token },
      setApiUrl,
      setToken,
      evaluationDate,
      setEvaluationDate,
      ready: urlReady && tokenReady,
    }),
    [apiUrl, token, setApiUrl, setToken, evaluationDate, urlReady, tokenReady],
  );
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsValue {
  const value = useContext(SettingsContext);
  if (!value) throw new Error("useSettings outside SettingsProvider");
  return value;
}
