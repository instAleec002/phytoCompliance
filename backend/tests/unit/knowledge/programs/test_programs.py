"""Field sheets into programs: the reader, the pest and date resolution, the dose check and the importer."""
import io
from datetime import date

import pytest
from openpyxl import Workbook

from knowledge.programs.doses import Dosis, controlar, leer_dosis
from knowledge.programs.importer import importar
from knowledge.programs.resolver import Resolvedor
from knowledge.programs.sheets import HojaInvalida, columna, leer_hoja

from ...domain.fakes import FakeRegistry
from .fakes import FakeAliases, grafo


def _xlsx(filas):
    wb = Workbook()
    for f in filas:
        wb.active.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _resolvedor():
    reg = (FakeRegistry().add("ADIKO", ["pyraclostrobin"], 14, crop="table_grape", pest="000626")
           .add("AZUFRAL", ["sulphur"], 0, crop="table_grape", pest="001451")
           .add("LORSBAN", ["chlorpyrifos"], 21, crop="table_grape", pest="000626")
           .add("PIRIMOR", ["chlorpyrifos"], 7, crop="table_grape", pest="000626"))
    return Resolvedor(grafo(), reg, FakeAliases(), espanol={"sulphur": "azufre", "chlorpyrifos": "clorpirifos"})


def test_headers_are_recognized_by_name_with_units_and_accents():
    assert columna("Ingrediente Activo") == "ingrediente"
    assert columna("Dosis (L/ha)") == "dosis"
    assert columna("Momento de aplicación") == "momento"
    assert columna("Lote") == "bloque"
    assert columna("Observaciones") is None


def test_sheet_finds_its_header_and_skips_headings_and_notes():
    contenido = _xlsx([["Programa fitosanitario 2026"], [], ["Fecha", "Producto comercial", "I.A.", "Dosis", "Obs."],
                       ["11-sep", "Adiko", "Piraclostrobina", "0.5 L/ha", "con adherente"],
                       ["Floración", None, None, None, None], [None, None, "Azufre", "2 kg/ha", None]])
    assert leer_hoja(contenido, "p.xlsx") == [
        {"fecha": "11-sep", "producto": "Adiko", "ingrediente": "Piraclostrobina", "dosis": "0.5 L/ha", "obs": "con adherente"},
        {"ingrediente": "Azufre", "dosis": "2 kg/ha"}]


def test_csv_with_semicolons_in_latin1():
    texto = "Fecha;Ingrediente activo;Dosis\n18-sep;Azufre;2 kg/ha\n".encode("cp1252")
    assert leer_hoja(texto, "p.csv") == [{"fecha": "18-sep", "ingrediente": "Azufre", "dosis": "2 kg/ha"}]
    with pytest.raises(HojaInvalida):
        leer_hoja(b"a,b\n1,2\n", "p.csv")
    with pytest.raises(HojaInvalida):
        leer_hoja(b"x", "p.pdf")


def test_dose_units_and_bases():
    assert leer_dosis("2 Lt/ha") == Dosis(2.0, "L", "ha")
    assert leer_dosis("300 ml/Cil") == Dosis(0.3, "L", "cil")
    assert leer_dosis("0.06Kg/ cil") == Dosis(0.06, "kg", "cil")
    assert leer_dosis("200 g/200 L") == Dosis(0.2, "kg", "cil")
    assert leer_dosis("100") is None and leer_dosis("0.5 %") is None and leer_dosis(None) is None


def test_dose_against_every_candidate_product_and_only_in_comparable_units():
    g = grafo()
    assert controlar(g, "0.25 L/cil", ("LORSBAN",), "table_grape").estado == "dentro"
    fuera = controlar(g, "0.35 L/cil", ("LORSBAN",), "table_grape")
    assert fuera.estado == "fuera_de_rango" and fuera.registradas == ["0.2–0.3 L/cilindro"]
    # resolved by ingredient: outside only if outside every product with that ingredient
    assert controlar(g, "0.45 L/cil", ("LORSBAN", "PIRIMOR"), "table_grape").estado == "dentro"
    assert controlar(g, "2.5 kg/ha", ("AZUFRAL",), "table_grape").estado == "dentro"     # «kl» is kilograms
    assert controlar(g, "2.5 L/ha", ("AZUFRAL",), "table_grape").estado == "no_comparable"
    assert controlar(g, "100", ("AZUFRAL",), "table_grape").estado == "no_comparable"


