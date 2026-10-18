"""Migra el correo de los estudiantes existentes al dominio institucional.

Para cada estudiante (no administrador) cuyo correo no termina en ``@STUDENT_EMAIL_DOMAIN``,
el nuevo correo es ``<usuario>@STUDENT_EMAIL_DOMAIN``. Se actualiza en la app y en Keycloak.

Uso: ``python scripts/migrate_student_emails.py [--dry-run]``
(``make migrate-emails`` / ``make migrate-emails ARGS=--dry-run``)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.db.models import Role, User
from app.db.session import session_scope
from app.services import auth


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Sólo muestra los cambios")
    args = parser.parse_args()

    domain = auth.student_domain()
    use_keycloak = get_settings().auth_provider == "keycloak"
    client = auth.KeycloakClient() if use_keycloak else None
    changed = skipped = 0
    with session_scope() as session:
        students = session.scalars(
            select(User).where(User.role != Role.ADMIN).order_by(User.username)
        )
        for user in students:
            if user.email.endswith("@" + domain):
                continue
            try:
                new_email = auth.student_email(user.username)
            except auth.AuthError as exc:
                print(f"  ✘ {user.username}: {exc} (revísalo a mano)")
                skipped += 1
                continue
            taken = session.scalar(
                select(User.id).where(func.lower(User.email) == new_email, User.id != user.id)
            )
            if taken:
                print(f"  ✘ {user.username}: {new_email} ya pertenece a otro usuario")
                skipped += 1
                continue
            print(f"  {'·' if args.dry_run else '✔'} {user.username}: {user.email} → {new_email}")
            changed += 1
            if args.dry_run:
                continue
            if client and user.keycloak_id:
                # Correo institucional asignado por la plataforma: se marca como verificado.
                client.update_user(user.keycloak_id, email=new_email, emailVerified=True)
            user.email = new_email
        if args.dry_run:
            session.rollback()
    action = "a migrar" if args.dry_run else "migrados"
    print(f"Estudiantes {action}: {changed}. Omitidos: {skipped}. Dominio: @{domain}")


if __name__ == "__main__":
    main()
