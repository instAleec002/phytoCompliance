"""Accounts, sessions, links, saved programs and lots."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from accounts.service import User


class UserOut(BaseModel):
    id: int
    usuario: str
    email: str
    nombre: str
    rol: str = Field(description="admin o usuario")
    estado: str = Field(description="invitado, activo o desactivado")
    ultimo_ingreso: datetime | None
    creado: datetime
    aviso_version: str | None = Field(default=None, description="Versión del aviso de privacidad aceptada")
    aviso_pendiente: bool = Field(default=False, description="True si debe aceptar la versión vigente del aviso")

    @classmethod
    def of(cls, u: User) -> UserOut:
        return cls(id=u.id, usuario=u.usuario, email=u.email, nombre=u.nombre, rol=u.rol, estado=u.estado,
                   ultimo_ingreso=u.ultimo_ingreso, creado=u.creado, aviso_version=u.aviso_version,
                   aviso_pendiente=u.notice_pending)


class LoginIn(BaseModel):
    identificador: str = Field(description="Nombre de usuario o correo", min_length=1, max_length=254)
    contrasena: str = Field(min_length=1, max_length=256)


class LoginOut(BaseModel):
    token: str = Field(description="Va en la cabecera Authorization: Bearer <token>")
    usuario: UserOut


class LinkIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class LinkInfoOut(BaseModel):
    usuario: str
    email: str
    nombre: str
    tipo: str = Field(description="activacion o restablecimiento")
    expira: datetime


class RedeemIn(LinkIn):
    contrasena: str = Field(min_length=1, max_length=256)
    aviso_version: str | None = Field(default=None, max_length=20,
                                      description="Versión del aviso de privacidad aceptada; obligatoria al activar")


class NoticeSectionOut(BaseModel):
    titulo: str
    texto: str


class NoticeOut(BaseModel):
    version: str
    secciones: list[NoticeSectionOut]


class NoticeAcceptIn(BaseModel):
    version: str = Field(max_length=20)


class RightRequestIn(BaseModel):
    tipo: str = Field(pattern="^(rectificacion|cancelacion|oposicion)$")
    detalle: str = Field(min_length=1, max_length=2000)


class RightRequestOut(BaseModel):
    id: int
    usuario_id: int
    usuario: str
    nombre: str
    email: str
    tipo: str = Field(description="rectificacion, cancelacion u oposicion")
    detalle: str
    estado: str = Field(description="pendiente, atendida o rechazada")
    respuesta: str | None
    creada: datetime
    atendida: datetime | None


class RightResolveIn(BaseModel):
    estado: str = Field(pattern="^(atendida|rechazada)$")
    respuesta: str = Field(min_length=1, max_length=2000)


class PasswordChangeIn(BaseModel):
    actual: str = Field(min_length=1, max_length=256)
    nueva: str = Field(min_length=1, max_length=256)


class SessionOut(BaseModel):
    id: int
    agente: str | None
    creada: datetime
    ultima_actividad: datetime
    expira: datetime
    actual: bool = False


class ActivityOut(BaseModel):
    id: int
    accion: str
    detalle: dict
    creado: datetime
    email: str | None = None
    nombre: str | None = None


class InviteIn(BaseModel):
    email: str = Field(max_length=254)
    usuario: str = Field(max_length=32)
    nombre: str = Field(min_length=1, max_length=120)
    rol: str = Field(default="usuario", pattern="^(admin|usuario)$")


class LinkOut(BaseModel):
    usuario: UserOut
    enlace: str = Field(description="Enlace de un solo uso para entregar al usuario; vence en 72 h")
    expira_en_horas: int = 72


class UserUpdateIn(BaseModel):
    rol: str | None = Field(default=None, pattern="^(admin|usuario)$")
    estado: str | None = Field(default=None, pattern="^(activo|desactivado)$")


class ProgramSummaryOut(BaseModel):
    id: int
    nombre: str
    cultivo: str
    bloques: int | None
    aplicaciones: int | None
    creado: datetime
    actualizado: datetime


class SavedProgramIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    cultivo: str = Field(min_length=1, max_length=40)
    contenido: dict = Field(description="El programa tal como lo edita la interfaz (bloques y aplicaciones)")


class ProgramOut(ProgramSummaryOut):
    contenido: dict


class LotSummaryOut(BaseModel):
    id: int
    codigo: str
    cultivo: str
    mercado: str
    muestreo: date
    perfil: str | None
    veredicto: str | None
    residuos: int | None
    creado: datetime


class LotOut(LotSummaryOut):
    entrada: dict
    resultado: dict
