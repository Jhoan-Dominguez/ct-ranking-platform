"""Perfil de usuario y búsqueda de personas."""

from __future__ import annotations

import io
from datetime import date

from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import User

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


class ProfileError(ValueError):
    pass


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def update_profile(session: Session, user: User, **fields) -> User:
    for key, max_len in PROFILE_FIELDS.items():
        if key in fields:
            value = (fields[key] or "").strip()
            if len(value) > max_len:
                raise ProfileError(f"El campo '{key}' supera {max_len} caracteres.")
            setattr(user, key, value)
    if "alias" in fields and user.alias:
        taken = session.scalar(
            select(User.id).where(func.lower(User.alias) == user.alias.lower(), User.id != user.id)
        )
        if taken:
            raise ProfileError("Ese alias ya lo usa otra persona.")
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
        return
    user.avatar, user.avatar_mime = process_avatar(raw), "image/png"


def search_users(
    session: Session, query: str = "", *, exclude_id: int | None = None, limit: int = 50
) -> list[User]:
    stmt = select(User).where(User.is_active.is_(True))
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
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
