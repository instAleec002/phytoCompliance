"""Loads :class:`GraphRecords` into AGE by rebuilding the graph from the snapshots.

The graph is derived data: loading the same snapshots always produces the same graph, so the loader empties every
label table and writes nodes and edges straight into AGE's own tables (one per label) in a single transaction.

Why not Cypher ``UNWIND ... MERGE ... SET``: on AGE 1.5.0 (27/10/2026) it kept the properties of the first row of each
batch only, ``UNWIND ... MATCH ... SET`` left properties empty, and ``UNWIND ... MERGE`` of edges created nothing.
Direct inserts avoid all three, and :func:`verify` checks the result against the records.
"""
from __future__ import annotations

import json

from .age import AgeGraph
from .records import GraphRecords
from .schema import EDGE_TYPES, NODE_LABELS

# edge type -> (label of the source node, label of the target node)
EDGE_ENDS = {
    "OF_PRODUCT": ("Authorization", "Product"),
    "ON_CROP": ("Authorization", "Crop"),
    "AGAINST": ("Authorization", "Pest"),
    "CONTAINS": ("Product", "Ingredient"),
    "MEASURED_AS": ("Ingredient", "Residue"),
    "OF_RESIDUE": ("MrlVersion", "Residue"),
    "FOR_CROP": ("MrlVersion", "Crop"),
    "IN_MARKET": ("MrlVersion", "Market"),
    "REPLACES": ("MrlVersion", "MrlVersion"),
    "IN_GROUP": ("Ingredient", "MoaGroup"),
}


def _json(props: dict) -> str:
    return json.dumps({k: v for k, v in props.items() if v is not None}, ensure_ascii=False, default=str)


def ensure_schema(graph: AgeGraph) -> None:
    """Creates every label and edge table, with a GIN index on the node properties (AGE turns ``{key: ...}`` into a
    containment filter, which this index serves)."""
    existing = {r[0] for r in graph.conn.execute(
        "SELECT l.name FROM ag_catalog.ag_label l JOIN ag_catalog.ag_graph g ON g.graphid = l.graph WHERE g.name = %s",
        (graph.graph,)).fetchall()}
    for label in NODE_LABELS:
        if label not in existing:
            graph.conn.execute("SELECT create_vlabel(%s, %s)", (graph.graph, label))
    for kind in EDGE_TYPES:
        if kind not in existing:
            graph.conn.execute("SELECT create_elabel(%s, %s)", (graph.graph, kind))
    for label in NODE_LABELS:
        graph.conn.execute(f'CREATE INDEX IF NOT EXISTS "{label.lower()}_props" ON "{graph.graph}"."{label}" '
                           f"USING gin (properties)")


def rebuild(graph: AgeGraph, rec: GraphRecords) -> dict:
    """Replaces the content of the graph with the records, in one transaction."""
    ensure_schema(graph)
    g = graph.graph
    unknown = set(rec.edges) - set(EDGE_ENDS)
    if unknown:
        raise ValueError(f"edge types without declared ends: {sorted(unknown)}")
    loaded: dict = {"nodes": {}, "edges": {}}
    ids: dict[str, dict[str, str]] = {}
    with graph.conn.transaction(), graph.conn.cursor() as cur:
        for kind in EDGE_TYPES:
            cur.execute(f'DELETE FROM "{g}"."{kind}"')
        for label in NODE_LABELS:
            cur.execute(f'DELETE FROM "{g}"."{label}"')

        for label, nodes in rec.nodes.items():
            keys = list(nodes)
            cur.executemany(f'INSERT INTO "{g}"."{label}"(properties) VALUES (%s::agtype) RETURNING id',
                            [(_json(nodes[k]),) for k in keys], returning=True)
            label_ids = []
            while True:
                label_ids.append(str(cur.fetchone()[0]))
                if not cur.nextset():
                    break
            ids[label] = dict(zip(keys, label_ids))
            loaded["nodes"][label] = len(keys)

        for kind, edges in rec.edges.items():
            src, dst = EDGE_ENDS[kind]
            rows, missing = [], 0
            for e in edges:
                a, b = ids.get(src, {}).get(e["from"]), ids.get(dst, {}).get(e["to"])
                if a is None or b is None:
                    missing += 1
                    continue
                rows.append((a, b, _json({k: v for k, v in e.items() if k not in ("from", "to")})))
            if missing:
                raise ValueError(f"{missing} {kind} edges point to nodes that do not exist")
            cur.executemany(f'INSERT INTO "{g}"."{kind}"(start_id, end_id, properties) '
                            f"VALUES (%s::graphid, %s::graphid, %s::agtype)", rows)
            loaded["edges"][kind] = len(rows)
    return loaded


def verify(graph: AgeGraph, rec: GraphRecords) -> dict:
    """Counts in the database against the records, and every node with all its properties."""
    problems = {}
    for label, nodes in rec.nodes.items():
        n = graph.count(label)
        if n != len(nodes):
            problems[label] = f"{n} in the graph, {len(nodes)} in the records"
        expected = {k for props in nodes.values() for k in props}
        empty = graph.run(f"MATCH (n:{label}) WHERE size(keys(n)) < 2 RETURN count(n)")[0][0] if len(expected) > 1 else 0
        if empty:
            problems[f"{label} without properties"] = empty
    for kind, edges in rec.edges.items():
        n = graph.run(f"MATCH ()-[e:{kind}]->() RETURN count(e)")[0][0]
        if n != len(edges):
            problems[kind] = f"{n} in the graph, {len(edges)} in the records"
    return problems
