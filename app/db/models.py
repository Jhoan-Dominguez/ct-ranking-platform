"""Modelos ORM de la plataforma (SQLAlchemy 2.0)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Role(StrEnum):
    STUDENT = "student"
    ADMIN = "admin"


class SubjectStatus(StrEnum):
    PLANNED = "pendiente"
    IN_PROGRESS = "cursando"
    PASSED = "aprobada"
    FAILED = "reprobada"


class SubjectCategory(StrEnum):
    SCIENCES = "ciencias"
    HUMANITIES = "humanidades"
    TECHNOLOGY = "tecnologia"
    LANGUAGES = "idiomas"


class ReportReason(StrEnum):
    SPAM = "spam"
    HARASSMENT = "acoso"
    INAPPROPRIATE = "contenido_inapropiado"
    IMPERSONATION = "suplantacion"
    OTHER = "otro"


class ReportStatus(StrEnum):
    PENDING = "pendiente"
    RESOLVED = "resuelto"
    DISMISSED = "descartado"


class ChallengeKind(StrEnum):
    GLOBAL = "global"
    USER = "usuario"


class Visibility(StrEnum):
    PUBLIC = "publico"
    FOLLOWERS = "seguidores"


class Difficulty(StrEnum):
    EASY = "facil"
    MEDIUM = "media"
    HARD = "dificil"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Sólo se usa con AUTH_PROVIDER=local; con Keycloak la contraseña vive en Keycloak.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    keycloak_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(20), default=Role.STUDENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Con Keycloak la cuenta se activa con el enlace del correo de verificación.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    # Eliminación diferida: la cuenta queda oculta y se borra en deletion_scheduled_for.
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    first_name: Mapped[str] = mapped_column(String(80), default="")
    last_name: Mapped[str] = mapped_column(String(80), default="")
    alias: Mapped[str] = mapped_column(String(50), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)
    avatar_mime: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(30), default="")
    birth_date: Mapped[date | None] = mapped_column(Date)
    city: Mapped[str] = mapped_column(String(100), default="")
    university: Mapped[str] = mapped_column(String(150), default="")
    student_code: Mapped[str] = mapped_column(String(30), default="")
    interests: Mapped[str] = mapped_column(String(300), default="")
    github_url: Mapped[str] = mapped_column(String(255), default="")
    linkedin_url: Mapped[str] = mapped_column(String(255), default="")

    # Plan de estudios
    program: Mapped[str] = mapped_column(String(150), default="")
    study_plan: Mapped[str] = mapped_column(String(150), default="")
    current_semester: Mapped[int] = mapped_column(Integer, default=1)
    total_semesters: Mapped[int] = mapped_column(Integer, default=10)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subjects: Mapped[list[Subject]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self) -> str:
        return self.alias or self.full_name or self.username

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def pending_deletion(self) -> bool:
        return self.deletion_scheduled_for is not None


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str] = mapped_column(String(30), default="")
    credits: Mapped[int] = mapped_column(Integer, default=3)
    semester: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default=SubjectStatus.IN_PROGRESS)
    category: Mapped[str] = mapped_column(String(20), default=SubjectCategory.TECHNOLOGY)
    teacher: Mapped[str] = mapped_column(String(150), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="subjects")
    items: Mapped[list[GradeItem]] = relationship(
        back_populates="subject", cascade="all, delete-orphan", order_by="GradeItem.id"
    )


class GradeItem(Base):
    __tablename__ = "grade_items"
    __table_args__ = (
        CheckConstraint("weight IS NULL OR (weight >= 0 AND weight <= 100)", name="ck_item_weight"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default="")
    grade: Mapped[float] = mapped_column(Float)
    # Porcentaje opcional sobre la nota final (0-100). Si ningún ítem lo define se usa promedio
    # simple.
    weight: Mapped[float | None] = mapped_column(Float)
    delivered_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subject: Mapped[Subject] = relationship(back_populates="items")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), default="General")
    tags: Mapped[str] = mapped_column(String(200), default="")
    is_solved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    author: Mapped[User] = relationship()
    comments: Mapped[list[Comment]] = relationship(
        back_populates="post", cascade="all, delete-orphan", order_by="Comment.created_at"
    )
    likes: Mapped[list[PostLike]] = relationship(cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    post: Mapped[Post] = relationship(back_populates="comments")
    author: Mapped[User] = relationship()


class PostLike(Base):
    __tablename__ = "post_likes"

    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default=ChallengeKind.USER)
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    difficulty: Mapped[str] = mapped_column(String(20), default=Difficulty.MEDIUM)
    points: Mapped[int] = mapped_column(Integer, default=10)
    visibility: Mapped[str] = mapped_column(String(20), default=Visibility.PUBLIC)
    # Código de regla automática (ver app/services/challenge_rules.py). None = verificación manual.
    rule: Mapped[str | None] = mapped_column(String(50))
    starts_at: Mapped[date | None] = mapped_column(Date)
    ends_at: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    creator: Mapped[User | None] = relationship()
    participants: Mapped[list[ChallengeParticipant]] = relationship(
        back_populates="challenge", cascade="all, delete-orphan"
    )


class ChallengeParticipant(Base):
    __tablename__ = "challenge_participants"
    __table_args__ = (UniqueConstraint("challenge_id", "user_id", name="uq_participant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[str] = mapped_column(Text, default="")

    challenge: Mapped[Challenge] = relationship(back_populates="participants")
    user: Mapped[User] = relationship()


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (CheckConstraint("follower_id <> followed_id", name="ck_no_self_follow"),)

    follower_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    followed_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    message: Mapped[str] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sender: Mapped[User] = relationship(foreign_keys=[sender_id])
    recipient: Mapped[User] = relationship(foreign_keys=[recipient_id])


class VerificationCode(Base):
    """Código de un solo uso enviado por correo (p. ej. para confirmar la eliminación)."""

    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(30))
    code_hash: Mapped[str] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserBlock(Base):
    __tablename__ = "user_blocks"
    __table_args__ = (CheckConstraint("blocker_id <> blocked_id", name="ck_no_self_block"),)

    blocker_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    blocked_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    blocked: Mapped[User] = relationship(foreign_keys=[blocked_id])


class UserReport(Base):
    __tablename__ = "user_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reported_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text, default="")
    # Contenido concreto reportado (opcional). Si se elimina, el reporte se conserva.
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL"))
    comment_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default=ReportStatus.PENDING, index=True)
    admin_note: Mapped[str] = mapped_column(Text, default="")
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reporter: Mapped[User] = relationship(foreign_keys=[reporter_id])
    reported: Mapped[User] = relationship(foreign_keys=[reported_id])
    resolved_by: Mapped[User | None] = relationship(foreign_keys=[resolved_by_id])
    post: Mapped[Post | None] = relationship()
    comment: Mapped[Comment | None] = relationship()
