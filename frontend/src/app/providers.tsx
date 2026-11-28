"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ApiError } from "@/lib/api/errors";
import { SessionProvider } from "@/lib/session";
import { SettingsProvider } from "@/lib/settings";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            // authentication and validation errors do not get better by retrying
            retry: (count, error) => !(error instanceof ApiError && [400, 401, 403, 404, 422].includes(error.status)) && count < 2,
          },
        },
      }),
  );
  return (
    <SettingsProvider>
      <QueryClientProvider client={client}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    </SettingsProvider>
  );
}
