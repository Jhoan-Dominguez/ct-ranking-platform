"""Gráficas académicas: avance de créditos por categoría y evolución del promedio."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.core.config import get_settings
from app.database.models import Subject, SubjectCategory
from app.services import academics
from app.ui.components.formatting import CATEGORY_LABELS

# Colores de las gráficas.
PASSED_COLOR = "#7CC6F2"  # azul claro: créditos aprobados
IN_PROGRESS_COLOR = "#9CA3AF"  # gris: créditos que se están cursando
REMAINING_COLOR = "rgba(156, 163, 175, 0.15)"
AVERAGE_COLOR = "#4F46E5"  # promedio por semestre (color primario de la app)
PASSING_COLOR = "#DC2626"  # rojo: nota mínima aprobatoria
GENERAL_AVERAGE_COLOR = "#16A34A"  # verde: promedio general
CHART_HEIGHT = 320  # altura común para que las gráficas lado a lado queden alineadas


def averages_chart(summary: academics.AcademicSummary) -> None:
    data = pd.DataFrame(
        [
            {"Semestre": f"S{x.semester}", "Promedio": x.average}
            for x in summary.semesters
            if x.average is not None
        ]
    )
    st.markdown("**Evolución del promedio por semestre**")
    if data.empty:
        st.caption("Aún no hay notas registradas.")
        return
    settings = get_settings()
    semesters = data["Semestre"].tolist()
    fig = go.Figure()
    fig.add_scatter(
        name="Promedio del semestre",
        x=semesters,
        y=data["Promedio"],
        mode="lines+markers",
        line={"color": AVERAGE_COLOR, "width": 3},
        hovertemplate="%{x}: %{y:.2f}<extra></extra>",
    )
    # Las líneas de referencia se dibujan como series para que aparezcan en la leyenda.
    fig.add_scatter(
        name=f"Nota mínima aprobatoria ({settings.grade_passing:g})",
        x=semesters,
        y=[settings.grade_passing] * len(semesters),
        mode="lines",
        line={"color": PASSING_COLOR, "dash": "dot"},
        hoverinfo="skip",
    )
    if summary.general_average is not None:
        fig.add_scatter(
            name=f"Promedio general ({summary.general_average:.2f})",
            x=semesters,
            y=[summary.general_average] * len(semesters),
            mode="lines",
            line={"color": GENERAL_AVERAGE_COLOR, "dash": "dash"},
            hoverinfo="skip",
        )
    fig.update_layout(
        height=CHART_HEIGHT,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        yaxis={"range": [0, settings.grade_max], "title": "Promedio"},
        xaxis={"title": None},
        legend={"orientation": "h", "y": -0.25},
        showlegend=True,
    )
    st.plotly_chart(fig, width="stretch")


def credits_chart(subjects: list[Subject]) -> None:
    """Barras apiladas (en % del plan) de créditos aprobados y en curso por categoría."""
    progress = academics.credit_progress(subjects)
    total = progress[-1]
    if total.total == 0:
        return
    rows = [p for p in progress if p.total > 0]
    labels = [
        "📊 Total" if p.category == "total" else CATEGORY_LABELS[SubjectCategory(p.category)]
        for p in rows
    ]
    remaining = [max(0.0, 100 - p.passed_pct - p.in_progress_pct) for p in rows]

    fig = go.Figure()
    fig.add_bar(
        name="Aprobados",
        y=labels,
        x=[p.passed_pct for p in rows],
        orientation="h",
        marker_color=PASSED_COLOR,
        text=[f"{p.passed} cr" if p.passed else "" for p in rows],
        customdata=[[p.passed, p.total] for p in rows],
        hovertemplate="%{y}<br>Aprobados: %{customdata[0]} de %{customdata[1]} créditos"
        " (%{x:.0f}%)<extra></extra>",
    )
    fig.add_bar(
        name="Cursando",
        y=labels,
        x=[p.in_progress_pct for p in rows],
        orientation="h",
        marker_color=IN_PROGRESS_COLOR,
        text=[f"{p.in_progress} cr" if p.in_progress else "" for p in rows],
        customdata=[[p.in_progress, p.total] for p in rows],
        hovertemplate="%{y}<br>Cursando: %{customdata[0]} de %{customdata[1]} créditos"
        " (%{x:.0f}%)<extra></extra>",
    )
    fig.add_bar(
        name="Por cursar",
        y=labels,
        x=remaining,
        orientation="h",
        marker_color=REMAINING_COLOR,
        text=[f"{p.passed_pct + p.in_progress_pct:.0f}% de {p.total} cr" for p in rows],
        textposition="inside",
        insidetextanchor="end",
        hoverinfo="skip",
    )
    fig.update_layout(
        barmode="stack",
        height=max(CHART_HEIGHT, 70 + 48 * len(rows)),
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        xaxis={"range": [0, 100], "ticksuffix": "%", "title": None},
        yaxis={"autorange": "reversed"},
        legend={"orientation": "h", "y": -0.25, "traceorder": "normal"},
    )
    st.markdown(
        f"**Avance de créditos** · {total.passed} aprobados + {total.in_progress} cursando "
        f"de {total.total} ({total.passed_pct + total.in_progress_pct:.0f}%)"
    )
    st.plotly_chart(fig, width="stretch")
