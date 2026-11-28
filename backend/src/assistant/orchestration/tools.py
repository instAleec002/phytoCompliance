"""Tools over the exact core (stage 5): what the language model can ask the graph and the rules instead of answering
from memory or from passages. Each tool resolves the names a question uses (Spanish or English ingredient names, the
crop, the market, a product's trade name) to graph keys, runs the same queries and rules as the API, and returns a
small dict with the value and its source (regulation, date, snapshot), so the answer can cite it as a graph row.

A tool never guesses: when a name does not resolve, or when the graph has no row, it says so («error» or
«sin_dato»), and the model must then say that the exact core has no answer.

``DEFINICIONES`` are the function declarations (JSON Schema) in the format of OpenAI-compatible chat endpoints and
Ollama; ``Herramientas.llamar(nombre, argumentos)`` runs one."""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from knowledge.graph.age import AgeGraph
from knowledge.graph.queries import in_force, mrl_versions
from knowledge.normalization.ingredients import Aliases


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in t).split())


CULTIVOS = {"blueberry": ["arandano", "arandanos", "blueberry", "blueberries", "vaccinium corymbosum"],
            "avocado": ["palto", "palta", "paltas", "aguacate", "avocado", "avocados", "persea americana"],
            "table_grape": ["uva de mesa", "uva", "uvas", "vid", "table grape", "table grapes", "grapes", "vitis vinifera"]}
MERCADOS = {"EU": ["eu", "ue", "union europea", "europa", "european union"],
            "US": ["us", "usa", "eeuu", "ee uu", "estados unidos", "united states", "epa"],
            "CODEX": ["codex", "codex alimentarius", "cxl"]}
NOMBRE_MERCADO = {"EU": "Unión Europea", "US": "Estados Unidos", "CODEX": "Codex Alimentarius"}


def _resolver(tabla: dict[str, list[str]], valor: str) -> str | None:
    n = _norm(valor)
    for clave, nombres in tabla.items():
        if n == _norm(clave) or n in nombres:
            return clave
    return None


def _fecha(valor: str | None) -> str:
    if not valor:
        return date.today().isoformat()
    try:
        return date.fromisoformat(str(valor)[:10]).isoformat()
    except ValueError:
        d, m, a = str(valor).replace("-", "/").split("/")[:3]          # 15/07/2024
        return date(int(a), int(m), int(d)).isoformat()


def _palabras(texto: str) -> list[str]:
    """Spelling-tolerant words of a pest name, four letters or more, plurals as singular («queresas», «botritis»)."""
    from knowledge.programs.resolver import _fonetico, _plano

    singular = (re.sub(r"(?<=[a-z]{4})(es|s)$", "", w) for w in re.sub(r"[^a-z ]", "", _plano(texto)).split())
    return [w for w in (_fonetico(x) for x in singular) if len(w) >= 4]


def _grupo(valor: str) -> tuple[str | None, str]:
    """«FRAC 3», «frac3», «IRAC 4A» or just «3» -> (scheme or None, code)."""
    m = re.match(r"\s*(frac|irac|hrac)?\s*:?\s*([0-9a-z]+)\s*$", str(valor or "").lower())
    if not m:
        return None, str(valor or "").strip().upper()
    return (m.group(1).upper() if m.group(1) else None), m.group(2).upper()


def _version(m: dict) -> dict:
    return {"valor_mg_kg": m.get("value_mg_kg"), "texto_oficial": m.get("value_text"), "residuo": m.get("residue"),
            "norma": m.get("regulation"), "aplica_desde": m.get("applies_from"), "aplica_hasta": m.get("valid_until"),
            "en_limite_de_determinacion": bool(m.get("at_limit_of_determination")), "instantanea": m.get("snapshot")}


class GrafoPorConsulta:
    """The graph opened for each query: the assistant lives as long as the API process, so it does not hold a connection
    (the API opens one per request too)."""

    def run(self, *args, **kwargs):
        with AgeGraph.connect() as g:
            return g.run(*args, **kwargs)


