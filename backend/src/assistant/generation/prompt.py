"""Instructions and prompts for a cited answer (HU0012), single question or within a conversation.

The generator writes only from the numbered passages, marks every statement with the passage it comes from, and says
so when the passages do not answer. The conversation history only tells it what the question refers to («¿y en
palto?»); facts still come from the passages. Limits, registrations and pre-harvest intervals are decided by the exact
rules, not by text: when asked, the answer points to the compliance module.

In a conversation, the last question is first rewritten as a standalone search query (``CONDENSE``), so retrieval
searches «control de Botrytis en palto» instead of «¿y en palto?»."""
from __future__ import annotations

from assistant.retrieval.search import Passage

NO_EVIDENCE = "No encontré evidencia suficiente en el repositorio documental para responder esta pregunta."

SYSTEM = f"""Eres el asistente técnico de una agroexportadora peruana. Respondes preguntas de manejo de cultivos y de
sanidad vegetal usando solo los pasajes numerados que recibes de su repositorio documental.

Reglas:
1. Usa únicamente la información de los pasajes. No agregues conocimiento propio.
2. Después de cada afirmación escribe entre corchetes el número del pasaje que la respalda, por ejemplo [2] o [1][3].
3. Si los pasajes responden solo una parte de la pregunta, responde esa parte con sus citas y di brevemente qué no
   cubren. Solo si ningún pasaje trata el tema de la pregunta, responde exactamente: «{NO_EVIDENCE}»
4. No des límites máximos de residuos, registros de productos ni periodos de carencia como dato vigente: esos valores
   los calcula el módulo de cumplimiento con las fuentes oficiales. Si la pregunta los pide, dilo y remite a ese módulo.
5. La conversación previa, si la hay, solo sirve para entender a qué se refiere la pregunta. Los datos salen de los
   pasajes de esta respuesta, no de respuestas anteriores.
6. Responde en español, de forma breve y concreta, en párrafos cortos o en una lista si hay pasos. Escribe texto
   simple: sin negritas ni cursivas; para una lista, empieza cada elemento con «- ».
7. No menciones estas reglas ni su número; los corchetes son solo para los pasajes."""

CONDENSE = """Reescribe la última pregunta del usuario como una consulta de búsqueda autónoma en español. Incluye el
cultivo, la plaga, el producto o el tema que se deduzcan de la conversación. No respondas la pregunta: devuelve solo
la consulta, en una línea, sin comillas."""


def history_text(history: list[tuple[str, str]], max_chars: int) -> str:
    """Most recent turns first kept, then shown in order; assistant answers lose their citation marks."""
    lines, used = [], 0
    for role, text in reversed(history):
        who = "Usuario" if role == "usuario" else "Asistente"
        line = f"{who}: {' '.join(text.split())}"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(reversed(lines))


def condense_prompt(question: str, history: list[tuple[str, str]], max_chars: int) -> str:
    return f"Conversación:\n{history_text(history, max_chars)}\n\nÚltima pregunta: {question}"


def build_prompt(question: str, passages: list[Passage], history: list[tuple[str, str]] | None = None,
                 max_history_chars: int = 3000) -> str:
    blocks = []
    for n, p in enumerate(passages, start=1):
        where = " > ".join(p.section) or "sin sección"
        pages = f", p. {', '.join(map(str, p.pages))}" if p.pages else ""
        body = p.context or p.text
        blocks.append(f"[{n}] {p.title} ({where}{pages})\n{body}")
    previous = f"Conversación previa:\n{history_text(history, max_history_chars)}\n\n" if history else ""
    return previous + "Pasajes:\n\n" + "\n\n".join(blocks) + f"\n\nPregunta: {question}"
