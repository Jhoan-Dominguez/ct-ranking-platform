"""Datos de demostración (``make seed-demo``). Es idempotente: si los usuarios ya existen no hace
nada. Todos los usuarios demo usan la contraseña DEMO_PASSWORD.

Los estudiantes cursan Ingeniería de Software (pensum de ``app/data/pensums.py``) y están en
distintos niveles: recién ingresados, iniciando, a mitad de carrera y a punto de terminar. Las
materias de semestres anteriores tienen notas y quedan aprobadas o reprobadas (las reprobadas se
repiten en el semestre siguiente), las del semestre actual están en curso con notas parciales y las
futuras quedan pendientes.
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.data.pensums import SOFTWARE_ENGINEERING
from app.db.models import (
    Challenge,
    ChallengeKind,
    ChallengeParticipant,
    Comment,
    Follow,
    GradeItem,
    Post,
    Subject,
    SubjectStatus,
    SupportMessage,
    User,
    Visibility,
)
from app.db.session import session_scope
from app.services import academics, auth, challenges

DEMO_PASSWORD = "Demo1234"
PENSUM = SOFTWARE_ENGINEERING

# usuario, nombre, apellido, alias, semestre actual, nivel académico (nota media esperada)
STUDENTS = [
    ("diego.lopez", "Diego", "López", "Dieguito", 1, 2.8),  # recién ingresa; arranque difícil
    ("valentina.rios", "Valentina", "Ríos", "Vale", 1, 4.1),
    ("carlos.ruiz", "Carlos", "Ruiz", "Charly", 2, 3.6),  # iniciando
    ("sofia.herrera", "Sofía", "Herrera", "Sofi", 3, 4.3),
    ("laura.gomez", "Laura", "Gómez", "Lau", 5, 3.9),  # mitad de carrera
    ("mateo.castro", "Mateo", "Castro", "Teo", 6, 3.3),  # varias materias repetidas
    ("juan.perez", "Juan", "Pérez", "Juanpe", 8, 3.8),  # a punto de terminar
    ("ana.martinez", "Ana", "Martínez", "Anita", 9, 4.4),
]

TEACHERS = [
    "Dra. Marcela Ortiz", "Ing. Jorge Salazar", "Mg. Paula Andrade", "Ing. Ricardo Mejía",
    "Dr. Felipe Cárdenas", "Mg. Natalia Vélez", "Lic. Andrés Duque", "Ing. Carolina Rojas",
]  # fmt: skip
ITEM_PLANS = [
    [("Parcial 1", 30), ("Parcial 2", 30), ("Examen final", 40)],
    [("Taller 1", 20), ("Parcial", 30), ("Proyecto", 30), ("Quiz", 20)],
    [("Seguimiento", 25), ("Exposición", 25), ("Trabajo final", 50)],
]

POSTS = [
    ("¿Cómo entender la recursión en Programación I?", "Duda académica",
     "Me cuesta entender cómo funciona la pila de llamadas en recursión. ¿Algún recurso?"),
    ("Grupo de estudio para Cálculo Integral", "Proyecto",
     "Busco personas para estudiar los viernes en la biblioteca. ¿Quién se apunta?"),
    ("Problemas con la inscripción de materias", "Problemática",
     "El sistema de inscripción se cae cada vez que intento matricular. ¿Les pasa?"),
    ("Recursos para Fundamentos de Bases de Datos", "Recursos",
     "Comparto una lista de cursos y ejercicios para practicar SQL desde cero."),
    ("¿Dónde hicieron la Práctica Empresarial?", "Vida universitaria",
     "Estoy por empezar octavo semestre y quiero recomendaciones de empresas para la práctica."),
    ("Patrones de diseño para Arquitectura de Software", "Duda académica",
     "¿Qué libro recomiendan para entender bien los patrones antes del parcial?"),
]  # fmt: skip
COMMENTS = [
    "¡Muy buena pregunta! A mí me sirvió dibujar el árbol de llamadas.",
    "Me apunto, avísame la hora.",
    "Totalmente de acuerdo, hay que reportarlo a bienestar.",
    "Gracias por compartir, justo lo que necesitaba.",
    "Te recomiendo los videos del canal de la facultad.",
    "Yo la hice en una empresa de software local y aprendí muchísimo.",
]


def _semester_start(semesters_ago: int) -> date:
    """Fecha aproximada de inicio de un semestre (el actual empezó hace ~2 meses)."""
    return date.today() - timedelta(days=60 + 182 * semesters_ago)


def _grade_subject(
    rng: random.Random, subject: Subject, level: float, start: date, partial: bool
) -> None:
    """Agrega ítems con notas. Si ``partial`` sólo se registran los primeros (semestre en curso)."""
    plan = rng.choice(ITEM_PLANS)
    difficulty = -0.3 if subject.category == "ciencias" else 0.0
    base = rng.gauss(level + difficulty, 0.45)
    if partial:
        plan = plan[: rng.randint(1, len(plan) - 1)]
    for i, (name, weight) in enumerate(plan):
        grade = round(max(0.0, min(5.0, rng.gauss(base, 0.4))), 1)
        subject.items.append(
            GradeItem(
                name=name,
                grade=grade,
                weight=weight,
                description=f"{name} de {subject.name}",
                delivered_on=start + timedelta(days=30 * (i + 1)),
            )
        )


def _build_history(session, rng: random.Random, user: User, level: float) -> None:
    academics.load_pensum(session, user, PENSUM.program)
    current = user.current_semester
    session.flush()
    for subject in academics.list_subjects(session, user.id):
        if subject.semester > current or subject.status != SubjectStatus.PLANNED:
            continue
        subject.teacher = rng.choice(TEACHERS)
        start = _semester_start(current - subject.semester)
        if subject.semester == current:
            subject.status = SubjectStatus.IN_PROGRESS
            _grade_subject(rng, subject, level, start, partial=True)
            continue
        _grade_subject(rng, subject, level, start, partial=False)
        grade = academics.subject_grade(subject.items)
        subject.status = academics.suggested_status(grade) or SubjectStatus.PASSED
        if subject.status == SubjectStatus.FAILED:
            # Se repite en el semestre siguiente (aprobada o en curso si es el actual).
            retake_sem = subject.semester + 1
            retake = Subject(
                user_id=user.id,
                name=subject.name,
                code=subject.code,
                credits=subject.credits,
                category=subject.category,
                semester=retake_sem,
                teacher=rng.choice(TEACHERS),
            )
            session.add(retake)
            in_progress = retake_sem == current
            _grade_subject(
                rng, retake, max(level, 3.6), _semester_start(current - retake_sem), in_progress
            )
            if in_progress:
                retake.status = SubjectStatus.IN_PROGRESS
            else:
                for item in retake.items:
                    item.grade = max(item.grade, 3.0)
                retake.status = SubjectStatus.PASSED


def load_demo(seed: int = 7) -> None:
    rng = random.Random(seed)
    now = datetime.now(UTC)
    with session_scope() as session:
        if session.scalar(select(User).where(User.username == STUDENTS[0][0])):
            print("Los datos demo ya existen; no se cargan de nuevo.")
            return

        users: list[User] = []
        for username, first, last, alias, semester, _level in STUDENTS:
            try:
                user = auth.register(
                    session,
                    username=username,
                    email=f"{username}@demo.edu.co",
                    password=DEMO_PASSWORD,
                    first_name=first,
                    last_name=last,
                    require_verification=False,  # cuentas demo ya activadas
                )
            except auth.AuthError:
                # Ya existe en Keycloak (p. ej. tras `make reset-db`): se vincula al iniciar sesión.
                user = User(
                    username=username,
                    email=f"{username}@demo.edu.co",
                    first_name=first,
                    last_name=last,
                )
                session.add(user)
            user.alias, user.current_semester = alias, semester
            user.university = "Universidad Demo"
            user.city = rng.choice(["Pereira", "Manizales", "Armenia", "Medellín"])
            user.student_code = f"2026{rng.randint(10000, 99999)}"
            user.bio = f"Estudiante de {PENSUM.program} en semestre {semester}."
            user.created_at = now - timedelta(days=182 * (semester - 1) + rng.randint(10, 60))
            user.last_login = now - timedelta(days=rng.randint(0, 12))
            users.append(user)
        session.flush()

        # Historia académica basada en el pensum
        for user, student in zip(users, STUDENTS, strict=True):
            _build_history(session, rng, user, level=student[5])

        # Foro
        posts = []
        for i, (title, category, body) in enumerate(POSTS):
            post = Post(
                author_id=users[i].id,
                title=title,
                body=body,
                category=category,
                created_at=now - timedelta(days=rng.randint(1, 20)),
                is_solved=i == 0,
            )
            session.add(post)
            posts.append(post)
        session.flush()
        for post in posts:
            for commenter in rng.sample(users, k=3):
                if commenter.id != post.author_id:
                    session.add(
                        Comment(
                            post_id=post.id,
                            author_id=commenter.id,
                            body=rng.choice(COMMENTS),
                            created_at=post.created_at + timedelta(hours=rng.randint(1, 48)),
                        )
                    )

        # Red social y mensajes de apoyo
        for user in users:
            for other in rng.sample([u for u in users if u is not user], k=3):
                session.add(Follow(follower_id=user.id, followed_id=other.id))
        for _ in range(10):
            sender, recipient = rng.sample(users, k=2)
            session.add(
                SupportMessage(
                    sender_id=sender.id,
                    recipient_id=recipient.id,
                    message=rng.choice(["¡Vamos, tú puedes! 💪", "No te rindas 🚀", "¡Ánimo! 🤝"]),
                    created_at=now - timedelta(days=rng.randint(0, 10)),
                )
            )

        # Retos de la comunidad
        community = [
            Challenge(
                title="30 días de LeetCode",
                description="Resuelve un ejercicio de programación diario durante 30 días.",
                kind=ChallengeKind.USER,
                creator_id=users[0].id,
                points=40,
                difficulty="dificil",
                ends_at=date.today() + timedelta(days=30),
            ),
            Challenge(
                title="Lee un artículo científico",
                description="Lee y resume un paper de tu área. Comparte el enlace como evidencia.",
                kind=ChallengeKind.USER,
                creator_id=users[2].id,
                points=15,
                difficulty="media",
                visibility=Visibility.FOLLOWERS,
            ),
        ]
        session.add_all(community)
        session.flush()

        global_challenges = list(
            session.scalars(select(Challenge).where(Challenge.kind == ChallengeKind.GLOBAL))
        )
        # Retos globales: se unen y se verifican con las reglas automáticas reales.
        for user in users:
            for challenge in rng.sample(global_challenges, k=min(5, len(global_challenges))):
                session.add(
                    ChallengeParticipant(
                        challenge_id=challenge.id,
                        user_id=user.id,
                        joined_at=now - timedelta(days=rng.randint(3, 15)),
                    )
                )
        session.flush()
        for user in users:
            challenges.refresh_automatic(session, user)

        # Retos de la comunidad: cumplimiento manual con evidencia.
        for challenge in community:
            for user in rng.sample(users, k=4):
                joined = now - timedelta(days=rng.randint(3, 15))
                done = rng.random() < 0.6
                session.add(
                    ChallengeParticipant(
                        challenge_id=challenge.id,
                        user_id=user.id,
                        joined_at=joined,
                        completed_at=joined + timedelta(hours=rng.randint(2, 60)) if done else None,
                        evidence="Completado en la demo" if done else "",
                    )
                )
    print(f"Datos demo cargados. Usuarios: {', '.join(s[0] for s in STUDENTS)} / {DEMO_PASSWORD}")
