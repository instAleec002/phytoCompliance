"""Codex pages (HTML fragments as codex.fao.org served them on 28/10/2026) and the precedence of levels."""
import pytest

from knowledge.graph.records import GraphRecords, add_codex
from knowledge.normalization.codex import CodexAliases, CodexIndex
from knowledge.sources.codex.models import CodexMrl
from knowledge.sources.codex.parser import parse_commodities, parse_commodity_page, parse_pesticide_index
from knowledge.sources.codex.snapshot import LayoutChanged, resolve

TREE = """<li class="category-item "
                    data-commodity-id="0552602c-179b-f111-b8dc-70a8a5613865"
                    data-level="3"
                    data-item-type="Commodity"><div><a class="category-link"><span class="category-label">Blueberries</span>
</a></div><div class="category-code-container ms-auto"><a><span class="category-code text-muted">FB 0020</span></a>
</div></li>"""

ROW = """<tr class="table-row "><td data-label="Pesticides"><a href="/x/pesticide-details?pestId=1">
 Mesotrione </a></td><td><span class="mrl-value">0.01</span> <span class="mrl-unit">mg/Kg</span></td>
<td><span class="year-value">2015</span></td><td data-label="Symbols">(*)</td><td data-label="Notes"></td></tr>"""
PAGE = f'<html><table class="unified-table" id="myTable"><tbody>{ROW}</tbody></table></html>'
EMPTY = "<html><main><h2>FB 4073 - Blueberry, highbush</h2><p>No results</p></main></html>"


def test_commodity_tree():
    [c] = parse_commodities(TREE)
    assert (c.code, c.name, c.id) == ("FB 0020", "Blueberries", "0552602c-179b-f111-b8dc-70a8a5613865")


def test_commodity_page_row_with_limit_of_determination():
    [m] = parse_commodity_page(PAGE, "FB 2006")
    assert (m.pesticide, m.value_mg_kg, m.year, m.at_limit_of_determination) == ("Mesotrione", 0.01, 2015, True)


def test_commodity_without_mrls_and_changed_layout():
    assert parse_commodity_page(EMPTY, "FB 4073") == []
    with pytest.raises(ValueError):
        parse_commodity_page("<html><p>Something else</p></html>", "FB 4073")


def test_pesticide_index():
    page = '<a href="/x/pesticide-details?pestId=a1">Abamectin (177)</a><a href="/x/pesticide-details?pestId=b2">' \
           'Fosetyl aluminium (302)</a>'
    assert parse_pesticide_index(page) == ["Abamectin (177)", "Fosetyl aluminium (302)"]


def test_resolve_needs_each_code_once():
    commodities = parse_commodities(TREE)
    assert resolve(commodities, {"blueberry": [{"code": "FB 0020"}]}) == {"FB 0020": commodities[0].id}
    with pytest.raises(LayoutChanged):
        resolve(commodities, {"blueberry": [{"code": "FB 2006"}]})


def mrl(code, pesticide, value, year=2020):
    return CodexMrl(commodity_code=code, pesticide=pesticide, value_mg_kg=value, value_text=f"{value} mg/Kg", year=year,
                    at_limit_of_determination=False, symbols=None, notes=None)


def test_the_most_specific_level_prevails_not_the_strictest():
    rec = GraphRecords()
    rec.node("Crop", "blueberry")
    rec.node("Ingredient", "spirotetramat")
    rec.node("Ingredient", "lambda-cyhalothrin")
    levels = {"blueberry": [{"code": "FB 0020", "name": "Blueberries", "level": "commodity"},
                            {"code": "FB 2006", "name": "Bush berries (subgroup)", "level": "subgroup"},
                            {"code": "FB 0018", "name": "Berries and other small fruits", "level": "group"}]}
    mrls = [mrl("FB 0018", "Spirotetramat", 0.5), mrl("FB 2006", "Spirotetramat", 1.5),
            mrl("FB 0018", "Cyhalothrin (includes lambda-cyhalothrin)", 0.2)]
    index = CodexIndex(["Spirotetramat (234)", "Cyhalothrin (includes lambda-cyhalothrin) (146)"], CodexAliases.load())
    add_codex(rec, mrls, levels, index, "2026-10-28", "codex:test")
    versions = {k: v for k, v in rec.nodes["MrlVersion"].items()}
    assert versions["CODEX:blueberry:spirotetramat:FB 2006"]["value_mg_kg"] == 1.5      # subgroup over group
    assert not any(k.endswith("spirotetramat:FB 0018") for k in versions)
    assert {e["to"] for e in rec.edges["MEASURED_AS"]} == {"CODEX:spirotetramat", "CODEX:cyhalothrin"}
    assert rec.nodes["Market"]["CODEX"]["known_from"] == "2026-10-28"
