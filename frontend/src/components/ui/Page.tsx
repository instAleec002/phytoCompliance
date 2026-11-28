import type { ReactNode } from "react";

import { ApiError } from "@/lib/api/errors";
import { showIcons, showNumbers } from "@/styles/ui.config";

import { Icon, SECTION_ICON } from "./Icon";

export function PageHead({ index, title, lead, actions }: { index: string; title: string; lead?: ReactNode; actions?: ReactNode }) {
  // the icon and the number follow the switches in ui.config.ts; a page without a section number (sign-in,
  // activation) shows its label, such as «Acceso», where the number would go
  const icon = showIcons ? SECTION_ICON[index] : undefined;
  const showIndex = showNumbers || !SECTION_ICON[index];
  return (
    <div className="page-head">
      <div className="page-title">
        {icon ? <Icon name={icon} size={48} className="page-icon" /> : null}
        <div>
          {showIndex && <div className="index">{index}</div>}
          <h1>{title}</h1>
          {lead && <p>{lead}</p>}
        </div>
      </div>
      {actions && <div className="row no-print">{actions}</div>}
    </div>
  );
}

export function Panel({ title, aside, children, flush }: { title?: ReactNode; aside?: ReactNode; children: ReactNode; flush?: boolean }) {
  return (
    <section className="panel">
      {(title || aside) && (
        <div className="panel-head">
          {typeof title === "string" ? <h2>{title}</h2> : title}
          {aside}
        </div>
      )}
      <div className={flush ? undefined : "panel-body"}>{children}</div>
    </section>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  const tone = error instanceof ApiError && error.status === 422 ? "risk" : "blocking";
  return (
    <div className="notice" data-tone={tone} role="alert">
      {message}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <div className="empty" aria-busy="true">
      Consultando {what}…
    </div>
  );
}