class Herramientas:
    def __init__(self, graph: AgeGraph, aliases: Aliases | None = None, espanol: dict[str, str] | None = None,
                 vocabulario=None):
        """``vocabulario`` (etapa 4, AGROVOC): respaldo para nombres que los alias no llevan a un ingrediente del grafo
        («metaldehído» -> metaldehyde)."""
        self.g = graph
        self.vocabulario = vocabulario
        self._ingredientes: set[str] | None = None
        self.aliases = aliases or Aliases.load()
        # nombres comunes en español -> ISO (el inverso de los que usa la suite estructurada)
        self.espanol = {_norm(es): iso for iso, es in (espanol or {}).items() if es}
        self._productos: list[tuple[str, str, str | None]] | None = None
        self._plagas: list[tuple[str, str, str]] | None = None
        self.interpretado: dict[str, str] = {}      # misspelled name -> ingredient it was read as (27/11/2026)

    # nombres -> claves del grafo ---------------------------------------------------------------------------------
    def ingrediente(self, nombre: str) -> str:
        if _norm(nombre) in self.espanol:
            return self.espanol[_norm(nombre)]
        iso = self.aliases.iso(nombre)
        if self._ingredientes is None:
            self._ingredientes = {r[0] for r in self.g.run("MATCH (i:Ingredient) RETURN i.key")}
        if iso in self._ingredientes:
            return iso
        for termino in (self.vocabulario.find(nombre) if self.vocabulario else []):  # AGROVOC: español, inglés, latín
            if termino.kind == "ingredient":
                return termino.key
        parecido = self._parecido(nombre)
        if parecido:
            self.interpretado[nombre] = parecido
            return parecido
        return iso

    def _parecido(self, nombre: str) -> str | None:
        """A misspelled ingredient («propanoquizafop») read as the one graph ingredient it is close to, in ISO or in
        Spanish: only when one candidate is clearly closer than the next, so a typo never picks between two real
        ingredients (27/11/2026)."""
        import difflib

        from knowledge.programs.resolver import _fonetico

        n = _norm(nombre)
        if len(n) < 6 or not self._ingredientes:
            return None
        nombres = {_norm(k): k for k in self._ingredientes}
        nombres.update({es: iso for es, iso in self.espanol.items() if iso in self._ingredientes})
        # Spanish and English spellings of the same name («clorpirifos», «chlorpyrifos») meet in their phonetic form
        foneticos = {}
        for escrito, clave in nombres.items():
            foneticos.setdefault(_fonetico(escrito), set()).add(clave)
        mismo = foneticos.get(_fonetico(n), set())
        if len(mismo) == 1:
            return next(iter(mismo))
        cerca = difflib.get_close_matches(n, list(nombres), n=2, cutoff=0.88)
        if not cerca:
            return None
        r = lambda x: difflib.SequenceMatcher(None, n, x).ratio()
        if len(cerca) > 1 and nombres[cerca[0]] != nombres[cerca[1]] and r(cerca[0]) - r(cerca[1]) < 0.04:
            return None
        return nombres[cerca[0]]

    def _nota(self, nombre: str) -> dict:
        """What the answer has to say when the name was read as another spelling."""
        if nombre in self.interpretado:
            return {"nombre_interpretado": f"«{nombre}» se leyó como {self.interpretado[nombre]}"}
        return {}

    def producto(self, nombre: str) -> list[tuple[str, str, str | None]]:
        """(key, nombre comercial, número de registro): coincidencia exacta del nombre normalizado; si no hay, los que
        lo contienen."""
        if self._productos is None:
            self._productos = self.g.run("MATCH (p:Product) RETURN p.key, p.trade_name, p.registration_number",
                                         columns=("k", "n", "r"))
        n = _norm(nombre)
        exactos = [p for p in self._productos if _norm(p[1]) == n or p[0] == nombre]
        return exactos or [p for p in self._productos if n and n in _norm(p[1])]

    def plaga(self, nombre: str) -> list[str]:
        if self._plagas is None:
            self._plagas = self.g.run("MATCH (t:Pest) RETURN t.key, t.common_name, t.scientific_name", columns=("k", "c", "s"))
        n = _norm(nombre)
        return [k for k, c, s in self._plagas if n in (_norm(k), _norm(c), _norm(s))]

    # herramientas ------------------------------------------------------------------------------------------------
    def limite_maximo(self, ingrediente: str, cultivo: str, mercado: str, fecha: str | None = None) -> dict:
        crop, market = _resolver(CULTIVOS, cultivo), _resolver(MERCADOS, mercado)
        if not crop or not market:
            return {"error": f"no reconozco el cultivo «{cultivo}» o el mercado «{mercado}»"}
        iso, dia = self.ingrediente(ingrediente), _fecha(fecha)
        vigentes = [m for m in mrl_versions(self.g, iso, crop, market) if in_force(m, dia)]
        base = {"ingrediente": iso, "cultivo": crop, "mercado": NOMBRE_MERCADO[market], "fecha": dia, **self._nota(ingrediente)}
        if not vigentes:
            return {**base, "sin_dato": "el grafo no tiene un límite vigente para esta combinación en esa fecha"}
        return {**base, "vigentes": [_version(m) for m in vigentes],
                "fuente": f"grafo: MrlVersion {market} · {', '.join(sorted({m.get('regulation') or '' for m in vigentes}))}"}

    def historial_limite(self, ingrediente: str, cultivo: str, mercado: str) -> dict:
        crop, market = _resolver(CULTIVOS, cultivo), _resolver(MERCADOS, mercado)
        if not crop or not market:
            return {"error": f"no reconozco el cultivo «{cultivo}» o el mercado «{mercado}»"}
        iso = self.ingrediente(ingrediente)
        vs = mrl_versions(self.g, iso, crop, market)
        if not vs:
            return {"ingrediente": iso, "sin_dato": "el grafo no tiene versiones del límite", **self._nota(ingrediente)}
        return {"ingrediente": iso, "cultivo": crop, "mercado": NOMBRE_MERCADO[market], **self._nota(ingrediente),
                "versiones": [_version(m) for m in vs], "fuente": f"grafo: MrlVersion {market} (nunca sobrescritas)"}

    def comparar_mercados(self, ingrediente: str, cultivo: str, fecha: str | None = None) -> dict:
        filas = {}
        for market in ("EU", "US", "CODEX"):
            r = self.limite_maximo(ingrediente, cultivo, market, fecha)
            vals = [v["valor_mg_kg"] for v in r.get("vigentes", []) if v["valor_mg_kg"] is not None]
            if len(vals) == 1:
                filas[market] = {"valor_mg_kg": vals[0], "norma": r["vigentes"][0]["norma"]}
        if not filas:
            return {"sin_dato": "ningún mercado tiene un único límite vigente para esta combinación"}
        estricto = min(filas, key=lambda k: filas[k]["valor_mg_kg"])
        return {"ingrediente": self.ingrediente(ingrediente), "fecha": _fecha(fecha), **self._nota(ingrediente),
                "por_mercado": {NOMBRE_MERCADO[k]: v for k, v in filas.items()},
                "mas_estricto": NOMBRE_MERCADO[estricto], "fuente": "grafo: MrlVersion vigentes por mercado"}

    def registro_producto(self, producto: str, cultivo: str, plaga: str | None = None) -> dict:
        crop = _resolver(CULTIVOS, cultivo)
        prods = self.producto(producto)
        if not crop:
            return {"error": f"no reconozco el cultivo «{cultivo}»"}
        if not prods:
            return {"error": f"no hay un producto «{producto}» en el registro del SENASA cargado"}
        if len(prods) > 1:
            return {"error": "el nombre coincide con varios productos", "candidatos": [p[1] for p in prods[:8]]}
        key, nombre, numero = prods[0]
        filas = self.g.run(
            "MATCH (a:Authorization)-[:OF_PRODUCT]->(:Product {key: $p}), (a)-[:ON_CROP]->(c:Crop), (a)-[:AGAINST]->(t:Pest) "
            "RETURN c.key, t.key, t.common_name, t.scientific_name, a.preharvest_interval_days",
            {"p": key}, columns=("c", "t", "tc", "ts", "phi"))
        en_cultivo = [f for f in filas if f[0] == crop]
        plagas = self.plaga(plaga) if plaga else []
        if plaga and plagas:
            en_cultivo_plaga = [f for f in en_cultivo if f[1] in plagas]
        else:
            en_cultivo_plaga = en_cultivo
        return {"producto": nombre, "numero_registro": numero, "cultivo": crop,
                "registrado": bool(en_cultivo_plaga),
                "plagas_autorizadas_en_el_cultivo": sorted({f"{f[2]} ({f[3]})" for f in en_cultivo}),
                "otros_cultivos_autorizados": sorted({f[0] for f in filas} - {crop}),
                **({"aviso": f"no reconozco la plaga «{plaga}»; se responde por cultivo"} if plaga and not plagas else {}),
                "fuente": "grafo: Authorization (SENASA SIGIA)"}

    def carencia(self, producto: str, cultivo: str) -> dict:
        crop = _resolver(CULTIVOS, cultivo)
        prods = self.producto(producto)
        if not crop or not prods:
            return {"error": f"no reconozco el cultivo «{cultivo}» o el producto «{producto}»"}
        if len(prods) > 1:
            return {"error": "el nombre coincide con varios productos", "candidatos": [p[1] for p in prods[:8]]}
        filas = self.g.run(
            "MATCH (a:Authorization)-[:OF_PRODUCT]->(:Product {key: $p}), (a)-[:ON_CROP]->(:Crop {key: $c}) "
            "RETURN collect(DISTINCT a.preharvest_interval_days), collect(DISTINCT a.preharvest_not_applicable)",
            {"p": prods[0][0], "c": crop}, columns=("phis", "na"))
        phis = sorted(x for x in (filas[0][0] if filas else []) if x is not None)
        if not phis:
            return {"producto": prods[0][1], "sin_dato": "el registro no indica periodo de carencia para este cultivo",
                    "no_aplica": any(filas[0][1]) if filas else False}
        return {"producto": prods[0][1], "cultivo": crop, "dias": phis[-1],
                **({"varios_valores": phis, "nota": "se da el mayor (el conservador)"} if len(phis) > 1 else {}),
                "fuente": "grafo: Authorization (SENASA SIGIA)"}

    def grupo_modo_accion(self, ingrediente: str) -> dict:
        iso = self.ingrediente(ingrediente)
        filas = self.g.run("MATCH (:Ingredient {key: $i})-[:IN_GROUP]->(g:MoaGroup) RETURN g.key", {"i": iso})
        grupos = sorted(r[0] for r in filas)
        if not grupos:
            return {"ingrediente": iso, "sin_dato": "el ingrediente no figura en las listas FRAC, IRAC ni HRAC cargadas",
                    **self._nota(ingrediente)}
        return {"ingrediente": iso, **self._nota(ingrediente), "grupos": [{"esquema": g.split(":", 1)[0], "grupo": g.split(":", 1)[1]} for g in grupos],
                "fuente": "grafo: MoaGroup (FRAC, IRAC, HRAC)"}

    # herramientas genéricas (27/11/2026): listas y conteos con consultas fijas -------------------------------------
    def plagas_en_cultivo(self, nombre: str, cultivo: str) -> list[tuple[str, str, str]]:
        """Pests registered on the crop that the name designates: every word of the name begins a word of the pest's
        common or scientific name («Erysiphe necator» is one pest; «queresa» is every scale insect)."""
        filas = self.g.run("MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $c}), (a)-[:AGAINST]->(t:Pest) "
                           "RETURN DISTINCT t.key, t.common_name, t.scientific_name", {"c": cultivo}, columns=("k", "c", "s"))
        palabras = _palabras(nombre)
        if not palabras:
            return []
        out = []
        for k, comun, cientifico in filas:
            if str(k).startswith("use:"):
                continue
            nombre_plaga = _palabras(f"{comun or ''} {cientifico or ''}")
            if all(any(x.startswith(w) for x in nombre_plaga) for w in palabras):
                out.append((k, comun, cientifico))
        return sorted(out)

    def productos_para_plaga(self, cultivo: str, plaga: str, carencia_maxima: int | None = None,
                             excluir_grupo: str | None = None, mercado: str | None = None) -> dict:
        crop = _resolver(CULTIVOS, cultivo)
        if not crop:
            return {"error": f"no reconozco el cultivo «{cultivo}»"}
        market = _resolver(MERCADOS, mercado) if mercado else None
        if mercado and not market:
            return {"error": f"no reconozco el mercado «{mercado}»"}
        plagas = self.plagas_en_cultivo(plaga, crop)
        if not plagas:
            return {"error": f"no reconozco la plaga «{plaga}» entre las registradas para {crop}"}
        filas = self.g.run(
            "MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $c}), (a)-[:AGAINST]->(t:Pest), (a)-[:OF_PRODUCT]->(p:Product) "
            "WHERE t.key IN $t OPTIONAL MATCH (p)-[:CONTAINS]->(i:Ingredient) "
            "RETURN p.key, p.trade_name, p.registration_number, a.preharvest_interval_days, collect(DISTINCT i.key)",
            {"c": crop, "t": [k for k, _, _ in plagas]}, columns=("k", "n", "r", "phi", "i"))
        productos: dict[str, dict] = {}
        for k, nombre, numero, phi, ings in filas:
            p = productos.setdefault(k, {"producto": nombre, "numero_registro": numero, "carencias": set(),
                                         "ingredientes": set()})
            p["carencias"].add(phi)
            p["ingredientes"].update(ings or [])
        todos = sorted({i for p in productos.values() for i in p["ingredientes"]})
        grupos: dict[str, set[str]] = {}
        if todos:
            for i, g in self.g.run("MATCH (i:Ingredient)-[:IN_GROUP]->(g:MoaGroup) WHERE i.key IN $i RETURN i.key, g.key",
                                   {"i": todos}, columns=("i", "g")):
                grupos.setdefault(i, set()).add(g)
        esquema, codigo = _grupo(excluir_grupo) if excluir_grupo else (None, None)
        salida, sin_carencia = [], 0
        for p in productos.values():
            conocidas = [x for x in p["carencias"] if x is not None]
            # the longest interval among the product's registrations for these pests (the conservative one)
            dias = max(conocidas) if conocidas and None not in p["carencias"] else None
            if carencia_maxima is not None:
                if dias is None:
                    sin_carencia += 1
                    continue
                if dias > carencia_maxima:
                    continue
            gs = sorted({g for i in p["ingredientes"] for g in grupos.get(i, set())})
            if codigo and any(g.split(":")[1].upper() == codigo and (esquema is None or g.split(":")[0] == esquema)
                              for g in gs):
                continue
            fila = {"producto": p["producto"], "numero_registro": p["numero_registro"], "carencia_dias": dias,
                    "ingredientes": sorted(p["ingredientes"]), "grupos": [g.replace(":", " ") for g in gs]}
            if market:
                hoy = date.today().isoformat()
                sin = [i for i in sorted(p["ingredientes"])
                       if not [m for m in mrl_versions(self.g, i, crop, market) if in_force(m, hoy)]]
                fila["ingredientes_sin_lmr_vigente"] = sin
            salida.append(fila)
        salida.sort(key=lambda f: (f["carencia_dias"] if f["carencia_dias"] is not None else 999, f["producto"]))
        return {"cultivo": crop, "plagas": [f"{c} ({s})" for _, c, s in plagas],
                "filtros": {k: v for k, v in (("carencia_maxima_dias", carencia_maxima), ("excluir_grupo", excluir_grupo),
                                               ("mercado", NOMBRE_MERCADO.get(market or ""))) if v is not None},
                "total": len(salida), "productos": salida[:25],
                **({"nota": f"se muestran 25 de {len(salida)}"} if len(salida) > 25 else {}),
                **({"sin_carencia_registrada": sin_carencia} if sin_carencia else {}),
                "fuente": "grafo: Authorization (SENASA SIGIA), MoaGroup (FRAC, IRAC, HRAC)"}

    def ingredientes_sin_limite(self, cultivo: str, mercado: str, fecha: str | None = None) -> dict:
        crop, market = _resolver(CULTIVOS, cultivo), _resolver(MERCADOS, mercado)
        if not crop or not market:
            return {"error": f"no reconozco el cultivo «{cultivo}» o el mercado «{mercado}»"}
        dia = _fecha(fecha)
        ings = sorted(r[0] for r in self.g.run(
            "MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $c}), (a)-[:OF_PRODUCT]->(:Product)-[:CONTAINS]->(i:Ingredient) "
            "RETURN DISTINCT i.key", {"c": crop}, columns=("i",)))
        sin, en_loq = [], []
        for i in ings:
            vigentes = [m for m in mrl_versions(self.g, i, crop, market) if in_force(m, dia)]
            if not vigentes:
                sin.append(i)
            elif any(m.get("at_limit_of_determination") for m in vigentes):
                en_loq.append(i)
        return {"cultivo": crop, "mercado": NOMBRE_MERCADO[market], "fecha": dia,
                "ingredientes_registrados": len(ings), "sin_lmr_vigente": len(sin), "en_limite_de_determinacion": len(en_loq),
                "lista_sin_lmr_vigente": sin[:40], "lista_en_limite_de_determinacion": en_loq[:40],
                "fuente": f"grafo: Authorization (SENASA SIGIA) y MrlVersion {market}"}

    def llamar(self, nombre: str, argumentos: dict) -> dict:
        """Runs a tool after validating its arguments with its Pydantic model. Invalid arguments come back as an error
        that names the field, so the model can call again with them fixed."""
        entrada = HERRAMIENTAS.get(nombre) or GENERICAS.get(nombre)
        if entrada is None:
            return {"error": f"no existe la herramienta «{nombre}»"}
        modelo, metodo = entrada
        limpios = {k: v for k, v in (argumentos or {}).items() if v not in (None, "")}
        try:
            datos = modelo.model_validate(limpios)
        except ValidationError as e:
            return {"error": f"argumentos inválidos para {nombre}",
                    "detalles": [{"campo": ".".join(str(x) for x in err["loc"]), "problema": err["msg"]} for err in e.errors()]}
        return getattr(self, metodo)(**datos.model_dump(exclude_none=True))


