"""Codex pesticide residue database (codex.fao.org), as server-rendered HTML.

- The commodity tree lists every commodity, subgroup and group with its id and Codex code ("FB 0020").
- A commodity page has one table: pesticide | MRL ("4.0 mg/Kg") | year adopted | symbols ("(*)": at or about the limit
  of determination) | notes.
- The pesticide index lists the pesticides with current Codex MRLs ("Abamectin (177)").
"""
from __future__ import annotations

import html
import re

from .models import CodexCommodity, CodexMrl

_ITEM = re.compile(r'<li class="category-item[^"]*"\s+data-commodity-id="([^"]+)"\s+data-level="(\d+)"\s+'
                   r'data-item-type="([^"]+)">(.*?)</li>', re.DOTALL)
_LABEL = re.compile(r'category-label">([^<]+)<')
_CODE = re.compile(r'category-code text-muted">([^<]+)<')
_ROW = re.compile(r'<tr class="table-row[^"]*">(.*?)</tr>', re.DOTALL)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_INDEX = re.compile(r'<a [^>]*href="[^"]*pesticide-details\?pestId=([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_VALUE = re.compile(r"^(\d*\.?\d+)\s*mg/kg$", re.IGNORECASE)


def _clean(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_commodities(page: str) -> list[CodexCommodity]:
    out = []
    for cid, level, kind, body in _ITEM.findall(page):
        label, code = _LABEL.search(body), _CODE.search(body)
        if label:
            out.append(CodexCommodity(id=cid, code=_clean(code.group(1)) if code else None,
                                      name=_clean(label.group(1)), tree_level=int(level), item_type=kind))
    return out


def parse_commodity_page(page: str, commodity_code: str) -> list[CodexMrl]:
    if 'id="myTable"' not in page:
        if f"{commodity_code} -" in _clean(page) and "No results" in _clean(page):
            return []                         # the commodity has no MRL of its own (its subgroup or group may)
        raise ValueError(f"Codex page of {commodity_code} without its MRL table: the layout changed")
    out = []
    for row in _ROW.findall(page):
        cells = [_clean(c) for c in _CELL.findall(row)]
        if len(cells) < 5:
            continue
        pesticide, value, year, symbols, notes = cells[:5]
        m = _VALUE.match(value)
        out.append(CodexMrl(commodity_code=commodity_code, pesticide=pesticide,
                            value_mg_kg=float(m.group(1)) if m else None, value_text=value,
                            year=int(year) if year.isdigit() else None,
                            at_limit_of_determination="(*)" in symbols, symbols=symbols or None, notes=notes or None))
    return out


def parse_pesticide_index(page: str) -> list[str]:
    return [_clean(name) for _, name in _INDEX.findall(page)]
