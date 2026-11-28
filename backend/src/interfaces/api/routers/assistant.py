"""The assistant over the document corpus (HU0012).

- ``POST /consulta``: one question, one cited answer, nothing stored but the activity entry.
- Conversations: several questions with their history. Each turn rewrites a follow-up question as a standalone query
  with the previous messages, retrieves, and answers with the recent history as context; both messages are stored with
  the answer's citations and trace.

The answerer (encoder, index signature, generator) is built once per process from config/assistant.yaml."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from assistant.answer import Answerer, AnswerResult, build_answerer
from knowledge.corpus.store import CorpusStore, connect, migrate

from ..schemas.assistant import (
    AnswerOut,
    CitationOut,
    ConversationIn,
    ConversationOut,
    ConversationSummaryOut,
    CorpusDocumentOut,
    CorpusStatusOut,
    MessageOut,
    QuestionIn,
    TurnOut,
)
from ..security import AccountsDep, UserDep

router = APIRouter(tags=["asistente"])


@lru_cache
def corpus_store() -> CorpusStore:
    conn = connect()
    migrate(conn)
    return CorpusStore(conn)


@lru_cache
def answerer() -> Answerer:
    return build_answerer(corpus_store())


def get_answerer() -> Answerer:
    try:
        return answerer()
    except RuntimeError as e:          # no index yet
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


AnswererDep = Annotated[Answerer, Depends(get_answerer)]
StoreDep = Annotated[CorpusStore, Depends(corpus_store)]


def _citations(result: AnswerResult) -> list[dict]:
    return [CitationOut(n=c.n, chunk_id=c.chunk_id, doc_id=c.doc_id, titulo=c.title, fuente=c.source, nivel=c.level,
                        url=c.url, seccion=c.section, paginas=c.pages, texto=c.text).model_dump() for c in result.citations]


@router.post("/consulta", response_model=AnswerOut, summary="Una pregunta suelta con respuesta citada")
def ask(body: QuestionIn, principal: UserDep, acc: AccountsDep, assistant: AnswererDep):
    result = assistant.answer(body.pregunta.strip())
    acc.audit(principal.user.id, "consulta", {"pregunta": result.question[:300], "evidencia": result.evidence,
                                              "citas": [c.doc_id for c in result.citations]})
    return AnswerOut(pregunta=result.question, respuesta=result.text, evidencia=result.evidence,
                     citas=_citations(result), traza=result.trace, filas_grafo=result.graph_rows)


# conversations ------------------------------------------------------------------------------------------------------

@router.get("/conversaciones", response_model=list[ConversationSummaryOut], summary="Mis conversaciones")
def list_conversations(principal: UserDep, acc: AccountsDep):
    return acc.conversations(principal.user.id)


@router.post("/conversaciones", response_model=ConversationOut, status_code=201, summary="Nueva conversación")
def new_conversation(body: ConversationIn, principal: UserDep, acc: AccountsDep):
    row = acc.create_conversation(principal.user.id, body.titulo or "Conversación nueva")
    return {**row, "mensajes": []}


@router.get("/conversaciones/{conversation_id}", response_model=ConversationOut, summary="Una conversación con sus mensajes")
def get_conversation(conversation_id: int, principal: UserDep, acc: AccountsDep):
    return acc.conversation(principal.user.id, conversation_id)


@router.patch("/conversaciones/{conversation_id}", response_model=ConversationSummaryOut, summary="Renombrar")
def rename_conversation(conversation_id: int, body: ConversationIn, principal: UserDep, acc: AccountsDep):
    acc.rename_conversation(principal.user.id, conversation_id, body.titulo or "Conversación")
    return next(c for c in acc.conversations(principal.user.id) if c["id"] == conversation_id)


@router.delete("/conversaciones/{conversation_id}", status_code=204, summary="Eliminar una conversación")
def delete_conversation(conversation_id: int, principal: UserDep, acc: AccountsDep):
    acc.delete_conversation(principal.user.id, conversation_id)


@router.post("/conversaciones/{conversation_id}/mensajes", response_model=TurnOut,
             summary="Preguntar dentro de una conversación (usa el historial)")
def ask_in_conversation(conversation_id: int, body: QuestionIn, principal: UserDep, acc: AccountsDep,
                        assistant: AnswererDep):
    uid = principal.user.id
    conv = acc.conversation(uid, conversation_id)
    history = [(m["rol"], m["texto"]) for m in conv["mensajes"]]
    question = body.pregunta.strip()
    result = assistant.answer(question, history)
    asked = acc.add_message(uid, conversation_id, "usuario", question)
    answered = acc.add_message(uid, conversation_id, "asistente", result.text, result.evidence, _citations(result),
                               result.trace)
    if not conv["mensajes"] and conv["titulo"] in ("Conversación nueva", "Conversación"):
        acc.rename_conversation(uid, conversation_id, question[:80])
    acc.audit(uid, "consulta", {"conversacion_id": conversation_id, "pregunta": question[:300],
                                "evidencia": result.evidence, "citas": [c.doc_id for c in result.citations]})
    return TurnOut(pregunta=MessageOut(**asked), respuesta=MessageOut(**answered))


# corpus --------------------------------------------------------------------------------------------------------------

@router.get("/corpus", response_model=CorpusStatusOut, summary="Documentos del corpus y su estado")
def corpus_status(st: StoreDep):
    keep = set(CorpusDocumentOut.model_fields)
    docs = [{k: v for k, v in r.items() if k in keep} for r in st.documents()]
    return CorpusStatusOut(documentos=[CorpusDocumentOut(**d) for d in docs], resumen=st.status())