# --- entradas de las herramientas (Pydantic): de aquí salen la validación y el JSON Schema que ve el modelo ------------
_ING = "ingrediente activo, en español o en inglés (p. ej. «azufre», «pyraclostrobin»)"
_CUL = "cultivo: arándano, palto o uva de mesa"
_MER = "mercado: Unión Europea, Estados Unidos o Codex"
_FEC = "fecha en que debe regir, AAAA-MM-DD o DD/MM/AAAA; hoy si no se indica"
_PRO = "nombre comercial del producto, como figura en el SENASA"


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class LimiteMaximoIn(_Entrada):
    """Límite máximo de residuos (LMR) vigente de un ingrediente en un cultivo y un mercado en una fecha."""
    ingrediente: str = Field(min_length=2, description=_ING)
    cultivo: str = Field(min_length=2, description=_CUL)
    mercado: str = Field(min_length=2, description=_MER)
    fecha: str | None = Field(None, description=_FEC)


class HistorialLimiteIn(_Entrada):
    """Todas las versiones de un LMR (con sus fechas), para saber qué valor regía antes o cuál viene."""
    ingrediente: str = Field(min_length=2, description=_ING)
    cultivo: str = Field(min_length=2, description=_CUL)
    mercado: str = Field(min_length=2, description=_MER)


