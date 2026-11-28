"""Loads the latest SIGIA and EU snapshots into the graph.

Usage (from backend/):
    uv run python -m interfaces.jobs.load_graph            # latest snapshots
    uv run python -m interfaces.jobs.load_graph --dry-run  # only build and count the records
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date

from interfaces.jobs.snapshot import codex_commodities, crops, moa_sources, primo_codes
from knowledge.graph.age import AgeGraph
from knowledge.graph.consistency import check_against_eu_status
from knowledge.graph.loader import rebuild, verify
from knowledge.graph.records import build
from knowledge.normalization.codex import CodexIndex
from knowledge.normalization.ingredients import ResidueIndex
from knowledge.normalization.moa import MoaIndex
from knowledge.normalization.substances import SubstanceIndex
from knowledge.normalization.us import UsIndex
from knowledge.snapshots.store import latest
from knowledge.sources.codex.models import CodexMrl
from knowledge.sources.eu_substances.models import ActiveSubstance
from knowledge.sources.moa.snapshot import parse_folder
from knowledge.sources.primo.models import AcuteConsumption
from knowledge.sources.us_tolerances.commodities import load_rules
from knowledge.sources.us_tolerances.models import UsSection


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    config = crops()
    sigia = {k: f for k, c in config.items() if c.get("sigia_crop") and (f := latest(f"sigia/{c['sigia_crop']}"))}
    eu = latest("eu_mrl")
    if eu is None:
        raise SystemExit("No EU snapshot yet: run interfaces.jobs.snapshot eu-mrl first")
    catalog = json.loads((eu / "residues_EN_ES.json").read_text(encoding="utf-8"))
    index = ResidueIndex(catalog)
    missing = index.missing_targets()
    if missing:
        raise SystemExit(f"Alias targets not in the EU catalog (update config/ingredient_aliases.yaml): {missing}")
    moa_folder = latest("moa")
    moa = None
    if moa_folder is not None:
        moa = MoaIndex(parse_folder(moa_folder, moa_sources()))
        if moa.missing_targets():
            raise SystemExit(f"MoA alias targets not in the lists (update config/moa_aliases.yaml): {moa.missing_targets()}")
    us_folder = latest("us_tolerances")
    us = None
    if us_folder is not None:
        sections = [UsSection(**s) for s in json.loads((us_folder / "sections.json").read_text(encoding="utf-8"))]
        manifest = json.loads((us_folder / "manifest.json").read_text(encoding="utf-8"))
        us_index = UsIndex(sections)
        if us_index.missing_targets():
            raise SystemExit(f"US alias targets not in Part 180 (update config/us_aliases.yaml): "
                             f"{us_index.missing_targets()}")
        us = {"sections": sections, "as_of": manifest["params"]["ecfr_up_to_date_as_of"], "rules": load_rules(),
              "index": us_index, "snapshot": f"us_tolerances:{us_folder.name}"}
    codex_folder = latest("codex")
    codex = None
    if codex_folder is not None:
        mrls = [CodexMrl(**m) for m in json.loads((codex_folder / "mrls.json").read_text(encoding="utf-8"))]
        codex_index = CodexIndex(json.loads((codex_folder / "pesticides.json").read_text(encoding="utf-8")))
        if codex_index.missing_targets():
            raise SystemExit(f"Codex alias targets not in the pesticide index (update config/codex_aliases.yaml): "
                             f"{codex_index.missing_targets()}")
        codex = {"mrls": mrls, "levels": codex_commodities(), "index": codex_index, "as_of": codex_folder.name,
                 "snapshot": f"codex:{codex_folder.name}"}
    toxicology = None
    subs_folder, primo_folder = latest("eu_substances"), latest("primo")
    if subs_folder is not None or primo_folder is not None:
        substances = None
        if subs_folder is not None:
            raw = json.loads((subs_folder / "active_substances.json").read_text(encoding="utf-8"))
            substances = SubstanceIndex([ActiveSubstance(**s) for s in raw])
            if substances.missing_targets():
                raise SystemExit(f"Substance alias targets not in the EU list (update config/substance_aliases.yaml): "
                                 f"{substances.missing_targets()}")
        consumption = None
        if primo_folder is not None:
            consumption = [AcuteConsumption(**c) for c in
                           json.loads((primo_folder / "acute_consumption.json").read_text(encoding="utf-8"))]
        toxicology = {"substances": substances, "consumption": consumption, "codes": primo_codes(config),
                      "snapshots": {"eu_substances": subs_folder and f"eu_substances:{subs_folder.name}",
                                    "primo": primo_folder and f"primo:{primo_folder.name}"}}
    rec = build(sigia, eu, config, index, moa, f"moa:{moa_folder.name}" if moa_folder else None, us, codex,
                toxicology)
    print("snapshots:", {"sigia": {k: f.name for k, f in sigia.items()}, "eu_mrl": eu.name, "moa": moa_folder and moa_folder.name,
                         "us_tolerances": us_folder and us_folder.name, "codex": codex_folder and codex_folder.name,
                         "eu_substances": subs_folder and subs_folder.name, "primo": primo_folder and primo_folder.name})
    if toxicology is not None:
        print("ARfD: chemical ingredients without an EU active substance:", rec.no_arfd_ingredients)
    print("records:", json.dumps(rec.summary(), ensure_ascii=False))
    reasons = Counter(r.split(";")[0].split(" (")[0] for r in rec.unmatched_ingredients.values() if r)
    print("ingredients without an EU residue, by reason:", json.dumps(reasons, ensure_ascii=False))
    unexplained = sorted(k for k, r in rec.unmatched_ingredients.items() if r is None)
    if unexplained:
        raise SystemExit(f"Ingredients with no EU residue and no documented reason (add them to "
                         f"config/ingredient_aliases.yaml): {unexplained}")
    groups = Counter(e["to"].split(":")[0] for e in rec.edges.get("IN_GROUP", []))
    print("ingredients in mode-of-action groups:", json.dumps(groups),
          "| chemical without a group:", len(rec.unclassified_ingredients))
    unclassified = sorted(k for k, r in rec.unclassified_ingredients.items() if r is None)
    if unclassified:
        raise SystemExit(f"Chemical ingredients with no mode-of-action group and no documented reason (add them to "
                         f"config/moa_aliases.yaml): {unclassified}")
    if us is not None:
        print("US: chemical ingredients without a section (not permitted):", len(rec.us_absent_ingredients))
        unchecked = sorted(k for k, r in rec.us_absent_ingredients.items() if r is None)
        if unchecked:
            raise SystemExit(f"Chemical ingredients with no 40 CFR 180 section that nobody checked (add them to "
                             f"config/us_aliases.yaml): {unchecked}")
    report = check_against_eu_status(rec, date.fromisoformat(eu.name))
    print("consistency with the EU status:", json.dumps(
        {c: {k: v if not isinstance(v, list) else len(v) for k, v in r.items()} for c, r in report.items()}))
    if any(r["only_by_dates"] or r["only_by_eu"] for r in report.values()):
        raise SystemExit("The version chain does not match the EU status; nothing was loaded")
    if args.dry_run:
        return
    with AgeGraph.connect() as graph:
        print("loaded:", json.dumps(rebuild(graph, rec), ensure_ascii=False))
        problems = verify(graph, rec)
        if problems:
            raise SystemExit(f"The graph does not match the records: {problems}")
        print("verified: every node and edge is in the graph, with its properties")


if __name__ == "__main__":
    main()
