"""Seguidores y mensajes de apoyo."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.database.models import Follow, SupportMessage, User
from app.services import moderation

SUPPORT_TEMPLATES = [
    "¡Vamos, tú puedes! 💪",
    "No te rindas, ya casi lo logras 🚀",
    "¡Qué gran progreso! Sigue así 👏",
    "Confío en ti, ese examen es tuyo 📚",
    "Un paso a la vez, lo estás haciendo muy bien 🌱",
    "¡Ánimo! Si necesitas ayuda, aquí estoy 🤝",
]
MAX_MESSAGE_LEN = 500


class SocialError(ValueError):
    pass


def follow(session: Session, follower_id: int, followed_id: int) -> None:
    if follower_id == followed_id:
        raise SocialError("No puedes seguirte a ti mismo.")
    if session.get(User, followed_id) is None:
        raise SocialError("Usuario no encontrado.")
    if moderation.is_blocked_between(session, follower_id, followed_id):
        raise SocialError("No puedes seguir a esta persona.")
    if not is_following(session, follower_id, followed_id):
        session.add(Follow(follower_id=follower_id, followed_id=followed_id))
        session.flush()


def unfollow(session: Session, follower_id: int, followed_id: int) -> None:
    rel = session.get(Follow, (follower_id, followed_id))
    if rel is not None:
        session.delete(rel)


def is_following(session: Session, follower_id: int, followed_id: int) -> bool:
    return session.get(Follow, (follower_id, followed_id)) is not None


def following_ids(session: Session, user_id: int) -> set[int]:
    return set(session.scalars(select(Follow.followed_id).where(Follow.follower_id == user_id)))


def followers(session: Session, user_id: int) -> list[User]:
    stmt = (
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.followed_id == user_id)
        .order_by(User.username)
    )
    return list(session.scalars(stmt))


def following(session: Session, user_id: int) -> list[User]:
    stmt = (
        select(User)
        .join(Follow, Follow.followed_id == User.id)
        .where(Follow.follower_id == user_id)
        .order_by(User.username)
    )
    return list(session.scalars(stmt))


def follow_counts(
    session: Session, user_id: int, hidden_ids: set[int] | None = None
) -> tuple[int, int]:
    """(seguidores, seguidos). ``hidden_ids`` excluye cuentas ocultas para quien mira
    (bloqueos y eliminación programada), igual que las listas de Personas."""
    followers_q = select(func.count()).select_from(Follow).where(Follow.followed_id == user_id)
    following_q = select(func.count()).select_from(Follow).where(Follow.follower_id == user_id)
    if hidden_ids:
        followers_q = followers_q.where(Follow.follower_id.not_in(hidden_ids))
        following_q = following_q.where(Follow.followed_id.not_in(hidden_ids))
    return session.scalar(followers_q) or 0, session.scalar(following_q) or 0


def send_support(session: Session, sender_id: int, recipient_id: int, message: str) -> None:
    message = message.strip()
    if sender_id == recipient_id:
        raise SocialError("No puedes enviarte mensajes a ti mismo.")
    if not message:
        raise SocialError("El mensaje está vacío.")
    if len(message) > MAX_MESSAGE_LEN:
        raise SocialError(f"El mensaje supera {MAX_MESSAGE_LEN} caracteres.")
    if session.get(User, recipient_id) is None:
        raise SocialError("Usuario no encontrado.")
    if moderation.is_blocked_between(session, sender_id, recipient_id):
        raise SocialError("No puedes enviar mensajes a esta persona.")
    session.add(SupportMessage(sender_id=sender_id, recipient_id=recipient_id, message=message))
    session.flush()


def inbox(session: Session, user_id: int, limit: int = 100) -> list[SupportMessage]:
    """Mensajes recibidos, sin los de usuarios bloqueados o en proceso de eliminación."""
    hidden = moderation.hidden_user_ids(session, user_id)
    stmt = (
        select(SupportMessage)
        .where(SupportMessage.recipient_id == user_id, SupportMessage.sender_id.not_in(hidden))
        .options(selectinload(SupportMessage.sender))
        .order_by(SupportMessage.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def sent(session: Session, user_id: int, limit: int = 100) -> list[SupportMessage]:
    stmt = (
        select(SupportMessage)
        .where(SupportMessage.sender_id == user_id)
        .options(selectinload(SupportMessage.recipient))
        .order_by(SupportMessage.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def unread_count(session: Session, user_id: int) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(SupportMessage)
            .where(
                SupportMessage.recipient_id == user_id,
                SupportMessage.is_read.is_(False),
                SupportMessage.sender_id.not_in(moderation.hidden_user_ids(session, user_id)),
            )
        )
        or 0
    )


def mark_all_read(session: Session, user_id: int) -> None:
    session.execute(
        update(SupportMessage)
        .where(SupportMessage.recipient_id == user_id, SupportMessage.is_read.is_(False))
        .values(is_read=True)
    )
