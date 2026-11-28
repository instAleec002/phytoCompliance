"use client";

import Link from "next/link";
import { Fragment, useState, type ReactNode } from "react";

import { Stamp } from "@/components/ui/Stamp";
import type { Citation, Message } from "@/lib/api/assistant";

import styles from "./assistant.module.css";
import { TOOL_LABEL, argsLine, graphRowsOf, rowLines, rowLink, type GraphRow } from "./graphRows";

const LEVEL: Record<string, { label: string; tone: "ok" | "info" | "neutral" }> = {
  A: { label: "Oficial", tone: "ok" },
  B: { label: "Ficha de producto", tone: "info" },
  C: { label: "Académico", tone: "info" },
  interno: { label: "Interno", tone: "neutral" },
};

/** One line of the answer: **bold**, *italics*, [n] marks (passages) and [G1] marks (rows of the exact core) as
 *  buttons that bring what they cite into view. The model writes a small subset of Markdown; nothing else is
 *  interpreted, and no HTML is injected. */
function inline(text: string, onMark: (n: number | string) => void, key: string): ReactNode[] {
  return text.split(/(\[G?\d{1,2}\]|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\b_[^_\s][^_]*_\b)/g).map((part, i) => {
    const k = `${key}-${i}`;
    const g = part.match(/^\[(G\d{1,2})\]$/);
    if (g) {
      const id = g[1]!;
      return (
        <button key={k} type="button" className={styles.mark} data-kind="graph" onClick={() => onMark(id)}
          aria-label={`Ver el dato ${id} del núcleo exacto`}>
          {id}
        </button>
      );
    }
    const m = part.match(/^\[(\d{1,2})\]$/);
    if (m) {
      const n = Number(m[1]);
      return (
        <button key={k} type="button" className={styles.mark} onClick={() => onMark(n)} aria-label={`Ver la cita ${n}`}>
          {n}
        </button>
      );
    }
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={k}>{inline(part.slice(2, -2), onMark, k)}</strong>;
    if (/^\*[^*\s][^*]*\*$/.test(part) || /^_[^_\s][^_]*_$/.test(part)) return <em key={k}>{part.slice(1, -1)}</em>;
    return <Fragment key={k}>{part}</Fragment>;
  });
}

/** Paragraphs and bullet lists («* », «- » or «1. » at the start of a line). */
function rich(text: string, onMark: (n: number | string) => void): ReactNode[] {
  const out: ReactNode[] = [];
  let items: string[] = [];
  let ordered = false;
  const flush = () => {
    if (!items.length) return;
    const lis = items.map((it, j) => <li key={j}>{inline(it, onMark, `l${out.length}-${j}`)}</li>);
    out.push(ordered ? <ol key={out.length}>{lis}</ol> : <ul key={out.length}>{lis}</ul>);
    items = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const bullet = line.match(/^[*-]\s+(.*)$/);
    const numbered = line.match(/^\d+[.)]\s+(.*)$/);
    const item = bullet ?? numbered;
    if (item) {
      if (items.length && ordered !== !bullet) flush();
      ordered = !bullet;
      items.push(item[1] ?? "");
      continue;
    }
    flush();
    if (line) out.push(<p key={out.length}>{inline(line, onMark, `p${out.length}`)}</p>);
  }
  flush();
  return out;
}

function sourceLink(c: Citation): string | null {
  if (!c.url || c.url.startsWith("local:")) return null;
  return c.url;
}

/** A cited passage: document, section and page always visible; the passage text opens on demand (or when its mark
 *  in the answer is clicked), so long answers with several citations stay readable. */
export function CitationCard({ c, focus }: { c: Citation; focus: boolean }) {
  const level = LEVEL[c.nivel] ?? { label: c.nivel, tone: "neutral" as const };
  const link = sourceLink(c);
  const [open, setOpen] = useState(false);
  const shown = open || focus;
  return (
    <div className={styles.citation} data-focus={focus} id={`cita-${c.chunk_id}`}>
      <div className={styles.citationHead}>
        <span className={styles.citationN}>[{c.n}]</span>
        <span className={styles.citationTitle}>{c.titulo}</span>
        <Stamp tone={level.tone}>{level.label}</Stamp>
      </div>
      <div className={styles.citationWhere}>
        {c.seccion.length ? c.seccion.join(" › ") : "Sin sección"}
        {c.paginas.length ? ` · p. ${c.paginas.join(", ")}` : ""}
        {link && (
          <>
            {" · "}
            <a href={link} target="_blank" rel="noreferrer">fuente</a>
          </>
        )}
        {" · "}
        <button type="button" className={styles.linkButton} onClick={() => setOpen(!shown)} aria-expanded={shown}>
          {shown ? "ocultar pasaje" : "ver pasaje"}
        </button>
      </div>
      {shown && <div className={styles.citationText}>{c.texto}</div>}
    </div>
  );
}

