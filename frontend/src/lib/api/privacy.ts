"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useSettings } from "../settings";
import { call, makeClient, useClient, type Schemas } from "./client";

// Privacy notice (Ley N.° 29733) and the rights of access, rectification, cancellation and opposition.

function useBase() {
  const client = useClient();
  const { connection, ready } = useSettings();
  return { client, connection, url: connection.apiUrl, key: [connection.apiUrl, connection.token], ready: ready && !!connection.token };
}

/** Public: shown before activating an account and on /privacidad. */
export function useNotice() {
  const { connection, ready } = useSettings();
  return useQuery({
    queryKey: [connection.apiUrl, "privacy-notice"],
    queryFn: () => call(connection.apiUrl, () => makeClient({ apiUrl: connection.apiUrl, token: "" }).GET("/api/auth/aviso-privacidad")),
    enabled: ready,
    staleTime: Infinity,
  });
}

export function useAcceptNotice() {
  const { client, url } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (version: string) => call(url, () => client.POST("/api/mis/aviso", { body: { version } })),
    onSuccess: () => queries.invalidateQueries(),
  });
}

export function useMyRights() {
  const { client, url, key, ready } = useBase();
  return useQuery({ queryKey: [...key, "my-rights"], queryFn: () => call(url, () => client.GET("/api/mis/derechos")), enabled: ready });
}

export function useRequestRight() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["RightRequestIn"]) => call(url, () => client.POST("/api/mis/derechos", { body })),
    onSuccess: () => queries.invalidateQueries({ queryKey: [...key, "my-rights"] }),
  });
}

export function useAdminRights() {
  const { client, url, key, ready } = useBase();
  return useQuery({ queryKey: [...key, "admin-rights"], queryFn: () => call(url, () => client.GET("/api/admin/derechos")), enabled: ready });
}

export function useResolveRight() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Schemas["RightResolveIn"] }) =>
      call(url, () => client.PATCH("/api/admin/derechos/{request_id}", { params: { path: { request_id: id } }, body })),
    onSuccess: () => queries.invalidateQueries({ queryKey: [...key, "admin-rights"] }),
  });
}

/** Right of access: the whole account as a JSON file. */
export function useDownloadMyData() {
  const { connection } = useBase();
  return useMutation({
    mutationFn: async () => {
      const r = await fetch(`${connection.apiUrl.replace(/\/$/, "")}/api/mis/datos`, {
        headers: { Authorization: `Bearer ${connection.token}` },
      });
      if (!r.ok) throw new Error(`No se pudo descargar (${r.status})`);
      const blob = await r.blob();
      const name = /filename="([^"]+)"/.exec(r.headers.get("content-disposition") ?? "")?.[1] ?? "mis-datos.json";
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
    },
  });
}
