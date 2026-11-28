"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useSettings } from "../settings";
import { call, makeClient, useClient, type Schemas } from "./client";

// Hooks of the account, saved work and administration endpoints.

function useBase() {
  const client = useClient();
  const { connection, ready } = useSettings();
  return { client, url: connection.apiUrl, key: [connection.apiUrl, connection.token], ready: ready && !!connection.token };
}

/** Link endpoints work without a session (the person is activating or resetting). */
export function useLinkInfo(token: string | null) {
  const { connection, ready } = useSettings();
  return useQuery({
    queryKey: [connection.apiUrl, "link", token],
    queryFn: () =>
      call(connection.apiUrl, () => makeClient({ apiUrl: connection.apiUrl, token: "" }).POST("/api/auth/enlace", { body: { token: token! } })),
    enabled: ready && !!token,
    retry: false,
  });
}

export function useRedeem() {
  const { connection } = useSettings();
  return useMutation({
    mutationFn: (body: Schemas["RedeemIn"]) =>
      call(connection.apiUrl, () => makeClient({ apiUrl: connection.apiUrl, token: "" }).POST("/api/auth/activar", { body })),
  });
}

export function useChangePassword() {
  const { client, url } = useBase();
  return useMutation({
    mutationFn: (body: Schemas["PasswordChangeIn"]) => call(url, () => client.POST("/api/mis/contrasena", { body })),
  });
}

export function useMySessions() {
  const { client, url, key, ready } = useBase();
  return useQuery({ queryKey: [...key, "my-sessions"], queryFn: () => call(url, () => client.GET("/api/mis/sesiones")), enabled: ready });
}

export function useRevokeSession() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => call(url, () => client.DELETE("/api/mis/sesiones/{session_id}", { params: { path: { session_id: id } } })),
    onSuccess: () => queries.invalidateQueries({ queryKey: [...key, "my-sessions"] }),
  });
}

export function useMyActivity() {
  const { client, url, key, ready } = useBase();
  return useQuery({ queryKey: [...key, "my-activity"], queryFn: () => call(url, () => client.GET("/api/mis/actividad")), enabled: ready });
}

// saved programs ----------------------------------------------------------------------------------------------------

export function useMyPrograms() {
  const { client, url, key, ready } = useBase();
  return useQuery({ queryKey: [...key, "my-programs"], queryFn: () => call(url, () => client.GET("/api/mis/programas")), enabled: ready });
}

export function useSaveProgram() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: Schemas["SavedProgramIn"] }) =>
      id === null
        ? call(url, () => client.POST("/api/mis/programas", { body }))
        : call(url, () => client.PUT("/api/mis/programas/{program_id}", { params: { path: { program_id: id } }, body })),
    onSuccess: () => queries.invalidateQueries({ queryKey: [...key, "my-programs"] }),
  });
}

export function useLoadProgram() {
  const { client, url } = useBase();
  return useMutation({
    mutationFn: (id: number) => call(url, () => client.GET("/api/mis/programas/{program_id}", { params: { path: { program_id: id } } })),
  });
}

export function useDeleteProgram() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => call(url, () => client.DELETE("/api/mis/programas/{program_id}", { params: { path: { program_id: id } } })),
    onSuccess: () => queries.invalidateQueries({ queryKey: [...key, "my-programs"] }),
  });
}

// evaluated lots ----------------------------------------------------------------------------------------------------

export function useMyLots() {
  const { client, url, key, ready } = useBase();
  return useQuery({ queryKey: [...key, "my-lots"], queryFn: () => call(url, () => client.GET("/api/mis/lotes")), enabled: ready });
}

export function useMyLot(id: number | null) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "my-lot", id],
    queryFn: () => call(url, () => client.GET("/api/mis/lotes/{lot_id}", { params: { path: { lot_id: id! } } })),
    enabled: ready && id !== null,
  });
}

// administration ----------------------------------------------------------------------------------------------------

export function useUsers() {
  const { client, url, key, ready } = useBase();
  return useQuery({ queryKey: [...key, "users"], queryFn: () => call(url, () => client.GET("/api/admin/usuarios")), enabled: ready });
}

export function useInvite() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["InviteIn"]) => call(url, () => client.POST("/api/admin/usuarios", { body })),
    onSuccess: () => queries.invalidateQueries({ queryKey: [...key, "users"] }),
  });
}

export function useUpdateUser() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Schemas["UserUpdateIn"] }) =>
      call(url, () => client.PATCH("/api/admin/usuarios/{user_id}", { params: { path: { user_id: id } }, body })),
    onSuccess: () => queries.invalidateQueries({ queryKey: [...key, "users"] }),
  });
}

export function useNewLink() {
  const { client, url } = useBase();
  return useMutation({
    mutationFn: (id: number) => call(url, () => client.POST("/api/admin/usuarios/{user_id}/enlace", { params: { path: { user_id: id } } })),
  });
}

export function useAudit(userId: number | null) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "audit", userId],
    queryFn: () => call(url, () => client.GET("/api/admin/auditoria", { params: { query: { usuario_id: userId ?? undefined } } })),
    enabled: ready,
  });
}

export function useUserWork(userId: number | null) {
  const { client, url, key, ready } = useBase();
  const programs = useQuery({
    queryKey: [...key, "user-programs", userId],
    queryFn: () => call(url, () => client.GET("/api/admin/usuarios/{user_id}/programas", { params: { path: { user_id: userId! } } })),
    enabled: ready && userId !== null,
  });
  const lots = useQuery({
    queryKey: [...key, "user-lots", userId],
    queryFn: () => call(url, () => client.GET("/api/admin/usuarios/{user_id}/lotes", { params: { path: { user_id: userId! } } })),
    enabled: ready && userId !== null,
  });
  return { programs, lots };
}

export function useUserProgram(userId: number | null, programId: number | null) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "user-program", userId, programId],
    queryFn: () =>
      call(url, () =>
        client.GET("/api/admin/usuarios/{user_id}/programas/{program_id}", { params: { path: { user_id: userId!, program_id: programId! } } }),
      ),
    enabled: ready && userId !== null && programId !== null,
  });
}

export function useUserLot(userId: number | null, lotId: number | null) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "user-lot", userId, lotId],
    queryFn: () =>
      call(url, () => client.GET("/api/admin/usuarios/{user_id}/lotes/{lot_id}", { params: { path: { user_id: userId!, lot_id: lotId! } } })),
    enabled: ready && userId !== null && lotId !== null,
  });
}
