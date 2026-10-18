"""Reglas de verificación automática para retos.

Cada regla mide el progreso del usuario sobre toda su historia, así los retos globales son
iguales para usuarios antiguos y nuevos: quien ya cumplía la condición la completa al unirse.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    Challenge,
    Comment,
    Follow,
    GradeItem,
    Post,
    Subject,
    SubjectStatus,
    SupportMessage,
    User,
)


@dataclass(frozen=True)
class Rule:
    label: str
    target: float
    measure: Callable[[Session, int], float]
    unit: str = ""


def _count(session: Session, stmt) -> float:
    return float(session.scalar(stmt) or 0)


def _general_average(session: Session, user_id: int) -> float:
    from app.services.academics import general_average, list_subjects

    return general_average(list_subjects(session, user_id)) or 0.0


def _rules() -> dict[str, Rule]:
    grade_max = get_settings().grade_max
    return {
        "first_post": Rule(
            "Publica tu primera discusión en el foro",
            1,
            lambda s, u: _count(s, select(func.count(Post.id)).where(Post.author_id == u)),
            "publicaciones",
        ),
        "forum_helper": Rule(
            "Responde 5 publicaciones de otros estudiantes",
            5,
            lambda s, u: _count(
                s,
                select(func.count(Comment.id))
                .join(Post, Post.id == Comment.post_id)
                .where(Comment.author_id == u, Post.author_id != u),
            ),
            "comentarios",
        ),
        "grades_10": Rule(
            "Registra 10 notas en tus materias",
            10,
            lambda s, u: _count(
                s,
                select(func.count(GradeItem.id))
                .join(Subject, Subject.id == GradeItem.subject_id)
                .where(Subject.user_id == u),
            ),
            "notas",
        ),
        "plan_5": Rule(
            "Arma tu plan de estudios con al menos 5 materias",
            5,
            lambda s, u: _count(s, select(func.count(Subject.id)).where(Subject.user_id == u)),
            "materias",
        ),
        "first_pass": Rule(
            "Aprueba tu primera materia registrada",
            1,
            lambda s, u: _count(
                s,
                select(func.count(Subject.id)).where(
                    Subject.user_id == u, Subject.status == SubjectStatus.PASSED
                ),
            ),
            "materias",
        ),
        "high_average": Rule(
            f"Alcanza un promedio general de {grade_max * 0.8:g}",
            grade_max * 0.8,
            _general_average,
            "promedio",
        ),
        "social_3": Rule(
            "Sigue a 3 compañeros",
            3,
            lambda s, u: _count(
                s, select(func.count()).select_from(Follow).where(Follow.follower_id == u)
            ),
            "seguidos",
        ),
        "supporter_5": Rule(
            "Envía 5 mensajes de apoyo",
            5,
            lambda s, u: _count(
                s, select(func.count(SupportMessage.id)).where(SupportMessage.sender_id == u)
            ),
            "mensajes",
        ),
        "creator": Rule(
            "Crea tu propio reto para la comunidad",
            1,
            lambda s, u: _count(
                s, select(func.count(Challenge.id)).where(Challenge.creator_id == u)
            ),
            "retos",
        ),
        "profile_complete": Rule(
            "Completa tu perfil (alias, foto, programa y biografía)",
            4,
            lambda s, u: _profile_fields(s, u),
            "campos",
        ),
    }


def _profile_fields(session: Session, user_id: int) -> float:
    user = session.get(User, user_id)
    if user is None:
        return 0
    return float(sum(bool(v) for v in (user.alias, user.avatar, user.program, user.bio)))


RULES: dict[str, Rule] = _rules()


def progress(session: Session, rule_code: str, user_id: int) -> tuple[float, float]:
    """(valor actual, meta)."""
    rule = RULES[rule_code]
    return rule.measure(session, user_id), rule.target


def is_satisfied(session: Session, rule_code: str, user_id: int) -> bool:
    current, target = progress(session, rule_code, user_id)
    return current >= target
