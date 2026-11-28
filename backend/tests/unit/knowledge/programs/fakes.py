"""A graph that answers the few queries the program importer makes, and the aliases it needs."""
from __future__ import annotations


class FakeGraph:
    def __init__(self, ingredients, products, pests, doses):
        self.ingredients = ingredients          # [key]
        self.products = products                # [(key, trade name, [ingredients])]
        self.pests = pests                      # [(key, common name, scientific name)]
        self.doses = doses                      # [(product, pest, unit, per hectare, per tank)]

    def run(self, cypher, params=None, columns=("result",)):
        if "MATCH (i:Ingredient)" in cypher:
            return [(k,) for k in self.ingredients]
        if "MATCH (p:Product) OPTIONAL MATCH" in cypher:
            return list(self.products)
        if "RETURN DISTINCT p.key, p.common_name" in cypher:
            return list(self.pests)
        if "a.dose_unit" in cypher:
            return [(x, u, h, t) for p, x, u, h, t in self.doses if p in params["products"]]
        raise AssertionError(f"consulta no prevista: {cypher}")


class FakeAliases:
    def iso(self, name):
        return name.strip().lower()


def grafo():
    return FakeGraph(
        ingredients=["pyraclostrobin", "sulphur", "chlorpyrifos"],
        products=[("ADIKO", "ADIKO SC", ["pyraclostrobin"]), ("AZUFRAL", "AZUFRAL 80 WP", ["sulphur"]),
                  ("LORSBAN", "LORSBAN 4E", ["chlorpyrifos"]), ("PIRIMOR", "PIRIMOR 48 EC", ["chlorpyrifos"])],
        pests=[("000437", "Oidiosis", "Erysiphe necator"), ("001451", "Oidiosis", "Erysiphe sp"),
               ("011204", "Oidium", "Oidium tuckeri"), ("000626", "Moho gris", "Botrytis cinerea"),
               ("use:0298", "Inmersion de frutos", "Botrytis cinerea")],
        doses=[("LORSBAN", "000626", "Lt", "1 - 1.5", ".2 - .3"), ("PIRIMOR", "000626", "Litro", None, ".4 - .5"),
               ("AZUFRAL", "000437", "kl", "2 - 3", None)])
