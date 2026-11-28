"""Field sheets (Excel or CSV) read into rows the resolver understands.

Columns are recognized by their name, not by their position, because every farm writes its own sheet: «Fecha»,
«Producto comercial», «Ingrediente activo», «Dosis (L/ha)», «Lote», «Plaga» and their usual variants. The first row
with at least two recognized names is the header; rows with neither a product nor an ingredient (headings, notes,
empty rows) are skipped. Columns that are not recognized are kept under their own name, so nothing written in the
field is lost.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime

# canonical key -> header names, compared without accents, case or punctuation
COLUMNAS = {
    "fecha": ("fecha", "fecha de aplicacion", "fecha aplicacion", "dia"),
    "momento": ("momento", "momento de aplicacion", "etapa", "etapa fenologica", "estado fenologico", "fenologia",
                "epoca"),
    "producto": ("producto", "producto comercial", "nombre comercial", "marca"),
    "ingrediente": ("ingrediente", "ingrediente activo", "ingredientes activos", "ia", "materia activa",
                    "principio activo"),
    "dosis": ("dosis",),
    "bloque": ("bloque", "lote", "parcela", "campo", "sector"),
    "plaga": ("plaga", "plagas", "plaga objetivo", "blanco biologico", "enfermedad"),
    "objetivo": ("objetivo", "motivo", "finalidad"),
}


class HojaInvalida(ValueError):
    """The file is not a sheet the reader understands (no header with the expected columns)."""


def _norma(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto).lower())
    t = "".join(c for c in t if not unicodedata.combining(c)).replace(".", "")      # «I.A.» is «ia»
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def columna(encabezado: str) -> str | None:
    """The canonical key of a header, or None. «Dosis (L/ha)» is «dosis»: a name followed by a unit still counts."""
    h = _norma(encabezado)
    if not h:
        return None
    for clave, nombres in COLUMNAS.items():
        if h in nombres:
            return clave
    for clave, nombres in COLUMNAS.items():
        if any(h.startswith(n + " ") for n in nombres if len(n) > 2):
            return clave
    return None


def _valor(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date() if (v.hour, v.minute, v.second) == (0, 0, 0) else v
    if isinstance(v, date):
        return v
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = str(v).strip()
    return t or None


def _filas(tabla: list[list]) -> list[dict]:
    for i, fila in enumerate(tabla[:15]):
        claves = [columna(c) if c is not None else None for c in fila]
        if sum(k is not None for k in claves) >= 2:
            break
    else:
        raise HojaInvalida("no se encontró una fila de encabezado con al menos dos columnas reconocidas "
                           f"({', '.join(COLUMNAS)})")
    nombres = [k or (_norma(c) if c is not None else None) for k, c in zip(claves, fila)]
    out = []
    for f in tabla[i + 1:]:
        d = {n: _valor(v) for n, v in zip(nombres, f) if n}
        d = {k: v for k, v in d.items() if v is not None}
        if d.get("producto") or d.get("ingrediente"):            # a row without either is a heading or a note
            out.append(d)
    return out


def leer_hoja(contenido: bytes, nombre: str) -> list[dict]:
    """Rows of a field sheet: ``.xlsx`` (first sheet) or ``.csv`` (comma, semicolon or tab; UTF-8 or Latin-1)."""
    if nombre.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        try:
            ws = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True).worksheets[0]
        except Exception as e:                                   # a damaged or mislabelled file
            raise HojaInvalida(f"no se pudo leer el Excel: {e}") from e
        return _filas([list(r) for r in ws.iter_rows(values_only=True)])
    if nombre.lower().endswith((".csv", ".txt")):
        for codificacion in ("utf-8-sig", "cp1252"):
            try:
                texto = contenido.decode(codificacion)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t")
        except csv.Error:
            dialecto = csv.excel
        return _filas([r for r in csv.reader(io.StringIO(texto), dialecto)])
    raise HojaInvalida("formato no reconocido: se aceptan .xlsx y .csv")
