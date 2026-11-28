"""Administration: invite users, change roles, deactivate and reactivate, issue reset links, and read (never edit)
the users' programs, lots and activity."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from shared.settings import Settings, get_settings

from ..schemas.accounts import (
    ActivityOut,
    InviteIn,
    LinkOut,
    LotOut,
    LotSummaryOut,
    ProgramOut,
    ProgramSummaryOut,
    RightRequestOut,
    RightResolveIn,
    UserOut,
    UserUpdateIn,
)
from ..schemas.assistant import ConversationOut, ConversationSummaryOut
from ..security import AccountsDep, AdminDep
from .mine import _lot, _program

router = APIRouter(prefix="/admin", tags=["administración"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _link(config: Settings, token: str) -> str:
    return f"{config.web_url.rstrip('/')}/activar/?t={token}"


@router.get("/derechos", response_model=list[RightRequestOut], summary="Solicitudes de derechos de los titulares")
def rights(principal: AdminDep, acc: AccountsDep, pendientes: bool = False):
    return [RightRequestOut(**r) for r in acc.rights_requests(pending_only=pendientes)]


@router.patch("/derechos/{request_id}", response_model=RightRequestOut,
              summary="Responde una solicitud de derechos (atendida o rechazada, con la respuesta al titular)")
def resolve_right(request_id: int, body: RightResolveIn, principal: AdminDep, acc: AccountsDep):
    acc.resolve_right(principal.user, request_id, body.estado, body.respuesta)
    return next(RightRequestOut(**r) for r in acc.rights_requests() if r["id"] == request_id)


@router.get("/usuarios", response_model=list[UserOut], summary="Todas las cuentas")
def users(principal: AdminDep, acc: AccountsDep):
    return [UserOut.of(u) for u in acc.users()]


@router.post("/usuarios", response_model=LinkOut, status_code=201,
             summary="Invita a un usuario; devuelve su enlace de activación de un solo uso")
def invite(body: InviteIn, principal: AdminDep, acc: AccountsDep, config: SettingsDep):
    user, token = acc.invite(principal.user, body.email, body.usuario, body.nombre, body.rol)
    return LinkOut(usuario=UserOut.of(user), enlace=_link(config, token))


@router.patch("/usuarios/{user_id}", response_model=UserOut, summary="Cambia el rol o desactiva/reactiva una cuenta")
def update(user_id: int, body: UserUpdateIn, principal: AdminDep, acc: AccountsDep):
    return UserOut.of(acc.update_user(principal.user, user_id, body.rol, body.estado))


@router.post("/usuarios/{user_id}/enlace", response_model=LinkOut,
             summary="Emite un enlace nuevo: de activación si la cuenta está invitada, de restablecimiento si no")
def new_link(user_id: int, principal: AdminDep, acc: AccountsDep, config: SettingsDep):
    token = acc.reset_link(principal.user, user_id)
    return LinkOut(usuario=UserOut.of(acc.user(user_id)), enlace=_link(config, token))


@router.get("/auditoria", response_model=list[ActivityOut], summary="Registro de actividad de todas las cuentas")
def activity(principal: AdminDep, acc: AccountsDep, usuario_id: int | None = None):
    return [ActivityOut(**a) for a in acc.activity(usuario_id, 300)]


@router.get("/usuarios/{user_id}/programas", response_model=list[ProgramSummaryOut], summary="Programas de un usuario")
def user_programs(user_id: int, principal: AdminDep, acc: AccountsDep):
    acc.user(user_id)
    return [ProgramSummaryOut(**p) for p in acc.programs(user_id)]


@router.get("/usuarios/{user_id}/programas/{program_id}", response_model=ProgramOut, summary="Un programa (solo lectura)")
def user_program(user_id: int, program_id: int, principal: AdminDep, acc: AccountsDep):
    return _program(acc.program(user_id, program_id))


@router.get("/usuarios/{user_id}/lotes", response_model=list[LotSummaryOut], summary="Lotes de un usuario")
def user_lots(user_id: int, principal: AdminDep, acc: AccountsDep):
    acc.user(user_id)
    return [LotSummaryOut(**lot) for lot in acc.lots(user_id)]


@router.get("/usuarios/{user_id}/lotes/{lot_id}", response_model=LotOut, summary="Un lote (solo lectura)")
def user_lot(user_id: int, lot_id: int, principal: AdminDep, acc: AccountsDep):
    return _lot(acc.lot(user_id, lot_id))

@router.get("/usuarios/{user_id}/conversaciones", response_model=list[ConversationSummaryOut],
            summary="Conversaciones de un usuario con el asistente")
def user_conversations(user_id: int, principal: AdminDep, acc: AccountsDep):
    acc.user(user_id)
    return acc.conversations(user_id)


@router.get("/usuarios/{user_id}/conversaciones/{conversation_id}", response_model=ConversationOut,
            summary="Una conversación (solo lectura)")
def user_conversation(user_id: int, conversation_id: int, principal: AdminDep, acc: AccountsDep):
    return acc.conversation(user_id, conversation_id)
