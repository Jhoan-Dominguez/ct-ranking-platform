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

import contextlib
import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta
from html import escape

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app import auth
from app.core import mailer
from app.core.config import get_settings
from app.database.models import Challenge, ChallengeKind, User, VerificationCode
from app.database.session import CommitBeforeRaiseError

log = logging.getLogger(__name__)

DELETE_PURPOSE = "delete_account"
EMAIL_PURPOSE = "change_email"
CODE_TTL = timedelta(minutes=15)
MAX_ATTEMPTS = 5
# Espera mínima entre dos códigos del mismo tipo (evita llenar el buzón de alguien).
RESEND_COOLDOWN = timedelta(seconds=60)


class AccountError(ValueError):
    pass


class InvalidCodeError(CommitBeforeRaiseError, AccountError):
    """Código incorrecto. Hereda de ``CommitBeforeRaiseError`` para que el intento fallido quede
    guardado aunque la acción se revierta; si no, el límite de intentos nunca se aplicaría."""


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    # SQLite (pruebas) devuelve fechas sin zona horaria; PostgreSQL las devuelve en UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _hash(code: str) -> str:
    settings = get_settings()
    # APP_SECRET_KEY en producción; en desarrollo se usa el secreto del cliente de Keycloak.
    key = (settings.app_secret_key or settings.keycloak_client_secret).encode()
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def _fmt(when: datetime) -> str:
    return _aware(when).astimezone().strftime("%d/%m/%Y %H:%M")


def _issue_code(session: Session, user: User, purpose: str, payload: str = "") -> str:
    """Invalida los códigos anteriores sin usar y crea uno nuevo. Devuelve el código en claro
    (sólo para enviarlo por correo; en la BD queda su HMAC)."""
    last = session.scalar(
        select(VerificationCode.created_at)
        .where(VerificationCode.user_id == user.id, VerificationCode.purpose == purpose)
        .order_by(VerificationCode.created_at.desc())
    )
    if last is not None and _now() - _aware(last) < RESEND_COOLDOWN:
        raise AccountError("Ya te enviamos un código hace un momento. Espera un minuto.")
    session.execute(
        update(VerificationCode)
        .where(
            VerificationCode.user_id == user.id,
            VerificationCode.purpose == purpose,
            VerificationCode.used_at.is_(None),
        )
        .values(used_at=_now())
    )
    code = f"{secrets.randbelow(10**6):06d}"
    session.add(
        VerificationCode(
            user_id=user.id,
            purpose=purpose,
            code_hash=_hash(code),
            payload=payload,
            expires_at=_now() + CODE_TTL,
        )
    )
    session.flush()
    return code


