"""The language model with the exact core's tools (stage 5), as a LangGraph state graph: Qwen3-8B (or any model behind
Ollama's native chat API) asks for tools, the code runs them, and the model writes the answer from their results. The
model never computes a limit or an interval itself: the values come from the graph through ``Herramientas``.

    modelo ──(pide herramientas)──> herramientas ──> modelo
       │──(respondió sin consultar nada, primera vez)──> insistir ──> modelo
       │──(respondió con un valor que ninguna herramienta devolvió, primera vez)──> corregir ──> modelo
       └──(respondió)──> fin

Every call and its result are kept in the state, so the answer can be checked against what the tools returned (a
value no tool gave is an invented one). The final answer is a ``RespuestaAgente``: its text and the passages and graph
rows it cites, keeping only citations to something that was actually consulted.

Since 27/11/2026 two checks run on the answer (assistant/orchestration/verificacion.py): the output guard above, and,
when a verifier model is configured, a sentence check that keeps only the sentences the cited evidence supports."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import TypedDict

import httpx
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from .tools import DEFINICIONES, DEFINICIONES_GENERICAS, DOCUMENTOS, BuscarDocumentosIn, Herramientas
from .verificacion import Juez, juzgar, oraciones, valores_sin_respaldo

SISTEMA = """Eres el asistente de cumplimiento fitosanitario de una agroexportadora peruana (arándano, palto y uva de mesa).
Hoy es {hoy}.
Para límites máximos de residuos (LMR), registros en el SENASA, periodos de carencia y grupos de modo de acción usa SIEMPRE
las herramientas: nunca des un valor de memoria. Si una herramienta responde «error» o «sin_dato», dilo tal cual y no
completes el dato por tu cuenta.
Responde en español y en pocas líneas. Primero el dato pedido con su unidad; si la pregunta es de sí o no, empieza con
«Sí» o «No». Después la fuente entre corchetes, copiada del resultado de la herramienta: [norma o registro, desde AAAA-MM-DD].{formato}"""

COMPLETO = """Eres el asistente técnico y de cumplimiento fitosanitario de una agroexportadora peruana (arándano, palto y
uva de mesa). Hoy es {hoy}.
Tienes dos clases de herramientas:
- Las del núcleo exacto (limite_maximo, historial_limite, comparar_mercados, registro_producto, carencia,
  grupo_modo_accion{genericas}): para cualquier límite, registro, carencia o modo de acción. Cada resultado trae un «id»
  (G1, G2…).
- buscar_documentos: guías del SENASA, manuales y tesis, para manejo agronómico, plagas y su control. Devuelve pasajes
  numerados (1, 2…).
