"""Account tasks from the command line: migrations, the first admin, a lost admin password, and a backup.

Usage (from backend/):
    uv run python -m interfaces.jobs.accounts_admin migrar
    uv run python -m interfaces.jobs.accounts_admin crear-admin [--email ... --usuario ... --nombre ...]
    uv run python -m interfaces.jobs.accounts_admin restablecer-admin [--usuario ...]
    uv run python -m interfaces.jobs.accounts_admin respaldo

The admin password is generated here and written only to non_private/non_envs/credenciales_admin.txt (outside the
repository, next to the database password); it is never printed. crear-admin refuses to overwrite that file.
"""
from __future__ import annotations

import argparse
import subprocess
from datetime import datetime

from accounts import credentials as cred
from accounts.db import SCHEMA, connect, migrate
from accounts.service import AccountError, Accounts
from shared.settings import REPO, settings

CREDENTIALS = REPO / "non_private" / "non_envs" / "credenciales_admin.txt"
BACKUPS = REPO / "non_local" / "non_backups"
COMPOSE = ["docker", "compose", "-p", "tp202620505", "-f", str(REPO / "ops" / "docker" / "docker-compose.yml"),
           "--env-file", str(REPO / "non_private" / "non_envs" / ".env")]


def write_credentials(email: str, usuario: str, password: str, action: str) -> None:
    CREDENTIALS.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS.write_text(
        "# Credenciales de la cuenta de administración del sistema TP202620505. No versionar ni compartir.\n"
        f"# {action} el {datetime.now():%d/%m/%Y %H:%M}. Inicio de sesión con el usuario o el correo.\n"
        f"usuario={usuario}\ncorreo={email}\ncontrasena={password}\n", encoding="utf-8")


def create_admin(args) -> None:
    if CREDENTIALS.exists():
        raise SystemExit(f"Ya existe {CREDENTIALS}; no se sobrescribe. Use restablecer-admin si perdió la contraseña.")
    conn = connect()
    migrate(conn)
    password = cred.generate_password()
    try:
        user = Accounts(conn).create_admin(args.email, args.usuario, args.nombre, password)
    except AccountError as e:
        raise SystemExit(str(e)) from e
    write_credentials(user.email, user.usuario, password, "Creada")
    print(f"Cuenta de administración «{user.usuario}» creada. Credenciales en {CREDENTIALS}")


def reset_admin(args) -> None:
    conn = connect()
    acc = Accounts(conn)
    try:
        user = acc.by_username(args.usuario)
    except AccountError as e:
        raise SystemExit(str(e)) from e
    if not user.is_admin:
        raise SystemExit(f"{user.usuario} no es administrador")
    password = cred.generate_password()
    acc.set_password(user.id, password)
    write_credentials(user.email, user.usuario, password, "Restablecida")
    print(f"Contraseña de «{user.usuario}» restablecida y sesiones cerradas. Credenciales en {CREDENTIALS}")


def backup(args) -> None:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    target = BACKUPS / f"cuentas-{datetime.now():%Y%m%d-%H%M%S}.sql"
    cmd = [*COMPOSE, "exec", "-T", "db", "pg_dump", "-U", settings.postgres_user, "-d", settings.postgres_db,
           "-n", SCHEMA, "--no-owner"]
    with target.open("wb") as out:
        done = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, check=False)  # the code is checked below
    if done.returncode != 0 or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise SystemExit(f"pg_dump falló: {done.stderr.decode(errors='replace').strip()}")
    print(f"Respaldo del esquema {SCHEMA}: {target} ({target.stat().st_size} bytes)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="task", required=True)
    sub.add_parser("migrar", help="aplica las migraciones pendientes del esquema de cuentas")
    c = sub.add_parser("crear-admin", help="crea la primera cuenta de administración")
    c.add_argument("--email", default="admin@example.org")
    c.add_argument("--usuario", default="admin")
    c.add_argument("--nombre", default="Administrador")
    r = sub.add_parser("restablecer-admin", help="nueva contraseña para un administrador")
    r.add_argument("--usuario", default="admin")
    sub.add_parser("respaldo", help="respalda el esquema de cuentas con pg_dump")
    args = parser.parse_args(argv)
    if args.task == "migrar":
        applied = migrate(connect())
        print("migraciones aplicadas:", applied or "ninguna pendiente")
    elif args.task == "crear-admin":
        create_admin(args)
    elif args.task == "restablecer-admin":
        reset_admin(args)
    else:
        backup(args)


if __name__ == "__main__":
    main()