def _consume_code(session: Session, user: User, purpose: str, code: str) -> VerificationCode:
    """Valida el código vigente y lo marca como usado. Cada fallo suma un intento (que se guarda
    aunque la transacción termine en error) y al quinto el código deja de servir."""
    record = session.scalar(
        select(VerificationCode)
        .where(
            VerificationCode.user_id == user.id,
            VerificationCode.purpose == purpose,
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
        if remaining <= 0:
            raise InvalidCodeError("Código incorrecto. Solicita un código nuevo.")
        raise InvalidCodeError(f"Código incorrecto. Te quedan {remaining} intentos.")
    record.used_at = _now()
    session.flush()
    return record


# --------------------------------------------------------------------------- eliminación


def request_deletion(session: Session, user: User, password: str, otp: str | None = None) -> None:
    if user.pending_deletion:
        raise AccountError("La eliminación de tu cuenta ya está programada.")
    auth.verify_credentials(user, password, otp)
    code = _issue_code(session, user, DELETE_PURPOSE)
    mailer.send(
        user.email,
        "Código para eliminar tu cuenta de CT Ranking",
        [
            f"Hola {escape(user.display_name)}, recibimos una solicitud para "
            "<b>eliminar tu cuenta</b>.",
            f"Tu código de confirmación es: <b>{code}</b> (válido por 15 minutos).",
            "Si no fuiste tú, ignora este correo y cambia tu contraseña.",
        ],
    )


def confirm_deletion(session: Session, user: User, code: str) -> datetime:
    """Valida el código y programa la eliminación. Devuelve la fecha programada."""
    _consume_code(session, user, DELETE_PURPOSE, code)
    days = get_settings().account_deletion_days
    user.deletion_requested_at = _now()
    user.deletion_scheduled_for = _now() + timedelta(days=days)
    session.flush()
    mailer.send(
        user.email,
        "Tu cuenta de CT Ranking será eliminada",
        [
            f"Hola {escape(user.display_name)}, tu cuenta quedó <b>desactivada</b> y se "
            f"eliminará definitivamente el <b>{_fmt(user.deletion_scheduled_for)}</b>.",
            "Se borrarán tu perfil, plan académico, notas, publicaciones, comentarios, retos "
            "creados, participaciones, seguidores y mensajes.",
            f"¿Cambiaste de opinión? Inicia sesión antes de esa fecha en "
            f"{escape(get_settings().app_url)} y pulsa «Cancelar eliminación».",
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
        [
            f"Hola {escape(user.display_name)}, tu cuenta de CT Ranking vuelve a estar activa. "
            "¡Bienvenido!"
        ],
    )


def pending_deletion_ids(session: Session) -> set[int]:
    return set(session.scalars(select(User.id).where(User.deletion_scheduled_for.is_not(None))))


def purge_due_accounts(session: Session, now: datetime | None = None) -> list[str]:
    """Elimina definitivamente las cuentas cuyo plazo venció. Devuelve los usuarios borrados.

    Cada cuenta se borra en un *savepoint*: primero en la BD (para comprobar que el borrado es
    válido) y después en Keycloak. Si Keycloak falla, se revierte sólo esa cuenta y se reintenta
    en la siguiente ejecución, sin dejar a medias las demás."""
    now = now or _now()
    due = list(
        session.scalars(
            select(User).where(
                User.deletion_scheduled_for.is_not(None), User.deletion_scheduled_for <= now
            )
        )
    )
    uses_keycloak = get_settings().auth_provider == "keycloak"
    deleted = []
    for user in due:
        username, keycloak_id = user.username, user.keycloak_id
        savepoint = session.begin_nested()
        try:
            # Los retos de la comunidad que creó se borran con él; los globales se conservan
            # (creator_id pasa a NULL) para no quitarles los puntos a los demás.
            session.execute(
                delete(Challenge).where(
                    Challenge.creator_id == user.id, Challenge.kind == ChallengeKind.USER
                )
            )
            # Las claves foráneas con ON DELETE CASCADE borran el resto de su contenido.
            session.delete(user)
            session.flush()
            if keycloak_id and uses_keycloak:
                auth.KeycloakClient().delete_user(keycloak_id)
        except Exception:
            savepoint.rollback()
            log.exception("No se pudo purgar la cuenta %s; se reintentará", username)
            continue
        savepoint.commit()
        deleted.append(username)
    return deleted


# --------------------------------------------------------------------------- cambio de correo


def request_email_change(session: Session, user: User, email: str) -> str:
    """Envía un código al correo **nuevo**. El correo sólo cambia cuando se confirma con
    ``confirm_email_change``, así nadie puede apropiarse de un correo que no controla.
    Devuelve el correo normalizado."""
    email = auth.validate_new_email(session, user, email)
    code = _issue_code(session, user, EMAIL_PURPOSE, payload=email)
    mailer.send(
        email,
        "Confirma tu nuevo correo en CT Ranking",
        [
            f"Hola {escape(user.display_name)}, pediste usar este correo en tu cuenta de "
            "CT Ranking.",
            f"Tu código de confirmación es: <b>{code}</b> (válido por 15 minutos).",
            "Si no fuiste tú, ignora este correo: tu dirección no se agregará a ninguna cuenta.",
        ],
    )
    return email


def confirm_email_change(session: Session, user: User, code: str) -> str:
    """Valida el código enviado al correo nuevo y aplica el cambio. Devuelve el correo nuevo."""
    record = _consume_code(session, user, EMAIL_PURPOSE, code)
    old_email, new_email = user.email, record.payload
    # Se vuelve a validar: otra cuenta pudo registrar ese correo mientras tanto.
    auth.validate_new_email(session, user, new_email)
    auth.apply_verified_email(session, user, new_email)
    session.flush()
    # Aviso al correo anterior. Si falla no se revierte el cambio (ya se aplicó en Keycloak).
    with contextlib.suppress(mailer.MailError):
        mailer.send(
            old_email,
            "Tu correo de CT Ranking cambió",
            [
                f"Hola {escape(user.display_name)}, el correo de tu cuenta ahora es "
                f"<b>{escape(new_email)}</b>.",
                "Si no fuiste tú, contacta al administrador de la plataforma.",
            ],
        )
    return new_email
