"""Rows of a spray program as technicians write them, resolved into what the validator receives (stage E, 27/11/2026).

A field sheet names products by trade name or by ingredient, with the spellings people use, and gives dates as a day
and month, a growth stage or a range of months. Each row is resolved into a registered product, a date and, when the
row or the program names it, the target pest, and the row records how it was resolved, because that is where real
programs differ from clean input:

- product: by trade name (prefix of the registry's trade name), else by ingredients (spelling-tolerant match against
  the graph's ingredients and their Spanish names, then the registered products with exactly those ingredients); when
  both are given and disagree, it says so. Among several registered candidates it takes the longest pre-harvest
  interval, as the registry does for a product without a pest;
- date: a full date as written; ``11-sep`` with its day and month in the campaign that ends at the planned harvest; a
  stage or a month range (``Junio - Julio``) on the last day of the range, the one nearest to harvest, marked as
  approximate;
- pest: a free text (``oídio (Erysiphe necator)``) against the common and scientific names of the pests registered on
  the crop; among the matches, the first one for which the product is registered;
- rows that are not pesticides (agricultural detergent) are set aside; rows that do not resolve stay unresolved, since a
  person has to decide them. A trade name that is not in the registry is never replaced by another product with the
  same ingredients: the row stays unresolved, because what was applied cannot be checked.

Moved from ``evaluation.programas_reales``, where it was measured on five published programs (run 2026-11-27_0405).
"""
from __future__ import annotations

import calendar
import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9,
         "oct": 10, "nov": 11, "dic": 12}
# stage -> month in the valley, from Tabla 20 of the Huaura thesis (the same source as the programs that lack dates)
ETAPAS = [("post", 7), ("poda", 7), ("brotamiento", 8), ("prefloraci", 8), ("inicio de floraci", 8),
          ("plena floraci", 9), ("floraci", 9), ("cuaja", 10), ("crecimiento de fruta", 1), ("desarrollo de fruto", 3)]
NO_PLAGUICIDA = ("detergente",)
# names of salts and oils that a spelling match between Spanish and English cannot bridge
LEXICO = {"sulfato de cobre": "copper sulphate", "hidroxido de cobre": "copper hydroxide",
          "oxicloruro de cobre": "copper oxychloride", "oxido cuproso": "copper oxide",
          "aceite agricola": "paraffin oil", "aceite mineral": "paraffin oil", "azufre": "sulphur"}


