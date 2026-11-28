from assistant.orchestration.tools import CULTIVOS, DEFINICIONES, MERCADOS, Herramientas, _fecha, _resolver


def test_crops_and_markets_resolve_in_spanish_and_english():
    assert _resolver(CULTIVOS, "Arándano") == "blueberry"
    assert _resolver(CULTIVOS, "uva de mesa") == "table_grape" and _resolver(CULTIVOS, "Palta") == "avocado"
    assert _resolver(MERCADOS, "la Unión Europea".replace("la ", "")) == "EU"
    assert _resolver(MERCADOS, "EE.UU.") == "US" and _resolver(MERCADOS, "Codex Alimentarius") == "CODEX"
    assert _resolver(CULTIVOS, "mango") is None


def test_dates_accept_iso_and_day_first():
    assert _fecha("2024-07-15") == "2024-07-15"
    assert _fecha("15/07/2024") == "2024-07-15"


class _SinGrafo:
    def run(self, *a, **k):
        return []


class _Aliases:
    def iso(self, name):
        return name.lower()


def test_unknown_tool_and_bad_arguments_are_errors_not_exceptions():
    h = Herramientas(_SinGrafo(), _Aliases(), {"sulphur": "azufre"})       # ISO -> español, como spanish_names
    assert "error" in h.llamar("no_existe", {})
    assert "error" in h.llamar("carencia", {"producto": "X"})                  # falta el cultivo
    assert "error" in h.llamar("limite_maximo", {"ingrediente": "azufre", "cultivo": "mango", "mercado": "UE"})
    assert h.ingrediente("Azufre") == "sulphur"                                  # nombre común en español -> ISO


def test_no_row_means_sin_dato():
    h = Herramientas(_SinGrafo(), _Aliases(), {})
    assert "sin_dato" in h.grupo_modo_accion("sulphur")


def test_every_definition_names_a_tool():
    h = Herramientas(_SinGrafo(), _Aliases(), {})
    for d in DEFINICIONES:
        assert "no existe" not in str(h.llamar(d["function"]["name"], {}))


class _Ingredientes:
    def run(self, cypher, *a, **k):
        if "MATCH (i:Ingredient) RETURN i.key" in cypher:
            return [("propaquizafop",), ("quizalofop-p-ethyl",), ("chlorpyrifos",), ("chlorpyrifos-methyl",), ("sulphur",)]
        return []


def test_misspelled_or_spanish_names_are_read_as_the_one_close_ingredient_and_said_so():
    h = Herramientas(_Ingredientes(), _Aliases(), {"sulphur": "azufre"})
    assert h.ingrediente("propanoquizafop") == "propaquizafop"
    assert h.ingrediente("clorpirifos") == "chlorpyrifos"                     # phonetic: ch/c, y/i
    assert h._nota("clorpirifos") == {"nombre_interpretado": "«clorpirifos» se leyó como chlorpyrifos"}
    assert h.ingrediente("xyzabcdef") == "xyzabcdef" and h._nota("xyzabcdef") == {}   # nothing close: left as written
    assert h.ingrediente("azufre") == "sulphur" and h._nota("azufre") == {}
