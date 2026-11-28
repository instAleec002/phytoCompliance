-- Conversations with the assistant (several questions with their history), owned by a user like programs and lots.
-- Each assistant message keeps its citations and its trace (standalone query, passages, model, times) for audit and
-- for the evaluation.

CREATE TABLE conversaciones (
    id          bigserial PRIMARY KEY,
    usuario_id  bigint NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    titulo      text NOT NULL,
    creado      timestamptz NOT NULL,
    actualizado timestamptz NOT NULL
);
CREATE INDEX conversaciones_usuario ON conversaciones (usuario_id, actualizado DESC);

CREATE TABLE mensajes (
    id              bigserial PRIMARY KEY,
    conversacion_id bigint NOT NULL REFERENCES conversaciones (id) ON DELETE CASCADE,
    rol             text NOT NULL CHECK (rol IN ('usuario', 'asistente')),
    texto           text NOT NULL,
    evidencia       boolean,
    citas           jsonb NOT NULL DEFAULT '[]',
    traza           jsonb NOT NULL DEFAULT '{}',
    creado          timestamptz NOT NULL
);
CREATE INDEX mensajes_conversacion ON mensajes (conversacion_id, id);