class CompararMercadosIn(_Entrada):
    """LMR vigente en la Unión Europea, Estados Unidos y el Codex, y cuál es el más estricto."""
    ingrediente: str = Field(min_length=2, description=_ING)
    cultivo: str = Field(min_length=2, description=_CUL)
    fecha: str | None = Field(None, description=_FEC)


class RegistroProductoIn(_Entrada):
    """Si un producto está registrado en el SENASA para un cultivo (y una plaga), y para qué plagas."""
    producto: str = Field(min_length=2, description=_PRO)
    cultivo: str = Field(min_length=2, description=_CUL)
    plaga: str | None = Field(None, description="plaga, nombre común o científico")


class CarenciaIn(_Entrada):
    """Periodo de carencia (días entre la última aplicación y la cosecha) de un producto en un cultivo."""
    producto: str = Field(min_length=2, description=_PRO)
    cultivo: str = Field(min_length=2, description=_CUL)


class GrupoModoAccionIn(_Entrada):
    """Grupo de modo de acción (FRAC, IRAC o HRAC) de un ingrediente activo."""
    ingrediente: str = Field(min_length=2, description=_ING)


class ProductosParaPlagaIn(_Entrada):
    """Productos registrados en el SENASA para un cultivo contra una plaga, con su carencia, ingredientes y grupo de
    modo de acción; filtra por carencia máxima, excluye un grupo (rotación) y, con un mercado, marca los ingredientes
    sin LMR vigente. Devuelve el total y la lista."""
    cultivo: str = Field(min_length=2, description=_CUL)
    plaga: str = Field(min_length=3, description="plaga, nombre común o científico (p. ej. «queresa», «Botrytis cinerea»)")
    carencia_maxima: int | None = Field(None, ge=0, le=365, description="solo productos con carencia de estos días o menos")
    excluir_grupo: str | None = Field(None, description="grupo de modo de acción a excluir, p. ej. «FRAC 3» o «IRAC 4A»")
    mercado: str | None = Field(None, description=_MER)


