import "@fontsource-variable/inter/index.css";
import "@fontsource/eb-garamond/600.css";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { Shell } from "@/components/shell/Shell";
import { THEME_BOOT } from "@/lib/theme";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "Cumplimiento fitosanitario", template: "%s · Cumplimiento fitosanitario" },
  description: "Límites máximos de residuos por mercado, validación de programas y resultados de laboratorio.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // data-theme is set before the first paint by THEME_BOOT (light unless the device chose dark)
    <html lang="es" data-theme="light" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
