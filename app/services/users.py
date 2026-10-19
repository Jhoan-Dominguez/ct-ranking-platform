"""Perfil de usuario y búsqueda de personas."""

from __future__ import annotations

import io
from datetime import UTC, date, datetime
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database.models import User

AVATAR_SIZE = 256
MAX_AVATAR_BYTES = 5 * 1024 * 1024

PROFILE_FIELDS = {
    "alias": 50,
    "bio": 1000,
    "phone": 30,
    "city": 100,
    "university": 150,
    "student_code": 30,
    "interests": 300,
    "github_url": 255,
    "linkedin_url": 255,
    "program": 150,
    "study_plan": 150,
}


URL_FIELDS = ("github_url", "linkedin_url")


class ProfileError(ValueError):
    pass


def _validate_url(value: str) -> str:
    """Sólo enlaces http(s) con dominio: evita ``javascript:`` y la inyección de Markdown."""
    if not value:
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ProfileError("Los enlaces deben empezar por https:// (o http://).")
    if any(c in value for c in " <>()[]\"'`"):
        raise ProfileError("El enlace contiene caracteres no válidos.")
    return value


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.username)))


def avatar_bytes(session: Session, user_id: int) -> bytes | None:
    """La foto (columna diferida) de un usuario, sin cargar el resto de la fila."""
    return session.scalar(select(User.avatar).where(User.id == user_id))


def update_profile(session: Session, user: User, **fields) -> User:
    # El alias se valida antes de asignarlo: con autoflush, asignarlo primero haría que el SELECT
    # de comprobación chocara con el índice único en lugar de dar un mensaje claro.
    alias = (fields.get("alias") or "").strip()
    if alias and alias.lower() != (user.alias or "").lower():
        taken = session.scalar(
            select(User.id).where(func.lower(User.alias) == alias.lower(), User.id != user.id)
        )
        if taken:
            raise ProfileError("Ese alias ya lo usa otra persona.")
    for key, max_len in PROFILE_FIELDS.items():
        if key in fields:
            value = (fields[key] or "").strip()
            if len(value) > max_len:
                raise ProfileError(f"El campo '{key}' supera {max_len} caracteres.")
            if key in URL_FIELDS:
                value = _validate_url(value)
            setattr(user, key, value)
    if "birth_date" in fields:
        birth: date | None = fields["birth_date"]
        if birth and birth > date.today():
            raise ProfileError("La fecha de nacimiento no puede estar en el futuro.")
        user.birth_date = birth
    if "current_semester" in fields or "total_semesters" in fields:
        current = int(fields.get("current_semester", user.current_semester))
        total = int(fields.get("total_semesters", user.total_semesters))
        if not 1 <= current <= total <= 20:
            raise ProfileError("El semestre actual debe estar entre 1 y el total de semestres.")
        user.current_semester, user.total_semesters = current, total
    return user


def process_avatar(raw: bytes) -> bytes:
    """Recorta al centro en cuadrado y redimensiona a 256px. Devuelve PNG."""
    if len(raw) > MAX_AVATAR_BYTES:
        raise ProfileError("La imagen supera 5 MB.")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ProfileError("El archivo no es una imagen válida.") from exc
    img = img.convert("RGBA")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((AVATAR_SIZE, AVATAR_SIZE))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def set_avatar(user: User, raw: bytes | None) -> None:
    if raw is None:
        user.avatar, user.avatar_mime = None, None
    else:
        user.avatar, user.avatar_mime = process_avatar(raw), "image/png"
    # Cambia la clave de la caché de la foto en la UI.
    user.avatar_updated_at = datetime.now(UTC)


def search_users(
    session: Session,
    query: str = "",
    *,
    exclude_id: int | None = None,
    hidden_ids: set[int] | None = None,
    limit: int = 50,
) -> list[User]:
    """Usuarios activos con la cuenta verificada. ``hidden_ids`` excluye, por ejemplo,
    bloqueos y cuentas en proceso de eliminación."""
    stmt = select(User).where(
        User.is_active.is_(True),
        User.email_verified.is_(True),
        User.deletion_scheduled_for.is_(None),
    )
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    if hidden_ids:
        stmt = stmt.where(User.id.not_in(hidden_ids))
    if query.strip():
        like = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.username).like(like),
                func.lower(User.alias).like(like),
                func.lower(User.first_name).like(like),
                func.lower(User.last_name).like(like),
                func.lower(User.program).like(like),
            )
        )
    return list(session.scalars(stmt.order_by(User.username).limit(limit)))
