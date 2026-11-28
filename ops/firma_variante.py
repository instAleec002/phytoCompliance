"""Firma de una variante de troceado y cuántos fragmentos tiene ya en la base (para no volver a indexarla).

    python ops/firma_variante.py max_tokens=256 header=short table_rows=true
"""
import sys

from knowledge.corpus.store import connect
from knowledge.documents import load_config


def valor(v: str):
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    return int(v) if v.isdigit() else v


opciones = dict(a.split("=", 1) for a in sys.argv[1:])
firma = load_config(**{k: valor(v) for k, v in opciones.items()}).signature()
n = connect().execute("SELECT count(*) FROM fragmentos WHERE firma = %s", (firma,)).fetchone()[0]
print(firma, n)
