"""Parses the answers of the EU Pesticides Database API (v3.0): paged MRL lists, the bulk NDJSON download and the
product list."""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import date, datetime

from .models import Applicability, EuProduct, MrlVersion


def to_date(text) -> date | None:
    if not text:
        return None
    return datetime.strptime(str(text).strip(), "%d/%m/%Y").date()


def to_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def to_float(value) -> float | None:
    """Numeric value of a limit; None for empty or textual values such as "No MRL required"."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace("*", "").replace(",", ".").strip())
    except ValueError:
        return None


def parse_mrl(item: dict) -> MrlVersion:
    """Works for both shapes: the paged ``pesticide-residues-mrls`` items and the rows of the bulk download, which also
    carry the residue and product names."""
    text = str(item.get("mrl_value") or "").strip()
    return MrlVersion(
        residue_id=int(item["pesticide_residue_id"]),
        residue_name=(item.get("pesticide_residue_name") or "").strip() or None,
        product_id=int(float(item["product_id"])),
        product_code=item.get("product_code"),
        product_name=item.get("product_name"),
        value_mg_kg=to_float(item.get("mrl_value_only") or text),
        value_text=text,
        at_limit_of_determination=(item.get("mrl_lod") == "*") or text.endswith("*"),
        no_mrl_required="no mrl required" in text.lower(),
        regulation=item.get("regulation_number") or "",
        regulation_url=item.get("regulation_url"),
        annex=item.get("included_in_annex"),
        voted_on=to_date(item.get("voted_date")),
        in_force_on=to_date(item.get("entry_into_force_date")),
        applies_from=to_date(item.get("application_date")),
        applicability=Applicability(item.get("applicability_text") or "Applicable"),
        version=to_int(item.get("current_version_number", item.get("pesticide_residue_version_nbr"))),
        original_residue_id=to_int(item.get("original_pesticide_residue_id")),
        next_residue_id=to_int(item.get("next_pesticide_residue_id")),
        footnote=item.get("footnote_text") or item.get("pesticide_residue_footnote"),
    )


def parse_page(payload: dict) -> list[MrlVersion]:
    return [parse_mrl(item) for item in payload.get("value", [])]


def iter_ndjson(lines: Iterable[str | bytes], product_codes: set[str] | None = None) -> Iterator[MrlVersion]:
    """Rows of the bulk download, optionally only for some product codes (e.g. {"0154010"} for blueberries)."""
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if product_codes and item.get("product_code") not in product_codes:
            continue
        yield parse_mrl(item)


def parse_products(payload: dict) -> list[EuProduct]:
    out = []
    for item in payload.get("value", []):
        names = [n.strip() for n in (item.get("product_scientific_names") or "").split(",") if n.strip()]
        out.append(EuProduct(product_id=int(item["product_id"]), parent_id=to_int(item.get("product_parent_id")),
                             code=item["product_code"], name=item["product_name"], scientific_names=names))
    return out