class IngredientesSinLimiteIn(_Entrada):
    """Cuántos y cuáles ingredientes activos de los productos registrados para un cultivo no tienen LMR vigente en un
    mercado, y cuáles lo tienen en el límite de determinación."""
    cultivo: str = Field(min_length=2, description=_CUL)
    mercado: str = Field(min_length=2, description=_MER)
    fecha: str | None = Field(None, description=_FEC)


class BuscarDocumentosIn(_Entrada):
    """Busca en las guías del SENASA, manuales y tesis pasajes sobre manejo agronómico, plagas, enfermedades y su
    control. Devuelve pasajes numerados para citar [1], [2]."""
    consulta: str = Field(min_length=3, description="qué buscar, en español")


# nombre -> (modelo de entrada, método de Herramientas)
HERRAMIENTAS: dict[str, tuple[type[BaseModel], str]] = {
    "limite_maximo": (LimiteMaximoIn, "limite_maximo"), "historial_limite": (HistorialLimiteIn, "historial_limite"),
    "comparar_mercados": (CompararMercadosIn, "comparar_mercados"),
    "registro_producto": (RegistroProductoIn, "registro_producto"), "carencia": (CarenciaIn, "carencia"),
    "grupo_modo_accion": (GrupoModoAccionIn, "grupo_modo_accion"),
}


