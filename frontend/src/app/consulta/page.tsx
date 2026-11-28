"use client";

import { useEffect, useRef, useState } from "react";

import { ErrorNote, Loading, PageHead, Panel } from "@/components/ui/Page";
import { AssistantMessage } from "@/features/assistant/Answer";
import styles from "@/features/assistant/assistant.module.css";
import {
  useAsk,
  useConversation,
  useConversations,
  useDeleteConversation,
  useNewConversation,
  useRenameConversation,
} from "@/lib/api/assistant";
import { fmtDateTime } from "@/lib/format";

// Questions in natural language, in conversations: agronomic answers cite document, section and page; limits,
// registrations and intervals come from the exact core and are cited as its rows [G1]; without evidence it says so.

const EXAMPLES = [
  "¿Cómo se maneja la Botrytis en arándano?",
  "¿Cuál es el LMR vigente de fenhexamid en arándano en la Unión Europea?",
  "¿Qué controladores biológicos hay para la cochinilla harinosa de la vid?",
  "¿Qué productos registrados para palto contra queresa tienen carencia de 7 días o menos?",
];

export default function ConsultaPage() {
  const conversations = useConversations();
  const create = useNewConversation();
  const remove = useDeleteConversation();
  const rename = useRenameConversation();
  const [renaming, setRenaming] = useState<string | null>(null);
  const [current, setCurrent] = useState<number | null>(null);
  const conversation = useConversation(current);
  const ask = useAsk();
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const first = conversations.data?.[0];
    if (current === null && first) setCurrent(first.id);
  }, [conversations.data, current]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [conversation.data, pending]);

  const send = async (text?: string) => {
    const q = (text ?? question).trim();
    if (q.length < 3 || ask.isPending) return;
    let id = current;
    if (id === null) {
      id = (await create.mutateAsync()).id;
      setCurrent(id);
    }
    setPending(q);
    setQuestion("");
    ask.mutate({ id, pregunta: q }, { onSettled: () => setPending(null) });
  };

  const startNew = () => create.mutate(undefined, { onSuccess: (c) => setCurrent(c.id) });

  return (
    <div className="page">
      <PageHead
        index="01"
        title="Consulta"
        lead="Preguntas sobre manejo de cultivos y sanidad vegetal, respondidas con los documentos del repositorio. Cada afirmación cita su documento, sección y página; los límites de residuos y los registros se consultan en los módulos de cumplimiento."
      />
      <div className={styles.layout}>
        <Panel title="Conversaciones" aside={<button type="button" className="btn btn-quiet" onClick={startNew}>Nueva</button>} flush>
          {conversations.isPending ? (
            <div className="panel-body"><Loading what="conversaciones" /></div>
          ) : !conversations.data?.length ? (
            <div className="panel-body small muted">Aún no hay conversaciones. Escriba una pregunta para empezar.</div>
          ) : (
            <ul className={styles.list}>
              {conversations.data.map((c) => (
                <li key={c.id}>
                  <button type="button" className={styles.item} aria-current={c.id === current} onClick={() => setCurrent(c.id)}>
                    <span className={styles.itemTitle} title={c.titulo}>{c.titulo}</span>
                    <span className={styles.itemMeta}>{c.preguntas}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title={
            renaming !== null && current !== null ? (
              <input className={styles.renameInput} autoFocus value={renaming} maxLength={120} aria-label="Nombre de la conversación"
                onChange={(e) => setRenaming(e.target.value)}
                onBlur={() => setRenaming(null)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") setRenaming(null);
                  if (e.key === "Enter" && renaming.trim()) {
                    rename.mutate({ id: current, titulo: renaming.trim() });
                    setRenaming(null);
                  }
                }} />
            ) : (
              conversation.data?.titulo ?? "Nueva conversación"
            )
          }
          aside={
            current !== null && (
              <span className="row" style={{ alignItems: "center" }}>
                {conversation.data && <span className="small muted">{fmtDateTime(conversation.data.actualizado)}</span>}
                {conversation.data && renaming === null && (
                  <button type="button" className="btn btn-quiet" onClick={() => setRenaming(conversation.data!.titulo)}>Renombrar</button>
                )}
                <button type="button" className="btn btn-quiet" onClick={() => {
                  if (window.confirm("¿Eliminar esta conversación?")) remove.mutate(current, { onSuccess: () => setCurrent(null) });
                }}>Eliminar</button>
              </span>
            )
          }
          flush
        >
          <div className={styles.thread} aria-live="polite">
            {conversation.isPending && current !== null && <Loading what="la conversación" />}
            {conversation.data?.mensajes.map((m) =>
              m.rol === "usuario" ? (
                <div key={m.id} className={styles.user}>{m.texto}</div>
              ) : (
                <AssistantMessage key={m.id} m={m} />
              ),
            )}
            {pending && (
              <>
                <div className={styles.user}>{pending}</div>
                <div className={styles.thinking}>Buscando en el repositorio y redactando la respuesta…</div>
              </>
            )}
            {!pending && !conversation.data?.mensajes.length && (
              <div className="stack" style={{ gap: 8 }}>
                <div className="small muted">
                  Pregunte por manejo agronómico (responde con las guías y tesis) o por límites, registros y carencias (responde
                  con el núcleo exacto). Las preguntas de seguimiento usan lo conversado: «¿y en palto?».
                </div>
                <div className={styles.examples}>
                  {EXAMPLES.map((e) => (
                    <button key={e} type="button" className={styles.example} disabled={ask.isPending} onClick={() => send(e)}>{e}</button>
                  ))}
                </div>
              </div>
            )}
            <ErrorNote error={ask.error ?? conversation.error} />
            <div ref={bottom} />
          </div>
          <div className={styles.composer}>
            <label className="field">
              <span>Pregunta</span>
              <textarea
                value={question}
                maxLength={1000}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  // Enter sends; Shift+Enter starts a new line (Ctrl+Enter also sends, as in the rest of the app)
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="Escriba su pregunta (Mayús+Enter para una línea nueva)"
              />
            </label>
            <div className="stack" style={{ gap: 4, alignItems: "flex-end" }}>
              <button type="button" className="btn btn-primary" disabled={question.trim().length < 3 || ask.isPending} onClick={() => send()}>
                Preguntar <kbd>↵</kbd>
              </button>
              <span className={styles.hint}>Responde solo con los documentos y el núcleo exacto</span>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
