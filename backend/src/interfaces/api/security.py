"""Who is calling: the session token in the ``Authorization: Bearer`` header (ADR 0001 of the frontend: the desktop app
loads the interface from its own origin, so no cookies). Sessions come from signing in with a username or email
(``/api/auth/iniciar-sesion``); every permission is checked here, on the server."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from accounts.service import Accounts, Session, User

bearer = HTTPBearer(auto_error=False, description="Token de sesión obtenido al iniciar sesión")


def accounts() -> Iterator[Accounts]:
    """One connection to the accounts schema per request; the tests replace it with a throwaway schema."""
    from accounts.db import connect

    conn = connect()
    try:
        yield Accounts(conn)
    finally:
        conn.close()


AccountsDep = Annotated[Accounts, Depends(accounts)]


@dataclass(frozen=True)
class Principal:
    user: User
    session: Session


def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                 acc: AccountsDep) -> Principal:
    found = acc.authenticate(credentials.credentials) if credentials else None
    if found is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión ausente, vencida o cerrada. Inicie sesión.",
                            headers={"WWW-Authenticate": "Bearer"})
    return Principal(*found)


def current_admin(principal: Annotated[Principal, Depends(current_user)]) -> Principal:
    if not principal.user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo un administrador puede hacer esto")
    return principal


UserDep = Annotated[Principal, Depends(current_user)]
AdminDep = Annotated[Principal, Depends(current_admin)]
