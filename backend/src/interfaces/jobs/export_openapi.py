"""Writes the OpenAPI schema of the API, from which the frontend generates its types.

Usage (from backend/):
    uv run python -m interfaces.jobs.export_openapi ../frontend/src/lib/api/openapi.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from interfaces.api.app import create_app
from shared.settings import Settings


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        raise SystemExit("usage: export_openapi <output.json>")
    schema = create_app(Settings(_env_file=None)).openapi()
    Path(args[0]).write_bytes((json.dumps(schema, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(f"{args[0]}: {len(schema['paths'])} paths")


if __name__ == "__main__":
    main()
