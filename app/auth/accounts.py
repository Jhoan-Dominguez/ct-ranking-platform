"""Eliminación diferida de cuentas con doble verificación.

Flujo:
1. ``request_deletion`` verifica la contraseña (y el código 2FA si lo tiene, porque Keycloak lo
   exige en el login) y envía al correo un código de 6 dígitos válido 15 minutos.
2. ``confirm_deletion`` valida ese código y programa la eliminación para dentro de
   ``ACCOUNT_DELETION_DAYS`` días (7 por defecto). Desde ese momento la cuenta queda desactivada:
   su perfil y contenido se ocultan y, si inicia sesión, sólo puede cancelar la eliminación.
3. ``cancel_deletion`` revierte la solicitud mientras no se cumpla el plazo.
4. ``purge_due_accounts`` borra definitivamente (en la app y en Keycloak) las cuentas cuyo plazo
   venció. Lo ejecuta una tarea periódica de la app y ``make purge-accounts``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import auth
from app.core import mailer
from app.core.config import get_settings
from app.database.models import User, VerificationCode

DELETE_PURPOSE = "delete_account"
CODE_TTL = timedelta(minutes=15)
MAX_ATTEMPTS = 5


class AccountError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    # SQLite (pruebas) devuelve fechas sin zona horaria; PostgreSQL las devuelve en UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _hash(code: str) -> str:
    key = get_settings().keycloak_client_secret.encode()  # secreto del servidor como "pepper"
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def _fmt(when: datetime) -> str:
    return _aware(when).astimezone().strftime("%d/%m/%Y %H:%M")


def request_deletion(session: Session, user: User, password: str, otp: str | None = None) -> None:
    if user.pending_deletion:
        raise AccountError("La eliminación de tu cuenta ya está programada.")
    auth.verify_credentials(user, password, otp)
    # Invalida códigos anteriores sin usar.
    session.execute(
        update(VerificationCode)
        .where(
            VerificationCode.user_id == user.id,
            VerificationCode.purpose == DELETE_PURPOSE,
            VerificationCode.used_at.is_(None),
        )
        .values(used_at=_now())
    )
    code = f"{secrets.randbelow(10**6):06d}"
    session.add(
        VerificationCode(
            user_id=user.id,
            purpose=DELETE_PURPOSE,
            code_hash=_hash(code),
            expires_at=_now() + CODE_TTL,
        )
    )
    session.flush()
    mailer.send(
        user.email,
        "Código para eliminar tu cuenta de CT Ranking",
        [
            f"Hola {user.display_name}, recibimos una solicitud para <b>eliminar tu cuenta</b>.",
            f"Tu código de confirmación es: <b>{code}</b> (válido por 15 minutos).",
            "Si no fuiste tú, ignora este correo y cambia tu contraseña.",
        ],
    )


def confirm_deletion(session: Session, user: User, code: str) -> datetime:
    """Valida el código y programa la eliminación. Devuelve la fecha programada."""
    record = session.scalar(
        select(VerificationCode)
        .where(
            VerificationCode.user_id == user.id,
            VerificationCode.purpose == DELETE_PURPOSE,
            VerificationCode.used_at.is_(None),
        )
        .order_by(VerificationCode.created_at.desc())
    )
    if record is None or _aware(record.expires_at) < _now():
        raise AccountError("El código expiró o no existe. Solicita uno nuevo.")
    if record.attempts >= MAX_ATTEMPTS:
        raise AccountError("Demasiados intentos con este código. Solicita uno nuevo.")
    if not hmac.compare_digest(record.code_hash, _hash(code.strip())):
        record.attempts += 1
        session.flush()
        remaining = MAX_ATTEMPTS - record.attempts
        raise AccountError(f"Código incorrecto. Te quedan {remaining} intentos.")
    record.used_at = _now()
    days = get_settings().account_deletion_days
    user.deletion_requested_at = _now()
    user.deletion_scheduled_for = _now() + timedelta(days=days)
    session.flush()
    mailer.send(
        user.email,
        "Tu cuenta de CT Ranking será eliminada",
        [
            f"Hola {user.display_name}, tu cuenta quedó <b>desactivada</b> y se eliminará "
            f"definitivamente el <b>{_fmt(user.deletion_scheduled_for)}</b>.",
            "Se borrarán tu perfil, plan académico, notas, publicaciones, comentarios, retos "
            "creados, participaciones, seguidores y mensajes.",
            f"¿Cambiaste de opinión? Inicia sesión antes de esa fecha en {get_settings().app_url} "
            "y pulsa «Cancelar eliminación».",
        ],
    )
    return user.deletion_scheduled_for


def cancel_deletion(session: Session, user: User) -> None:
    if not user.pending_deletion:
        return
    user.deletion_requested_at = None
    user.deletion_scheduled_for = None
    session.flush()
    mailer.send(
        user.email,
        "Cancelaste la eliminación de tu cuenta",
        [f"Hola {user.display_name}, tu cuenta de CT Ranking vuelve a estar activa. ¡Bienvenido!"],
    )


def pending_deletion_ids(session: Session) -> set[int]:
    return set(session.scalars(select(User.id).where(User.deletion_scheduled_for.is_not(None))))


def purge_due_accounts(session: Session, now: datetime | None = None) -> list[str]:
    """Elimina definitivamente las cuentas cuyo plazo venció. Devuelve los usuarios borrados."""
    now = now or _now()
    due = list(
        session.scalars(
            select(User).where(
                User.deletion_scheduled_for.is_not(None), User.deletion_scheduled_for <= now
            )
        )
    )
    deleted = []
    for user in due:
        if user.keycloak_id and get_settings().auth_provider == "keycloak":
            auth.KeycloakClient().delete_user(user.keycloak_id)
        deleted.append(user.username)
        # Las claves foráneas con ON DELETE CASCADE borran su contenido.
        session.delete(user)
    session.flush()
    return deleted
