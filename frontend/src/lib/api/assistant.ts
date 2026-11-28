"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useSettings } from "../settings";
import { call, useClient, type Schemas } from "./client";

// Hooks of the assistant: conversations with their messages, asking within a conversation, and the corpus counter.

export type Conversation = Schemas["ConversationOut"];
export type Message = Schemas["MessageOut"];
export type Citation = Schemas["CitationOut"];

function useBase() {
  const client = useClient();
  const { connection, ready } = useSettings();
  return { client, url: connection.apiUrl, key: [connection.apiUrl, connection.token], ready: ready && !!connection.token };
}

export function useConversations() {
  const { client, url, key, ready } = useBase();
  return useQuery({ queryKey: [...key, "conversations"], queryFn: () => call(url, () => client.GET("/api/conversaciones")), enabled: ready });
}

export function useConversation(id: number | null) {
  const { client, url, key, ready } = useBase();
  return useQuery({
    queryKey: [...key, "conversation", id],
    queryFn: () => call(url, () => client.GET("/api/conversaciones/{conversation_id}", { params: { path: { conversation_id: id! } } })),
    enabled: ready && id !== null,
  });
}

export function useNewConversation() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: () => call(url, () => client.POST("/api/conversaciones", { body: { titulo: "" } })),
    onSuccess: () => queries.invalidateQueries({ queryKey: [...key, "conversations"] }),
  });
}

export function useDeleteConversation() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      call(url, () => client.DELETE("/api/conversaciones/{conversation_id}", { params: { path: { conversation_id: id } } })),
    onSuccess: () => queries.invalidateQueries({ queryKey: [...key, "conversations"] }),
  });
}

export function useRenameConversation() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({ id, titulo }: { id: number; titulo: string }) =>
      call(url, () =>
        client.PATCH("/api/conversaciones/{conversation_id}", { params: { path: { conversation_id: id } }, body: { titulo } }),
      ),
    onSuccess: (_c, { id }) => {
      queries.invalidateQueries({ queryKey: [...key, "conversations"] });
      queries.invalidateQueries({ queryKey: [...key, "conversation", id] });
    },
  });
}

/** Ask within a conversation. The id travels with each call: a question can create the conversation it belongs to,
 *  and a hook bound to the id of the last render would still hold the previous one. */
export function useAsk() {
  const { client, url, key } = useBase();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({ id, pregunta }: { id: number; pregunta: string }) =>
      call(url, () =>
        client.POST("/api/conversaciones/{conversation_id}/mensajes", {
          params: { path: { conversation_id: id } },
          body: { pregunta },
        }),
      ),
    onSuccess: (_turn, { id }) => {
      queries.invalidateQueries({ queryKey: [...key, "conversation", id] });
      queries.invalidateQueries({ queryKey: [...key, "conversations"] });
    },
  });
}

export function useCorpus() {
  const { client, url, key, ready } = useBase();
  return useQuery({ queryKey: [...key, "corpus"], queryFn: () => call(url, () => client.GET("/api/corpus")), enabled: ready });
}
