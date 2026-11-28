"use client";

import createClient from "openapi-fetch";
import { useMemo } from "react";

import { useSettings, type Connection } from "../settings";
import { ApiError, SESSION_LOST, toApiError } from "./errors";
import type { components, paths } from "./schema";

// Typed client generated from the OpenAPI schema of the backend (npm run gen:api after the API changes).

export type Schemas = components["schemas"];

export function makeClient({ apiUrl, token }: Connection) {
  const client = createClient<paths>({ baseUrl: apiUrl.replace(/\/+$/, "") });
  client.use({
    onRequest({ request }) {
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
  });
  return client;
}

export type Client = ReturnType<typeof makeClient>;

export function useClient(): Client {
  const { connection } = useSettings();
  return useMemo(() => makeClient(connection), [connection]);
}

/** Unwraps an openapi-fetch call: the data, or an ApiError with a message for the user. */
export async function call<T>(
  apiUrl: string,
  request: () => Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: { data?: T; error?: unknown; response: Response };
  try {
    result = await request();
  } catch {
    throw toApiError(0, null, apiUrl);
  }
  if (result.response.ok && (result.data !== undefined || result.response.status === 204)) return result.data as T;
  const error = result.error instanceof ApiError ? result.error : toApiError(result.response.status, result.error, apiUrl);
  // a 401 on any call but sign-in means the session is gone: the session provider signs out
  if (error.status === 401 && !result.response.url.includes("/api/auth/iniciar-sesion")) {
    window.dispatchEvent(new Event(SESSION_LOST));
  }
  throw error;
}
