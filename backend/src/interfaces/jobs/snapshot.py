"""Takes dated snapshots of the official sources.

Usage (from backend/):
    uv run python -m interfaces.jobs.snapshot sigia --crop blueberry
    uv run python -m interfaces.jobs.snapshot eu-mrl
    uv run python -m interfaces.jobs.snapshot moa
    uv run python -m interfaces.jobs.snapshot us-tolerances
    uv run python -m interfaces.jobs.snapshot codex
    uv run python -m interfaces.jobs.snapshot eu-substances
    uv run python -m interfaces.jobs.snapshot primo
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from knowledge.sources.codex.client import CodexClient
from knowledge.sources.codex.snapshot import take_snapshot as codex_snapshot
from knowledge.sources.eu_mrl.client import EuMrlClient
from knowledge.sources.eu_mrl.snapshot import take_snapshot as eu_snapshot
from knowledge.sources.eu_substances.snapshot import take_snapshot as substances_snapshot
from knowledge.sources.moa.client import MoaClient
from knowledge.sources.moa.snapshot import take_snapshot as moa_snapshot
from knowledge.sources.primo.snapshot import take_snapshot as primo_snapshot
from knowledge.sources.sigia.client import SigiaClient
from knowledge.sources.sigia.snapshot import take_snapshot as sigia_snapshot
from knowledge.sources.us_tolerances.client import EcfrClient
from knowledge.sources.us_tolerances.snapshot import take_snapshot as us_snapshot

CONFIG = Path(__file__).resolve().parents[3] / "config"


def crops() -> dict:
    return yaml.safe_load((CONFIG / "crops.yaml").read_text(encoding="utf-8"))


def moa_sources() -> dict:
    return yaml.safe_load((CONFIG / "moa_sources.yaml").read_text(encoding="utf-8"))


def codex_commodities() -> dict:
    return yaml.safe_load((CONFIG / "codex_commodities.yaml").read_text(encoding="utf-8"))


def primo_codes(config: dict | None = None) -> dict[str, int]:
    """Crop key -> EU commodity code without the leading zero, as PRIMo writes it (0154010 -> 154010)."""
    return {k: int(v["eu_code"]) for k, v in (config or crops()).items() if v.get("eu_code")}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="source", required=True)
    s = sub.add_parser("sigia", help="SENASA registry for one crop")
    s.add_argument("--crop", required=True, help="key in config/crops.yaml, e.g. blueberry")
    sub.add_parser("eu-mrl", help="EU limits for every crop with an eu_code")
    sub.add_parser("moa", help="FRAC, IRAC and HRAC mode-of-action classifications")
    sub.add_parser("us-tolerances", help="US tolerances and exemptions, 40 CFR Part 180 (eCFR)")
    sub.add_parser("codex", help="Codex MRLs for the commodities of config/codex_commodities.yaml")
    sub.add_parser("eu-substances", help="EU active substances with their ARfD")
    sub.add_parser("primo", help="EFSA PRIMo 3.1 acute consumption data")
    args = parser.parse_args(argv)

    config = crops()
    if args.source == "eu-substances":
        with EuMrlClient() as client:
            snap = substances_snapshot(client)
    elif args.source == "primo":
        with MoaClient() as client:
            snap = primo_snapshot(yaml.safe_load((CONFIG / "primo.yaml").read_text(encoding="utf-8")),
                                  primo_codes(config), client)
    elif args.source == "codex":
        with CodexClient() as client:
            snap = codex_snapshot(codex_commodities(), client)
    elif args.source == "us-tolerances":
        with EcfrClient() as client:
            snap = us_snapshot(client)
    elif args.source == "moa":
        with MoaClient() as client:
            snap = moa_snapshot(moa_sources(), client)
    elif args.source == "sigia":
        crop_id = config[args.crop].get("sigia_crop")
        if not crop_id:
            raise SystemExit(f"{args.crop} has no sigia_crop in config/crops.yaml yet")
        with SigiaClient() as client:
            snap = sigia_snapshot(crop_id, client)
    else:
        codes = {k: v["eu_code"] for k, v in config.items() if v.get("eu_code")}
        with EuMrlClient() as client:
            snap = eu_snapshot(codes, client)
    print(f"{snap.folder}  {snap.counts}")


if __name__ == "__main__":
    main()
