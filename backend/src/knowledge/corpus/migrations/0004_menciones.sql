-- Graph terms that each fragment names (stage D4, 27/11/2026), per index signature: built from the vocabulary index
-- (the same one that recognizes the terms of a question), over the fragment's text without its header.
CREATE TABLE IF NOT EXISTS menciones (
    firma    text NOT NULL,
    chunk_id text NOT NULL,
    doc_id   text NOT NULL,
    tipo     text NOT NULL,      -- pest | ingredient | crop
    clave    text NOT NULL,
    PRIMARY KEY (firma, chunk_id, tipo, clave)
);
CREATE INDEX IF NOT EXISTS menciones_termino ON menciones (firma, tipo, clave);
