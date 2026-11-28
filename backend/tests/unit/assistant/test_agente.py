"""The LangGraph agent against a scripted Ollama: the guard that insists, a tool call, and citations limited to what
was consulted. No GPU and no graph needed."""
import json

import httpx

from assistant.orchestration.agente import Agente, RespuestaAgente


class _Herramientas:
    def __init__(self):
        self.vistas = []

    def llamar(self, nombre, args):
        self.vistas.append((nombre, args))
        return {"vigentes": [{"valor_mg_kg": 0.05, "norma": "Reg. (EU) 2023/1719"}]}


class _Pasaje:
    def __init__(self, t):
        self.title, self.section, self.pages, self.text = "Guía", ["Plagas"], [3], t


def _ollama(guion):
    """An Ollama that answers the scripted messages in order and records every request."""
    pedidos = []

    def responder(request):
        pedidos.append(json.loads(request.content))
        return httpx.Response(200, json={"message": guion[len(pedidos) - 1], "prompt_eval_count": 10, "eval_count": 5})
    return httpx.Client(transport=httpx.MockTransport(responder)), pedidos


def _agente(guion, **kw):
    a = Agente("http://ollama.test/v1", "qwen3:8b", _Herramientas(), **kw)
    a.http, pedidos = _ollama(guion)
    return a, pedidos


def test_insists_once_when_the_model_answers_without_tools():
    llamada = {"function": {"name": "limite_maximo", "arguments": {"ingrediente": "x", "cultivo": "palto", "mercado": "UE"}}}
    a, pedidos = _agente([{"content": "0,1 mg/kg"}, {"content": "", "tool_calls": [llamada]}, {"content": "0,05 mg/kg"}])
    r = a.responder("¿LMR?")
    assert r.texto == "0,05 mg/kg" and r.rondas == 3
    assert a.h.vistas == [("limite_maximo", llamada["function"]["arguments"])]
    assert "No consultaste" in pedidos[1]["messages"][-1]["content"]          # la insistencia
    assert pedidos[2]["messages"][-1]["role"] == "tool"                       # el resultado vuelve al modelo


def test_without_the_guard_an_answer_without_tools_is_accepted():
    a, pedidos = _agente([{"content": "0,1 mg/kg"}], guarda=False)
    r = a.responder("¿LMR?")
    assert r.texto == "0,1 mg/kg" and r.rondas == 1 and len(pedidos) == 1 and r.llamadas == []


def test_without_tools_it_does_not_insist():
    a = Agente("http://ollama.test/v1", "qwen3:8b", None)
    a.http, pedidos = _ollama([{"content": "No lo sé."}])
    assert a.responder("¿LMR?").texto == "No lo sé." and len(pedidos) == 1 and "tools" not in pedidos[0]


def test_assistant_mode_numbers_rows_and_passages_and_keeps_only_real_citations():
    llamadas = [{"function": {"name": "limite_maximo", "arguments": {"ingrediente": "x", "cultivo": "palto", "mercado": "UE"}}},
                {"function": {"name": "buscar_documentos", "arguments": {"consulta": "control de oídio"}}}]
    a, _ = _agente([{"content": "", "tool_calls": llamadas}, {"content": "0,05 mg/kg [G1]; azufre [2] y [9] [G7]"}],
                   documentos=lambda q: [_Pasaje("uno"), _Pasaje("dos")])
    r = a.responder("¿LMR y control?")
    assert [f["id"] for f in r.filas] == ["G1"] and len(r.pasajes) == 2
    assert r.citas == RespuestaAgente(texto=r.texto, citas_documentos=[2], citas_grafo=["G1"])   # [9] y [G7] no existen


def test_invalid_document_search_comes_back_as_a_field_error():
    a, _ = _agente([{"content": "", "tool_calls": [{"function": {"name": "buscar_documentos", "arguments": {}}}]},
                    {"content": "No hay respaldo."}], documentos=lambda q: [])
    r = a.responder("?")
    assert r.llamadas[0]["resultado"]["detalles"][0]["campo"] == "consulta"


# --- checks on the answer (27/11/2026) -----------------------------------------------------------------------------
_LLAMADA = {"function": {"name": "limite_maximo", "arguments": {"ingrediente": "x", "cultivo": "palto", "mercado": "UE"}}}


def test_output_guard_sends_back_a_value_no_tool_returned_once():
    # the tool returns 0.05; the model writes 0.01 from memory, is sent back once, and then copies the tool's value
    a, pedidos = _agente([{"content": "", "tool_calls": [_LLAMADA]}, {"content": "0,01 mg/kg"},
                          {"content": "0,05 mg/kg [Reg. (EU) 2023/1719]"}])
    r = a.responder("¿LMR?")
    assert r.texto.startswith("0,05 mg/kg") and r.corregido == [0.01]
    assert "0.01" in pedidos[2]["messages"][-1]["content"] and "no aparece" in pedidos[2]["messages"][-1]["content"]


def test_output_guard_sends_back_only_once_and_can_be_switched_off():
    a, pedidos = _agente([{"content": "", "tool_calls": [_LLAMADA]}, {"content": "0,01 mg/kg"}, {"content": "0,02 mg/kg"}])
    assert a.responder("¿LMR?").texto == "0,02 mg/kg" and len(pedidos) == 3
    a, pedidos = _agente([{"content": "", "tool_calls": [_LLAMADA]}, {"content": "0,01 mg/kg"}], guarda_valores=False)
    assert a.responder("¿LMR?").texto == "0,01 mg/kg" and len(pedidos) == 2


class _Verificador:
    def __init__(self, etiquetas):
        self.etiquetas, self.vistos = etiquetas, []

    def chat(self, system, prompt):
        self.vistos.append(prompt)
        return json.dumps({"veredictos": [{"i": i, "v": v} for i, v in enumerate(self.etiquetas, 1)]})


def test_sentence_check_keeps_only_supported_sentences():
    buscar = {"function": {"name": "buscar_documentos", "arguments": {"consulta": "oídio"}}}
    v = _Verificador(["respaldada", "ausente", "respaldada"])
    a, _ = _agente([{"content": "", "tool_calls": [buscar]},
                    {"content": "El azufre controla el oídio [1]. Se aplica cada 3 días en verano. Rige en floración [2]."}],
                   documentos=lambda q: [_Pasaje("azufre contra oídio"), _Pasaje("aplicar en floración")], verificador=v)
    r = a.responder("¿Control del oídio?")
    assert r.texto == "El azufre controla el oídio [1]. Rige en floración [2]."
    assert r.retiradas == [{"oracion": "Se aplica cada 3 días en verano.", "etiqueta": "ausente"}]
    assert r.texto_sin_verificar.startswith("El azufre") and "[1] azufre contra oídio" in v.vistos[0]


def test_sentence_check_with_nothing_supported_is_an_abstention():
    buscar = {"function": {"name": "buscar_documentos", "arguments": {"consulta": "oídio"}}}
    a, _ = _agente([{"content": "", "tool_calls": [buscar]}, {"content": "Se aplica cada 3 días en verano [1]."}],
                   documentos=lambda q: [_Pasaje("azufre contra oídio")], verificador=_Verificador(["ausente"]))
    r = a.responder("?")
    assert r.texto.startswith("No encontré evidencia") and r.citas.citas_documentos == []