def definicion(nombre: str, modelo: type[BaseModel]) -> dict:
    """The function declaration (OpenAI, Ollama and Gemini format) generated from the Pydantic model: plain types and
    descriptions, without Pydantic's titles or the null branch of optional fields, which small models handle worse."""
    esquema = modelo.model_json_schema()
    propiedades = {}
    for campo, s in esquema["properties"].items():
        tipo = s.get("type") or next((x["type"] for x in s.get("anyOf", []) if x.get("type") != "null"), "string")
        propiedades[campo] = {"type": tipo, "description": s.get("description", "")}
    return {"type": "function", "function": {
        "name": nombre, "description": " ".join((modelo.__doc__ or "").split()),
        "parameters": {"type": "object", "properties": propiedades, "required": esquema.get("required", [])}}}


# generic tools (27/11/2026): lists and counts over the same graph, with fixed queries; on with orchestration.genericas
GENERICAS: dict[str, tuple[type[BaseModel], str]] = {
    "productos_para_plaga": (ProductosParaPlagaIn, "productos_para_plaga"),
    "ingredientes_sin_limite": (IngredientesSinLimiteIn, "ingredientes_sin_limite"),
}

DEFINICIONES = [definicion(n, m) for n, (m, _) in HERRAMIENTAS.items()]
DEFINICIONES_GENERICAS = [definicion(n, m) for n, (m, _) in GENERICAS.items()]
DOCUMENTOS = definicion("buscar_documentos", BuscarDocumentosIn)