def _plano(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _fonetico(nombre: str) -> str:
    """Spelling-tolerant form of a name in Spanish or English (clorpirifos ~ chlorpyrifos)."""
    t = re.sub(r"[^a-z ]", "", _plano(nombre))
    for a, b in (("ph", "f"), ("th", "t"), ("ch", "c"), ("y", "i"), ("z", "s"), ("k", "c"), ("qu", "c"), ("x", "cs")):
        t = t.replace(a, b)
    return " ".join(re.sub(r"[aeo]$", "", w) for w in t.split())


@dataclass
class Fila:
    pid: str
    n: int
    texto: str
    tipo: str = "plaguicida"                 # plaguicida | no_plaguicida | no_resuelta
    producto: str | None = None
    nombre_producto: str | None = None
    via: str | None = None                   # nombre_comercial | ingrediente
    ingredientes: tuple[str, ...] = ()
    candidatos: int = 0
    candidatos_ids: tuple[str, ...] = ()     # every registered product the row could be (the dose check uses them)
    discrepancia: str | None = None
    fecha: date | None = None
    fecha_exacta: bool = False
    plaga: str | None = None
    notas: list[str] = field(default_factory=list)
    # the row's «objetivo» read as pests (27/11/2026), a flag for review that does not change the validation:
    # registrado | no_registrado | sin_resolver (the text names no pest: «limpieza», «hongos de madera»)
    objetivo_plagas: tuple[str, ...] = ()
    registro_objetivo: str | None = None


class Resolvedor:
    def __init__(self, graph, registry, aliases, espanol: dict[str, str] | None = None):
        from knowledge.normalization.ingredients import spanish_names

        self.g, self.registry = graph, registry
        espanol = spanish_names(aliases) if espanol is None else espanol
        self.ingredientes = {r[0] for r in graph.run("MATCH (i:Ingredient) RETURN i.key", columns=("k",))}
        self.nombres = {}                                    # spelling-tolerant name -> ingredient key
        for k in self.ingredientes:
            self.nombres.setdefault(_fonetico(k), k)
        for iso, es in espanol.items():
            if iso in self.ingredientes:
                self.nombres.setdefault(_fonetico(es), iso)
        self.aliases = aliases
        self.productos = {r[0]: (r[1] or "", tuple(sorted(r[2]))) for r in graph.run(
            "MATCH (p:Product) OPTIONAL MATCH (p)-[:CONTAINS]->(i:Ingredient) RETURN p.key, p.trade_name, collect(i.key)",
            columns=("k", "n", "i"))}
        self._plagas: dict[str, list[tuple]] = {}

    def ingrediente(self, nombre: str) -> str | None:
        lex = LEXICO.get(re.sub(r"\s+", " ", _plano(nombre)).strip())
        if lex:
            hits = sorted(k for k in self.ingredientes if k == lex or k.startswith(lex))
            if hits:
                return hits[0]
        iso = self.aliases.iso(nombre)
        if iso in self.ingredientes:
            return iso
        f = _fonetico(nombre)
        if not f:
            return None
        if f in self.nombres:
            return self.nombres[f]
        mejor = difflib.get_close_matches(f, list(self.nombres), n=2, cutoff=0.86)
        if mejor and (len(mejor) == 1 or difflib.SequenceMatcher(None, f, mejor[0]).ratio()
                      - difflib.SequenceMatcher(None, f, mejor[1]).ratio() > 0.03):
            return self.nombres[mejor[0]]
        pref = sorted(k for k in self.ingredientes if _fonetico(k).startswith(f.split()[0][:8])) if len(f) >= 8 else []
        if len(pref) > 1 and len({k.split()[0] for k in pref}) == 1:
            # a genus written alone («Trichodermas») stands for any of its species (27/11/2026: picking the first
            # species alphabetically chose one registered only for grape when others are registered for avocado)
            return pref[0].split()[0] + "*"
        return pref[0] if pref else None

    def ingredientes_de(self, texto: str) -> tuple[tuple[str, ...], list[str]]:
        partes = [p.strip() for p in re.split(r"\s+y\s+|\+|,", texto) if p.strip()]
        claves = [self.ingrediente(p) for p in partes]
        return tuple(sorted(k for k in claves if k)), [p for p, k in zip(partes, claves) if not k]

    def _phi(self, producto: str, cultivo: str) -> int:
        reg = self.registry.registration(producto, cultivo)
        return -1 if reg is None else (reg.preharvest_interval_days or 0)

    def por_nombre(self, texto: str, cultivo: str) -> list[str]:
        base = _plano(texto).split()[0]
        cands = [k for k, (n, _) in self.productos.items() if _plano(n).split()[:1] == [base]]
        return sorted(cands, key=lambda k: (self._phi(k, cultivo) < 0, -self._phi(k, cultivo), k))

    def por_ingredientes(self, ingredientes: tuple[str, ...], cultivo: str) -> list[str]:
        """Products with exactly these ingredients; a salt or a strain written generically (copper sulphate,
        Trichoderma) also matches its registered forms (copper sulphate pentahydrate, Trichoderma harzianum)."""
        cands = [k for k, (_, ing) in self.productos.items() if ing == ingredientes]
        if not cands and len(ingredientes) == 1:
            base = ingredientes[0].rstrip("*")          # «trichoderma*»: any species of the genus
            cands = [k for k, (_, ing) in self.productos.items() if len(ing) == 1 and ing[0].startswith(base)]
        return sorted(cands, key=lambda k: (self._phi(k, cultivo) < 0, -self._phi(k, cultivo), k))

    def plagas(self, texto: str, cultivo: str) -> list[str]:
        """SIGIA pests that a free text names, among the pests with an authorization on the crop: each word of the text
        (four letters or more, spelling-tolerant) that begins a word of the pest's common or scientific name counts
        once. Ordered by how many words match, then by key, so «oídio (Erysiphe necator)» puts Erysiphe necator first,
        then Erysiphe sp. and the other powdery mildews. Plurals count as their singular («queresas», «ácaros»), and
        SIGIA's other uses (``use:`` keys, such as fruit dipping) are not pests."""
        if cultivo not in self._plagas:
            self._plagas[cultivo] = [r for r in self.g.run(
                "MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $crop}), (a)-[:AGAINST]->(p:Pest) "
                "RETURN DISTINCT p.key, p.common_name, p.scientific_name", {"crop": cultivo}, columns=("k", "c", "s"))
                if not str(r[0]).startswith("use:")]
        singular = (re.sub(r"(?<=[a-z]{4})(es|s)$", "", w) for w in re.sub(r"[^a-z ]", "", _plano(texto)).split())
        palabras = [w for w in (_fonetico(x) for x in singular) if len(w) >= 4]
        puntos = []
        for k, comun, cientifico in self._plagas[cultivo]:
            nombre = _fonetico(f"{comun or ''} {cientifico or ''}").split()
            n = sum(any(x.startswith(w) for x in nombre) for w in palabras)
            if n:
                puntos.append((-n, k))
        return [k for _, k in sorted(puntos)]

    def fecha(self, prog: dict, fila: dict) -> tuple[date | None, bool]:
        cosecha = date.fromisoformat(str(prog.get("cosecha") or prog["cosecha_evaluacion"]))
        # the campaign is the twelve months up to the planned harvest: a day and month after the harvest day belong to
        # the year before (27/11/2026: the earlier rule only held for harvests before September)
        anio = lambda mes, dia: cosecha.year if (mes, dia) <= (cosecha.month, cosecha.day) else cosecha.year - 1
        valor = fila.get("fecha")
        if isinstance(valor, datetime):
            return valor.date(), True
        if isinstance(valor, date):
            return valor, True
        if valor:
            texto = _plano(str(valor)).strip()
            m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ t].*)?", texto)
            if m:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), True
            m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})", texto)
            if m:
                y = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
                return date(y, int(m.group(2)), int(m.group(1))), True
            m = re.match(r"(\d{1,2})\s*[-/ ]\s*([a-z]{3})", texto)
            if m and m.group(2) in MESES:
                mes, dia = MESES[m.group(2)], int(m.group(1))
                return date(anio(mes, dia), mes, dia), True
            return None, False
        momento = _plano(str(fila.get("momento") or ""))
        mes = None
        m = re.search(r"quincena de (\w{3})", momento)
        if m and m.group(1) in MESES:
            mes, dia = MESES[m.group(1)], 15
        else:
            meses = [MESES[w[:3]] for w in re.findall(r"[a-z]+", momento) if w[:3] in MESES and len(w) >= 4]
            if meses:
                mes = meses[-1]
            else:
                mes = next((v for k, v in ETAPAS if k in momento), None)
            dia = None
        if mes is None:
            return None, False
        y = anio(mes, 1)                     # by month: a stage in the harvest month stays in the harvest year
        return date(y, mes, dia or calendar.monthrange(y, mes)[1]), False

    def resolver(self, prog: dict, n: int, fila: dict) -> Fila:
        cultivo = prog["cultivo"]
        texto = " | ".join(str(fila.get(k)) for k in ("fecha", "momento", "producto", "ingrediente", "dosis") if fila.get(k))
        out = Fila(prog["pid"], n, texto)
        ing_texto = str(fila.get("ingrediente") or "")
        if any(w in _plano(ing_texto) for w in NO_PLAGUICIDA):
            out.tipo = "no_plaguicida"
            return out
        ingredientes, sin_resolver = self.ingredientes_de(ing_texto) if ing_texto else ((), [])
        if sin_resolver:
            out.notas.append("ingrediente sin resolver: " + ", ".join(sin_resolver))
        producto = str(fila.get("producto") or "").strip()
        cands = self.por_nombre(producto, cultivo) if producto else []
        if producto and not cands:
            otros = self.por_ingredientes(ingredientes, cultivo) if ingredientes else []
            out.tipo, out.ingredientes = "no_resuelta", ingredientes
            out.notas.append(f"el nombre comercial {producto} no está en el registro"
                             + (f"; {len(otros)} productos tienen los mismos ingredientes" if otros else ""))
            return out
        if cands:
            out.via = "nombre_comercial"
            if ingredientes and not sin_resolver and self.productos[cands[0]][1] != ingredientes:
                out.discrepancia = (f"el nombre {producto} es {', '.join(self.productos[cands[0]][1])}; "
                                    f"la fila dice {ing_texto}")
        elif ingredientes and not sin_resolver:
            cands = self.por_ingredientes(ingredientes, cultivo)
            out.via = "ingrediente" if cands else None
            if not cands:
                out.notas.append("ningún producto del registro tiene exactamente esos ingredientes")
        if not cands:
            out.tipo = "no_resuelta"
            out.ingredientes = ingredientes
            return out
        out.producto, out.candidatos, out.candidatos_ids = cands[0], len(cands), tuple(cands)
        out.nombre_producto, out.ingredientes = self.productos[cands[0]]
        out.fecha, out.fecha_exacta = self.fecha(prog, fila)
        if out.fecha is None:
            out.tipo = "no_resuelta"
            out.notas.append("fecha sin resolver")
            return out
        texto_plaga = str(fila.get("plaga") or prog.get("plaga") or "").strip()
        if texto_plaga:
            plagas = self.plagas(texto_plaga, cultivo)
            if plagas:
                out.plaga = next((p for p in plagas if self.registry.registration(out.producto, cultivo, p)), plagas[0])
            else:
                out.notas.append(f"plaga sin resolver: {texto_plaga}")
        objetivo = str(fila.get("objetivo") or "").strip()
        if objetivo:
            out.objetivo_plagas = tuple(self.plagas(objetivo, cultivo))
            if not out.objetivo_plagas:
                out.registro_objetivo = "sin_resolver"
            else:
                productos = out.candidatos_ids if out.via == "ingrediente" else (out.producto,)
                registrado = any(self.registry.registration(p, cultivo, x) for p in productos for x in out.objetivo_plagas)
                out.registro_objetivo = "registrado" if registrado else "no_registrado"
                if not registrado:
                    out.notas.append(f"sin registro contra el objetivo declarado ({objetivo})")
        return out
