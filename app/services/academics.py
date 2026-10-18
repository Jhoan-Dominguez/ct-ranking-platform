"""Plan de estudios, historia académica, ítems calificables y cálculo de promedios.

Reglas de cálculo:
- Nota de una materia: si todos sus ítems tienen porcentaje (> 0) se usa el promedio ponderado
  normalizado por la suma de porcentajes registrados ("nota acumulada"). En otro caso se usa el
  promedio simple de los ítems.
- Promedio de un semestre: promedio ponderado por créditos de las materias de ese semestre que
  ya tienen nota.
- Promedio general (acumulado): promedio ponderado por créditos de todas las materias vistas
  (cursando, aprobadas o reprobadas) que tienen nota.
- Avance de créditos: créditos aprobados y en curso frente al total del plan registrado, por
  categoría. Una materia repetida (misma clave código/nombre) cuenta una sola vez en el total.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.data.pensums import PENSUMS
from app.db.models import GradeItem, Subject, SubjectCategory, SubjectStatus, User

SEEN_STATUSES = {SubjectStatus.IN_PROGRESS, SubjectStatus.PASSED, SubjectStatus.FAILED}


class AcademicError(ValueError):
    pass


# --------------------------------------------------------------------------- cálculos puros


def subject_grade(items: Iterable[GradeItem]) -> float | None:
    items = list(items)
    if not items:
        return None
    if all(i.weight and i.weight > 0 for i in items):
        total_weight = sum(i.weight for i in items)  # type: ignore[misc]
        return sum(i.grade * i.weight for i in items) / total_weight  # type: ignore[operator]
    return sum(i.grade for i in items) / len(items)


def weighted_progress(items: Iterable[GradeItem]) -> float:
    """Porcentaje de la nota final ya evaluado (suma de pesos registrados, máx. 100)."""
    return min(100.0, sum(i.weight or 0 for i in items))


def credit_weighted_average(pairs: Iterable[tuple[float | None, int]]) -> float | None:
    """Promedio ponderado por créditos ignorando materias sin nota. Créditos <= 0 cuentan como 1."""
    graded = [(g, c if c and c > 0 else 1) for g, c in pairs if g is not None]
    if not graded:
        return None
    return sum(g * c for g, c in graded) / sum(c for _, c in graded)


def semester_average(subjects: Sequence[Subject], semester: int) -> float | None:
    return credit_weighted_average(
        (subject_grade(s.items), s.credits)
        for s in subjects
        if s.semester == semester and s.status in SEEN_STATUSES
    )


def general_average(subjects: Sequence[Subject]) -> float | None:
    return credit_weighted_average(
        (subject_grade(s.items), s.credits) for s in subjects if s.status in SEEN_STATUSES
    )


@dataclass
class SemesterSummary:
    semester: int
    average: float | None
    subjects: int
    credits: int


@dataclass
class AcademicSummary:
    general_average: float | None
    current_semester_average: float | None
    semesters: list[SemesterSummary]
    passed_credits: int
    in_progress: int
    passed: int
    failed: int
    planned: int


def summarize(subjects: Sequence[Subject], current_semester: int) -> AcademicSummary:
    semesters = sorted({s.semester for s in subjects})
    by_status = dict.fromkeys(SubjectStatus, 0)
    for s in subjects:
        by_status[SubjectStatus(s.status)] += 1
    return AcademicSummary(
        general_average=general_average(subjects),
        current_semester_average=semester_average(subjects, current_semester),
        semesters=[
            SemesterSummary(
                semester=n,
                average=semester_average(subjects, n),
                subjects=sum(1 for s in subjects if s.semester == n),
                credits=sum(s.credits for s in subjects if s.semester == n),
            )
            for n in semesters
        ],
        passed_credits=sum(s.credits for s in subjects if s.status == SubjectStatus.PASSED),
        in_progress=by_status[SubjectStatus.IN_PROGRESS],
        passed=by_status[SubjectStatus.PASSED],
        failed=by_status[SubjectStatus.FAILED],
        planned=by_status[SubjectStatus.PLANNED],
    )


@dataclass
class CreditProgress:
    category: str  # valor de SubjectCategory o "total"
    total: int
    passed: int
    in_progress: int

    @property
    def passed_pct(self) -> float:
        return 100 * self.passed / self.total if self.total else 0.0

    @property
    def in_progress_pct(self) -> float:
        return 100 * self.in_progress / self.total if self.total else 0.0


def _subject_key(subject: Subject) -> str:
    return (subject.code or subject.name).strip().lower()


def credit_progress(subjects: Sequence[Subject]) -> list[CreditProgress]:
    """Créditos aprobados / en curso / totales del plan por categoría, más una fila "total".

    Si una materia aparece varias veces (p. ej. reprobada y luego repetida) se toma su mejor
    estado: aprobada > cursando > reprobada/pendiente.
    """
    rank = {
        SubjectStatus.PASSED: 3,
        SubjectStatus.IN_PROGRESS: 2,
        SubjectStatus.FAILED: 1,
        SubjectStatus.PLANNED: 0,
    }
    best: dict[str, Subject] = {}
    for s in subjects:
        key = _subject_key(s)
        if key not in best or rank[SubjectStatus(s.status)] > rank[SubjectStatus(best[key].status)]:
            best[key] = s

    rows = []
    for category in [*SubjectCategory, "total"]:
        group = [s for s in best.values() if category == "total" or s.category == category]
        rows.append(
            CreditProgress(
                category=str(category),
                total=sum(s.credits for s in group),
                passed=sum(s.credits for s in group if s.status == SubjectStatus.PASSED),
                in_progress=sum(s.credits for s in group if s.status == SubjectStatus.IN_PROGRESS),
            )
        )
    return rows


def suggested_status(grade: float | None) -> SubjectStatus | None:
    if grade is None:
        return None
    passing = get_settings().grade_passing
    return SubjectStatus.PASSED if grade >= passing else SubjectStatus.FAILED


# --------------------------------------------------------------------------- persistencia


def list_subjects(session: Session, user_id: int) -> list[Subject]:
    stmt = (
        select(Subject)
        .where(Subject.user_id == user_id)
        .options(selectinload(Subject.items))
        .order_by(Subject.semester, Subject.name)
    )
    return list(session.scalars(stmt))


def user_summary(session: Session, user_id: int, current_semester: int) -> AcademicSummary:
    return summarize(list_subjects(session, user_id), current_semester)


def _validate_subject(name: str, credits: int, semester: int, status: str, category: str) -> None:
    if not name.strip():
        raise AcademicError("La materia necesita un nombre.")
    if credits < 0:
        raise AcademicError("Los créditos no pueden ser negativos.")
    if semester < 1:
        raise AcademicError("El semestre debe ser 1 o mayor.")
    if status not in {s.value for s in SubjectStatus}:
        raise AcademicError(f"Estado inválido: {status}")
    if category not in {c.value for c in SubjectCategory}:
        raise AcademicError(f"Categoría inválida: {category}")


def add_subject(
    session: Session,
    user_id: int,
    *,
    name: str,
    semester: int,
    credits: int = 3,
    status: str = SubjectStatus.IN_PROGRESS,
    category: str = SubjectCategory.TECHNOLOGY,
    code: str = "",
    teacher: str = "",
) -> Subject:
    _validate_subject(name, credits, semester, status, category)
    subject = Subject(
        user_id=user_id,
        name=name.strip(),
        semester=semester,
        credits=credits,
        status=status,
        category=category,
        code=code.strip(),
        teacher=teacher.strip(),
    )
    session.add(subject)
    session.flush()
    return subject


def _owned_subject(session: Session, user_id: int, subject_id: int) -> Subject:
    subject = session.get(Subject, subject_id)
    if subject is None or subject.user_id != user_id:
        raise AcademicError("Materia no encontrada.")
    return subject


def update_subject(session: Session, user_id: int, subject_id: int, **fields) -> Subject:
    subject = _owned_subject(session, user_id, subject_id)
    merged = {
        "name": fields.get("name", subject.name),
        "credits": fields.get("credits", subject.credits),
        "semester": fields.get("semester", subject.semester),
        "status": fields.get("status", subject.status),
        "category": fields.get("category", subject.category),
    }
    _validate_subject(**merged)
    for key in ("name", "code", "teacher", "credits", "semester", "status", "category"):
        if key in fields:
            value = fields[key]
            setattr(subject, key, value.strip() if isinstance(value, str) else value)
    return subject


def load_pensum(session: Session, user: User, program: str) -> int:
    """Agrega al plan del usuario las materias del pensum que aún no tiene (como pendientes) y
    actualiza programa, plan y total de semestres. Devuelve cuántas materias agregó."""
    pensum = PENSUMS.get(program)
    if pensum is None:
        raise AcademicError("Programa no disponible en el catálogo.")
    existing = {_subject_key(s) for s in list_subjects(session, user.id)}
    added = 0
    for ps in pensum.subjects:
        if ps.code.lower() in existing or ps.name.lower() in existing:
            continue
        session.add(
            Subject(
                user_id=user.id,
                name=ps.name,
                code=ps.code,
                credits=ps.credits,
                semester=ps.semester,
                category=ps.category,
                status=SubjectStatus.PLANNED,
            )
        )
        added += 1
    user.program, user.study_plan = pensum.program, pensum.plan
    user.total_semesters = pensum.semesters
    user.current_semester = min(user.current_semester, pensum.semesters)
    session.flush()
    return added


def delete_subject(session: Session, user_id: int, subject_id: int) -> None:
    session.delete(_owned_subject(session, user_id, subject_id))


def _validate_item(name: str, grade: float, weight: float | None) -> None:
    settings = get_settings()
    if not name.strip():
        raise AcademicError("El ítem necesita un nombre.")
    if not settings.grade_min <= grade <= settings.grade_max:
        raise AcademicError(
            f"La calificación debe estar entre {settings.grade_min:g} y {settings.grade_max:g}."
        )
    if weight is not None and not 0 <= weight <= 100:
        raise AcademicError("El porcentaje debe estar entre 0 y 100.")


def add_item(
    session: Session,
    user_id: int,
    subject_id: int,
    *,
    name: str,
    grade: float,
    description: str = "",
    weight: float | None = None,
    delivered_on: date | None = None,
) -> GradeItem:
    subject = _owned_subject(session, user_id, subject_id)
    weight = weight or None
    _validate_item(name, grade, weight)
    if weight and weighted_progress(subject.items) + weight > 100:
        raise AcademicError("La suma de porcentajes de la materia superaría el 100%.")
    item = GradeItem(
        name=name.strip(),
        description=description.strip(),
        grade=grade,
        weight=weight,
        delivered_on=delivered_on,
    )
    # Se agrega por la relación para que subject.items quede sincronizado en la sesión.
    subject.items.append(item)
    session.flush()
    return item


def update_item(session: Session, user_id: int, item_id: int, **fields) -> GradeItem:
    item = session.get(GradeItem, item_id)
    if item is None or item.subject.user_id != user_id:
        raise AcademicError("Ítem no encontrado.")
    weight = fields.get("weight", item.weight) or None
    _validate_item(fields.get("name", item.name), fields.get("grade", item.grade), weight)
    others = [i for i in item.subject.items if i.id != item.id]
    if weight and weighted_progress(others) + weight > 100:
        raise AcademicError("La suma de porcentajes de la materia superaría el 100%.")
    for key in ("name", "description", "grade", "delivered_on"):
        if key in fields:
            value = fields[key]
            setattr(item, key, value.strip() if isinstance(value, str) else value)
    item.weight = weight
    return item


def delete_item(session: Session, user_id: int, item_id: int) -> None:
    item = session.get(GradeItem, item_id)
    if item is None or item.subject.user_id != user_id:
        raise AcademicError("Ítem no encontrado.")
    session.delete(item)
