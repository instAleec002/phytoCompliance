"""The corpus in PostgreSQL (schema ``corpus``): documents with their status, chunks per pipeline signature with a
lexical index, and dense vectors per embedding model (pgvector, HNSW, cosine). Migrations follow the accounts
pattern: numbered SQL files applied once each.

The pgvector type lives in ``public``, so the search path is ``corpus, public``."""
from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path

import psycopg

from knowledge.documents.model import Chunk
from shared.settings import settings

from .download import DocumentRecord

SCHEMA = "corpus"
MIGRATIONS = Path(__file__).parent / "migrations"


def connect(schema: str = SCHEMA, url: str | None = None) -> psycopg.Connection:
    if not schema.replace("_", "").isalnum():
        raise ValueError(f"invalid schema name: {schema}")
    conn = psycopg.connect(url or settings.database_url, autocommit=True)
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    conn.execute(f'SET search_path = "{schema}", public')
    return conn


def migrate(conn: psycopg.Connection) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS migraciones (nombre text PRIMARY KEY, aplicada timestamptz NOT NULL DEFAULT now())")
    done = {r[0] for r in conn.execute("SELECT nombre FROM migraciones").fetchall()}
    applied = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO migraciones (nombre) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied


def vector_literal(v: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


class CorpusStore:
    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    # documents ----------------------------------------------------------------------------------------------------
    def upsert_documents(self, records: Iterable[DocumentRecord], snapshot: str) -> None:
        with self.conn.transaction():
            for r in records:
                self.conn.execute(
                    """INSERT INTO documentos (doc_id, fuente, nivel, titulo, anio, tipo, licencia, url, archivo, sha256,
                                               instantanea, estado, motivo)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (doc_id) DO UPDATE SET fuente=EXCLUDED.fuente, nivel=EXCLUDED.nivel,
                         titulo=EXCLUDED.titulo, anio=EXCLUDED.anio, tipo=EXCLUDED.tipo, licencia=EXCLUDED.licencia,
                         url=EXCLUDED.url, archivo=EXCLUDED.archivo, sha256=EXCLUDED.sha256,
                         instantanea=EXCLUDED.instantanea,
                         estado=CASE WHEN documentos.sha256 = EXCLUDED.sha256 AND documentos.estado = 'indexado'
                                     THEN 'indexado' ELSE EXCLUDED.estado END,
                         motivo=EXCLUDED.motivo, actualizado=now()""",
                    (r.doc_id, r.source, r.level, r.title or r.doc_id, r.year, r.doc_type, r.licence or "", r.url,
                     r.file, r.sha256, snapshot, r.status, r.reason))

    def set_status(self, doc_id: str, status: str, reason: str = "", pages: int | None = None,
                   fmt: str | None = None, text_pages: int | None = None) -> None:
        """``text_pages``: pages with extractable text; the rest of ``pages`` are counted as skipped (OCR off)."""
        no_text = pages - text_pages if pages is not None and text_pages is not None else None
        self.conn.execute("UPDATE documentos SET estado=%s, motivo=%s, paginas=COALESCE(%s, paginas), "
                          "formato=COALESCE(%s, formato), paginas_con_texto=COALESCE(%s, paginas_con_texto), "
                          "paginas_sin_texto=COALESCE(%s, paginas_sin_texto), actualizado=now() WHERE doc_id=%s",
                          (status, reason, pages, fmt, text_pages, no_text, doc_id))

    def documents(self, status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM documentos" + (" WHERE estado = %s" if status else "") + " ORDER BY fuente, doc_id"
        cur = self.conn.execute(sql, (status,) if status else ())
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    # chunks and vectors -------------------------------------------------------------------------------------------
    def replace_chunks(self, doc_id: str, signature: str, chunks: Sequence[Chunk]) -> None:
        with self.conn.transaction():
            self.conn.execute("DELETE FROM fragmentos WHERE doc_id=%s AND firma=%s", (doc_id, signature))
            with self.conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO fragmentos (chunk_id, firma, doc_id, orden, texto, encabezado, paginas, seccion,
                                               tipos, tokens, rol, padre, texto_vector)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [(c.chunk_id, signature, doc_id, i, c.text, c.header, list(c.pages), list(c.section), list(c.kinds),
                      c.tokens, c.meta.get("role", "atomic"), c.meta.get("parent_id"), c.vector_text or None)
                     for i, c in enumerate(chunks)])

    def save_vectors(self, signature: str, model: str, rows: Sequence[tuple[str, Sequence[float]]]) -> None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO vectores (chunk_id, firma, modelo, vector) VALUES (%s,%s,%s,%s::vector)
                   ON CONFLICT (chunk_id, firma, modelo) DO UPDATE SET vector = EXCLUDED.vector""",
                [(cid, signature, model, vector_literal(v)) for cid, v in rows])

    def pending_embeddings(self, signature: str, model: str) -> list[tuple[str, str]]:
        """(chunk_id, text to encode) of the embeddable chunks of a signature that have no vector for ``model`` yet;
        the text is the header plus the chunk (or its sentence form, for tables), exactly as Chunk.embedding_text builds it."""
        rows = self.conn.execute(
            """SELECT f.chunk_id, f.encabezado, COALESCE(f.texto_vector, f.texto) FROM fragmentos f
               WHERE f.firma = %s AND f.rol <> 'parent'
                 AND NOT EXISTS (SELECT 1 FROM vectores v WHERE v.chunk_id = f.chunk_id AND v.firma = f.firma AND v.modelo = %s)
               ORDER BY f.doc_id, f.orden""", (signature, model)).fetchall()
        return [(cid, f"{head}\n\n{text}" if head else text) for cid, head, text in rows]

    def record_run(self, signature: str, model: str, config: dict, documents: int, chunks: int, seconds: float) -> None:
        self.conn.execute("INSERT INTO indexaciones (firma, modelo, config, documentos, fragmentos, segundos) "
                          "VALUES (%s,%s,%s,%s,%s,%s)", (signature, model, json.dumps(config), documents, chunks, seconds))

    # counter ------------------------------------------------------------------------------------------------------
    def status(self) -> dict:
        by = self.conn.execute("SELECT fuente, nivel, estado, count(*) FROM documentos GROUP BY 1,2,3 ORDER BY 1,3").fetchall()
        chunks = self.conn.execute("SELECT firma, count(*), count(DISTINCT doc_id) FROM fragmentos GROUP BY 1").fetchall()
        vectors = self.conn.execute("SELECT firma, modelo, count(*) FROM vectores GROUP BY 1,2").fetchall()
        pages = self.conn.execute(
            """SELECT fuente, sum(paginas), sum(paginas_con_texto), sum(paginas_sin_texto),
                      count(*) FILTER (WHERE paginas_sin_texto > 0 AND paginas_con_texto > 0),
                      count(*) FILTER (WHERE paginas > 0 AND paginas_con_texto = 0)
               FROM documentos WHERE paginas IS NOT NULL GROUP BY 1 ORDER BY 1""").fetchall()
        return {"documentos": [{"fuente": f, "nivel": n, "estado": e, "n": c} for f, n, e, c in by],
                "paginas_ocr_apagado": [{"fuente": f, "paginas": p, "con_texto": t, "omitidas_sin_ocr": s,
                                         "documentos_con_paginas_omitidas": parcial, "documentos_escaneados": escaneados}
                                        for f, p, t, s, parcial, escaneados in pages],
                "fragmentos": [{"firma": f, "n": n, "documentos": d} for f, n, d in chunks],
                "vectores": [{"firma": f, "modelo": m, "n": n} for f, m, n in vectors]}
