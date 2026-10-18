"""Plan de estudios, materias, ítems calificables y promedios."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.config import get_settings
from app.data.pensums import PENSUMS
from app.db.models import Subject, SubjectCategory, SubjectStatus
from app.db.session import session_scope
from app.services import academics, users
from app.ui import common
from app.ui.common import CATEGORY_LABELS

STATUS_LABELS = {
    SubjectStatus.PLANNED: "📝 Pendiente",
    SubjectStatus.IN_PROGRESS: "📖 Cursando",
    SubjectStatus.PASSED: "✅ Aprobada",
    SubjectStatus.FAILED: "❌ Reprobada",
}
# Colores de la gráfica de avance de créditos.
PASSED_COLOR = "#7CC6F2"  # azul claro: créditos aprobados
IN_PROGRESS_COLOR = "#9CA3AF"  # gris: créditos que se están cursando
REMAINING_COLOR = "rgba(156, 163, 175, 0.15)"
AVERAGE_COLOR = "#4F46E5"  # promedio por semestre (color primario de la app)
PASSING_COLOR = "#DC2626"  # rojo: nota mínima aprobatoria
GENERAL_AVERAGE_COLOR = "#16A34A"  # verde: promedio general
CHART_HEIGHT = 320  # altura común para que las gráficas lado a lado queden alineadas


def _plan_header(user) -> None:
    with st.expander("⚙️ Datos del plan de estudios", expanded=not user.program):
        with st.form("plan"):
            c1, c2 = st.columns(2)
            program = c1.text_input("Programa / carrera", user.program)
            plan = c2.text_input("Plan de estudios (versión o pensum)", user.study_plan)
            c3, c4 = st.columns(2)
            current = c3.number_input("Semestre actual", 1, 20, user.current_semester)
            total = c4.number_input("Total de semestres del plan", 1, 20, user.total_semesters)
            if st.form_submit_button("Guardar plan", type="primary"):
                common.run_action(
                    lambda s: users.update_profile(
                        s,
                        s.merge(user),
                        program=program,
                        study_plan=plan,
                        current_semester=current,
                        total_semesters=total,
                    ),
                    "Plan actualizado",
                )

        st.markdown("**Cargar un pensum del catálogo**")
        st.caption(
            "Agrega a tu plan todas las materias del programa como «Pendiente» (las que ya "
            "tengas registradas no se duplican). Luego marca las que ya cursaste."
        )
        c5, c6 = st.columns([3, 1], vertical_alignment="bottom")
        program_name = c5.selectbox("Programa", list(PENSUMS), key="pensum_program")
        if c6.button("Cargar pensum", icon="📥", width="stretch"):
            pensum = PENSUMS[program_name]
            common.run_action(
                lambda s: academics.load_pensum(s, s.merge(user), program_name),
                f"Pensum de {pensum.program} cargado ({len(pensum.subjects)} materias, "
                f"{pensum.total_credits} créditos)",
            )


@st.dialog("Agregar materia")
def _add_subject_dialog(user) -> None:
    with st.form("add_subject"):
        name = st.text_input("Nombre de la materia")
        c1, c2 = st.columns(2)
        code = c1.text_input("Código (opcional)")
        teacher = c2.text_input("Docente (opcional)")
        c3, c4, c5 = st.columns(3)
        semester = c3.number_input("Semestre", 1, 20, user.current_semester)
        credits = c4.number_input("Créditos", 0, 20, 3)
        status = c5.selectbox(
            "Estado", list(SubjectStatus), format_func=lambda v: STATUS_LABELS[v], index=1
        )
        category = st.selectbox(
            "Categoría", list(SubjectCategory), format_func=lambda c: CATEGORY_LABELS[c], index=2
        )
        if st.form_submit_button("Agregar", type="primary"):
            common.run_action(
                lambda s: academics.add_subject(
                    s,
                    user.id,
                    name=name,
                    code=code,
                    teacher=teacher,
                    semester=semester,
                    credits=credits,
                    status=status,
                    category=category,
                ),
                "Materia agregada",
            )


@st.dialog("Editar materia")
def _edit_subject_dialog(user_id: int, subject: Subject) -> None:
    with st.form("edit_subject"):
        name = st.text_input("Nombre", subject.name)
        c1, c2 = st.columns(2)
        code = c1.text_input("Código", subject.code)
        teacher = c2.text_input("Docente", subject.teacher)
        c3, c4, c5 = st.columns(3)
        semester = c3.number_input("Semestre", 1, 20, subject.semester)
        credits = c4.number_input("Créditos", 0, 20, subject.credits)
        statuses = list(SubjectStatus)
        status = c5.selectbox(
            "Estado",
            statuses,
            index=statuses.index(SubjectStatus(subject.status)),
            format_func=lambda v: STATUS_LABELS[v],
        )
        categories = list(SubjectCategory)
        category = st.selectbox(
            "Categoría",
            categories,
            index=categories.index(SubjectCategory(subject.category)),
            format_func=lambda c: CATEGORY_LABELS[c],
        )
        if st.form_submit_button("Guardar", type="primary"):
            common.run_action(
                lambda s: academics.update_subject(
                    s,
                    user_id,
                    subject.id,
                    name=name,
                    code=code,
                    teacher=teacher,
                    semester=semester,
                    credits=credits,
                    status=status,
                    category=category,
                ),
                "Materia actualizada",
            )


def _item_form(user_id: int, subject_id: int, key: str, item=None) -> None:
    settings = get_settings()
    with st.form(key, clear_on_submit=item is None):
        c1, c2, c3 = st.columns([2, 1, 1])
        name = c1.text_input("Nombre del trabajo / tarea", item.name if item else "")
        grade = c2.number_input(
            "Calificación",
            settings.grade_min,
            settings.grade_max,
            float(item.grade) if item else settings.grade_min,
            step=0.1,
            format="%.2f",
        )
        weight = c3.number_input(
            "Porcentaje (%)",
            0.0,
            100.0,
            float(item.weight or 0) if item else 0.0,
            step=5.0,
            help="Opcional. 0 = sin porcentaje (promedio simple).",
        )
        description = st.text_area("Descripción", item.description if item else "", height=80)
        delivered = st.date_input("Fecha de entrega", item.delivered_on if item else None)
        if st.form_submit_button("Guardar ítem" if item else "Agregar ítem", type="primary"):
            if item is None:
                common.run_action(
                    lambda s: academics.add_item(
                        s,
                        user_id,
                        subject_id,
                        name=name,
                        grade=grade,
                        weight=weight or None,
                        description=description,
                        delivered_on=delivered,
                    ),
                    "Ítem agregado",
                )
            else:
                common.run_action(
                    lambda s: academics.update_item(
                        s,
                        user_id,
                        item.id,
                        name=name,
                        grade=grade,
                        weight=weight or None,
                        description=description,
                        delivered_on=delivered,
                    ),
                    "Ítem actualizado",
                )


@st.dialog("Editar ítem", width="large")
def _edit_item_dialog(user_id: int, item) -> None:
    _item_form(user_id, item.subject_id, f"edit_item_{item.id}", item)


def _subject_key(subject: Subject) -> str:
    return f"subject_expander_{subject.id}"


def _semester_key(semester: int) -> str:
    return f"plan_semester_expander_{semester}"


EXPANDER_MEMORY = "_academics_open_expanders"


def _remember(key: str) -> None:
    st.session_state.setdefault(EXPANDER_MEMORY, {})[key] = st.session_state[key]


def _set_expanded(keys: list[str], expanded: bool) -> None:
    # Se ejecuta como callback (antes del rerun), así que fija el estado antes de dibujar.
    memory = st.session_state.setdefault(EXPANDER_MEMORY, {})
    for key in keys:
        st.session_state[key] = memory[key] = expanded


def _stateful_expander(label: str, key: str):
    """Expander cuyo estado abierto/cerrado se conserva aunque cambie su título.

    Streamlit identifica el expander también por su etiqueta (que aquí incluye notas y
    promedios), así que al cambiar ésta lo trataría como uno nuevo y lo cerraría. Por eso se
    recuerda el estado en session_state y se restaura antes de dibujarlo.
    """
    memory = st.session_state.setdefault(EXPANDER_MEMORY, {})
    if key in memory:
        st.session_state[key] = memory[key]
    return st.expander(label, key=key, on_change=_remember, args=(key,))


def _expand_controls(keys: list[str], scope: str) -> None:
    """Botones para expandir o colapsar a la vez todos los menús de una pestaña."""
    if not keys:
        return
    with st.container(horizontal=True, horizontal_alignment="right"):
        st.button(
            "Expandir todo",
            key=f"expand_all_{scope}",
            icon=":material/unfold_more:",
            type="tertiary",
            on_click=_set_expanded,
            args=(keys, True),
        )
        st.button(
            "Colapsar todo",
            key=f"collapse_all_{scope}",
            icon=":material/unfold_less:",
            type="tertiary",
            on_click=_set_expanded,
            args=(keys, False),
        )


def _subject_card(user, subject: Subject) -> None:
    grade = academics.subject_grade(subject.items)
    progress = academics.weighted_progress(subject.items)
    passing = get_settings().grade_passing
    color = "green" if grade is not None and grade >= passing else "red" if grade else "gray"
    title = (
        f"{STATUS_LABELS[SubjectStatus(subject.status)]} · **{subject.name}** "
        f"{f'({subject.code})' if subject.code else ''} · {subject.credits} cr · "
        f":{color}[nota {common.fmt_grade(grade)}]"
    )
    with _stateful_expander(title, _subject_key(subject)):
        meta, actions = st.columns([3, 2])
        meta.caption(
            f"{CATEGORY_LABELS[SubjectCategory(subject.category)]} · "
            f"Docente: {subject.teacher or '—'} · Semestre {subject.semester} · "
            f"Porcentaje evaluado: {progress:.0f}%"
        )
        b1, b2, b3 = actions.columns(3)
        if b1.button("Editar", key=f"edit_s_{subject.id}", icon="✏️"):
            _edit_subject_dialog(user.id, subject)
        suggested = academics.suggested_status(grade)
        if (
            suggested
            and subject.status == SubjectStatus.IN_PROGRESS
            and b2.button(
                "Cerrar",
                key=f"close_s_{subject.id}",
                icon="🏁",
                help=f"Marcar como {suggested.value} según la nota actual",
            )
        ):
            common.run_action(
                lambda s: academics.update_subject(s, user.id, subject.id, status=suggested),
                f"Materia marcada como {suggested.value}",
            )
        if b3.button("Borrar", key=f"del_s_{subject.id}", icon="🗑️"):
            common.run_action(
                lambda s: academics.delete_subject(s, user.id, subject.id), "Materia eliminada"
            )

        if subject.items:
            for item in subject.items:
                c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 0.5, 0.5], vertical_alignment="center")
                c1.markdown(
                    f"**{item.name}**" + (f"  \n_{item.description}_" if item.description else "")
                )
                c2.markdown(f"Nota **{item.grade:.2f}**")
                c3.markdown(f"{item.weight:g}%" if item.weight else "—")
                if c4.button("✏️", key=f"edit_i_{item.id}", help="Editar"):
                    _edit_item_dialog(user.id, item)
                if c5.button("🗑️", key=f"del_i_{item.id}", help="Eliminar"):
                    common.run_action(
                        lambda s, iid=item.id: academics.delete_item(s, user.id, iid),
                        "Ítem eliminado",
                    )
        else:
            st.caption("Sin ítems calificados todavía.")
        st.markdown("**Agregar ítem calificable**")
        _item_form(user.id, subject.id, f"add_item_{subject.id}")


def _averages_chart(summary: academics.AcademicSummary) -> None:
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


def _semester_table(subjects: list[Subject]) -> None:
    table = pd.DataFrame(
        [
            {
                "Materia": x.name,
                "Código": x.code,
                "Categoría": CATEGORY_LABELS[SubjectCategory(x.category)],
                "Créditos": x.credits,
                "Estado": STATUS_LABELS[SubjectStatus(x.status)],
                "Nota": academics.subject_grade(x.items),
                "Ítems": len(x.items),
            }
            for x in subjects
        ]
    )
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={"Nota": st.column_config.NumberColumn(format="%.2f")},
    )


def render() -> None:
    user = common.require_user()
    head, button = st.columns([4, 1], vertical_alignment="bottom")
    head.title("📚 Plan académico")
    if button.button("Agregar materia", icon="➕", type="primary", width="stretch"):
        _add_subject_dialog(user)

    _plan_header(user)

    with session_scope() as s:
        subjects = academics.list_subjects(s, user.id)
        summary = academics.summarize(subjects, user.current_semester)

        cols = st.columns(5)
        cols[0].metric("Promedio general", common.fmt_grade(summary.general_average))
        cols[1].metric(
            f"Promedio semestre {user.current_semester}",
            common.fmt_grade(summary.current_semester_average),
        )
        cols[2].metric("Créditos aprobados", summary.passed_credits)
        cols[3].metric("Aprobadas / reprobadas", f"{summary.passed} / {summary.failed}")
        cols[4].metric("Avance del plan", f"{user.current_semester}/{user.total_semesters}")
        st.caption(
            "La nota de cada materia es el promedio de sus ítems (ponderado si todos tienen "
            "porcentaje). Los promedios de semestre y general se ponderan por créditos e "
            "incluyen materias cursando, aprobadas y reprobadas que tengan notas."
        )

        tab_now, tab_history, tab_plan = st.tabs(
            [f"Semestre actual ({user.current_semester})", "Historia académica", "Plan completo"]
        )
        with tab_now:
            current = [x for x in subjects if x.semester == user.current_semester]
            if not current:
                st.info("No tienes materias en el semestre actual. Usa «Agregar materia».")
            _expand_controls([_subject_key(x) for x in current], "current")
            for subject in current:
                _subject_card(user, subject)

        with tab_history:
            left, right = st.columns(2, gap="medium")
            with left:
                credits_chart(subjects)
            with right:
                _averages_chart(summary)
            past = [sem for sem in summary.semesters if sem.semester < user.current_semester]
            if not past:
                st.info("Aún no registras semestres anteriores.")
            past_numbers = {sem.semester for sem in past}
            _expand_controls(
                [_subject_key(x) for x in subjects if x.semester in past_numbers], "history"
            )
            for sem in past:
                st.markdown(
                    f"#### Semestre {sem.semester} · promedio {common.fmt_grade(sem.average)} "
                    f"· {sem.credits} créditos"
                )
                for subject in subjects:
                    if subject.semester == sem.semester:
                        _subject_card(user, subject)

        with tab_plan:
            if not subjects:
                st.info(
                    "Registra todas las materias de tu pensum o cárgalo desde «Datos del plan "
                    "de estudios» (quedan como «Pendiente» para planear semestres futuros)."
                )
            _expand_controls([_semester_key(x.semester) for x in summary.semesters], "plan")
            for sem in summary.semesters:
                sem_subjects = [x for x in subjects if x.semester == sem.semester]
                passed = sum(1 for x in sem_subjects if x.status == SubjectStatus.PASSED)
                marker = " · 📍 actual" if sem.semester == user.current_semester else ""
                average = f" · promedio {common.fmt_grade(sem.average)}" if sem.average else ""
                with _stateful_expander(
                    f"📘 **Semestre {sem.semester}**{marker} · {sem.subjects} materias · "
                    f"{sem.credits} créditos · {passed}/{sem.subjects} aprobadas{average}",
                    _semester_key(sem.semester),
                ):
                    _semester_table(sem_subjects)
