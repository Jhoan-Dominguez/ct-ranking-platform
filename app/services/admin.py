"""Métricas y consultas para el panel de administración."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.database.models import (
    Challenge,
    ChallengeKind,
    ChallengeParticipant,
    Comment,
    Follow,
    GradeItem,
    Post,
    ReportStatus,
    Role,
    Subject,
    SupportMessage,
    User,
    UserReport,
)
from app.services import academics, challenges, social


@dataclass
class GlobalMetrics:
    users: int
    active_users_7d: int
    new_users_30d: int
    posts: int
    comments: int
    challenges_global: int
    challenges_user: int
    participations: int
    completions: int
    messages: int
    follows: int
    grade_items: int
    pending_reports: int
    pending_deletions: int
    unverified_users: int


class AdminError(ValueError):
    pass


def _require_admin(actor: User) -> None:
    # La página ya lo verifica; se repite aquí para que el servicio sea seguro por sí mismo.
    if not actor.is_admin:
        raise AdminError("Sólo un administrador puede hacer esto.")


def _count(session: Session, model, *where) -> int:
    return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


def _count_q(model, *where):
    return select(func.count()).select_from(model).where(*where).scalar_subquery()


def global_metrics(session: Session) -> GlobalMetrics:
    """Todas las métricas en una sola consulta (subconsultas escalares)."""
    now = datetime.now(UTC)
    fields = {
        "users": _count_q(User),
        "active_users_7d": _count_q(User, User.last_login >= now - timedelta(days=7)),
        "new_users_30d": _count_q(User, User.created_at >= now - timedelta(days=30)),
        "posts": _count_q(Post),
        "comments": _count_q(Comment),
        "challenges_global": _count_q(Challenge, Challenge.kind == ChallengeKind.GLOBAL),
        "challenges_user": _count_q(Challenge, Challenge.kind == ChallengeKind.USER),
        "participations": _count_q(ChallengeParticipant),
        "completions": _count_q(
            ChallengeParticipant, ChallengeParticipant.completed_at.is_not(None)
        ),
        "messages": _count_q(SupportMessage),
        "follows": _count_q(Follow),
        "grade_items": _count_q(GradeItem),
        "pending_reports": _count_q(UserReport, UserReport.status == ReportStatus.PENDING),
        "pending_deletions": _count_q(User, User.deletion_scheduled_for.is_not(None)),
        "unverified_users": _count_q(User, User.email_verified.is_(False)),
    }
    row = session.execute(select(*(q.label(name) for name, q in fields.items()))).one()
    return GlobalMetrics(**{name: int(value or 0) for name, value in row._mapping.items()})


def students_frame(session: Session, user_ids: set[int] | None = None) -> pd.DataFrame:
    """Una fila por estudiante con datos académicos y de actividad."""
    stmt = select(User).options(selectinload(User.subjects).selectinload(Subject.items))
    if user_ids is not None:
        stmt = stmt.where(User.id.in_(user_ids))
    users = list(session.scalars(stmt.order_by(User.username)))

    def counts(column, group_col) -> dict[int, int]:
        rows = session.execute(select(group_col, func.count(column)).group_by(group_col))
        return dict(rows.all())  # type: ignore[arg-type]

    posts = counts(Post.id, Post.author_id)
    comments = counts(Comment.id, Comment.author_id)
    msgs_received = counts(SupportMessage.id, SupportMessage.recipient_id)
    reports = counts(UserReport.id, UserReport.reported_id)
    followers = counts(Follow.follower_id, Follow.followed_id)
    completed = dict(
        session.execute(
            select(ChallengeParticipant.user_id, func.count())
            .where(ChallengeParticipant.completed_at.is_not(None))
            .group_by(ChallengeParticipant.user_id)
        ).all()
    )
    scores = challenges.scores_by_user(session)
    passing = get_settings().grade_passing

    records = []
    for u in users:
        summary = academics.summarize(u.subjects, u.current_semester)
        records.append(
            {
                "id": u.id,
                "usuario": u.username,
                "nombre": u.full_name,
                "programa": u.program,
                "semestre": u.current_semester,
                "rol": u.role,
                "activo": u.is_active,
                "verificado": u.email_verified,
                "eliminacion_programada": u.deletion_scheduled_for,
                "reportes_recibidos": reports.get(u.id, 0),
                "promedio_general": summary.general_average,
                "promedio_semestre": summary.current_semester_average,
                "materias_cursando": summary.in_progress,
                "materias_aprobadas": summary.passed,
                "materias_reprobadas": summary.failed,
                "creditos_aprobados": summary.passed_credits,
                "publicaciones": posts.get(u.id, 0),
                "comentarios": comments.get(u.id, 0),
                "retos_completados": completed.get(u.id, 0),
                "puntos": scores.get(u.id, 0),
                "seguidores": followers.get(u.id, 0),
                "apoyos_recibidos": msgs_received.get(u.id, 0),
                "ultimo_ingreso": u.last_login,
                "en_riesgo": (
                    summary.general_average is not None and summary.general_average < passing
                )
                or (
                    summary.current_semester_average is not None
                    and summary.current_semester_average < passing
                ),
            }
        )
    return pd.DataFrame.from_records(records)


def activity_frame(session: Session, days: int = 30) -> pd.DataFrame:
    """Actividad diaria (publicaciones, comentarios, retos completados, mensajes), agrupada por
    día en SQL."""
    since = datetime.now(UTC) - timedelta(days=days)
    series = {
        "publicaciones": Post.created_at,
        "comentarios": Comment.created_at,
        "retos completados": ChallengeParticipant.completed_at,
        "mensajes de apoyo": SupportMessage.created_at,
    }
    index = pd.date_range(end=pd.Timestamp.now().normalize(), periods=days, freq="D").date
    frame = pd.DataFrame(index=index)
    for name, column in series.items():
        day = func.date(column)
        rows = session.execute(select(day, func.count()).where(column >= since).group_by(day))
        # SQLite devuelve la fecha como texto y PostgreSQL como date.
        counts = {pd.Timestamp(d).date(): n for d, n in rows}
        frame[name] = pd.Series(counts, dtype="float64")
    return frame.fillna(0).astype(int)


@dataclass
class UserDetail:
    user: User
    subjects: list[Subject]
    summary: academics.AcademicSummary
    followers: list[User]
    following: list[User]
    posts: list[Post]
    participations: list[ChallengeParticipant]
    messages_received: int
    messages_sent: int


def user_detail(session: Session, user_id: int) -> UserDetail | None:
    user = session.get(User, user_id)
    if user is None:
        return None
    subjects = academics.list_subjects(session, user_id)
    parts = list(
        session.scalars(
            select(ChallengeParticipant)
            .where(ChallengeParticipant.user_id == user_id)
            .options(selectinload(ChallengeParticipant.challenge))
            .order_by(ChallengeParticipant.joined_at.desc())
        )
    )
    return UserDetail(
        user=user,
        subjects=subjects,
        summary=academics.summarize(subjects, user.current_semester),
        followers=social.followers(session, user_id),
        following=social.following(session, user_id),
        posts=list(
            session.scalars(
                select(Post).where(Post.author_id == user_id).order_by(Post.created_at.desc())
            )
        ),
        participations=parts,
        messages_received=_count(session, SupportMessage, SupportMessage.recipient_id == user_id),
        messages_sent=_count(session, SupportMessage, SupportMessage.sender_id == user_id),
    )


def challenges_frame(session: Session) -> pd.DataFrame:
    rows = []
    for ch in session.scalars(
        select(Challenge).options(
            selectinload(Challenge.participants), selectinload(Challenge.creator)
        )
    ):
        done = [p for p in ch.participants if p.completed_at]
        rows.append(
            {
                "id": ch.id,
                "titulo": ch.title,
                "tipo": ch.kind,
                "creador": ch.creator.username if ch.creator else "—",
                "dificultad": ch.difficulty,
                "puntos": ch.points,
                "visibilidad": ch.visibility,
                "automatico": bool(ch.rule),
                "activo": ch.is_active,
                "participantes": len(ch.participants),
                "completados": len(done),
                "tasa_exito": len(done) / len(ch.participants) if ch.participants else 0.0,
            }
        )
    return pd.DataFrame.from_records(rows)


def set_role(session: Session, actor: User, user_id: int, role: str) -> None:
    """Cambia el rol en la app, que es la fuente de verdad (el rol de Keycloak sólo se usa al
    crear la cuenta local)."""
    _require_admin(actor)
    if role not in {r.value for r in Role}:
        raise AdminError("Rol inválido.")
    if user_id == actor.id:
        raise AdminError("No puedes cambiar tu propio rol.")
    user = session.get(User, user_id)
    if user is None:
        raise AdminError("Usuario no encontrado.")
    user.role = role


def posts_frame(session: Session) -> pd.DataFrame:
    stmt = select(Post).options(selectinload(Post.author), selectinload(Post.comments))
    return pd.DataFrame.from_records(
        [
            {
                "id": p.id,
                "titulo": p.title,
                "autor": p.author.username,
                "categoria": p.category,
                "resuelta": p.is_solved,
                "comentarios": len(p.comments),
                "creada": p.created_at,
            }
            for p in session.scalars(stmt.order_by(Post.created_at.desc()))
        ]
    )


def comments_frame(session: Session) -> pd.DataFrame:
    stmt = select(Comment).options(selectinload(Comment.author), selectinload(Comment.post))
    return pd.DataFrame.from_records(
        [
            {
                "id": c.id,
                "publicacion": c.post.title,
                "autor": c.author.username,
                "comentario": c.body[:200],
                "creado": c.created_at,
            }
            for c in session.scalars(stmt.order_by(Comment.created_at.desc()))
        ]
    )


def messages_frame(session: Session) -> pd.DataFrame:
    stmt = select(SupportMessage).options(
        selectinload(SupportMessage.sender), selectinload(SupportMessage.recipient)
    )
    return pd.DataFrame.from_records(
        [
            {
                "id": m.id,
                "de": m.sender.username,
                "para": m.recipient.username,
                "mensaje": m.message,
                "leido": m.is_read,
                "enviado": m.created_at,
            }
            for m in session.scalars(stmt.order_by(SupportMessage.created_at.desc()))
        ]
    )


def delete_message(session: Session, actor: User, message_id: int) -> None:
    _require_admin(actor)
    message = session.get(SupportMessage, message_id)
    if message is not None:
        session.delete(message)
