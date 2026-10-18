"""Datos base de la plataforma: usuario administrador y retos globales. Idempotente."""

from __future__ import annotations

from sqlalchemy import select

from app import auth
from app.core.config import get_settings
from app.database.models import Challenge, ChallengeKind, Difficulty, Role, User
from app.database.session import session_scope

GLOBAL_CHALLENGES = [
    ("Rompe el hielo", "Publica tu primera discusión en el foro.", "first_post", "facil", 10),
    ("Arquitecto de tu carrera", "Registra al menos 5 materias en tu plan.", "plan_5", "facil", 10),
    (
        "Perfil al 100%",
        "Completa alias, foto, programa y biografía.",
        "profile_complete",
        "facil",
        10,
    ),
    ("Red de apoyo", "Sigue a 3 compañeros de la plataforma.", "social_3", "facil", 15),
    (
        "Mentor del foro",
        "Responde 5 publicaciones de otros estudiantes.",
        "forum_helper",
        "media",
        25,
    ),
    (
        "Bitácora de notas",
        "Registra 10 notas de trabajos, tareas o parciales.",
        "grades_10",
        "media",
        20,
    ),
    ("Porrista", "Envía 5 mensajes de apoyo a tus compañeros.", "supporter_5", "facil", 15),
    ("Creador de retos", "Crea tu propio reto para la comunidad.", "creator", "media", 20),
    ("Primera victoria", "Marca como aprobada tu primera materia.", "first_pass", "media", 25),
    (
        "Excelencia académica",
        "Alcanza un promedio general del 80% de la escala.",
        "high_average",
        "dificil",
        50,
    ),
]


def seed_base() -> None:
    settings = get_settings()
    with session_scope() as session:
        admin = session.scalar(select(User).where(User.username == settings.admin_username))
        if admin is None:
            admin = User(
                username=settings.admin_username,
                email=settings.admin_email,
                first_name="Administrador",
                last_name="CT",
                role=Role.ADMIN,
            )
            session.add(admin)
        admin.role = Role.ADMIN
        # Con Keycloak la contraseña vive allí; el hash local sólo se usa con AUTH_PROVIDER=local.
        if settings.auth_provider == "local" and not admin.password_hash:
            admin.password_hash = auth.hash_password(settings.admin_password)
        session.flush()

        existing = set(
            session.scalars(select(Challenge.rule).where(Challenge.kind == ChallengeKind.GLOBAL))
        )
        for title, description, rule, difficulty, points in GLOBAL_CHALLENGES:
            if rule in existing:
                continue
            session.add(
                Challenge(
                    title=title,
                    description=description,
                    rule=rule,
                    difficulty=Difficulty(difficulty),
                    points=points,
                    kind=ChallengeKind.GLOBAL,
                    creator_id=admin.id,
                )
            )
