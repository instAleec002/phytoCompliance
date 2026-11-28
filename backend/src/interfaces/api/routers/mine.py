"""The user's own account and work: password, sessions, activity, saved programs and evaluated lots."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..schemas.accounts import (
    ActivityOut,
    LotOut,
    LotSummaryOut,
    NoticeAcceptIn,
    PasswordChangeIn,
    ProgramOut,
    ProgramSummaryOut,
    RightRequestIn,
    RightRequestOut,
    SavedProgramIn,
    SessionOut,
    UserOut,
)
from ..security import AccountsDep, UserDep

router = APIRouter(prefix="/mis", tags=["mi cuenta"])


@router.post("/contrasena", status_code=204, summary="Cambia la contraseña; las demás sesiones se cierran")
def change_password(body: PasswordChangeIn, principal: UserDep, acc: AccountsDep):
    acc.change_password(principal.user, principal.session, body.actual, body.nueva)


@router.get("/sesiones", response_model=list[SessionOut], summary="Sesiones abiertas de la cuenta")
def sessions(principal: UserDep, acc: AccountsDep):
    return [SessionOut(**s, actual=s["id"] == principal.session.id) for s in acc.sessions(principal.user.id)]


@router.delete("/sesiones/{session_id}", status_code=204, summary="Cierra una sesión (p. ej. un equipo olvidado)")
def revoke(session_id: int, principal: UserDep, acc: AccountsDep):
    acc.revoke_session(principal.user.id, session_id)


@router.get("/actividad", response_model=list[ActivityOut], summary="Registro de actividad propio")
def activity(principal: UserDep, acc: AccountsDep):
    return [ActivityOut(**a) for a in acc.activity(principal.user.id, 100)]


@router.post("/aviso", response_model=UserOut, summary="Acepta la versión vigente del aviso de privacidad")
def accept_notice(body: NoticeAcceptIn, principal: UserDep, acc: AccountsDep):
    return UserOut.of(acc.accept_notice(principal.user, body.version))


@router.get("/datos", summary="Descarga todos los datos personales de la cuenta (derecho de acceso)")
def personal_data(principal: UserDep, acc: AccountsDep):
    data = jsonable_encoder(acc.personal_data(principal.user))
    name = f"mis-datos-{principal.user.usuario}.json"
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/derechos", response_model=list[RightRequestOut], summary="Solicitudes de derechos propias")
def my_rights(principal: UserDep, acc: AccountsDep):
    return [RightRequestOut(**r) for r in acc.rights_requests(principal.user.id)]


@router.post("/derechos", response_model=RightRequestOut, status_code=201,
             summary="Solicita la rectificación, la cancelación o la oposición (Ley N.° 29733)")
def request_right(body: RightRequestIn, principal: UserDep, acc: AccountsDep):
    row = acc.request_right(principal.user, body.tipo, body.detalle)
    return RightRequestOut(**row, usuario=principal.user.usuario, nombre=principal.user.nombre,
                           email=principal.user.email)


@router.get("/programas", response_model=list[ProgramSummaryOut], summary="Programas guardados")
def programs(principal: UserDep, acc: AccountsDep):
    return [ProgramSummaryOut(**p) for p in acc.programs(principal.user.id)]


@router.post("/programas", response_model=ProgramOut, status_code=201, summary="Guarda un programa nuevo")
def create_program(body: SavedProgramIn, principal: UserDep, acc: AccountsDep):
    row = acc.save_program(principal.user.id, body.nombre, body.cultivo, body.contenido)
    return _program(row)


@router.get("/programas/{program_id}", response_model=ProgramOut, summary="Un programa guardado")
def get_program(program_id: int, principal: UserDep, acc: AccountsDep):
    return _program(acc.program(principal.user.id, program_id))


@router.put("/programas/{program_id}", response_model=ProgramOut, summary="Actualiza un programa guardado")
def update_program(program_id: int, body: SavedProgramIn, principal: UserDep, acc: AccountsDep):
    return _program(acc.save_program(principal.user.id, body.nombre, body.cultivo, body.contenido, program_id))


@router.delete("/programas/{program_id}", status_code=204, summary="Elimina un programa guardado")
def delete_program(program_id: int, principal: UserDep, acc: AccountsDep):
    acc.delete_program(principal.user.id, program_id)


@router.get("/lotes", response_model=list[LotSummaryOut], summary="Lotes evaluados")
def lots(principal: UserDep, acc: AccountsDep):
    return [LotSummaryOut(**lot) for lot in acc.lots(principal.user.id)]


@router.get("/lotes/{lot_id}", response_model=LotOut, summary="Un lote evaluado, con su entrada y su resultado")
def get_lot(lot_id: int, principal: UserDep, acc: AccountsDep):
    return _lot(acc.lot(principal.user.id, lot_id))


def _program(row: dict) -> ProgramOut:
    content = row["contenido"]
    return ProgramOut(id=row["id"], nombre=row["nombre"], cultivo=row["cultivo"], contenido=content,
                      bloques=len(content.get("blocks", [])), aplicaciones=len(content.get("applications", [])),
                      creado=row["creado"], actualizado=row["actualizado"])


def _lot(row: dict) -> LotOut:
    return LotOut(id=row["id"], codigo=row["codigo"], cultivo=row["cultivo"], mercado=row["mercado"],
                  muestreo=row["muestreo"], perfil=row["perfil"], veredicto=row["veredicto"],
                  residuos=len(row["entrada"].get("measurements", [])), creado=row["creado"], entrada=row["entrada"],
                  resultado=row["resultado"])
