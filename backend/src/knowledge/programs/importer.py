"""A field sheet turned into a program the validator can check, row by row with how each row was resolved."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from domain.validation.models import Application, Block, Program

from .doses import ControlDosis, controlar
from .resolver import Fila, Resolvedor

BLOQUE = "L1"                    # block of the rows that do not name one

ESTADOS = {("plaguicida", "nombre_comercial"): "resuelta_por_nombre", ("plaguicida", "ingrediente"): "resuelta_por_ingrediente",
           ("no_plaguicida", None): "no_plaguicida"}


@dataclass
class FilaImportada:
    n: int
    original: dict
    estado: str                  # resuelta_por_nombre | resuelta_por_ingrediente | no_plaguicida | necesita_persona
    bloque: str
    resolucion: Fila
    dosis: ControlDosis | None = None

    @property
    def fecha_aproximada(self) -> bool:
        return self.resolucion.fecha is not None and not self.resolucion.fecha_exacta


@dataclass
class Importacion:
    nombre: str
    cultivo: str
    filas: list[FilaImportada]
    programa: Program | None                       # None when no row resolved
    resumen: dict = field(default_factory=dict)


def importar(filas: list[dict], *, nombre: str, cultivo: str, mercados: list[str], cosecha: date,
             resolvedor: Resolvedor, plaga: str | None = None, graph=None) -> Importacion:
    """Resolves every row and builds the program with the rows that resolved, one block per «bloque» (all with the
    planned harvest and the markets given). With ``graph``, it also checks each resolved dose against SIGIA."""
    prog = {"pid": nombre, "cultivo": cultivo, "cosecha": cosecha.isoformat(), "plaga": plaga}
    salida = []
    for n, f in enumerate(filas, 1):
        r = resolvedor.resolver(prog, n, f)
        estado = ESTADOS.get((r.tipo, r.via if r.tipo == "plaguicida" else None), "necesita_persona")
        bloque = str(f.get("bloque") or BLOQUE).strip()
        dosis = (controlar(graph, f.get("dosis"), r.candidatos_ids if r.via == "ingrediente" else (r.producto,),
                           cultivo, r.plaga)
                 if graph is not None and r.tipo == "plaguicida" else None)
        salida.append(FilaImportada(n, f, estado, bloque, r, dosis))
    apps = [Application(x.bloque, x.resolucion.producto, x.resolucion.fecha, x.resolucion.plaga)
            for x in salida if x.resolucion.tipo == "plaguicida"]
    bloques = sorted({a.block for a in apps})
    programa = Program(cultivo, tuple(Block(b, cosecha, tuple(mercados)) for b in bloques), tuple(apps)) if apps else None
    cuenta = lambda e: sum(x.estado == e for x in salida)
    resumen = {"filas": len(salida), "resueltas_por_nombre": cuenta("resuelta_por_nombre"),
               "resueltas_por_ingrediente": cuenta("resuelta_por_ingrediente"), "no_plaguicida": cuenta("no_plaguicida"),
               "necesitan_persona": cuenta("necesita_persona"),
               "fechas_aproximadas": sum(x.fecha_aproximada for x in salida if x.resolucion.tipo == "plaguicida"),
               "dosis_fuera_de_rango": sum(bool(x.dosis) and x.dosis.estado == "fuera_de_rango" for x in salida),
               "dosis_no_comparables": sum(bool(x.dosis) and x.dosis.estado == "no_comparable" for x in salida),
               "objetivo_registrado": sum(x.resolucion.registro_objetivo == "registrado" for x in salida),
               "objetivo_no_registrado": sum(x.resolucion.registro_objetivo == "no_registrado" for x in salida),
               "objetivo_sin_resolver": sum(x.resolucion.registro_objetivo == "sin_resolver" for x in salida)}
    return Importacion(nombre, cultivo, salida, programa, resumen)