Si la pregunta tiene una parte de cumplimiento y otra agronómica, usa las dos clases. Nunca des un valor de cumplimiento
de memoria ni una recomendación sin un pasaje que la respalde. Si una herramienta responde «error» o «sin_dato», dilo.
Responde en español, claro y breve. Cita cada dato justo después de darlo: [G1] para una fila del núcleo exacto y [1], [2]
para los pasajes. Si ninguna herramienta respalda la respuesta, dilo en lugar de responder.{formato}"""

# with the list and count tools only (27/11/2026): a «cuántos» or «cuáles» question is not a yes/no one
FORMATO_LISTAS = """
Si la pregunta pide cuáles, nombra cada uno; si pide cuántos, da el número. Una pregunta que empieza con «cuántos» o
«cuáles» no es de sí o no."""

SIN_HERRAMIENTAS = """Eres el asistente de cumplimiento fitosanitario de una agroexportadora peruana (arándano, palto y uva de mesa).
Hoy es {hoy}.
Responde en español y en pocas líneas. Primero el dato pedido con su unidad; si la pregunta es de sí o no, empieza con
«Sí» o «No». Si no lo sabes con certeza, dilo."""

# si el modelo responde sin haber consultado ninguna herramienta, se le pide una vez que lo haga (no se acepta un valor
# de memoria en una pregunta de cumplimiento)
INSISTIR = "No consultaste ninguna herramienta. Usa la herramienta que corresponda para obtener el dato y responde con su resultado."

# guarda de salida: un valor con unidad que ninguna herramienta devolvió se devuelve al modelo una vez
CORREGIR = ("Tu respuesta da {valores} y ese valor no aparece en los resultados de las herramientas. Responde de nuevo "
            "usando solo los valores que devolvieron las herramientas, tal como aparecen, con su fuente.")

# D2 (27/11/2026): una búsqueda por cada parte de la pregunta; una sola búsqueda no trae el segundo documento
POR_PARTES = """
Si la pregunta relaciona dos temas (por ejemplo, una plaga y otra, un producto y un cultivo, o una práctica y su
efecto), usa buscar_documentos una vez para cada tema, con una consulta corta para cada uno, antes de responder. Si
de una de las partes no encuentras pasajes, dilo en lugar de completarla."""

# lo que se muestra cuando la verificación por oraciones no deja ninguna oración respaldada
SIN_RESPALDO = "No encontré evidencia suficiente en los documentos consultados para responder esta pregunta."

CITA_DOC = re.compile(r"\[(\d{1,2})\]")
CITA_GRAFO = re.compile(r"\[(G\d{1,2})\]")


class RespuestaAgente(BaseModel):
    """The final answer, formalized: its text and what it cites, limited to what was actually consulted."""
    texto: str
    citas_documentos: list[int] = Field(default_factory=list)     # números de pasaje (1, 2…)
    citas_grafo: list[str] = Field(default_factory=list)          # ids de filas del núcleo exacto (G1, G2…)

    @classmethod
    def desde_texto(cls, texto: str, n_pasajes: int, ids_filas: set[str]) -> RespuestaAgente:
        docs = sorted({int(n) for n in CITA_DOC.findall(texto) if 1 <= int(n) <= n_pasajes})
        grafo = sorted({g for g in CITA_GRAFO.findall(texto) if g in ids_filas}, key=lambda g: int(g[1:]))
        return cls(texto=texto, citas_documentos=docs, citas_grafo=grafo)


@dataclass
class Respuesta:
    texto: str
    llamadas: list[dict] = field(default_factory=list)       # {nombre, argumentos, resultado}
    pasajes: list = field(default_factory=list)              # los de buscar_documentos, numerados 1, 2… en orden
    filas: list[dict] = field(default_factory=list)          # resultados del núcleo exacto con su id G1, G2…
    citas: RespuestaAgente | None = None
    rondas: int = 0
    segundos: float = 0.0
    tokens: dict = field(default_factory=dict)
    corregido: list[float] = field(default_factory=list)     # valores que la guarda de salida devolvió al modelo
    texto_sin_verificar: str | None = None                   # la respuesta antes de la verificación por oraciones
    retiradas: list[dict] = field(default_factory=list)      # oraciones retiradas, con su etiqueta
    evidencia_sin_verificar: list[dict] = field(default_factory=list)   # lo que citaba la respuesta original


class Estado(TypedDict):
    mensajes: list[dict]
    ultimo: dict
    rondas: int
    insistido: bool
    corregido: list[float]
    llamadas: list[dict]
    pasajes: list
    filas: list[dict]
    entrada: int
    salida: int


class Agente:
    def __init__(self, base_url: str, model: str, herramientas: Herramientas | None, temperature: float = 0.0,
                 max_rondas: int = 4, num_predict: int = 1024, timeout_s: float = 300, documentos=None,
                 pasajes_por_busqueda: int = 6, caracteres_por_pasaje: int = 1200, guarda: bool = True,
                 guarda_valores: bool = True, verificador: Juez | None = None, por_partes: bool = False,
                 seed: int | None = None, genericas: bool = False):
        """``herramientas=None`` is the baseline: the same model and prompt style, answering from memory.
        ``documentos``: a function (consulta) -> list of passages; with it, the agent also has ``buscar_documentos``
        and the graph results get an id to cite (G1, G2…), which is how the assistant uses it.
        ``guarda=False`` is the ablation of the guard: an answer given without consulting is accepted as it is.
        ``guarda_valores``: the output guard (a value no tool returned goes back to the model once).
        ``verificador``: a model that labels each sentence of the final answer against what it cites; only supported
        sentences are kept (with ``documentos`` only, where answers are written from passages).
        ``seed``: Ollama's sampling seed, the same in every call, so that with temperature 0 the same question over the
        same graph and passages gives the same answer (measured with ``repetibilidad-s2``).
        ``genericas``: also the list and count tools (productos_para_plaga, ingredientes_sin_limite; 27/11/2026)."""
        self.url = base_url.rstrip("/").removesuffix("/v1") + "/api/chat"
        self.model, self.h, self.guarda = model, herramientas, guarda
        self.guarda_valores, self.verificador, self.por_partes = guarda_valores, verificador, por_partes
        self.temperature, self.max_rondas, self.num_predict, self.seed = temperature, max_rondas, num_predict, seed
        self.documentos, self.k_pasajes, self.max_chars = documentos, pasajes_por_busqueda, caracteres_por_pasaje
        self.http = httpx.Client(timeout=timeout_s)
        self.genericas = genericas
        self.tools = (DEFINICIONES + (DEFINICIONES_GENERICAS if genericas else []) + ([DOCUMENTOS] if documentos else [])
                      if herramientas else None)
        self.grafo = self._construir()

    # --- el grafo de estados ------------------------------------------------------------------------------------------
    def _construir(self):
        g = StateGraph(Estado)
        g.add_node("modelo", self._modelo)
        g.add_node("herramientas", self._herramientas)
        g.add_node("insistir", self._insistir)
        g.add_node("corregir", self._corregir)
        g.set_entry_point("modelo")
        g.add_conditional_edges("modelo", self._ruta, {"herramientas": "herramientas", "insistir": "insistir",
                                                       "corregir": "corregir", "fin": END})
        g.add_edge("herramientas", "modelo")
        g.add_edge("insistir", "modelo")
        g.add_edge("corregir", "modelo")
        return g.compile()

    def _modelo(self, s: Estado) -> dict:
        cuerpo = {"model": self.model, "stream": False, "think": False, "messages": s["mensajes"],
                  "options": {"temperature": self.temperature, "num_predict": self.num_predict}}
        if self.seed is not None:
            cuerpo["options"]["seed"] = self.seed
        if self.tools:
            cuerpo["tools"] = self.tools
        resp = self.http.post(self.url, json=cuerpo)
        resp.raise_for_status()
        data = resp.json()
        msg = data["message"]
        nuevo = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            nuevo["tool_calls"] = msg["tool_calls"]
        return {"ultimo": msg, "mensajes": s["mensajes"] + [nuevo], "rondas": s["rondas"] + 1,
                "entrada": s["entrada"] + (data.get("prompt_eval_count") or 0),
                "salida": s["salida"] + (data.get("eval_count") or 0)}

    def _ruta(self, s: Estado) -> str:
        if s["rondas"] >= self.max_rondas:
            return "fin"
        if self.h and s["ultimo"].get("tool_calls"):
            return "herramientas"
        if self.h and self.guarda and not s["llamadas"] and not s["insistido"]:
            return "insistir"
        if (self.h and self.guarda_valores and s["llamadas"] and not s["corregido"]
                and valores_sin_respaldo(s["ultimo"].get("content") or "", s["llamadas"])):
            return "corregir"
        return "fin"

    def _insistir(self, s: Estado) -> dict:
        return {"mensajes": s["mensajes"] + [{"role": "user", "content": INSISTIR}], "insistido": True}

    def _corregir(self, s: Estado) -> dict:
        valores = valores_sin_respaldo(s["ultimo"].get("content") or "", s["llamadas"])
        texto = ", ".join(f"{v:g}" for v in valores)
        return {"mensajes": s["mensajes"] + [{"role": "user", "content": CORREGIR.format(valores=texto)}],
                "corregido": valores}

    def _verificar(self, texto: str, pasajes: list, filas: list[dict]) -> tuple[str, list[dict], list[dict]]:
        """Keeps the sentences of the answer that the cited passages and rows support, as the verifier labels them.
        Also returns what the original answer cited, so the evaluation can grade it next to the verified one."""
        citas = RespuestaAgente.desde_texto(texto, len(pasajes), {f["id"] for f in filas})
        citada = [{"ref": f"[{n}]", "doc_id": getattr(pasajes[n - 1], "doc_id", None),
                   "chunk_id": getattr(pasajes[n - 1], "chunk_id", None), "texto": pasajes[n - 1].text}
                  for n in citas.citas_documentos]
        citada += [{"ref": f"[{f['id']}]", "doc_id": None, "chunk_id": None,
                    "texto": json.dumps(f["resultado"], ensure_ascii=False)} for f in filas if f["id"] in citas.citas_grafo]
        frases = oraciones(texto)
        if not frases or not citada:
            return texto, [], citada
        etiquetas = juzgar(self.verificador, frases, [f"{e['ref']} {e['texto']}" for e in citada])
        retiradas = [{"oracion": f, "etiqueta": e} for f, e in zip(frases, etiquetas) if e != "respaldada"]
        if not retiradas:
            return texto, [], citada
        quedan = [f for f, e in zip(frases, etiquetas) if e == "respaldada"]
        return (" ".join(quedan) if quedan else SIN_RESPALDO), retiradas, citada

    def _herramientas(self, s: Estado) -> dict:
        mensajes, llamadas = list(s["mensajes"]), list(s["llamadas"])
        pasajes, filas = list(s["pasajes"]), list(s["filas"])
        for c in s["ultimo"].get("tool_calls") or []:
            f = c.get("function", {})
            nombre, args = f.get("name", ""), f.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            resultado = self._ejecutar(nombre, args, pasajes, filas)
            llamadas.append({"nombre": nombre, "argumentos": args, "resultado": resultado})
            mensajes.append({"role": "tool", "tool_name": nombre, "content": json.dumps(resultado, ensure_ascii=False)})
        return {"mensajes": mensajes, "llamadas": llamadas, "pasajes": pasajes, "filas": filas}

    def _ejecutar(self, nombre: str, args: dict, pasajes: list, filas: list) -> dict:
        if nombre == "buscar_documentos" and self.documentos:
            try:
                consulta = BuscarDocumentosIn.model_validate(args).consulta
            except ValueError:
                return {"error": "argumentos inválidos para buscar_documentos",
                        "detalles": [{"campo": "consulta", "problema": "falta lo que hay que buscar"}]}
            encontrados = list(self.documentos(consulta))[: self.k_pasajes]
            if not encontrados:
                return {"sin_dato": "no hay pasajes que respondan esta búsqueda"}
            salida = []
            for p in encontrados:
                pasajes.append(p)
                salida.append({"n": len(pasajes), "documento": p.title, "seccion": " > ".join(p.section),
                               "paginas": p.pages, "texto": p.text[: self.max_chars]})
            return {"pasajes": salida}
        resultado = self.h.llamar(nombre, args)
        if self.documentos and "error" not in resultado:            # en el asistente, cada fila se cita por su id
            resultado = {"id": f"G{len(filas) + 1}", **resultado}
            filas.append({"id": resultado["id"], "herramienta": nombre, "argumentos": args, "resultado": resultado})
        return resultado

    # --- uso ----------------------------------------------------------------------------------------------------------
    def responder(self, pregunta: str, hoy: date | None = None) -> Respuesta:
        t0 = time.perf_counter()
        plantilla = COMPLETO if self.documentos else (SISTEMA if self.h else SIN_HERRAMIENTAS)
        sistema = plantilla.format(hoy=(hoy or date.today()).isoformat(),
                                   genericas=", productos_para_plaga, ingredientes_sin_limite" if self.genericas else "",
                                   formato=FORMATO_LISTAS if self.genericas else "")
        if self.por_partes and self.documentos:
            sistema += POR_PARTES
        inicial: Estado = {"mensajes": [{"role": "system", "content": sistema}, {"role": "user", "content": pregunta}],
                           "ultimo": {}, "rondas": 0, "insistido": False, "corregido": [], "llamadas": [], "pasajes": [],
                           "filas": [], "entrada": 0, "salida": 0}
        s = self.grafo.invoke(inicial, {"recursion_limit": 3 * self.max_rondas + 8})
        texto = (s["ultimo"].get("content") or "").strip() if not s["ultimo"].get("tool_calls") else ""
        texto = texto or "No llegué a una respuesta en las rondas permitidas."
        original, retiradas, citada = None, [], []
        if self.verificador is not None and self.documentos:
            original = texto
            texto, retiradas, citada = self._verificar(texto, s["pasajes"], s["filas"])
        return Respuesta(texto=texto, llamadas=s["llamadas"], pasajes=s["pasajes"], filas=s["filas"],
                         citas=RespuestaAgente.desde_texto(texto, len(s["pasajes"]), {f["id"] for f in s["filas"]}),
                         rondas=s["rondas"], segundos=round(time.perf_counter() - t0, 2),
                         tokens={"entrada": s["entrada"], "salida": s["salida"]}, corregido=s["corregido"],
                         texto_sin_verificar=original if retiradas else None, retiradas=retiradas,
                         evidencia_sin_verificar=citada if retiradas else [])
