import type { ReactNode } from "react";

import { LIMIT_STATUS, SEVERITY, type Tone } from "@/lib/labels";

export function Stamp({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span className="stamp" data-tone={tone} title={title}>
      {children}
    </span>
  );
}

export function SeverityStamp({ severity }: { severity: string }) {
  const s = SEVERITY[severity] ?? { label: severity, tone: "neutral" as Tone };
  return <Stamp tone={s.tone}>{s.label}</Stamp>;
}

export function LimitStamp({ status }: { status: string }) {
  const s = LIMIT_STATUS[status] ?? { label: status, tone: "neutral" as Tone };
  return <Stamp tone={s.tone}>{s.label}</Stamp>;
}

export function VerdictStamp({ verdict }: { verdict: string | null | undefined }) {
  if (!verdict) return <Stamp tone="ok">Sin hallazgos</Stamp>;
  return <SeverityStamp severity={verdict} />;
}
