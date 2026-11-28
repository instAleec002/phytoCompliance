-- Document corpus and its index (schema «corpus»). Rebuildable from the snapshots: nothing here is the only copy.

CREATE TABLE documentos (
    doc_id      text PRIMARY KEY,
    fuente      text NOT NULL,
    nivel       text NOT NULL CHECK (nivel IN ('A', 'B', 'C', 'interno')),
    titulo      text NOT NULL,
    anio        text,
    tipo        text,
    licencia    text NOT NULL,
    url         text NOT NULL,
    archivo     text,
    sha256      text,
    instantanea text NOT NULL,                  -- snapshot folder (date) the file comes from
    estado      text NOT NULL CHECK (estado IN ('descargado', 'excluido', 'indexado', 'fallido')),
    motivo      text NOT NULL DEFAULT '',
    paginas     int,
    formato     text,
    actualizado timestamptz NOT NULL DEFAULT now()
);

-- one row per chunk and per pipeline configuration (signature), so two configurations can live side by side
CREATE TABLE fragmentos (
    chunk_id   text NOT NULL,
    firma      text NOT NULL,
    doc_id     text NOT NULL REFERENCES documentos (doc_id) ON DELETE CASCADE,
    orden      int NOT NULL,
    texto      text NOT NULL,
    encabezado text NOT NULL DEFAULT '',
    paginas    int[] NOT NULL DEFAULT '{}',
    seccion    text[] NOT NULL DEFAULT '{}',
    tipos      text[] NOT NULL DEFAULT '{}',
    tokens     int NOT NULL,
    rol        text NOT NULL DEFAULT 'atomic',  -- atomic | parent | child (parent_child chunker)
    padre      text,
    -- lexical index: header and text, Spanish stemming
    lexico     tsvector GENERATED ALWAYS AS (to_tsvector('spanish', encabezado || ' ' || texto)) STORED,
    PRIMARY KEY (chunk_id, firma)
);
CREATE INDEX fragmentos_lexico ON fragmentos USING gin (lexico);
CREATE INDEX fragmentos_doc ON fragmentos (doc_id, firma);

-- dense vectors, per embedding model (the model and its dimension are part of the key)
CREATE TABLE vectores (
    chunk_id text NOT NULL,
    firma    text NOT NULL,
    modelo   text NOT NULL,
    vector   vector(1024) NOT NULL,
    PRIMARY KEY (chunk_id, firma, modelo),
    FOREIGN KEY (chunk_id, firma) REFERENCES fragmentos (chunk_id, firma) ON DELETE CASCADE
);
CREATE INDEX vectores_hnsw ON vectores USING hnsw (vector vector_cosine_ops);

-- each indexing run: what configuration, which model, how many chunks
CREATE TABLE indexaciones (
    id         bigserial PRIMARY KEY,
    firma      text NOT NULL,
    modelo     text NOT NULL,
    config     jsonb NOT NULL,
    documentos int NOT NULL,
    fragmentos int NOT NULL,
    segundos   numeric NOT NULL,
    creada     timestamptz NOT NULL DEFAULT now()
);
