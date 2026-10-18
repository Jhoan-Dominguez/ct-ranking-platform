import pytest

from app.data.pensums import SOFTWARE_ENGINEERING
from app.db.models import GradeItem, Subject, SubjectCategory, SubjectStatus
from app.services import academics


def _subject(
    semester,
    credits,
    grades,
    status=SubjectStatus.IN_PROGRESS,
    weights=None,
    name="x",
    category=SubjectCategory.TECHNOLOGY,
):
    weights = weights or [None] * len(grades)
    s = Subject(
        name=name, code="", semester=semester, credits=credits, status=status, category=category
    )
    s.items = [GradeItem(name="i", grade=g, weight=w) for g, w in zip(grades, weights, strict=True)]
    return s


def test_subject_grade_simple_average():
    assert academics.subject_grade(_subject(1, 3, [3.0, 4.0, 5.0]).items) == pytest.approx(4.0)


def test_subject_grade_weighted_and_normalized():
    # 30% con 5.0 y 20% con 2.5 -> acumulado normalizado (1.5 + 0.5) / 0.5 = 4.0
    items = _subject(1, 3, [5.0, 2.5], weights=[30, 20]).items
    assert academics.subject_grade(items) == pytest.approx(4.0)
    assert academics.weighted_progress(items) == 50


def test_subject_grade_mixed_weights_falls_back_to_mean():
    items = _subject(1, 3, [5.0, 3.0], weights=[40, None]).items
    assert academics.subject_grade(items) == pytest.approx(4.0)


def test_subject_without_items_has_no_grade():
    assert academics.subject_grade([]) is None


def test_semester_and_general_average_weighted_by_credits():
    subjects = [
        _subject(1, 4, [5.0], SubjectStatus.PASSED),
        _subject(1, 2, [2.0], SubjectStatus.FAILED),
        _subject(2, 3, [4.0]),
        _subject(2, 3, []),  # sin nota: no cuenta
        _subject(3, 3, [1.0], SubjectStatus.PLANNED),  # pendiente: no cuenta
    ]
    assert academics.semester_average(subjects, 1) == pytest.approx((5 * 4 + 2 * 2) / 6)
    assert academics.semester_average(subjects, 2) == pytest.approx(4.0)
    assert academics.semester_average(subjects, 3) is None
    assert academics.general_average(subjects) == pytest.approx((20 + 4 + 12) / 9)

    summary = academics.summarize(subjects, current_semester=2)
    assert summary.current_semester_average == pytest.approx(4.0)
    assert summary.passed_credits == 4
    assert (summary.passed, summary.failed, summary.in_progress, summary.planned) == (1, 1, 2, 1)


def test_items_crud_and_validation(session, make_user):
    user = make_user()
    subj = academics.add_subject(session, user.id, name="Cálculo", semester=1, credits=4)
    academics.add_item(session, user.id, subj.id, name="Parcial", grade=4.5, weight=60)
    with pytest.raises(academics.AcademicError, match="100%"):
        academics.add_item(session, user.id, subj.id, name="Final", grade=3.0, weight=50)
    with pytest.raises(academics.AcademicError, match="entre"):
        academics.add_item(session, user.id, subj.id, name="Malo", grade=7, weight=10)
    item = academics.add_item(session, user.id, subj.id, name="Final", grade=3.0, weight=40)
    session.refresh(subj)
    assert academics.subject_grade(subj.items) == pytest.approx(4.5 * 0.6 + 3.0 * 0.4)

    academics.update_item(session, user.id, item.id, grade=5.0)
    assert item.grade == 5.0

    other = make_user()
    with pytest.raises(academics.AcademicError):
        academics.delete_item(session, other.id, item.id)
    academics.delete_subject(session, user.id, subj.id)
    session.flush()
    assert academics.list_subjects(session, user.id) == []


def test_credit_progress_by_category_counts_retakes_once():
    subjects = [
        _subject(1, 3, [4.0], SubjectStatus.PASSED, name="Cálculo", category="ciencias"),
        _subject(1, 3, [2.0], SubjectStatus.FAILED, name="Física", category="ciencias"),
        _subject(2, 3, [3.5], SubjectStatus.PASSED, name="Física", category="ciencias"),
        _subject(2, 1, [], SubjectStatus.IN_PROGRESS, name="Inglés I", category="idiomas"),
        _subject(3, 4, [], SubjectStatus.PLANNED, name="Redes"),
    ]
    rows = {p.category: p for p in academics.credit_progress(subjects)}
    assert (rows["ciencias"].total, rows["ciencias"].passed) == (6, 6)
    assert (rows["idiomas"].total, rows["idiomas"].in_progress) == (1, 1)
    assert (rows["tecnologia"].total, rows["tecnologia"].passed) == (4, 0)
    assert rows["humanidades"].total == 0
    total = rows["total"]
    assert (total.total, total.passed, total.in_progress) == (11, 6, 1)
    assert total.passed_pct == pytest.approx(600 / 11)


def test_load_pensum_is_idempotent_and_updates_plan(session, make_user):
    user = make_user()
    academics.add_subject(
        session, user.id, name="Programación I", semester=2, status=SubjectStatus.PASSED
    )
    added = academics.load_pensum(session, user, SOFTWARE_ENGINEERING.program)
    assert added == len(SOFTWARE_ENGINEERING.subjects) - 1  # Programación I ya existía
    assert academics.load_pensum(session, user, SOFTWARE_ENGINEERING.program) == 0
    assert (user.program, user.total_semesters) == ("Ingeniería de Software", 9)

    subjects = academics.list_subjects(session, user.id)
    assert {s.category for s in subjects} == {c.value for c in SubjectCategory}
    total = academics.credit_progress(subjects)[-1]
    assert (total.total, total.passed) == (SOFTWARE_ENGINEERING.total_credits, 3)

    with pytest.raises(academics.AcademicError):
        academics.load_pensum(session, user, "Programa inexistente")


def test_subject_category_is_validated(session, make_user):
    user = make_user()
    with pytest.raises(academics.AcademicError, match="Categoría"):
        academics.add_subject(session, user.id, name="X", semester=1, category="arte")
    subj = academics.add_subject(session, user.id, name="Inglés", semester=1, category="idiomas")
    academics.update_subject(session, user.id, subj.id, category="humanidades")
    assert subj.category == "humanidades"
