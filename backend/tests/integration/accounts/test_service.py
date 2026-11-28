"""Accounts over the local PostgreSQL, in a throwaway schema, with a clock the tests move. Skipped when the database is
not running (make db)."""
import secrets
from datetime import UTC, date, datetime, timedelta

import psycopg
import pytest

from accounts import credentials as cred
from accounts import privacy
from accounts.db import connect, migrate
from accounts.service import ABSOLUTE, IDLE, LOCK, AccountError, Accounts, AuthFailed, InvalidToken

PASSWORD = "luz-de-campo-2026"
OTHER = "otra-clave-segura-77"


class Clock:
    def __init__(self):
        self.t = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)

    def __call__(self):
        return self.t

    def advance(self, delta):
        self.t += delta


@pytest.fixture
def schema():
    name = f"cuentas_test_{secrets.token_hex(4)}"
    try:
        conn = connect(name)
    except psycopg.OperationalError:
        pytest.skip("local database not running (make db)")
    migrate(conn)
    yield conn
    conn.execute(f'DROP SCHEMA "{name}" CASCADE')
    conn.close()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def acc(schema, clock):
    return Accounts(schema, clock)


@pytest.fixture
def admin(acc):
    return acc.create_admin("andrea@example.org", "andrea", "Andrea", PASSWORD)


def invited_user(acc, admin, usuario="ana", email="ana@example.org"):
    user, token = acc.invite(admin, email, usuario, "Ana Quispe", "usuario")
    acc.redeem(token, OTHER, privacy.VERSION)
    return acc.user(user.id)


def test_migrations_are_applied_once(schema):
    assert migrate(schema) == []


def test_admin_signs_in_with_username_or_email(acc, admin):
    for ident in ("andrea", "ANDREA", "andrea@example.org", "Andrea@Example.org "):
        user, token = acc.login(ident, PASSWORD, "pytest")
        assert user.id == admin.id and user.is_admin
        auth = acc.authenticate(token)
        assert auth and auth[0].usuario == "andrea"


def test_one_message_for_every_failure(acc, admin):
    messages = set()
    for ident, pw in (("andrea", "mala-clave-123"), ("nadie", PASSWORD), ("nadie@example.org", PASSWORD)):
        with pytest.raises(AuthFailed) as e:
            acc.login(ident, pw)
        messages.add(str(e.value))
    assert len(messages) == 1


def test_invitation_activation_and_single_use(acc, admin):
    user, token = acc.invite(admin, "ana@example.org", "Ana.Q", "Ana Quispe", "usuario")
    assert (user.estado, user.usuario) == ("invitado", "ana.q")
    with pytest.raises(AuthFailed):
        acc.login("ana.q", OTHER)                                   # no password yet
    info = acc.invitation_info(token)
    assert (info["usuario"], info["tipo"]) == ("ana.q", "activacion")
    acc.redeem(token, OTHER, privacy.VERSION)
    assert acc.login("ana.q", OTHER)[0].estado == "activo"
    with pytest.raises(InvalidToken):
        acc.redeem(token, "tercera-clave-segura", privacy.VERSION)                   # used


def test_invitation_expires_and_is_replaced(acc, admin, clock):
    user, first = acc.invite(admin, "ana@example.org", "ana", "Ana", "usuario")
    second = acc.reset_link(admin, user.id)
    with pytest.raises(InvalidToken):
        acc.invitation_info(first)                                  # replaced by the new link
    clock.advance(timedelta(hours=73))
    with pytest.raises(InvalidToken):
        acc.redeem(second, OTHER, privacy.VERSION)


def test_password_policy(acc, admin):
    _, token = acc.invite(admin, "ana@example.org", "ana", "Ana", "usuario")
    for weak in ("corta", "qwerty123456", "aaaaaaaaaaaaaaaa", "ana"):
        with pytest.raises(cred.WeakPassword):
            acc.redeem(token, weak, privacy.VERSION)


def test_duplicates_and_bad_names(acc, admin):
    with pytest.raises(AccountError, match="usuario"):
        acc.invite(admin, "otra@example.org", "andrea", "X", "usuario")
    with pytest.raises(AccountError, match="correo"):
        acc.invite(admin, "ANDREA@example.org", "otra", "X", "usuario")
    for bad in ("ab", "con espacio", "a@b", "x" * 40):
        with pytest.raises(AccountError):
            acc.invite(admin, f"{secrets.token_hex(3)}@example.org", bad, "X", "usuario")


def test_lockout_after_five_failures(acc, admin, clock):
    for _ in range(5):
        with pytest.raises(AuthFailed):
            acc.login("andrea", "mala-clave-123")
    with pytest.raises(AuthFailed):
        acc.login("andrea", PASSWORD)                               # locked even with the right password
    clock.advance(LOCK + timedelta(seconds=1))
    assert acc.login("andrea", PASSWORD)[0].id == admin.id


