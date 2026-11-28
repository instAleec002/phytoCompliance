"""Sign-in, sign-out, the current user, and the one-time links (activation and password reset)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from accounts import privacy

from ..schemas.accounts import LinkIn, LinkInfoOut, LoginIn, LoginOut, NoticeOut, RedeemIn, UserOut
from ..security import AccountsDep, UserDep

public = APIRouter(prefix="/auth", tags=["sesión"])
private = APIRouter(prefix="/auth", tags=["sesión"])


@public.post("/iniciar-sesion", response_model=LoginOut, summary="Inicia sesión con nombre de usuario o correo")
def login(body: LoginIn, request: Request, acc: AccountsDep):
    user, token = acc.login(body.identificador, body.contrasena, request.headers.get("user-agent"))
    return LoginOut(token=token, usuario=UserOut.of(user))


@public.post("/enlace", response_model=LinkInfoOut, summary="Datos de un enlace de activación o restablecimiento")
def link_info(body: LinkIn, acc: AccountsDep):
    return LinkInfoOut(**acc.invitation_info(body.token))


@public.post("/activar", response_model=UserOut,
             summary="Fija la contraseña con un enlace de un solo uso; al activar, acepta el aviso de privacidad")
def redeem(body: RedeemIn, acc: AccountsDep):
    return UserOut.of(acc.redeem(body.token, body.contrasena, body.aviso_version))


@public.get("/aviso-privacidad", response_model=NoticeOut, summary="Aviso de privacidad vigente (Ley N.° 29733)")
def privacy_notice():
    return NoticeOut(**privacy.notice())


@private.get("/yo", response_model=UserOut, summary="La cuenta de la sesión actual")
def me(principal: UserDep):
    return UserOut.of(principal.user)


@private.post("/cerrar-sesion", status_code=204, summary="Cierra la sesión actual")
def logout(principal: UserDep, acc: AccountsDep):
    acc.logout(principal.session)
