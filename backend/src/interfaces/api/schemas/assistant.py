"""Shapes of the assistant endpoints: single questions, conversations with their messages, and the corpus counter."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class QuestionIn(BaseModel):
    pregunta: str = Field(min_length=3, max_length=1000)


class CitationOut(BaseModel):
    n: int
    chunk_id: str
    doc_id: str
    titulo: str
    fuente: str
    nivel: str
    url: str
    seccion: list[str]
    paginas: list[int]
    texto: str


class AnswerOut(BaseModel):
    pregunta: str
    respuesta: str
    evidencia: bool
    citas: list[CitationOut]
    traza: dict
    filas_grafo: list[dict] = []          # etapa 5: filas del núcleo exacto citadas como [G1]…


class ConversationIn(BaseModel):
    titulo: str = Field(default="", max_length=120)


class MessageOut(BaseModel):
    id: int
    rol: str
    texto: str
    evidencia: bool | None
    citas: list[CitationOut]
    traza: dict
    creado: datetime


class ConversationSummaryOut(BaseModel):
    id: int
    titulo: str
    creado: datetime
    actualizado: datetime
    preguntas: int


class ConversationOut(BaseModel):
    id: int
    titulo: str
    creado: datetime
    actualizado: datetime
    mensajes: list[MessageOut]


class TurnOut(BaseModel):
    """One exchange: the user's message as stored and the assistant's answer."""

    pregunta: MessageOut
    respuesta: MessageOut


class CorpusDocumentOut(BaseModel):
    doc_id: str
    fuente: str
    nivel: str
    titulo: str
    anio: str | None
    tipo: str | None
    licencia: str
    url: str
    estado: str
    motivo: str
    paginas: int | None
    formato: str | None
    actualizado: datetime


class CorpusStatusOut(BaseModel):
    documentos: list[CorpusDocumentOut]
    resumen: dict
