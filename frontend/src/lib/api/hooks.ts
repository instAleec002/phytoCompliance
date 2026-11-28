"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { useSettings } from "../settings";
import { call, useClient, type Schemas } from "./client";

// One hook per endpoint. Query keys include the connection so changing the API URL or token refetches everything.

function useBase() {
  const client = useClient();
  const { connection, ready } = useSettings();
  const key = [connection.apiUrl, connection.token];
  // data endpoints need a session; without one they would only answer 401
  return { client, url: connection.apiUrl, key, ready: ready && !!connection.token, apiReady: ready };
}

export function useHealth() {
  const { client, url, apiReady } = useBase();
  return useQuery({
    queryKey: [url, "health"],
    queryFn: () => call(url, () => client.GET("/api/salud")),
    enabled: apiReady,
    refetchInterval: 60_000,
    retry: false,
  });
}

export function useCrops() {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "crops"],
    queryFn: () => call(url, () => client.GET("/api/cultivos")),
    enabled: ready,
    staleTime: Infinity,
  });
}

export function useMarkets() {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "markets"],
    queryFn: () => call(url, () => client.GET("/api/mercados")),
    enabled: ready,
    staleTime: 5 * 60_000,
  });
}

export function usePests(crop: string | null) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "pests", crop],
    queryFn: () => call(url, () => client.GET("/api/plagas", { params: { query: { cultivo: crop ?? "" } } })),
    enabled: ready && !!crop,
    staleTime: Infinity,
  });
}

export function useProducts(crop: string | null, pest: string | null) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "products", crop, pest],
    queryFn: () =>
      call(url, () => client.GET("/api/productos", { params: { query: { cultivo: crop ?? "", plaga: pest ?? "" } } })),
    enabled: ready && !!crop && !!pest,
    staleTime: Infinity,
  });
}

export function useIngredients(query: string, crop?: string | null) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "ingredients", query, crop ?? null],
    queryFn: () =>
      call(url, () =>
        client.GET("/api/ingredientes", { params: { query: { q: query, cultivo: crop ?? undefined, limite: 20 } } }),
      ),
    enabled: ready && query.trim().length >= 2,
    staleTime: Infinity,
  });
}

export function useLimit(ingredient: string, crop: string, market: string, day: string) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "limit", ingredient, crop, market, day],
    queryFn: () =>
      call(url, () =>
        client.GET("/api/lmr", { params: { query: { ingrediente: ingredient, cultivo: crop, mercado: market, fecha: day } } }),
      ),
    enabled: ready && !!ingredient && !!crop,
  });
}

export function useVersions(ingredient: string, crop: string, market: string) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "versions", ingredient, crop, market],
    queryFn: () =>
      call(url, () =>
        client.GET("/api/lmr/versiones", { params: { query: { ingrediente: ingredient, cultivo: crop, mercado: market } } }),
      ),
    enabled: ready && !!ingredient && !!crop,
  });
}

export function useProfiles() {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "profiles"],
    queryFn: () => call(url, () => client.GET("/api/perfiles")),
    enabled: ready,
    staleTime: Infinity,
  });
}

export function useValidate() {
  const { client, url } = useBase();
  return useMutation({
    mutationFn: (program: Schemas["ProgramIn"]) => call(url, () => client.POST("/api/validar", { body: program })),
  });
}

export function useImportProgram() {
  const { client, url } = useBase();
  return useMutation({
    mutationFn: (body: Schemas["ImportIn"]) => call(url, () => client.POST("/api/programas/importar", { body })),
  });
}

export function useProgramAlerts() {
  const { client, url } = useBase();
  return useMutation({
    mutationFn: ({ program, day }: { program: Schemas["ProgramIn"]; day: string }) =>
      call(url, () => client.POST("/api/alertas/programa", { body: program, params: { query: { fecha: day } } })),
  });
}

export function useLab() {
  const { client, url } = useBase();
  return useMutation({
    mutationFn: (lot: Schemas["LabResultIn"]) => call(url, () => client.POST("/api/laboratorio", { body: lot })),
  });
}

export function useAlerts(ingredient: string, crop: string, market: string, day: string) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "alerts", ingredient, crop, market, day],
    queryFn: () =>
      call(url, () =>
        client.GET("/api/alertas", { params: { query: { ingrediente: ingredient, cultivo: crop, mercado: market, fecha: day } } }),
      ),
    enabled: ready && ingredient.length > 1 && !!crop,
  });
}
