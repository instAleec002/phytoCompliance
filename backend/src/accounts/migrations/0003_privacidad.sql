-- Privacy notice acceptance and requests for the rights of rectification, cancellation and opposition (Ley N.° 29733).
-- Access is served directly (the person downloads their data); the other rights are requests an admin answers.

ALTER TABLE usuarios ADD COLUMN aviso_version text;
ALTER TABLE usuarios ADD COLUMN aviso_aceptado timestamptz;

CREATE TABLE solicitudes_derechos (
    id           bigserial PRIMARY KEY,
    usuario_id   bigint NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    tipo         text NOT NULL CHECK (tipo IN ('acceso', 'rectificacion', 'cancelacion', 'oposicion')),
    detalle      text NOT NULL,
    estado       text NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'atendida', 'rechazada')),
    respuesta    text,
    creada       timestamptz NOT NULL,
    atendida     timestamptz,
    atendida_por bigint REFERENCES usuarios (id) ON DELETE SET NULL
);
CREATE INDEX solicitudes_derechos_estado ON solicitudes_derechos (estado, creada DESC);
CREATE INDEX solicitudes_derechos_usuario ON solicitudes_derechos (usuario_id, creada DESC);