def test_pest_text_names_the_powdery_mildews_most_specific_first():
    r = _resolvedor()
    assert r.plagas("oídio (Erysiphe necator)", "table_grape") == ["000437", "001451", "011204"]
    assert r.plagas("arañita roja", "table_grape") == []


def test_dates_full_day_month_and_stage():
    r, prog = _resolvedor(), {"cosecha": "2026-12-28"}
    assert r.fecha(prog, {"fecha": date(2026, 9, 11)}) == (date(2026, 9, 11), True)
    assert r.fecha(prog, {"fecha": "11/09/2026"}) == (date(2026, 9, 11), True)
    assert r.fecha(prog, {"fecha": "11-sep"}) == (date(2026, 9, 11), True)
    assert r.fecha(prog, {"momento": "Plena floración"}) == (date(2026, 9, 30), False)
    # a harvest in May: July is after the previous harvest, March is before this one
    palto = {"cosecha": "2027-05-15"}
    assert r.fecha(palto, {"momento": "Post-cosecha / Junio - Julio"}) == (date(2026, 7, 31), False)
    assert r.fecha(palto, {"fecha": "11-mar"}) == (date(2027, 3, 11), True)
    assert r.fecha(palto, {"fecha": "11-sep"}) == (date(2026, 9, 11), True)


def test_import_resolves_rows_picks_a_registered_pest_and_leaves_unknown_names_to_a_person():
    filas = [{"fecha": "11-sep", "producto": "Azufral", "dosis": "2.5 kg/ha"},
             {"fecha": "18-sep", "ingrediente": "Clorpirifos", "dosis": "0.6 L/cil", "bloque": "B2"},
             {"fecha": "25-sep", "producto": "Bayfidan", "ingrediente": "Triadimenol"},
             {"fecha": "26-sep", "ingrediente": "Detergente agrícola"}]
    imp = importar(filas, nombre="p", cultivo="table_grape", mercados=["EU"], cosecha=date(2026, 12, 28),
                   resolvedor=_resolvedor(), plaga="oídio", graph=grafo())
    a, b, c, d = imp.filas
    assert (a.estado, a.resolucion.producto, a.resolucion.plaga, a.dosis.estado) == (
        "resuelta_por_nombre", "AZUFRAL", "001451", "dentro")          # the mildew AZUFRAL is registered for
    assert (b.estado, b.resolucion.producto, b.bloque, b.dosis.estado) == (
        "resuelta_por_ingrediente", "LORSBAN", "B2", "fuera_de_rango")  # longest interval first; 0.6 > every range
    assert c.estado == "necesita_persona" and any("no está en el registro" in n for n in c.resolucion.notas)
    assert d.estado == "no_plaguicida" and d.dosis is None
    assert [blk.key for blk in imp.programa.blocks] == ["B2", "L1"] and len(imp.programa.applications) == 2
    assert imp.resumen["necesitan_persona"] == 1 and imp.resumen["dosis_fuera_de_rango"] == 1


def test_target_column_is_read_as_pests_with_plurals_and_flags_unregistered_uses():
    r = _resolvedor()
    assert r.plagas("botritis", "table_grape") == ["000626"]               # plural, spelling; «use:» is not a pest
    filas = [{"fecha": "11-sep", "ingrediente": "Clorpirifos", "objetivo": "botritis"},
             {"fecha": "12-sep", "producto": "Azufral", "objetivo": "moho gris"},
             {"fecha": "13-sep", "producto": "Adiko", "objetivo": "hongos de madera"}]
    imp = importar(filas, nombre="p", cultivo="table_grape", mercados=["EU"], cosecha=date(2026, 12, 28),
                   resolvedor=r)
    a, b, c = (x.resolucion for x in imp.filas)
    assert (a.registro_objetivo, b.registro_objetivo, c.registro_objetivo) == ("registrado", "no_registrado", "sin_resolver")
    assert b.plaga is None and imp.resumen["objetivo_no_registrado"] == 1     # the validation is not changed