/** A row of the exact core the answer cites: the tool, its arguments and what it returned, with its source. */
export function GraphRowCard({ row, messageId, focus }: { row: GraphRow; messageId: number; focus: boolean }) {
  const link = rowLink(row);
  const fuente = row.resultado?.fuente;
  return (
    <div className={styles.citation} data-focus={focus} data-kind="graph" id={`fila-${messageId}-${row.id}`}>
      <div className={styles.citationHead}>
        <span className={styles.citationN}>[{row.id}]</span>
        <span className={styles.citationTitle}>{TOOL_LABEL[row.herramienta] ?? row.herramienta}</span>
        <Stamp tone="ok">Núcleo exacto</Stamp>
      </div>
      <div className={styles.citationWhere}>
        {argsLine(row)}
        {link && <>{" · "}<Link prefetch={false} href={link}>abrir</Link></>}
      </div>
      <ul className={styles.rowLines}>
        {rowLines(row).map((l, i) => <li key={i}>{l}</li>)}
      </ul>
      {typeof fuente === "string" && <div className="cite">{fuente}</div>}
    </div>
  );
}

type Call = { nombre: string; argumentos?: Record<string, unknown> };

export function AssistantMessage({ m }: { m: Message }) {
  const [focus, setFocus] = useState<number | string | null>(null);
  const [copied, setCopied] = useState(false);
  const trace = m.traza as Record<string, unknown>;
  const rows = graphRowsOf(trace);
  const calls = (Array.isArray(trace.llamadas) ? trace.llamadas : []) as Call[];
  const removed = Array.isArray(trace.retiradas) ? (trace.retiradas as string[]) : [];
  const corrected = Array.isArray(trace.corregido) ? (trace.corregido as string[]) : [];
  const show = (n: number | string) => {
    setFocus(n);
    const id = typeof n === "string"
      ? `fila-${m.id}-${n}`
      : (() => { const c = m.citas.find((x) => x.n === n); return c ? `cita-${c.chunk_id}` : null; })();
    if (id) document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(m.texto);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <div className={styles.bot}>
      {m.evidencia === false ? (
        <div className="notice" data-tone="info">{m.texto}</div>
      ) : (
        <div className={styles.answer}>
          {rich(m.texto, show)}
          <div className={styles.answerTools}>
            <button type="button" className={styles.linkButton} onClick={copy}>{copied ? "copiado" : "copiar"}</button>
          </div>
        </div>
      )}
      {rows.length > 0 && (
        <div className={styles.citations} aria-label="Datos del núcleo exacto">
          {rows.map((r) => <GraphRowCard key={r.id} row={r} messageId={m.id} focus={focus === r.id} />)}
        </div>
      )}
      {m.citas.length > 0 && (
        <div className={styles.citations} aria-label="Pasajes citados">
          {m.citas.map((c) => (
            <CitationCard key={c.n} c={c} focus={focus === c.n} />
          ))}
        </div>
      )}
      <details className={styles.trace}>
        <summary>Cómo se obtuvo</summary>
        <dl className="evidence">
          <dt>Consulta usada</dt>
          <dd>{String(trace.standalone_query ?? "")}</dd>
          {calls.length > 0 && (
            <>
              <dt>Herramientas consultadas</dt>
              <dd>{calls.map((c, i) => (
                <div key={i}>{TOOL_LABEL[c.nombre] ?? (c.nombre === "buscar_documentos" ? "Búsqueda en documentos" : c.nombre)}
                  {c.argumentos ? <span className="muted"> · {argsLine({ id: "", herramienta: c.nombre, argumentos: c.argumentos, resultado: {} })}</span> : null}</div>
              ))}</dd>
            </>
          )}
          {corrected.length > 0 && (
            <>
              <dt>Guarda de salida</dt>
              <dd>La primera respuesta daba {corrected.join(", ")}, que ninguna herramienta devolvió; se pidió corregirla.</dd>
            </>
          )}
          {removed.length > 0 && (
            <>
              <dt>Verificación por oraciones</dt>
              <dd>Se retiraron {removed.length} oraciones que la evidencia citada no respaldaba.</dd>
            </>
          )}
          <dt>Pasajes recuperados</dt>
          <dd>{Array.isArray(trace.passages) ? trace.passages.length : 0}</dd>
          <dt>Generador</dt>
          <dd>{String(trace.model ?? trace.generator ?? "")}</dd>
          <dt>Tiempos</dt>
          <dd>
            {trace.retrieval_s !== undefined ? `recuperación ${String(trace.retrieval_s)} s · ` : ""}
            {trace.generation_s !== undefined ? `generación ${String(trace.generation_s)} s` : ""}
          </dd>
        </dl>
      </details>
    </div>
  );
}
