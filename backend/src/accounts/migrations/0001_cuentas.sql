-- Cuentas de usuario, sesiones, invitaciones, trabajo guardado y auditoría. Esquema propio, separado del grafo.
-- Las contraseñas se guardan como hash argon2id y los tokens (sesión, invitación) solo como hash SHA-256.

CREATE TABLE usuarios (
    id                bigserial PRIMARY KEY,
    email             text NOT NULL,
    usuario           text NOT NULL CHECK (usuario ~ '^[a-z0-9._-]{3,32}$'),
    nombre            text NOT NULL,
    rol               text NOT NULL CHECK (rol IN ('admin', 'usuario')),
    estado            text NOT NULL CHECK (estado IN ('invitado', 'activo', 'desactivado')),
    password_hash     text,
    intentos_fallidos integer NOT NULL DEFAULT 0,
    bloqueado_hasta   timestamptz,
    ultimo_ingreso    timestamptz,
    creado            timestamptz NOT NULL,
    actualizado       timestamptz NOT NULL
);
CREATE UNIQUE INDEX usuarios_email ON usuarios (lower(email));
CREATE UNIQUE INDEX usuarios_usuario ON usuarios (usuario);

CREATE TABLE sesiones (
    id                bigserial PRIMARY KEY,
    usuario_id        bigint NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    token_hash        bytea NOT NULL UNIQUE,
    agente            text,
    creada            timestamptz NOT NULL,
    ultima_actividad  timestamptz NOT NULL,
    expira            timestamptz NOT NULL,          -- límite absoluto
    revocada          timestamptz
);
CREATE INDEX sesiones_usuario ON sesiones (usuario_id);

CREATE TABLE invitaciones (
    id          bigserial PRIMARY KEY,
    usuario_id  bigint NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    tipo        text NOT NULL CHECK (tipo IN ('activacion', 'restablecimiento')),
    token_hash  bytea NOT NULL UNIQUE,
    creada_por  bigint REFERENCES usuarios (id),
    creada      timestamptz NOT NULL,
    expira      timestamptz NOT NULL,
    usada       timestamptz
);

CREATE TABLE programas (
    id          bigserial PRIMARY KEY,
    usuario_id  bigint NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    nombre      text NOT NULL,
    cultivo     text NOT NULL,
    contenido   jsonb NOT NULL,
    creado      timestamptz NOT NULL,
    actualizado timestamptz NOT NULL
);
CREATE INDEX programas_usuario ON programas (usuario_id, actualizado DESC);

CREATE TABLE lotes (
    id          bigserial PRIMARY KEY,
    usuario_id  bigint NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    codigo      text NOT NULL,
    cultivo     text NOT NULL,
    mercado     text NOT NULL,
    muestreo    date NOT NULL,
    perfil      text,
    veredicto   text,
    entrada     jsonb NOT NULL,
    resultado   jsonb NOT NULL,
    creado      timestamptz NOT NULL
);
CREATE INDEX lotes_usuario ON lotes (usuario_id, creado DESC);

CREATE TABLE auditoria (
    id          bigserial PRIMARY KEY,
    usuario_id  bigint REFERENCES usuarios (id) ON DELETE SET NULL,
    accion      text NOT NULL,
    detalle     jsonb NOT NULL DEFAULT '{}'::jsonb,
    creado      timestamptz NOT NULL
);
CREATE INDEX auditoria_creado ON auditoria (creado DESC);
CREATE INDEX auditoria_usuario ON auditoria (usuario_id, creado DESC);
