"""Builds the nodes and edges of the graph from dated snapshots. Pure code: no database, so it can be tested alone.

Each node is ``{"key": ..., **properties}`` and each edge is ``{"from": key, "to": key, **properties}``, grouped by
label or edge type in a :class:`GraphRecords`.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from knowledge.normalization.codex import CodexIndex
from knowledge.normalization.ingredients import ResidueIndex, ingredient_key
from knowledge.normalization.moa import MoaIndex
from knowledge.normalization.substances import SubstanceIndex
from knowledge.normalization.us import UsIndex
from knowledge.sources.eu_mrl.parser import parse_mrl
from knowledge.sources.sigia.parser import parse_pests, parse_products


@dataclass
class GraphRecords:
    nodes: dict[str, dict[str, dict]] = field(default_factory=lambda: defaultdict(dict))   # label -> key -> props
    edges: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))       # type -> list
    unmatched_ingredients: dict[str, str | None] = field(default_factory=dict)            # name -> known reason
    unclassified_ingredients: dict[str, str | None] = field(default_factory=dict)        # chemical, no MoA group
    us_absent_ingredients: dict[str, str | None] = field(default_factory=dict)           # chemical, no US section
    no_arfd_ingredients: list[str] = field(default_factory=list)                         # chemical, no EU substance
    _seen: dict = field(default_factory=dict, repr=False)

    def node(self, label: str, key: str, **props) -> str:
        current = self.nodes[label].setdefault(key, {"key": key})
        current.update({k: v for k, v in props.items() if v is not None})
        return key

    def edge(self, kind: str, src: str, dst: str, **props) -> None:
        """One edge per (type, source, target): the same ingredient appears in many products, but it is measured as
        its residue only once."""
        seen = self._seen.setdefault(kind, {})
        if (src, dst) in seen:
            seen[(src, dst)].update({k: v for k, v in props.items() if v is not None})
            return
        edge = {"from": src, "to": dst, **{k: v for k, v in props.items() if v is not None}}
        seen[(src, dst)] = edge
        self.edges[kind].append(edge)

    def summary(self) -> dict:
        return {"nodes": {k: len(v) for k, v in self.nodes.items()}, "edges": {k: len(v) for k, v in self.edges.items()},
                "unmatched_ingredients": len(self.unmatched_ingredients)}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def add_crops(rec: GraphRecords, crops: dict) -> None:
    for key, c in crops.items():
        rec.node("Crop", key, name_es=c.get("name_es"), scientific_name=c.get("scientific"), sigia_id=c.get("sigia_crop"),
                 eu_product_id=c.get("eu_product_id"), eu_code=c.get("eu_code"), us_crop_group=c.get("us_crop_group"))


def add_markets(rec: GraphRecords) -> None:
    for key, name in (("EU", "Unión Europea"), ("US", "Estados Unidos"), ("CODEX", "Codex Alimentarius")):
        rec.node("Market", key, name=name)


def add_sigia(rec: GraphRecords, folder: Path, crop_key: str, crop_id: str, index: ResidueIndex) -> None:
    """Pests, products, authorizations and ingredients of one crop from a SIGIA snapshot folder."""
    snapshot = f"sigia:{folder.name}"
    for pest in parse_pests(_read(folder / f"pests_{crop_id}.json")):
        key = pest.pest_id or f"use:{pest.other_use_class}"
        rec.node("Pest", key, scientific_name=pest.scientific_name or None, common_name=pest.common_name,
                 other_use=pest.is_other_use, snapshot=snapshot)

    for path in sorted(folder.glob(f"products_{crop_id}_*.json")):
        pest_key = path.stem.split("_", 2)[2]
        pest_key = f"use:{pest_key[3:]}" if pest_key.startswith("use") else pest_key
        for p in parse_products(_read(path)):
            rec.node("Product", p.product_id, trade_name=p.trade_name, registration_number=p.registration_number,
                     holder=p.holder_name, product_type=p.product_type, use_class=p.use_class, toxicity=p.toxicity,
                     snapshot=snapshot)
            auth = f"{p.product_id}:{crop_key}:{pest_key}"
            rec.node("Authorization", auth, preharvest_interval_days=p.preharvest_interval_days,
                     preharvest_not_applicable=p.preharvest_interval_not_applicable or None,
                     peru_mrl_mg_kg=p.peru_mrl_mg_kg, dose_unit=p.dose_unit,
                     dose_per_hectare=p.dose_per_hectare.raw if p.dose_per_hectare else None,
                     dose_per_tank=p.dose_per_tank.raw if p.dose_per_tank else None,
                     tank_capacity_l=p.tank_capacity_l, notes=p.notes, snapshot=snapshot)
            rec.edge("OF_PRODUCT", auth, p.product_id)
            rec.edge("ON_CROP", auth, crop_key)
            rec.edge("AGAINST", auth, pest_key)
            for name in p.active_ingredients:
                match = index.match(name)
                rec.node("Ingredient", match.iso, biological=p.is_biological)
                rec.edge("CONTAINS", p.product_id, match.iso)
                for rid in match.residue_ids:
                    # from the catalog too: a residue may have no limit row for these crops (chitosan, citronella oil)
                    rec.node("Residue", f"EU:{rid}", eu_id=rid, name_en=index.names.get(rid))
                    rec.edge("MEASURED_AS", match.iso, f"EU:{rid}", ambiguous=match.ambiguous or None)
                if not match.matched:
                    rec.unmatched_ingredients[match.iso] = match.not_in_eu


def add_eu(rec: GraphRecords, folder: Path, crops: dict) -> None:
    """Residues and MRL versions (with their REPLACES chain) from an EU snapshot folder."""
    snapshot = f"eu_mrl:{folder.name}"
    catalog = _read(folder / "residues_EN_ES.json")
    names: dict[int, dict] = defaultdict(dict)
    for row in catalog:
        names[int(row["pesticide_residue_id"])][row["pesticide_residue_lg"]] = row["pesticide_residue_name"].strip()

    for crop_key, crop in crops.items():
        code = crop.get("eu_code")
        path = folder / f"mrls_{code}.json"
        if not code or not path.exists():
            continue
        _add_mrl_versions(rec, [parse_mrl(i) for i in _read(path)], crop_key, names, snapshot)


def version_key(m) -> str:
    """Identity of one version: the same residue keeps its id across versions, which differ by regulation and date.
    A row repeated with different successors (``next_residue_id``) is the same version."""
    return f"EU:{m.product_id}:{m.residue_id}:{m.annex or '-'}:{m.applies_from or '-'}:{m.regulation}"


def _add_mrl_versions(rec: GraphRecords, versions: list, crop_key: str, names: dict, snapshot: str) -> None:
    unique: dict[str, object] = {}
    successors: dict[str, set[int]] = defaultdict(set)
    for m in versions:
        key = version_key(m)
        unique.setdefault(key, m)
        if m.next_residue_id:
            successors[key].add(m.next_residue_id)

    # One chain per residue across annexes: a limit can move from Annex III to Annex II with the same residue id.
    # Versions with the same application date (the same limit listed in two annexes) do not replace each other.
    chains: dict[int, list[str]] = defaultdict(list)
    for key, m in unique.items():
        chains[m.residue_id].append(key)
    first_date = {rid: min((unique[k].applies_from for k in keys if unique[k].applies_from), default=None)
                  for rid, keys in chains.items()}

    valid_until: dict[str, object] = {}
    replaces: list[tuple[str, str]] = []
    def order(k):
        m = unique[k]
        return (m.applies_from, m.voted_on or m.applies_from)

    def newer(k, old) -> bool:
        """Later application date; or the same date set by a regulation voted later (a correction of the earlier one).
        The same regulation listed in two annexes is not newer."""
        a, b = unique[k], unique[old]
        if a.regulation == b.regulation:
            return False
        return order(k) > order(old)

    for keys in chains.values():                                 # a later version of the same residue replaces it
        dated = sorted((k for k in keys if unique[k].applies_from), key=order)
        for old in dated:
            later = [k for k in dated if newer(k, old)]
            if later:
                first = min(order(k) for k in later)
                valid_until[old] = first[0]
                replaces += [(k, old) for k in later if order(k) == first]
    for old, nexts in successors.items():                        # a new residue definition replaces the old one
        if old in valid_until:
            continue
        starts = [(first_date[r], r) for r in nexts if first_date.get(r)]
        if starts:
            start, rid = min(starts)
            valid_until[old] = start
            replaces += [(k, old) for k in chains[rid] if unique[k].applies_from == start]

    for key, m in unique.items():
        residue = f"EU:{m.residue_id}"
        rec.node("Residue", residue, eu_id=m.residue_id, name_en=names.get(m.residue_id, {}).get("EN"),
                 name_es=names.get(m.residue_id, {}).get("ES"), snapshot=snapshot)
        rec.node("MrlVersion", key, value_mg_kg=m.value_mg_kg, value_text=m.value_text,
                 at_limit_of_determination=m.at_limit_of_determination, no_mrl_required=m.no_mrl_required,
                 regulation=m.regulation, regulation_url=m.regulation_url, annex=m.annex, voted_on=m.voted_on,
                 applies_from=m.applies_from, valid_until=valid_until.get(key), applicability=m.applicability.value,
                 # the EU says it no longer applies but its data carry no end date (withdrawn, or the successor is
                 # not listed for this product): never invented, flagged instead
                 end_date_unknown=(m.applicability.value == "No longer applicable" and key not in valid_until) or None,
                 version=m.version, footnote=m.footnote, snapshot=snapshot)
        rec.edge("OF_RESIDUE", key, residue)
        rec.edge("FOR_CROP", key, crop_key)
        rec.edge("IN_MARKET", key, "EU")
    for new, old in dict.fromkeys(replaces):
        rec.edge("REPLACES", new, old)


def add_us(rec: GraphRecords, sections: list, as_of: str, rules: dict, us: UsIndex, snapshot: str) -> None:
    """US tolerances and exemptions of 40 CFR 180 for the crops with commodity rules. The eCFR gives the text in force
    at ``as_of``: versions start that day and the Market node says so (``known_from``)."""
    rec.node("Market", "US", known_from=as_of, source="40 CFR Part 180 (eCFR)", snapshot=snapshot)
    for section in sections:
        residue = f"US:{section.number}:{section.substance}"
        for crop_key, rule in rules.items():
            if crop_key not in rec.nodes["Crop"]:
                continue
            versions = []
            if section.kind == "exemption":
                versions.append({"key": f"US:{crop_key}:{section.number}:{section.substance}:exempt",
                                 "value_mg_kg": None, "value_text": "Exempt", "no_mrl_required": True,
                                 "footnote": f"Exento del requisito de tolerancia, con las condiciones de uso de "
                                             f"40 CFR {section.number}: {section.exemption.text}",
                                 "regulation": f"40 CFR {section.number}", "valid_until": None})
            for t in section.tolerances:
                if not rule.covers(t.commodity):
                    continue
                notes = [n for n in (US_KIND_NOTE.get(t.kind), rule.note(t.commodity)) if n]
                versions.append({"key": f"US:{crop_key}:{section.number}:{t.paragraph}:{t.commodity}",
                                 "value_mg_kg": t.value_ppm, "value_text": t.value_text, "no_mrl_required": None,
                                 "footnote": "; ".join(notes) or None, "commodity": t.commodity,
                                 "regulation": f"40 CFR {section.number}{t.paragraph}",
                                 "valid_until": t.expires_on.isoformat() if t.expires_on else None})
            if not versions:
                continue
            rec.node("Residue", residue, name_en=section.substance, cfr_section=section.number, snapshot=snapshot)
            for v in versions:
                key = v.pop("key")
                rec.node("MrlVersion", key, applies_from=as_of, history_known=False, applicability="Applicable",
                         snapshot=snapshot, **v)
                rec.edge("OF_RESIDUE", key, residue)
                rec.edge("FOR_CROP", key, crop_key)
                rec.edge("IN_MARKET", key, "US")
    for key, props in list(rec.nodes["Ingredient"].items()):
        found = us.sections(key, biological=bool(props.get("biological")))
        for section in found:
            residue = f"US:{section.number}:{section.substance}"
            if residue in rec.nodes["Residue"]:
                rec.edge("MEASURED_AS", key, residue)
        if not found and not props.get("biological"):
            rec.us_absent_ingredients[key] = us.reason(key)


def add_toxicology(rec: GraphRecords, substances: SubstanceIndex | None, consumption: list | None,
                   codes: dict[str, int], snapshots: dict[str, str]) -> None:
    """ARfD of each ingredient (EU active substances) and the acute consumption of each crop (EFSA PRIMo)."""
    if substances is not None:
        for key, props in list(rec.nodes["Ingredient"].items()):
            a = substances.arfd(key)
            if a is not None:
                rec.node("Ingredient", key, arfd_mg_kg_bw=a.value_mg_kg_bw, arfd_status=a.status, arfd_source=a.source,
                         eu_substances=list(a.substances), arfd_snapshot=snapshots.get("eu_substances"))
            elif not props.get("biological"):
                rec.no_arfd_ingredients.append(key)
    if consumption is not None:
        for crop_key, code in codes.items():
            rows = [c.model_dump() for c in consumption if c.commodity_code == code]
            if crop_key in rec.nodes["Crop"] and rows:
                rec.node("Crop", crop_key, acute_consumption=rows, acute_snapshot=snapshots.get("primo"))


def add_codex(rec: GraphRecords, mrls: list, levels: dict, codex: CodexIndex, as_of: str, snapshot: str) -> None:
    """Codex MRLs. For each crop and pesticide only the most specific level counts (commodity, then subgroup, then
    group), as a commodity MRL prevails over the group one. The database gives the current list only: versions start
    on the snapshot date, with the adoption year as a note."""
    rec.node("Market", "CODEX", known_from=as_of, source="Codex Alimentarius, base de LMR de plaguicidas",
             snapshot=snapshot)
    by_code: dict[str, list] = defaultdict(list)
    for m in mrls:
        by_code[m.commodity_code].append(m)
    for crop_key, crop_levels in levels.items():
        if crop_key not in rec.nodes["Crop"]:
            continue
        chosen: dict[str, tuple] = {}
        for rank, level in enumerate(crop_levels):
            for m in by_code.get(level["code"], []):
                key = ingredient_key(m.pesticide)
                if key not in chosen:
                    chosen[key] = (m, level)
        for key, (m, level) in chosen.items():
            residue = f"CODEX:{key}"
            rec.node("Residue", residue, name_en=m.pesticide, snapshot=snapshot)
            version = f"CODEX:{crop_key}:{key}:{level['code']}"
            note = "; ".join(x for x in (f"adoptado en {m.year}" if m.year else None,
                                         f"LMR de {level['name']} ({level['code']})", m.notes) if x)
            rec.node("MrlVersion", version, value_mg_kg=m.value_mg_kg, value_text=m.value_text,
                     at_limit_of_determination=m.at_limit_of_determination or None, applies_from=as_of,
                     history_known=False, applicability="Applicable", footnote=note,
                     regulation=f"Codex Alimentarius, LMR de {m.pesticide} en {level['name']} ({level['code']})",
                     snapshot=snapshot)
            rec.edge("OF_RESIDUE", version, residue)
            rec.edge("FOR_CROP", version, crop_key)
            rec.edge("IN_MARKET", version, "CODEX")
    for key in list(rec.nodes["Ingredient"]):
        pesticide = codex.key(key)
        if pesticide and f"CODEX:{pesticide}" in rec.nodes["Residue"]:
            rec.edge("MEASURED_AS", key, f"CODEX:{pesticide}")


US_KIND_NOTE = {"section_18": "tolerancia temporal por exención de emergencia (sección 18)",
                "regional": "tolerancia con registro regional", "indirect": "residuos indirectos o inadvertidos"}


def add_moa(rec: GraphRecords, moa: MoaIndex, snapshot: str) -> None:
    """Mode-of-action groups of every ingredient already in the records. A chemical ingredient without a group must
    have a documented reason; biological agents are left without one when the lists do not name them."""
    for key, props in list(rec.nodes["Ingredient"].items()):
        entries = moa.entries(key)
        for e in entries:
            rec.node("MoaGroup", e.group, scheme=e.scheme, code=e.code, group_name=e.group_name, snapshot=snapshot)
            rec.edge("IN_GROUP", key, e.group, listed_as=e.name)
        if not entries and not props.get("biological"):
            rec.unclassified_ingredients[key] = moa.reason(key)


def build(sigia_folders: dict[str, Path], eu_folder: Path | None, crops: dict, index: ResidueIndex | None,
          moa: MoaIndex | None = None, moa_snapshot: str | None = None, us: dict | None = None,
          codex: dict | None = None, toxicology: dict | None = None) -> GraphRecords:
    """``sigia_folders``: crop key -> its latest SIGIA snapshot (each crop is downloaded on its own day).
    ``us``: {"sections", "as_of", "rules", "index", "snapshot"} from the latest 40 CFR 180 snapshot, or None."""
    rec = GraphRecords()
    add_crops(rec, crops)
    add_markets(rec)
    if eu_folder:
        add_eu(rec, eu_folder, crops)
    if index:
        for crop_key, folder in sorted(sigia_folders.items()):
            crop_id = crops[crop_key].get("sigia_crop")
            if crop_id and (folder / f"pests_{crop_id}.json").exists():
                add_sigia(rec, folder, crop_key, crop_id, index)
    if moa is not None:
        add_moa(rec, moa, moa_snapshot or "moa")
    if us is not None:
        add_us(rec, us["sections"], us["as_of"], us["rules"], us["index"], us["snapshot"])
    if codex is not None:
        add_codex(rec, codex["mrls"], codex["levels"], codex["index"], codex["as_of"], codex["snapshot"])
    if toxicology is not None:
        add_toxicology(rec, toxicology["substances"], toxicology["consumption"], toxicology["codes"],
                       toxicology["snapshots"])
    return rec
