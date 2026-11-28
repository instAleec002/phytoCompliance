"""Regla de la arquitectura: el dominio (reglas exactas) no depende de la capa de lenguaje."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nombres = set()
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.Import):
            nombres |= {a.name.split(".")[0] for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.add(nodo.module.split(".")[0])
    return nombres


def test_domain_does_not_import_assistant_or_interfaces():
    prohibidos = {"assistant", "interfaces"}
    for archivo in (SRC / "domain").rglob("*.py"):
        assert not (_imports(archivo) & prohibidos), f"{archivo} importa la capa de lenguaje o las interfaces"


def test_domain_reads_data_only_through_its_ports():
    """Las reglas reciben los datos por los puertos de domain.ports: no conocen el grafo ni la base de datos."""
    prohibidos = {"knowledge", "psycopg", "fastapi"}
    for archivo in (SRC / "domain").rglob("*.py"):
        assert not (_imports(archivo) & prohibidos), f"{archivo} accede a los datos sin pasar por los puertos"
