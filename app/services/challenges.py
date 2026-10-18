"""Retos dinámicos: globales (iguales para todos) y creados por estudiantes, con ranking."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session, selectinload

from app.database.models import (
    Challenge,
    ChallengeKind,
    ChallengeParticipant,
    Difficulty,
    Follow,
    User,
    Visibility,
)
from app.services import challenge_rules

FIRST_FINISHER_BONUS = 0.5  # +50% de los puntos para quien completa primero
SCOPES = {
    "Todos": "all",
    "Globales": "global",
    "Comunidad": "community",
    "De quienes sigo": "following",
    "Creados por mí": "mine",
    "En los que participo": "joined",
}


class ChallengeError(ValueError):
    pass


@dataclass
class ChallengeRow:
    challenge: Challenge
    participants: int
    completed: int
    my_participation: ChallengeParticipant | None

    @property
    def joined(self) -> bool:
        return self.my_participation is not None

    @property
    def done(self) -> bool:
        return bool(self.my_participation and self.my_participation.completed_at)


@dataclass
class RankingEntry:
    position: int | None
    user: User
    joined_at: datetime
    completed_at: datetime | None
    evidence: str


@dataclass
class ChallengeStats:
    participants: int
    completed: int
    first: RankingEntry | None

    @property
    def completion_rate(self) -> float:
        return self.completed / self.participants if self.participants else 0.0


@dataclass
class LeaderboardEntry:
    user: User
    score: int
    completed: int
    firsts: int


def _now() -> datetime:
    return datetime.now(UTC)


def _is_open(challenge: Challenge, today: date | None = None) -> bool:
    today = today or date.today()
    if not challenge.is_active:
        return False
    if challenge.starts_at and today < challenge.starts_at:
        return False
    return not (challenge.ends_at and today > challenge.ends_at)


def is_open(challenge: Challenge) -> bool:
    return _is_open(challenge)


def _visibility_filter(user: User):
    if user.is_admin:
        return true()
    follows_creator = (
        select(Follow.followed_id).where(Follow.follower_id == user.id).scalar_subquery()
    )
    return or_(
        Challenge.kind == ChallengeKind.GLOBAL,
        Challenge.visibility == Visibility.PUBLIC,
        Challenge.creator_id == user.id,
        Challenge.creator_id.in_(follows_creator),
    )


def _get_visible(session: Session, user: User, challenge_id: int) -> Challenge:
    challenge = session.scalar(
        select(Challenge).where(Challenge.id == challenge_id, _visibility_filter(user))
    )
    if challenge is None:
        raise ChallengeError("Reto no encontrado o no disponible para ti.")
    return challenge


def create_challenge(
    session: Session,
    creator: User,
    *,
    title: str,
    description: str,
    difficulty: str = Difficulty.MEDIUM,
    points: int = 10,
    visibility: str = Visibility.PUBLIC,
    starts_at: date | None = None,
    ends_at: date | None = None,
    kind: str = ChallengeKind.USER,
    rule: str | None = None,
) -> Challenge:
    title, description = title.strip(), description.strip()
    if len(title) < 5:
        raise ChallengeError("El título debe tener al menos 5 caracteres.")
    if not description:
        raise ChallengeError("Describe en qué consiste el reto.")
    if difficulty not in {d.value for d in Difficulty}:
        raise ChallengeError("Dificultad inválida.")
    if visibility not in {v.value for v in Visibility}:
        raise ChallengeError("Visibilidad inválida.")
    if not 1 <= points <= 100:
        raise ChallengeError("Los puntos deben estar entre 1 y 100.")
    if starts_at and ends_at and ends_at < starts_at:
        raise ChallengeError("La fecha de cierre debe ser posterior a la de inicio.")
    if kind == ChallengeKind.GLOBAL and not creator.is_admin:
        raise ChallengeError("Sólo un administrador puede crear retos globales.")
    if rule is not None and rule not in challenge_rules.RULES:
        raise ChallengeError("Regla automática desconocida.")
    challenge = Challenge(
        title=title,
        description=description,
        difficulty=difficulty,
        points=points,
        visibility=Visibility.PUBLIC if kind == ChallengeKind.GLOBAL else visibility,
        starts_at=starts_at,
        ends_at=ends_at,
        kind=kind,
        rule=rule,
        creator_id=creator.id,
    )
    session.add(challenge)
    session.flush()
    return challenge


def list_challenges(
    session: Session,
    user: User,
    *,
    scope: str = "all",
    only_open: bool = False,
    hidden_creator_ids: set[int] | None = None,
) -> list[ChallengeRow]:
    stmt = (
        select(Challenge)
        .where(_visibility_filter(user))
        .options(selectinload(Challenge.participants), selectinload(Challenge.creator))
        .order_by(Challenge.kind, Challenge.created_at.desc())
    )
    if scope == "global":
        stmt = stmt.where(Challenge.kind == ChallengeKind.GLOBAL)
    elif scope == "community":
        stmt = stmt.where(Challenge.kind == ChallengeKind.USER)
    elif scope == "following":
        followed = select(Follow.followed_id).where(Follow.follower_id == user.id)
        stmt = stmt.where(Challenge.creator_id.in_(followed), Challenge.kind == ChallengeKind.USER)
    elif scope == "mine":
        stmt = stmt.where(Challenge.creator_id == user.id)
    if hidden_creator_ids:
        stmt = stmt.where(
            or_(Challenge.creator_id.is_(None), Challenge.creator_id.not_in(hidden_creator_ids))
        )
    if scope == "joined":
        joined = select(ChallengeParticipant.challenge_id).where(
            ChallengeParticipant.user_id == user.id
        )
        stmt = stmt.where(Challenge.id.in_(joined))
    rows = []
    for ch in session.scalars(stmt):
        if only_open and not _is_open(ch):
            continue
        mine = next((p for p in ch.participants if p.user_id == user.id), None)
        rows.append(
            ChallengeRow(
                challenge=ch,
                participants=len(ch.participants),
                completed=sum(1 for p in ch.participants if p.completed_at),
                my_participation=mine,
            )
        )
    return rows


def _participation(session: Session, user_id: int, challenge_id: int) -> ChallengeParticipant:
    part = session.scalar(
        select(ChallengeParticipant).where(
            ChallengeParticipant.user_id == user_id,
            ChallengeParticipant.challenge_id == challenge_id,
        )
    )
    if part is None:
        raise ChallengeError("Primero debes unirte al reto.")
    return part


def join(session: Session, user: User, challenge_id: int) -> ChallengeParticipant:
    challenge = _get_visible(session, user, challenge_id)
    if not _is_open(challenge):
        raise ChallengeError("El reto no está abierto.")
    existing = session.scalar(
        select(ChallengeParticipant).where(
            ChallengeParticipant.user_id == user.id,
            ChallengeParticipant.challenge_id == challenge_id,
        )
    )
    if existing is not None:
        return existing
    part = ChallengeParticipant(challenge_id=challenge_id, user_id=user.id)
    session.add(part)
    session.flush()
    if challenge.rule and challenge_rules.is_satisfied(session, challenge.rule, user.id):
        part.completed_at = _now()
        part.evidence = "Verificado automáticamente"
    return part


def leave(session: Session, user: User, challenge_id: int) -> None:
    part = _participation(session, user.id, challenge_id)
    if part.completed_at:
        raise ChallengeError("No puedes abandonar un reto que ya completaste.")
    session.delete(part)


def complete(session: Session, user: User, challenge_id: int, evidence: str = "") -> None:
    challenge = _get_visible(session, user, challenge_id)
    part = _participation(session, user.id, challenge_id)
    if part.completed_at:
        raise ChallengeError("Ya completaste este reto.")
    if not _is_open(challenge):
        raise ChallengeError("El reto ya no está abierto.")
    if challenge.rule:
        current, target = challenge_rules.progress(session, challenge.rule, user.id)
        if current < target:
            raise ChallengeError(f"Aún no cumples la meta: {current:g} de {target:g}.")
        evidence = evidence.strip() or "Verificado automáticamente"
    elif not evidence.strip():
        raise ChallengeError("Describe o enlaza la evidencia de que completaste el reto.")
    part.completed_at = _now()
    part.evidence = evidence.strip()


def refresh_automatic(session: Session, user: User) -> list[str]:
    """Completa los retos automáticos en los que el usuario participa y ya cumple.
    Devuelve los títulos recién completados."""
    stmt = (
        select(ChallengeParticipant)
        .join(Challenge)
        .where(
            ChallengeParticipant.user_id == user.id,
            ChallengeParticipant.completed_at.is_(None),
            Challenge.rule.is_not(None),
        )
        .options(selectinload(ChallengeParticipant.challenge))
    )
    done = []
    for part in session.scalars(stmt):
        ch = part.challenge
        if _is_open(ch) and challenge_rules.is_satisfied(session, ch.rule, user.id):  # type: ignore[arg-type]
            part.completed_at = _now()
            part.evidence = "Verificado automáticamente"
            done.append(ch.title)
    return done


def ranking(session: Session, challenge_id: int) -> list[RankingEntry]:
    """Primero quienes completaron (por fecha de cumplimiento), luego los pendientes."""
    parts = list(
        session.scalars(
            select(ChallengeParticipant)
            .where(ChallengeParticipant.challenge_id == challenge_id)
            .options(selectinload(ChallengeParticipant.user))
        )
    )
    completed = sorted((p for p in parts if p.completed_at), key=lambda p: p.completed_at)  # type: ignore[arg-type, return-value]
    pending = sorted((p for p in parts if not p.completed_at), key=lambda p: p.joined_at)
    entries = [
        RankingEntry(i, p.user, p.joined_at, p.completed_at, p.evidence)
        for i, p in enumerate(completed, start=1)
    ]
    entries += [RankingEntry(None, p.user, p.joined_at, None, "") for p in pending]
    return entries


def stats(session: Session, challenge_id: int) -> ChallengeStats:
    entries = ranking(session, challenge_id)
    completed = [e for e in entries if e.completed_at]
    return ChallengeStats(
        participants=len(entries),
        completed=len(completed),
        first=completed[0] if completed else None,
    )


def leaderboard(
    session: Session,
    *,
    limit: int = 10,
    user_ids: set[int] | None = None,
    exclude_ids: set[int] | None = None,
) -> list[LeaderboardEntry]:
    """Puntos totales: suma de puntos de retos completados + bonus por llegar primero."""
    rows = session.execute(
        select(ChallengeParticipant, Challenge)
        .join(Challenge)
        .where(ChallengeParticipant.completed_at.is_not(None))
        .options(selectinload(ChallengeParticipant.user))
    ).all()
    first_by_challenge: dict[int, ChallengeParticipant] = {}
    for part, _ in rows:
        current = first_by_challenge.get(part.challenge_id)
        if current is None or part.completed_at < current.completed_at:  # type: ignore[operator]
            first_by_challenge[part.challenge_id] = part

    score: dict[int, int] = defaultdict(int)
    completed: dict[int, int] = defaultdict(int)
    firsts: dict[int, int] = defaultdict(int)
    users: dict[int, User] = {}
    for part, ch in rows:
        if user_ids is not None and part.user_id not in user_ids:
            continue
        if exclude_ids and part.user_id in exclude_ids:
            continue
        users[part.user_id] = part.user
        score[part.user_id] += ch.points
        completed[part.user_id] += 1
        if first_by_challenge[ch.id] is part:
            score[part.user_id] += math.ceil(ch.points * FIRST_FINISHER_BONUS)
            firsts[part.user_id] += 1
    ordered = sorted(users, key=lambda uid: (-score[uid], -firsts[uid], users[uid].username))
    return [
        LeaderboardEntry(users[uid], score[uid], completed[uid], firsts[uid])
        for uid in ordered[:limit]
    ]


def set_active(session: Session, actor: User, challenge_id: int, active: bool) -> None:
    challenge = session.get(Challenge, challenge_id)
    if challenge is None:
        raise ChallengeError("Reto no encontrado.")
    if not (actor.is_admin or challenge.creator_id == actor.id):
        raise ChallengeError("Sólo el creador o un administrador puede modificar el reto.")
    challenge.is_active = active


def delete_challenge(session: Session, actor: User, challenge_id: int) -> None:
    challenge = session.get(Challenge, challenge_id)
    if challenge is None:
        return
    if not (actor.is_admin or challenge.creator_id == actor.id):
        raise ChallengeError("Sólo el creador o un administrador puede eliminar el reto.")
    session.delete(challenge)


@dataclass
class ActivityEntry:
    user: User
    challenge_title: str
    completed_at: datetime


def following_activity(session: Session, user: User, limit: int = 15) -> list[ActivityEntry]:
    """Últimos retos completados por las personas que sigo (para animarlas)."""
    followed = select(Follow.followed_id).where(Follow.follower_id == user.id)
    parts = session.scalars(
        select(ChallengeParticipant)
        .where(
            ChallengeParticipant.user_id.in_(followed),
            ChallengeParticipant.completed_at.is_not(None),
        )
        .options(
            selectinload(ChallengeParticipant.user), selectinload(ChallengeParticipant.challenge)
        )
        .order_by(ChallengeParticipant.completed_at.desc())
        .limit(limit)
    )
    return [ActivityEntry(p.user, p.challenge.title, p.completed_at) for p in parts]  # type: ignore[arg-type]


def completed_by(session: Session, user_id: int) -> list[ChallengeParticipant]:
    return list(
        session.scalars(
            select(ChallengeParticipant)
            .where(
                ChallengeParticipant.user_id == user_id,
                ChallengeParticipant.completed_at.is_not(None),
            )
            .options(selectinload(ChallengeParticipant.challenge))
            .order_by(ChallengeParticipant.completed_at.desc())
        )
    )
