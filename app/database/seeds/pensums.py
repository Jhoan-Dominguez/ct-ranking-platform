"""Catálogo de planes de estudio (pensum) que un estudiante puede cargar en su plan académico.

Fuente: ``docs/pensum.png`` (Ingeniería de Software, 9 semestres). La imagen no indica créditos;
los valores asignados son una estimación que se puede ajustar aquí.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.database.models import SubjectCategory

C = SubjectCategory.SCIENCES
H = SubjectCategory.HUMANITIES
T = SubjectCategory.TECHNOLOGY
I = SubjectCategory.LANGUAGES  # noqa: E741


@dataclass(frozen=True)
class PlanSubject:
    semester: int
    code: str
    name: str
    credits: int
    category: SubjectCategory


@dataclass(frozen=True)
class Pensum:
    program: str
    plan: str
    semesters: int
    subjects: tuple[PlanSubject, ...]

    @property
    def total_credits(self) -> int:
        return sum(s.credits for s in self.subjects)


def _semester(number: int, *subjects: tuple[str, int, SubjectCategory]) -> list[PlanSubject]:
    return [
        PlanSubject(number, f"IS{number}{i:02d}", name, credits, category)
        for i, (name, credits, category) in enumerate(subjects, start=1)
    ]


SOFTWARE_ENGINEERING = Pensum(
    program="Ingeniería de Software",
    plan="Pensum Ingeniería de Software",
    semesters=9,
    subjects=tuple(
        _semester(
            1,
            ("Introducción a la Ingeniería de Software", 3, T),
            ("Innovación Tecnológica", 2, T),
            ("Teoría General de los Sistemas", 2, C),
            ("Fundamentos de Matemáticas", 3, C),
            ("Pensamiento Computacional", 3, T),
            ("Cátedra Pablo Olivares Marmolejo", 1, H),
            ("Inglés I", 1, I),
        )
        + _semester(
            2,
            ("Requerimientos de Software", 3, T),
            ("Programación I", 3, T),
            ("Metodologías de Software", 2, T),
            ("Cálculo Diferencial", 3, C),
            ("Álgebra Lineal", 3, C),
            ("Ser (Be-It)", 1, H),
            ("Inglés II", 1, I),
        )
        + _semester(
            3,
            ("Fundamentos de Diseño de Software", 3, T),
            ("Programación II", 3, T),
            ("Fundamentos de Bases de Datos", 3, T),
            ("Cálculo Integral", 3, C),
            ("Estadística I", 3, C),
            ("Saber Convivir (Live-It)", 1, H),
            ("Inglés III", 1, I),
        )
        + _semester(
            4,
            ("Diseño de Software", 3, T),
            ("Programación III", 3, T),
            ("Diseño de Bases de Datos", 3, T),
            ("Fundamentos de Investigación", 2, H),
            ("Estadística II", 3, C),
            ("Saber Hacer (Do-It)", 1, H),
            ("Inglés IV", 1, I),
        )
        + _semester(
            5,
            ("Arquitectura de Software", 3, T),
            ("Programación IV", 3, T),
            ("Teoría de Grafos", 3, C),
            ("Física I", 3, C),
            ("Saber Conocer (Know-It)", 1, H),
            ("Inglés V", 1, I),
        )
        + _semester(
            6,
            ("Pruebas de Software", 3, T),
            ("Proyecto de Software Empresarial", 3, T),
            ("Análisis Numérico", 3, C),
            ("Física II", 3, C),
            ("Espíritu Emprendedor", 2, H),
            ("Inglés VI", 1, I),
        )
        + _semester(
            7,
            ("Mantenimiento de Software", 3, T),
            ("Normatividad de Software", 2, T),
            ("Business Intelligence", 3, T),
            ("Profundización I", 3, T),
            ("Investigación Cualitativa y Cuantitativa", 2, H),
            ("Formulación y Evaluación de Proyectos de Ingeniería", 2, H),
            ("Electiva I", 2, H),
        )
        + _semester(
            8,
            ("Calidad del Software I", 3, T),
            ("Analítica y Visualización de Datos", 3, T),
            ("Profundización II", 3, T),
            ("Práctica Empresarial", 6, T),
            ("Ética, Constitución y Gobernanza", 2, H),
            ("Electiva II", 2, H),
        )
        + _semester(
            9,
            ("Calidad del Software II", 3, T),
            ("Experiencia de Usuario", 3, T),
            ("Tecnologías Emergentes", 3, T),
            ("Profundización III", 3, T),
            ("Investigación de Operaciones", 3, C),
            ("Gerencia de Proyectos de Ingeniería", 2, H),
            ("Electiva III", 2, H),
        )
    ),
)

PENSUMS: dict[str, Pensum] = {p.program: p for p in (SOFTWARE_ENGINEERING,)}
