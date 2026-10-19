"""Retos dinámicos: globales (iguales para todos) y creados por estudiantes, con ranking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import Select, case, func, or_, select, true
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

# +50% de los puntos (redondeado hacia arriba) para quien completa primero. Se calcula en SQL
# con aritmética entera: ceil(p * NUM / DEN) = (p * NUM + DEN - 1) // DEN.
FIRST_FINISHER_BONUS = (1, 2)
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
    # Conteos en SQL en lugar de cargar todas las participaciones de cada reto.
    n_participants = (
        select(func.count(ChallengeParticipant.id))
        .where(ChallengeParticipant.challenge_id == Challenge.id)
        .scalar_subquery()
    )
    n_completed = (
        select(func.count(ChallengeParticipant.id))
        .where(
            ChallengeParticipant.challenge_id == Challenge.id,
            ChallengeParticipant.completed_at.is_not(None),
        )
        .scalar_subquery()
    )
    stmt = (
        select(Challenge, n_participants, n_completed)
        .where(_visibility_filter(user))
        .options(selectinload(Challenge.creator))
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
    mine = {
        p.challenge_id: p
        for p in session.scalars(
            select(ChallengeParticipant).where(ChallengeParticipant.user_id == user.id)
        )
    }
    rows = []
    for ch, participants, completed in session.execute(stmt):
        if only_open and not _is_open(ch):
            continue
        rows.append(
            ChallengeRow(
                challenge=ch,
                participants=participants,
                completed=completed,
                my_participation=mine.get(ch.id),
            )
        )
    return rows


def get_challenge(session: Session, challenge_id: int) -> Challenge | None:
    return session.get(Challenge, challenge_id)


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


def stats(
    session: Session, challenge_id: int, entries: list[RankingEntry] | None = None
) -> ChallengeStats:
    """Métricas del reto. Acepta el resultado de ``ranking`` para no repetir la consulta."""
    entries = ranking(session, challenge_id) if entries is None else entries
    completed = [e for e in entries if e.completed_at]
    return ChallengeStats(
        participants=len(entries),
        completed=len(completed),
        first=completed[0] if completed else None,
    )


def _scores_query() -> Select:
    """Puntaje por usuario calculado en SQL: suma de puntos de retos completados más el bono de
    quien terminó primero cada reto (``ROW_NUMBER`` por reto ordenado por fecha).

    Las cuentas con eliminación programada no cuentan, ni siquiera para decidir quién fue
    primero: así su salida no le quita el bono al primer usuario activo."""
    num, den = FIRST_FINISHER_BONUS
    ranked = (
        select(
            ChallengeParticipant.user_id,
            Challenge.points,
            func.row_number()
            .over(
                partition_by=ChallengeParticipant.challenge_id,
                order_by=(ChallengeParticipant.completed_at, ChallengeParticipant.id),
            )
            .label("place"),
        )
        .join(Challenge, Challenge.id == ChallengeParticipant.challenge_id)
        .join(User, User.id == ChallengeParticipant.user_id)
        .where(
            ChallengeParticipant.completed_at.is_not(None),
            User.deletion_scheduled_for.is_(None),
        )
        .subquery()
    )
    is_first = ranked.c.place == 1
    bonus = case((is_first, (ranked.c.points * num + den - 1) // den), else_=0)
    return select(
        ranked.c.user_id,
        (func.sum(ranked.c.points) + func.sum(bonus)).label("score"),
        func.count().label("completed"),
        func.sum(case((is_first, 1), else_=0)).label("firsts"),
    ).group_by(ranked.c.user_id)


def leaderboard(
    session: Session,
    *,
    limit: int = 10,
    user_ids: set[int] | None = None,
    exclude_ids: set[int] | None = None,
) -> list[LeaderboardEntry]:
    """Puntos totales: suma de puntos de retos completados + bonus por llegar primero.

    ``user_ids`` y ``exclude_ids`` sólo filtran a quién se muestra: el primero de cada reto se
    decide entre todas las cuentas activas."""
    scores = _scores_query().subquery()
    stmt = (
        select(User, scores.c.score, scores.c.completed, scores.c.firsts)
        .join(scores, scores.c.user_id == User.id)
        .order_by(scores.c.score.desc(), scores.c.firsts.desc(), User.username)
        .limit(limit)
    )
    if user_ids is not None:
        stmt = stmt.where(User.id.in_(user_ids))
    if exclude_ids:
        stmt = stmt.where(User.id.not_in(exclude_ids))
    return [
        LeaderboardEntry(user, int(score), int(completed), int(firsts))
        for user, score, completed, firsts in session.execute(stmt)
    ]


def scores_by_user(session: Session) -> dict[int, int]:
    """Puntaje de cada usuario con retos completados (para tablas como la del panel)."""
    scores = _scores_query().subquery()
    rows = session.execute(select(scores.c.user_id, scores.c.score))
    return {user_id: int(score) for user_id, score in rows}


@dataclass
class Standing:
    score: int
    completed: int
    position: int | None


def standing(session: Session, user_id: int) -> Standing:
    """Puntaje y posición de un usuario en el ranking general, sin cargar todo el ranking."""
    scores = _scores_query().subquery()
    ranked = select(
        scores.c.user_id,
        scores.c.score,
        scores.c.completed,
        func.row_number()
        .over(order_by=(scores.c.score.desc(), scores.c.firsts.desc(), User.username))
        .label("position"),
    ).join(User, User.id == scores.c.user_id)
    positions = ranked.subquery()
    row = session.execute(select(positions).where(positions.c.user_id == user_id)).first()
    if row is None:
        return Standing(0, 0, None)
    return Standing(int(row.score), int(row.completed), int(row.position))


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