def test_session_idle_and_absolute_expiry(acc, admin, clock):
    _, token = acc.login("andrea", PASSWORD)
    clock.advance(IDLE - timedelta(minutes=1))
    assert acc.authenticate(token)                                  # activity renews the idle window
    clock.advance(IDLE + timedelta(seconds=1))
    assert acc.authenticate(token) is None
    _, token = acc.login("andrea", PASSWORD)
    for _ in range(int(ABSOLUTE / IDLE) + 1):
        clock.advance(IDLE - timedelta(minutes=1))
        acc.authenticate(token)
    assert acc.authenticate(token) is None                          # 30 days at most, whatever the activity


def test_logout_and_revoking_other_sessions(acc, admin):
    _, t1 = acc.login("andrea", PASSWORD, "web")
    _, t2 = acc.login("andrea", PASSWORD, "escritorio")
    user, s1 = acc.authenticate(t1)
    assert len(acc.sessions(user.id)) == 2
    other = next(s for s in acc.sessions(user.id) if s["id"] != s1.id)
    acc.revoke_session(user.id, other["id"])
    assert acc.authenticate(t2) is None
    acc.logout(s1)
    assert acc.authenticate(t1) is None


def test_change_password_keeps_this_session_only(acc, admin):
    _, t1 = acc.login("andrea", PASSWORD)
    _, t2 = acc.login("andrea", PASSWORD)
    user, s1 = acc.authenticate(t1)
    with pytest.raises(AccountError):
        acc.change_password(user, s1, "no-es-la-actual-1", OTHER)
    acc.change_password(user, s1, PASSWORD, OTHER)
    assert acc.authenticate(t1) and acc.authenticate(t2) is None
    assert acc.login("andrea", OTHER)


def test_reset_link_ends_every_session(acc, admin):
    ana = invited_user(acc, admin)
    _, token = acc.login("ana", OTHER)
    link = acc.reset_link(admin, ana.id)
    assert acc.invitation_info(link)["tipo"] == "restablecimiento"
    acc.redeem(link, "nueva-clave-segura-9")
    assert acc.authenticate(token) is None
    assert acc.login("ana@example.org", "nueva-clave-segura-9")


def test_deactivation_cuts_sessions_and_sign_in(acc, admin):
    ana = invited_user(acc, admin)
    _, token = acc.login("ana", OTHER)
    acc.update_user(admin, ana.id, estado="desactivado")
    assert acc.authenticate(token) is None
    with pytest.raises(AuthFailed):
        acc.login("ana", OTHER)
    with pytest.raises(AccountError):
        acc.reset_link(admin, ana.id)
    acc.update_user(admin, ana.id, estado="activo")
    assert acc.login("ana", OTHER)


def test_there_is_always_an_active_admin(acc, admin):
    with pytest.raises(AccountError, match="administrador"):
        acc.update_user(admin, admin.id, rol="usuario")
    with pytest.raises(AccountError, match="administrador"):
        acc.update_user(admin, admin.id, estado="desactivado")
    ana = invited_user(acc, admin)
    acc.update_user(admin, ana.id, rol="admin")
    assert acc.update_user(admin, admin.id, rol="usuario").rol == "usuario"


def test_saved_work_belongs_to_its_owner(acc, admin):
    ana = invited_user(acc, admin)
    draft = {"crop": "blueberry", "blocks": [{"key": "A1"}], "applications": [{"block": "A1"}, {"block": "A1"}]}
    p = acc.save_program(ana.id, "Campaña 2026", "blueberry", draft)
    [listed] = acc.programs(ana.id)
    assert (listed["nombre"], listed["aplicaciones"], listed["bloques"]) == ("Campaña 2026", 2, 1)
    assert acc.programs(admin.id) == []
    with pytest.raises(AccountError):
        acc.program(admin.id, p["id"])                              # not the owner
    acc.save_program(ana.id, "Campaña 2026 v2", "blueberry", draft, p["id"])
    assert acc.program(ana.id, p["id"])["nombre"] == "Campaña 2026 v2"
    lot = acc.save_lot(ana.id, "L-1", "blueberry", "EU", date(2026, 10, 28), "lidl_2025", "blocking",
                       {"measurements": [{"ingredient": "x"}]}, {"verdict": "blocking"})
    assert acc.lots(ana.id)[0]["residuos"] == 1 and acc.lot(ana.id, lot["id"])["resultado"]["verdict"] == "blocking"
    acc.delete_program(ana.id, p["id"])
    assert acc.programs(ana.id) == []


def test_activity_log(acc, admin):
    ana = invited_user(acc, admin)
    acc.login("ana", OTHER)
    actions = [a["accion"] for a in acc.activity(ana.id)]
    assert actions[:3] == ["ingreso", "aviso_aceptado", "cuenta_activada"]
    assert {"usuario_invitado", "admin_creado"} <= {a["accion"] for a in acc.activity()}
