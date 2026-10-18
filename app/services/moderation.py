"""Bloqueos entre usuarios y reportes para moderación.

Un bloqueo es **bidireccional** en sus efectos: ninguno de los dos ve el contenido del otro
(publicaciones, comentarios, mensajes, perfil, búsqueda), ni puede seguirlo o enviarle mensajes
de apoyo. Al bloquear se eliminan los seguimientos entre ambos. Los reportes llegan al panel de
administrador, que los resuelve o descarta.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Comment,
    Follow,
    Post,
    ReportReason,
    ReportStatus,
    User,
    UserBlock,
    UserReport,
)

REASON_LABELS = {
    ReportReason.SPAM: "Spam o publicidad",
    ReportReason.HARASSMENT: "Acoso o intimidación",
    ReportReason.INAPPROPRIATE: "Contenido inapropiado",
    ReportReason.IMPERSONATION: "Suplantación de identidad",
    ReportReason.OTHER: "Otro motivo",
}
STATUS_LABELS = {
    ReportStatus.PENDING: "🕒 Pendiente",
    ReportStatus.RESOLVED: "✅ Resuelto",
    ReportStatus.DISMISSED: "🚫 Descartado",
}


class ModerationError(ValueError):
    pass


# --------------------------------------------------------------------------- bloqueos


def block(session: Session, blocker_id: int, blocked_id: int) -> None:
    if blocker_id == blocked_id:
        raise ModerationError("No puedes bloquearte a ti mismo.")
    if session.get(User, blocked_id) is None:
        raise ModerationError("Usuario no encontrado.")
    if session.get(UserBlock, (blocker_id, blocked_id)) is None:
        session.add(UserBlock(blocker_id=blocker_id, blocked_id=blocked_id))
    session.execute(
        delete(Follow).where(
            or_(
                (Follow.follower_id == blocker_id) & (Follow.followed_id == blocked_id),
                (Follow.follower_id == blocked_id) & (Follow.followed_id == blocker_id),
            )
        )
    )
    session.flush()


def unblock(session: Session, blocker_id: int, blocked_id: int) -> None:
    row = session.get(UserBlock, (blocker_id, blocked_id))
    if row is not None:
        session.delete(row)
        session.flush()


def has_blocked(session: Session, blocker_id: int, blocked_id: int) -> bool:
    return session.get(UserBlock, (blocker_id, blocked_id)) is not None


def is_blocked_between(session: Session, a: int, b: int) -> bool:
    return has_blocked(session, a, b) or has_blocked(session, b, a)


def blocked_ids(session: Session, user_id: int) -> set[int]:
    """Usuarios con los que hay un bloqueo en cualquier dirección."""
    rows = session.execute(
        select(UserBlock.blocker_id, UserBlock.blocked_id).where(
            or_(UserBlock.blocker_id == user_id, UserBlock.blocked_id == user_id)
        )
    )
    return {b if a == user_id else a for a, b in rows}


def blocked_users(session: Session, user_id: int) -> list[User]:
    """Usuarios que ``user_id`` bloqueó (para la lista de desbloqueo)."""
    stmt = (
        select(UserBlock)
        .where(UserBlock.blocker_id == user_id)
        .options(selectinload(UserBlock.blocked))
        .order_by(UserBlock.created_at.desc())
    )
    return [row.blocked for row in session.scalars(stmt)]


def hidden_user_ids(session: Session, viewer_id: int) -> set[int]:
    """Usuarios cuyo contenido no debe ver ``viewer_id``: bloqueos y cuentas en eliminación."""
    from app.services.accounts import pending_deletion_ids

    return (blocked_ids(session, viewer_id) | pending_deletion_ids(session)) - {viewer_id}


# --------------------------------------------------------------------------- reportes


def report(
    session: Session,
    reporter_id: int,
    reported_id: int,
    *,
    reason: str,
    description: str = "",
    post_id: int | None = None,
    comment_id: int | None = None,
) -> UserReport:
    if reporter_id == reported_id:
        raise ModerationError("No puedes reportarte a ti mismo.")
    if reason not in {r.value for r in ReportReason}:
        raise ModerationError("Elige un motivo válido.")
    description = description.strip()
    if reason == ReportReason.OTHER and not description:
        raise ModerationError("Describe el motivo del reporte.")
    if len(description) > 2000:
        raise ModerationError("La descripción es demasiado larga (máx. 2000 caracteres).")
    if session.get(User, reported_id) is None:
        raise ModerationError("Usuario no encontrado.")
    if post_id is not None and session.get(Post, post_id) is None:
        raise ModerationError("La publicación ya no existe.")
    if comment_id is not None and session.get(Comment, comment_id) is None:
        raise ModerationError("El comentario ya no existe.")
    duplicate = session.scalar(
        select(UserReport).where(
            UserReport.reporter_id == reporter_id,
            UserReport.reported_id == reported_id,
            UserReport.status == ReportStatus.PENDING,
            UserReport.post_id.is_(post_id) if post_id is None else UserReport.post_id == post_id,
            UserReport.comment_id.is_(comment_id)
            if comment_id is None
            else UserReport.comment_id == comment_id,
        )
    )
    if duplicate is not None:
        raise ModerationError("Ya enviaste este reporte; el equipo de moderación lo revisará.")
    row = UserReport(
        reporter_id=reporter_id,
        reported_id=reported_id,
        reason=reason,
        description=description,
        post_id=post_id,
        comment_id=comment_id,
    )
    session.add(row)
    session.flush()
    return row


def list_reports(session: Session, status: str | None = None) -> list[UserReport]:
    stmt = select(UserReport).options(
        selectinload(UserReport.reporter),
        selectinload(UserReport.reported),
        selectinload(UserReport.resolved_by),
        selectinload(UserReport.post),
        selectinload(UserReport.comment),
    )
    if status:
        stmt = stmt.where(UserReport.status == status)
    return list(session.scalars(stmt.order_by(UserReport.created_at.desc())))


def pending_reports_count(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(UserReport)
            .where(UserReport.status == ReportStatus.PENDING)
        )
        or 0
    )


def reports_against_count(session: Session, user_id: int) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(UserReport).where(UserReport.reported_id == user_id)
        )
        or 0
    )


def close_report(
    session: Session, admin: User, report_id: int, status: str, note: str = ""
) -> None:
    if not admin.is_admin:
        raise ModerationError("Sólo un administrador puede gestionar reportes.")
    if status not in (ReportStatus.RESOLVED, ReportStatus.DISMISSED):
        raise ModerationError("Estado inválido.")
    row = session.get(UserReport, report_id)
    if row is None:
        raise ModerationError("Reporte no encontrado.")
    row.status = status
    row.admin_note = note.strip()
    row.resolved_by_id = admin.id
    row.resolved_at = datetime.now(UTC)
    session.flush()
