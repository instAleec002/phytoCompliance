"""Accounts: invitations, sign-in, sessions, roles, saved work and the activity log.

Rules
- No public registration: an admin invites (email, name, role) and gets a one-time activation link valid 72 h, which
  they hand over themselves. A forgotten password is a reset link, issued the same way.
- Sign-in takes the username or the email (a username never contains "@", so the two cannot be confused).
- Sign-in fails with one message whatever the cause (unknown email, wrong password, inactive account, lockout), and
  five failures lock the account for 15 minutes.
- A session lasts 12 h without activity and 30 days at most; signing out, deactivating the user or resetting the
  password revokes it at once.
- There is always at least one active admin: the last one cannot be demoted or deactivated.
The clock is injected so expiry and lockout are tested without waiting.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import credentials as cred
from . import privacy

IDLE = timedelta(hours=12)
ABSOLUTE = timedelta(days=30)
INVITATION = timedelta(hours=72)
MAX_ATTEMPTS = 5
LOCK = timedelta(minutes=15)
ROLES = ("admin", "usuario")
USERNAME = re.compile(r"^[a-z0-9._-]{3,32}$")


class AccountError(Exception):
    """A request that the rules refuse; the message is meant for the user."""


class AuthFailed(AccountError):
    def __init__(self):
        super().__init__("Correo o contraseña incorrectos, o la cuenta no está disponible")


class InvalidToken(AccountError):
    def __init__(self):
        super().__init__("El enlace no es válido, ya se usó o venció. Pida uno nuevo al administrador.")


class NotFound(AccountError):
    pass


@dataclass(frozen=True)
class User:
    id: int
    email: str
    usuario: str
    nombre: str
    rol: str
    estado: str
    ultimo_ingreso: datetime | None
    creado: datetime
    aviso_version: str | None = None      # privacy notice version the person accepted

    @property
    def is_admin(self) -> bool:
        return self.rol == "admin"

    @property
    def notice_pending(self) -> bool:
        return self.aviso_version != privacy.VERSION


@dataclass(frozen=True)
class Session:
    id: int
    usuario_id: int
    creada: datetime
    ultima_actividad: datetime
    expira: datetime
    agente: str | None


def clean_username(usuario: str) -> str:
    name = usuario.strip().lower()
    if not USERNAME.match(name):
        raise AccountError("Usuario no válido: de 3 a 32 caracteres entre a-z, 0-9, punto, guion y guion bajo")
    return name


def clean_email(email: str) -> str:
    email = email.strip()
    if email.count("@") != 1 or len(email) > 254 or " " in email:
        raise AccountError("Correo no válido")
    return email


def _duplicate(e: psycopg.errors.UniqueViolation) -> AccountError:
    which = "usuario" if "usuarios_usuario" in str(e) else "correo"
    return AccountError(f"Ya existe una cuenta con ese {which}")


def utcnow() -> datetime:
    return datetime.now(UTC)


def _user(row: dict) -> User:
    return User(row["id"], row["email"], row["usuario"], row["nombre"], row["rol"], row["estado"], row["ultimo_ingreso"],
                row["creado"], row.get("aviso_version"))


class Accounts:
    def __init__(self, conn: psycopg.Connection, clock: Callable[[], datetime] = utcnow):
        self.conn = conn
        self.now = clock

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        with self.conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(sql, params).fetchone()

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(sql, params).fetchall()

    # activity log ------------------------------------------------------------------------------------------------

    def audit(self, user_id: int | None, action: str, detail: dict | None = None) -> None:
        self.conn.execute("INSERT INTO auditoria (usuario_id, accion, detalle, creado) VALUES (%s, %s, %s, %s)",
                          (user_id, action, Jsonb(detail or {}), self.now()))

    def activity(self, user_id: int | None = None, limit: int = 200) -> list[dict]:
        where, params = ("WHERE a.usuario_id = %s", (user_id, limit)) if user_id else ("", (limit,))
        return self._all(f"SELECT a.id, a.accion, a.detalle, a.creado, u.email, u.nombre FROM auditoria a "
                         f"LEFT JOIN usuarios u ON u.id = a.usuario_id {where} ORDER BY a.creado DESC, a.id DESC LIMIT %s",
                         params)

    # users -------------------------------------------------------------------------------------------------------

    def user(self, user_id: int) -> User:
        row = self._one("SELECT * FROM usuarios WHERE id = %s", (user_id,))
        if not row:
            raise NotFound("Usuario inexistente")
        return _user(row)

    def users(self) -> list[User]:
        return [_user(r) for r in self._all("SELECT * FROM usuarios ORDER BY rol, usuario")]

    def create_admin(self, email: str, usuario: str, nombre: str, password: str) -> User:
        """The first account, from the command line (make crear-admin)."""
        email, usuario = clean_email(email), clean_username(usuario)
        cred.check_policy(password, email, usuario)
        now = self.now()
        try:
            row = self._one("INSERT INTO usuarios (email, usuario, nombre, rol, estado, password_hash, creado, actualizado) "
                            "VALUES (%s, %s, %s, 'admin', 'activo', %s, %s, %s) RETURNING *",
                            (email, usuario, nombre.strip(), cred.hash_password(password), now, now))
        except psycopg.errors.UniqueViolation as e:
            raise _duplicate(e) from e
        self.audit(row["id"], "admin_creado", {"email": email, "usuario": usuario})
        return _user(row)

    def invite(self, admin: User, email: str, usuario: str, nombre: str, rol: str) -> tuple[User, str]:
        if rol not in ROLES:
            raise AccountError(f"Rol desconocido: {rol}")
        email, usuario = clean_email(email), clean_username(usuario)
        now = self.now()
        try:
            row = self._one("INSERT INTO usuarios (email, usuario, nombre, rol, estado, creado, actualizado) "
                            "VALUES (%s, %s, %s, %s, 'invitado', %s, %s) RETURNING *",
                            (email, usuario, nombre.strip(), rol, now, now))
        except psycopg.errors.UniqueViolation as e:
            raise _duplicate(e) from e
        token = self._new_invitation(row["id"], "activacion", admin.id)
        self.audit(admin.id, "usuario_invitado", {"usuario_id": row["id"], "email": email, "usuario": usuario, "rol": rol})
        return _user(row), token

    def reset_link(self, admin: User, user_id: int) -> str:
        target = self.user(user_id)
        if target.estado == "desactivado":
            raise AccountError("Reactive la cuenta antes de enviar un enlace")
        kind = "activacion" if target.estado == "invitado" else "restablecimiento"
        token = self._new_invitation(user_id, kind, admin.id)
        self.audit(admin.id, "enlace_emitido", {"usuario_id": user_id, "tipo": kind})
        return token

    def _new_invitation(self, user_id: int, kind: str, by: int | None) -> str:
        now = self.now()
        # a new link replaces the earlier unused ones
        self.conn.execute("UPDATE invitaciones SET usada = %s WHERE usuario_id = %s AND usada IS NULL", (now, user_id))
        token = cred.new_token()
        self.conn.execute("INSERT INTO invitaciones (usuario_id, tipo, token_hash, creada_por, creada, expira) "
                          "VALUES (%s, %s, %s, %s, %s, %s)", (user_id, kind, cred.token_hash(token), by, now, now + INVITATION))
        return token

    def update_user(self, admin: User, user_id: int, rol: str | None = None, estado: str | None = None) -> User:
        target = self.user(user_id)
        if rol is not None and rol not in ROLES:
            raise AccountError(f"Rol desconocido: {rol}")
        if estado is not None and estado not in ("activo", "desactivado"):
            raise AccountError("Estado no válido")
        if estado == "activo" and target.estado == "invitado":
            raise AccountError("La cuenta se activa con su enlace de activación")
        losing_admin = target.is_admin and target.estado == "activo" and (rol == "usuario" or estado == "desactivado")
        if losing_admin:
            admins = self._one("SELECT count(*) AS n FROM usuarios WHERE rol = 'admin' AND estado = 'activo'")["n"]
            if admins <= 1:
                raise AccountError("Debe quedar al menos un administrador activo")
        row = self._one("UPDATE usuarios SET rol = coalesce(%s, rol), estado = coalesce(%s, estado), actualizado = %s "
                        "WHERE id = %s RETURNING *", (rol, estado, self.now(), user_id))
        if estado == "desactivado":
            self._revoke_all(user_id)
        self.audit(admin.id, "usuario_actualizado", {"usuario_id": user_id, "rol": rol, "estado": estado})
        return _user(row)

    # links -------------------------------------------------------------------------------------------------------

    def _invitation(self, token: str) -> dict:
        row = self._one("SELECT i.*, u.email, u.usuario, u.nombre, u.estado FROM invitaciones i "
                        "JOIN usuarios u ON u.id = i.usuario_id "
                        "WHERE i.token_hash = %s", (cred.token_hash(token),))
        if not row or row["usada"] is not None or row["expira"] <= self.now() or row["estado"] == "desactivado":
            raise InvalidToken()
        return row

    def invitation_info(self, token: str) -> dict:
        row = self._invitation(token)
        return {"email": row["email"], "usuario": row["usuario"], "nombre": row["nombre"], "tipo": row["tipo"],
                "expira": row["expira"]}

    def redeem(self, token: str, password: str, notice_version: str | None = None) -> User:
        """Sets the password of an activation or reset link; a reset also ends every open session. Activating requires
        accepting the current privacy notice (``notice_version``); a reset does not ask again."""
        row = self._invitation(token)
        activation = row["tipo"] == "activacion"
        if activation and notice_version != privacy.VERSION:
            raise AccountError("Para activar la cuenta debe aceptar el aviso de privacidad vigente")
        cred.check_policy(password, row["email"], row["usuario"])
        now = self.now()
        with self.conn.transaction():
            self.conn.execute("UPDATE invitaciones SET usada = %s WHERE id = %s", (now, row["id"]))
            user = self._one("UPDATE usuarios SET password_hash = %s, estado = 'activo', intentos_fallidos = 0, "
                             "bloqueado_hasta = NULL, actualizado = %s WHERE id = %s RETURNING *",
                             (cred.hash_password(password), now, row["usuario_id"]))
            self._revoke_all(row["usuario_id"])
            if activation:
                user = self._accept(row["usuario_id"], now)
        self.audit(row["usuario_id"], "cuenta_activada" if activation else "contrasena_restablecida")
        if activation:
            self.audit(row["usuario_id"], "aviso_aceptado", {"version": privacy.VERSION})
        return _user(user)

    # privacy and ARCO rights -------------------------------------------------------------------------------------

    def _accept(self, user_id: int, now: datetime) -> dict:
        return self._one("UPDATE usuarios SET aviso_version = %s, aviso_aceptado = %s WHERE id = %s RETURNING *",
                         (privacy.VERSION, now, user_id))

    def accept_notice(self, user: User, version: str) -> User:
        """An account created before the notice, or before its last change, accepts the current version."""
        if version != privacy.VERSION:
            raise AccountError("El aviso cambió; vuelva a leer la versión vigente")
        row = self._accept(user.id, self.now())
        self.audit(user.id, "aviso_aceptado", {"version": version})
        return _user(row)

    def request_right(self, user: User, tipo: str, detalle: str) -> dict:
        if tipo not in privacy.RIGHTS or tipo == "acceso":
            raise AccountError("El acceso se ejerce descargando sus datos; las solicitudes son de rectificación, "
                               "cancelación u oposición")
        detalle = detalle.strip()
        if len(detalle) < 10:
            raise AccountError("Describa en al menos 10 caracteres qué dato o qué tratamiento se trata")
        row = self._one("INSERT INTO solicitudes_derechos (usuario_id, tipo, detalle, creada) VALUES (%s, %s, %s, %s) "
                        "RETURNING *", (user.id, tipo, detalle, self.now()))
        self.audit(user.id, "derecho_solicitado", {"solicitud": row["id"], "tipo": tipo})
        return row

    def rights_requests(self, user_id: int | None = None, pending_only: bool = False) -> list[dict]:
        conds, params = [], []
        if user_id is not None:
            conds.append("s.usuario_id = %s")
            params.append(user_id)
        if pending_only:
            conds.append("s.estado = 'pendiente'")
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        return self._all(f"SELECT s.*, u.usuario, u.nombre, u.email FROM solicitudes_derechos s "
                         f"JOIN usuarios u ON u.id = s.usuario_id {where} ORDER BY s.creada DESC, s.id DESC",
                         tuple(params))

    def resolve_right(self, admin: User, request_id: int, estado: str, respuesta: str) -> dict:
        if estado not in ("atendida", "rechazada"):
            raise AccountError("El estado debe ser atendida o rechazada")
        respuesta = respuesta.strip()
        if len(respuesta) < 10:
            raise AccountError("La respuesta al titular debe explicar lo que se hizo o el motivo del rechazo")
        row = self._one("UPDATE solicitudes_derechos SET estado = %s, respuesta = %s, atendida = %s, atendida_por = %s "
                        "WHERE id = %s AND estado = 'pendiente' RETURNING *",
                        (estado, respuesta, self.now(), admin.id, request_id))
        if not row:
            raise NotFound("La solicitud no existe o ya fue respondida")
        self.audit(admin.id, "derecho_respondido", {"solicitud": request_id, "estado": estado,
                                                    "titular": row["usuario_id"]})
        return row

    def personal_data(self, user: User) -> dict:
        """Everything the system keeps about the person (right of access), without secrets: no password hash and no
        token hashes."""
        profile = self._one("SELECT id, email, usuario, nombre, rol, estado, ultimo_ingreso, creado, actualizado, "
                            "aviso_version, aviso_aceptado FROM usuarios WHERE id = %s", (user.id,))
        conversations = self.conversations(user.id)
        data = {
            "aviso_de_privacidad": privacy.VERSION,
            "cuenta": profile,
            "sesiones": self.sessions(user.id),
            "actividad": self.activity(user.id, 10_000),
            "programas": self._all("SELECT * FROM programas WHERE usuario_id = %s ORDER BY id", (user.id,)),
            "lotes": self._all("SELECT * FROM lotes WHERE usuario_id = %s ORDER BY id", (user.id,)),
            "conversaciones": [self.conversation(user.id, c["id"]) for c in conversations],
            "solicitudes_de_derechos": self.rights_requests(user.id),
        }
        self.audit(user.id, "datos_descargados")
        return data

    # sign-in and sessions ----------------------------------------------------------------------------------------

    def login(self, identifier: str, password: str, agent: str | None = None) -> tuple[User, str]:
        """``identifier``: the username or the email."""
        ident = identifier.strip()
        if "@" in ident:
            row = self._one("SELECT * FROM usuarios WHERE lower(email) = lower(%s)", (ident,))
        else:
            row = self._one("SELECT * FROM usuarios WHERE usuario = lower(%s)", (ident,))
        now = self.now()
        if row is None:
            cred.verify_password(cred.DUMMY_HASH, password)        # same work as for a real account
            raise AuthFailed()
        if row["bloqueado_hasta"] and row["bloqueado_hasta"] > now:
            raise AuthFailed()
        if row["estado"] != "activo" or not cred.verify_password(row["password_hash"], password):
            attempts = row["intentos_fallidos"] + 1
            locked = now + LOCK if attempts >= MAX_ATTEMPTS else None
            self.conn.execute("UPDATE usuarios SET intentos_fallidos = %s, bloqueado_hasta = %s WHERE id = %s",
                              (0 if locked else attempts, locked, row["id"]))
            self.audit(row["id"], "ingreso_fallido", {"bloqueada": bool(locked)})
            raise AuthFailed()
        if cred.needs_rehash(row["password_hash"]):
            self.conn.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s",
                              (cred.hash_password(password), row["id"]))
        token = cred.new_token()
        self.conn.execute("INSERT INTO sesiones (usuario_id, token_hash, agente, creada, ultima_actividad, expira) "
                          "VALUES (%s, %s, %s, %s, %s, %s)",
                          (row["id"], cred.token_hash(token), (agent or "")[:300], now, now, now + ABSOLUTE))
        user = self._one("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL, ultimo_ingreso = %s "
                         "WHERE id = %s RETURNING *", (now, row["id"]))
        self.audit(row["id"], "ingreso")
        return _user(user), token

    def authenticate(self, token: str) -> tuple[User, Session] | None:
        row = self._one("SELECT s.id AS sid, s.creada, s.ultima_actividad, s.expira, s.revocada, s.agente, u.* "
                        "FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id WHERE s.token_hash = %s",
                        (cred.token_hash(token),))
        now = self.now()
        if (row is None or row["revocada"] is not None or row["expira"] <= now
                or row["ultima_actividad"] + IDLE <= now or row["estado"] != "activo"):
            return None
        self.conn.execute("UPDATE sesiones SET ultima_actividad = %s WHERE id = %s", (now, row["sid"]))
        session = Session(row["sid"], row["id"], row["creada"], now, row["expira"], row["agente"])
        return _user(row), session

    def logout(self, session: Session) -> None:
        self.conn.execute("UPDATE sesiones SET revocada = %s WHERE id = %s AND revocada IS NULL", (self.now(), session.id))
        self.audit(session.usuario_id, "salida")

    def sessions(self, user_id: int) -> list[dict]:
        now = self.now()
        return self._all("SELECT id, agente, creada, ultima_actividad, expira FROM sesiones WHERE usuario_id = %s "
                         "AND revocada IS NULL AND expira > %s AND ultima_actividad > %s ORDER BY ultima_actividad DESC",
                         (user_id, now, now - IDLE))

    def revoke_session(self, user_id: int, session_id: int) -> None:
        cur = self.conn.execute("UPDATE sesiones SET revocada = %s WHERE id = %s AND usuario_id = %s AND revocada IS NULL",
                                (self.now(), session_id, user_id))
        if cur.rowcount == 0:
            raise NotFound("Sesión inexistente o ya cerrada")

    def _revoke_all(self, user_id: int, keep: int | None = None) -> None:
        self.conn.execute("UPDATE sesiones SET revocada = %s WHERE usuario_id = %s AND revocada IS NULL "
                          "AND id IS DISTINCT FROM %s", (self.now(), user_id, keep))

    def set_password(self, user_id: int, password: str) -> None:
        """From the command line only (make restablecer-admin): new password, every session ends."""
        user = self.user(user_id)
        cred.check_policy(password, user.email, user.usuario)
        self.conn.execute("UPDATE usuarios SET password_hash = %s, estado = 'activo', intentos_fallidos = 0, "
                          "bloqueado_hasta = NULL, actualizado = %s WHERE id = %s",
                          (cred.hash_password(password), self.now(), user_id))
        self._revoke_all(user_id)
        self.audit(user_id, "contrasena_restablecida_consola")

    def by_username(self, usuario: str) -> User:
        row = self._one("SELECT * FROM usuarios WHERE usuario = lower(%s)", (usuario.strip(),))
        if not row:
            raise NotFound(f"No existe el usuario {usuario}")
        return _user(row)

    def change_password(self, user: User, session: Session, current: str, new: str) -> None:
        row = self._one("SELECT password_hash FROM usuarios WHERE id = %s", (user.id,))
        if not cred.verify_password(row["password_hash"], current):
            raise AccountError("La contraseña actual no es correcta")
        cred.check_policy(new, user.email, user.usuario)
        self.conn.execute("UPDATE usuarios SET password_hash = %s, actualizado = %s WHERE id = %s",
                          (cred.hash_password(new), self.now(), user.id))
        self._revoke_all(user.id, keep=session.id)        # the other devices sign in again
        self.audit(user.id, "contrasena_cambiada")

    # saved work --------------------------------------------------------------------------------------------------

    def programs(self, user_id: int) -> list[dict]:
        return self._all("SELECT id, nombre, cultivo, creado, actualizado, "
                         "jsonb_array_length(contenido -> 'applications') AS aplicaciones, "
                         "jsonb_array_length(contenido -> 'blocks') AS bloques "
                         "FROM programas WHERE usuario_id = %s ORDER BY actualizado DESC", (user_id,))

    def program(self, user_id: int, program_id: int) -> dict:
        row = self._one("SELECT * FROM programas WHERE id = %s AND usuario_id = %s", (program_id, user_id))
        if not row:
            raise NotFound("Programa inexistente")
        return row

    def save_program(self, user_id: int, nombre: str, cultivo: str, contenido: dict, program_id: int | None = None) -> dict:
        now = self.now()
        if program_id is None:
            row = self._one("INSERT INTO programas (usuario_id, nombre, cultivo, contenido, creado, actualizado) "
                            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING *", (user_id, nombre, cultivo, Jsonb(contenido), now, now))
        else:
            row = self._one("UPDATE programas SET nombre = %s, cultivo = %s, contenido = %s, actualizado = %s "
                            "WHERE id = %s AND usuario_id = %s RETURNING *",
                            (nombre, cultivo, Jsonb(contenido), now, program_id, user_id))
            if not row:
                raise NotFound("Programa inexistente")
        self.audit(user_id, "programa_guardado", {"programa_id": row["id"], "nombre": nombre})
        return row

    def delete_program(self, user_id: int, program_id: int) -> None:
        cur = self.conn.execute("DELETE FROM programas WHERE id = %s AND usuario_id = %s", (program_id, user_id))
        if cur.rowcount == 0:
            raise NotFound("Programa inexistente")
        self.audit(user_id, "programa_eliminado", {"programa_id": program_id})

    # conversations with the assistant ---------------------------------------------------------------------------

    def conversations(self, user_id: int) -> list[dict]:
        return self._all("SELECT c.id, c.titulo, c.creado, c.actualizado, "
                         "(SELECT count(*) FROM mensajes m WHERE m.conversacion_id = c.id AND m.rol = 'usuario') AS preguntas "
                         "FROM conversaciones c WHERE c.usuario_id = %s ORDER BY c.actualizado DESC", (user_id,))

    def conversation(self, user_id: int, conversation_id: int) -> dict:
        row = self._one("SELECT * FROM conversaciones WHERE id = %s AND usuario_id = %s", (conversation_id, user_id))
        if not row:
            raise NotFound("Conversación inexistente")
        row["mensajes"] = self._all("SELECT id, rol, texto, evidencia, citas, traza, creado FROM mensajes "
                                    "WHERE conversacion_id = %s ORDER BY id", (conversation_id,))
        return row

    def create_conversation(self, user_id: int, titulo: str) -> dict:
        now = self.now()
        row = self._one("INSERT INTO conversaciones (usuario_id, titulo, creado, actualizado) VALUES (%s, %s, %s, %s) "
                        "RETURNING *", (user_id, titulo.strip()[:120] or "Conversación", now, now))
        self.audit(user_id, "conversacion_creada", {"conversacion_id": row["id"]})
        return row

    def rename_conversation(self, user_id: int, conversation_id: int, titulo: str) -> dict:
        row = self._one("UPDATE conversaciones SET titulo = %s, actualizado = %s WHERE id = %s AND usuario_id = %s "
                        "RETURNING *", (titulo.strip()[:120], self.now(), conversation_id, user_id))
        if not row:
            raise NotFound("Conversación inexistente")
        return row

    def delete_conversation(self, user_id: int, conversation_id: int) -> None:
        cur = self.conn.execute("DELETE FROM conversaciones WHERE id = %s AND usuario_id = %s", (conversation_id, user_id))
        if cur.rowcount == 0:
            raise NotFound("Conversación inexistente")
        self.audit(user_id, "conversacion_eliminada", {"conversacion_id": conversation_id})

    def add_message(self, user_id: int, conversation_id: int, rol: str, texto: str, evidencia: bool | None = None,
                    citas: list | None = None, traza: dict | None = None) -> dict:
        self.conversation(user_id, conversation_id)          # ownership check
        now = self.now()
        row = self._one("INSERT INTO mensajes (conversacion_id, rol, texto, evidencia, citas, traza, creado) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id, rol, texto, evidencia, citas, traza, creado",
                        (conversation_id, rol, texto, evidencia, Jsonb(citas or []), Jsonb(traza or {}), now))
        self.conn.execute("UPDATE conversaciones SET actualizado = %s WHERE id = %s", (now, conversation_id))
        return row

    def save_lot(self, user_id: int, codigo: str, cultivo: str, mercado: str, muestreo: date, perfil: str | None,
                 veredicto: str | None, entrada: dict, resultado: dict) -> dict:
        row = self._one("INSERT INTO lotes (usuario_id, codigo, cultivo, mercado, muestreo, perfil, veredicto, entrada, "
                        "resultado, creado) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, creado",
                        (user_id, codigo, cultivo, mercado, muestreo, perfil, veredicto, Jsonb(entrada), Jsonb(resultado),
                         self.now()))
        self.audit(user_id, "lote_evaluado", {"lote_id": row["id"], "codigo": codigo, "veredicto": veredicto})
        return row

    def lots(self, user_id: int) -> list[dict]:
        return self._all("SELECT id, codigo, cultivo, mercado, muestreo, perfil, veredicto, creado, "
                         "jsonb_array_length(entrada -> 'measurements') AS residuos "
                         "FROM lotes WHERE usuario_id = %s ORDER BY creado DESC", (user_id,))

    def lot(self, user_id: int, lot_id: int) -> dict:
        row = self._one("SELECT * FROM lotes WHERE id = %s AND usuario_id = %s", (lot_id, user_id))
        if not row:
            raise NotFound("Lote inexistente")
        return row
