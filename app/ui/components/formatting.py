"""Formato de valores para mostrar: notas, fechas y etiquetas."""

from __future__ import annotations

from datetime import date, datetime

from app.database.models import SubjectCategory

CATEGORY_LABELS = {
    SubjectCategory.SCIENCES: "🔬 Ciencias",
    SubjectCategory.HUMANITIES: "📜 Humanidades",
    SubjectCategory.TECHNOLOGY: "💻 Tecnología",
    SubjectCategory.LANGUAGES: "🌐 Idiomas",
}


def fmt_grade(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def fmt_dt(value: datetime | date | None, with_time: bool = True) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone()
        return value.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")
    return value.strftime("%d/%m/%Y")
