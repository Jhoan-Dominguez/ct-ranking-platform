"""Panel de administrador: métricas generales, detalle de estudiantes, grupos y contenido."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

from app import auth
from app.auth import accounts
from app.core.config import get_settings
from app.database.models import ReportReason, ReportStatus, Role, User
from app.database.session import session_scope
from app.services import academics, admin, challenges, forum, moderation
from app.ui.components import actions, formatting, rankings, session, widgets
from app.ui.components.charts import credits_chart

STUDENT_COLUMNS = {
    "promedio_general": st.column_config.NumberColumn("Prom. general", format="%.2f"),
    "promedio_semestre": st.column_config.NumberColumn("Prom. semestre", format="%.2f"),
    "en_riesgo": st.column_config.CheckboxColumn("En riesgo"),
    "verificado": st.column_config.CheckboxColumn("Correo verificado"),
    "eliminacion_programada": st.column_config.DatetimeColumn(
        "Se elimina el", format="DD/MM/YY HH:mm"
    ),
    "reportes_recibidos": st.column_config.NumberColumn("Reportes"),
    "ultimo_ingreso": st.column_config.DatetimeColumn("Último ingreso", format="DD/MM/YY HH:mm"),
}


def _overview(s) -> None:
    m = admin.global_metrics(s)
    row1 = st.columns(6)
    row1[0].metric("Usuarios", m.users, f"+{m.new_users_30d} en 30 días")
    row1[1].metric("Activos (7 días)", m.active_users_7d)
    row1[2].metric("Publicaciones", m.posts)
    row1[3].metric("Comentarios", m.comments)
    row1[4].metric("Mensajes de apoyo", m.messages)
    row1[5].metric("Relaciones de seguimiento", m.follows)
    row2 = st.columns(6)
    row2[0].metric("Retos globales", m.challenges_global)
    row2[1].metric("Retos de la comunidad", m.challenges_user)
    row2[2].metric("Participaciones", m.participations)
    row2[3].metric("Retos completados", m.completions)
    rate = m.completions / m.participations if m.participations else 0
    row2[4].metric("Tasa de éxito en retos", f"{rate:.0%}")
    row2[5].metric("Notas registradas", m.grade_items)
    row3 = st.columns(6)
    row3[0].metric("Reportes pendientes", m.pending_reports)
    row3[1].metric("Cuentas por eliminar", m.pending_deletions)
    row3[2].metric("Cuentas sin activar", m.unverified_users)

    activity = admin.activity_frame(s, days=30)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Actividad de los últimos 30 días**")
        fig = px.line(activity, markers=False, labels={"index": "Fecha", "value": "Cantidad"})
        fig.update_layout(height=320, legend_title_text="", margin={"t": 10})
        st.plotly_chart(fig, width="stretch")

    students = admin.students_frame(s)
    with c2:
        st.markdown("**Distribución del promedio general**")
        graded = students.dropna(subset=["promedio_general"]) if not students.empty else students
        if graded.empty:
            st.caption("Aún no hay notas registradas.")
        else:
            fig = px.histogram(
                graded,
                x="promedio_general",
                nbins=10,
                labels={"promedio_general": "Promedio general"},
            )
            fig.add_vline(x=get_settings().grade_passing, line_dash="dot", line_color="red")
            fig.update_layout(height=320, margin={"t": 10}, yaxis_title="Estudiantes")
            st.plotly_chart(fig, width="stretch")

    st.markdown(
        "**⚠️ Estudiantes en riesgo académico** (promedio general o del semestre "
        f"por debajo de {get_settings().grade_passing:g})"
    )
    risk = students[students["en_riesgo"]] if not students.empty else students
    if risk.empty:
        st.success("No hay estudiantes en riesgo.")
    else:
        st.dataframe(
            risk[
                [
                    "usuario",
                    "nombre",
                    "programa",
                    "semestre",
                    "promedio_general",
                    "promedio_semestre",
                    "materias_reprobadas",
                    "ultimo_ingreso",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config=STUDENT_COLUMNS,
        )

    st.markdown("**Retos**")
    st.dataframe(
        admin.challenges_frame(s),
        hide_index=True,
        width="stretch",
        column_config={"tasa_exito": st.column_config.ProgressColumn("Éxito", format="percent")},
    )


def _user_label(users: list[User]) -> dict[int, str]:
    return {u.id: f"{u.username} — {u.full_name or 'sin nombre'}" for u in users}


def _student_detail(s, all_users: list[User]) -> None:
    labels = _user_label(all_users)
    user_id = st.selectbox(
        "Estudiante", list(labels), format_func=labels.get, index=None, placeholder="Buscar…"
    )
    if user_id is None:
        st.info("Selecciona un estudiante para ver su información completa.")
        return
    detail = admin.user_detail(s, user_id)
    if detail is None:
        return
    u, summary = detail.user, detail.summary
    passing = get_settings().grade_passing

    head, info = st.columns([1, 4])
    head.markdown(widgets.avatar_html(u, 110), unsafe_allow_html=True)
    with info:
        st.subheader(f"{u.full_name} (@{u.username})")
        st.caption(
            f"{u.email} · {u.program or 'sin programa'} · semestre {u.current_semester}/"
            f"{u.total_semesters} · {u.university or '—'} · código {u.student_code or '—'}"
        )
        st.caption(
            f"Registrado {formatting.fmt_dt(u.created_at)} · "
            f"último ingreso {formatting.fmt_dt(u.last_login)}"
            f" · rol {u.role} · {'activo' if u.is_active else 'deshabilitado'}"
        )
    at_risk = any(
        x is not None and x < passing
        for x in (summary.general_average, summary.current_semester_average)
    )
    if at_risk:
        st.error("⚠️ Estudiante en riesgo académico: considera hacerle seguimiento.")

    cols = st.columns(7)
    cols[0].metric("Prom. general", formatting.fmt_grade(summary.general_average))
    cols[1].metric("Prom. semestre", formatting.fmt_grade(summary.current_semester_average))
    cols[2].metric("Créditos aprobados", summary.passed_credits)
    cols[3].metric("Reprobadas", summary.failed)
    cols[4].metric("Retos completados", sum(1 for p in detail.participations if p.completed_at))
    cols[5].metric("Seguidores", len(detail.followers))
    cols[6].metric("Apoyos recibidos", detail.messages_received)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Promedio por semestre**")
        sem = pd.DataFrame(
            [{"Semestre": x.semester, "Promedio": x.average} for x in summary.semesters]
        )
        if sem.dropna().empty:
            st.caption("Sin notas.")
        else:
            fig = px.bar(
                sem.dropna(), x="Semestre", y="Promedio", range_y=[0, get_settings().grade_max]
            )
            fig.add_hline(y=passing, line_dash="dot", line_color="red")
            fig.update_layout(height=280, margin={"t": 10})
            st.plotly_chart(fig, width="stretch")
    with c2:
        st.markdown("**Materias**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Semestre": x.semester,
                        "Materia": x.name,
                        "Categoría": x.category,
                        "Créditos": x.credits,
                        "Estado": x.status,
                        "Nota": academics.subject_grade(x.items),
                        "Ítems": len(x.items),
                    }
                    for x in detail.subjects
                ]
            ),
            hide_index=True,
            width="stretch",
            height=280,
            column_config={"Nota": st.column_config.NumberColumn(format="%.2f")},
        )

    credits_chart(detail.subjects)

    with st.expander("Ítems calificados"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Materia": x.name,
                        "Ítem": i.name,
                        "Nota": i.grade,
                        "Porcentaje": i.weight,
                        "Descripción": i.description,
                    }
                    for x in detail.subjects
                    for i in x.items
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**Retos**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Reto": p.challenge.title,
                        "Unido": p.joined_at,
                        "Completado": p.completed_at,
                        "Evidencia": p.evidence,
                    }
                    for p in detail.participations
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    with c4:
        st.markdown("**Publicaciones**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Título": p.title, "Categoría": p.category, "Creada": p.created_at}
                    for p in detail.posts
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            f"Sigue a {len(detail.following)} · le siguen {len(detail.followers)} · "
            f"mensajes enviados {detail.messages_sent}"
        )


def _groups(s) -> None:
    students = admin.students_frame(s)
    if students.empty:
        st.info("No hay usuarios.")
        return
    c1, c2, c3 = st.columns(3)
    programs = c1.multiselect("Programa", sorted(p for p in students["programa"].unique() if p))
    semesters = c2.multiselect("Semestre", sorted(students["semestre"].unique()))
    picked = c3.multiselect("Estudiantes específicos", students["usuario"].tolist())
    group = students
    if programs:
        group = group[group["programa"].isin(programs)]
    if semesters:
        group = group[group["semestre"].isin(semesters)]
    if picked:
        group = group[group["usuario"].isin(picked)]
    if group.empty:
        st.warning("Ningún estudiante coincide con los filtros.")
        return

    cols = st.columns(6)
    cols[0].metric("Estudiantes", len(group))
    mean = group["promedio_general"].mean()
    cols[1].metric("Promedio del grupo", formatting.fmt_grade(None if pd.isna(mean) else mean))
    cols[2].metric("En riesgo", int(group["en_riesgo"].sum()))
    cols[3].metric("Retos completados (media)", f"{group['retos_completados'].mean():.1f}")
    cols[4].metric("Publicaciones", int(group["publicaciones"].sum()))
    cols[5].metric("Apoyos recibidos", int(group["apoyos_recibidos"].sum()))

    left, right = st.columns([3, 2])
    with left:
        chart = group.dropna(subset=["promedio_general"])
        if not chart.empty:
            fig = px.bar(
                chart.sort_values("promedio_general"),
                x="promedio_general",
                y="usuario",
                orientation="h",
                color="en_riesgo",
                color_discrete_map={True: "#d62728", False: "#2ca02c"},
                labels={"promedio_general": "Promedio general", "usuario": ""},
            )
            fig.add_vline(x=get_settings().grade_passing, line_dash="dot")
            fig.update_layout(height=max(250, 28 * len(chart)), margin={"t": 10})
            st.plotly_chart(fig, width="stretch")
    with right:
        rankings.leaderboard_banner(s, "Ranking del grupo", user_ids=set(group["id"]))
    st.dataframe(group, hide_index=True, width="stretch", column_config=STUDENT_COLUMNS)
    st.download_button(
        "Descargar CSV", group.to_csv(index=False).encode(), "grupo.csv", "text/csv", icon="⬇️"
    )


def _content(s, admin_user: User) -> None:
    kind = st.segmented_control(
        "Tipo", ["Publicaciones", "Comentarios", "Retos", "Mensajes"], default="Publicaciones"
    )
    frames = {
        "Publicaciones": admin.posts_frame,
        "Comentarios": admin.comments_frame,
        "Retos": admin.challenges_frame,
        "Mensajes": admin.messages_frame,
    }
    if kind is None:
        return
    df = frames[kind](s)
    st.dataframe(df, hide_index=True, width="stretch")
    if df.empty:
        return
    c1, c2 = st.columns([1, 3], vertical_alignment="bottom")
    target = c1.selectbox(
        "ID a eliminar", df["id"].tolist(), index=None, key=f"del_{kind}", placeholder="Selecciona…"
    )
    if target is not None and c2.button(f"Eliminar de {kind.lower()}", icon="🗑️"):
        target = int(target)
        deleters = {
            "Publicaciones": lambda s2: forum.delete_post(s2, admin_user, target),
            "Comentarios": lambda s2: forum.delete_comment(s2, admin_user, target),
            "Retos": lambda s2: challenges.delete_challenge(s2, admin_user, target),
            "Mensajes": lambda s2: admin.delete_message(s2, target),
        }
        actions.run_action(deleters[kind], "Elemento eliminado")


def _reports(s, admin_user: User) -> None:
    status_options = {
        "🕒 Pendientes": ReportStatus.PENDING,
        "✅ Resueltos": ReportStatus.RESOLVED,
        "🚫 Descartados": ReportStatus.DISMISSED,
        "Todos": None,
    }
    choice = st.segmented_control(
        "Estado", list(status_options), default="🕒 Pendientes", key="report_status"
    )
    reports = moderation.list_reports(s, status_options.get(choice or "🕒 Pendientes"))
    if not reports:
        st.success("No hay reportes en esta vista.")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": r.id,
                    "Fecha": r.created_at,
                    "Reportado": r.reported.username,
                    "Reportado por": r.reporter.username,
                    "Motivo": moderation.REASON_LABELS[ReportReason(r.reason)],
                    "Contenido": "publicación"
                    if r.post_id
                    else "comentario"
                    if r.comment_id
                    else "perfil",
                    "Estado": moderation.STATUS_LABELS[ReportStatus(r.status)],
                    "Reportes contra el usuario": moderation.reports_against_count(
                        s, r.reported_id
                    ),
                }
                for r in reports
            ]
        ),
        hide_index=True,
        width="stretch",
        column_config={"Fecha": st.column_config.DatetimeColumn(format="DD/MM/YY HH:mm")},
    )
    labels = {r.id: f"#{r.id} · {r.reported.username} · {r.reason}" for r in reports}
    report_id = st.selectbox(
        "Revisar reporte",
        list(labels),
        format_func=labels.get,
        index=None,
        placeholder="Selecciona un reporte…",
    )
    if report_id is None:
        return
    r = next(x for x in reports if x.id == report_id)
    with st.container(border=True):
        widgets.user_chip(r.reported, 36, f"reportado por @{r.reporter.username}")
        st.markdown(
            f"**Motivo:** {moderation.REASON_LABELS[ReportReason(r.reason)]}  \n"
            f"**Detalles:** {r.description or '—'}"
        )
        if r.post:
            st.markdown(f"**Publicación:** {r.post.title}")
            st.caption(r.post.body[:500])
        elif r.comment:
            st.markdown("**Comentario:**")
            st.caption(r.comment.body[:500])
        elif r.post_id is None and r.comment_id is None:
            st.caption("Reporte sobre el perfil del usuario.")
        if r.status != ReportStatus.PENDING:
            who = r.resolved_by.username if r.resolved_by else "—"
            st.info(
                f"{moderation.STATUS_LABELS[ReportStatus(r.status)]} por @{who} el "
                f"{formatting.fmt_dt(r.resolved_at)}. {r.admin_note}"
            )
            return
        note = st.text_input("Nota de resolución (opcional)", key=f"note_{r.id}")
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("Resolver", icon="✅", type="primary", key=f"resolve_{r.id}"):
            actions.run_action(
                lambda s2: moderation.close_report(
                    s2, admin_user, r.id, ReportStatus.RESOLVED, note
                ),
                "Reporte resuelto",
            )
        if c2.button("Descartar", icon="🚫", key=f"dismiss_{r.id}"):
            actions.run_action(
                lambda s2: moderation.close_report(
                    s2, admin_user, r.id, ReportStatus.DISMISSED, note
                ),
                "Reporte descartado",
            )
        if (r.post_id or r.comment_id) and c3.button(
            "Eliminar contenido", icon="🗑️", key=f"del_content_{r.id}"
        ):

            def _delete_content(s2):
                if r.post_id:
                    forum.delete_post(s2, admin_user, r.post_id)
                else:
                    forum.delete_comment(s2, admin_user, r.comment_id)
                moderation.close_report(
                    s2, admin_user, r.id, ReportStatus.RESOLVED, note or "Contenido eliminado"
                )

            actions.run_action(_delete_content, "Contenido eliminado y reporte resuelto")
        if r.reported.is_active and c4.button(
            "Deshabilitar usuario", icon="⛔", key=f"disable_{r.id}"
        ):

            def _disable(s2):
                auth.set_active(s2, s2.get(User, r.reported_id), False)
                moderation.close_report(
                    s2, admin_user, r.id, ReportStatus.RESOLVED, note or "Cuenta deshabilitada"
                )

            actions.run_action(_disable, "Usuario deshabilitado y reporte resuelto")


def _users(s, admin_user: User, all_users: list[User]) -> None:
    st.dataframe(
        admin.students_frame(s), hide_index=True, width="stretch", column_config=STUDENT_COLUMNS
    )
    labels = _user_label(all_users)
    user_id = st.selectbox(
        "Usuario a gestionar",
        list(labels),
        format_func=labels.get,
        index=None,
        placeholder="Selecciona un usuario…",
    )
    if user_id is None:
        return
    target = next(u for u in all_users if u.id == user_id)
    c1, c2 = st.columns(2)
    with c1:
        role = st.radio(
            "Rol",
            [Role.STUDENT, Role.ADMIN],
            index=int(target.is_admin),
            horizontal=True,
            format_func=lambda r: "Estudiante" if r == Role.STUDENT else "Administrador",
        )
        if st.button("Guardar rol", disabled=target.id == admin_user.id):
            actions.run_action(lambda s2: admin.set_role(s2, user_id, role), "Rol actualizado")
    with c2:
        label = "Deshabilitar cuenta" if target.is_active else "Habilitar cuenta"
        if st.button(label, disabled=target.id == admin_user.id):
            actions.run_action(
                lambda s2: auth.set_active(s2, s2.get(User, user_id), not target.is_active),
                "Estado de la cuenta actualizado",
            )
    if target.id == admin_user.id:
        st.caption("No puedes cambiar tu propio rol ni deshabilitar tu cuenta.")
    if target.pending_deletion:
        st.warning(
            f"Eliminación programada para el {formatting.fmt_dt(target.deletion_scheduled_for)} "
            f"(solicitada el {formatting.fmt_dt(target.deletion_requested_at)}).",
            icon="⚠️",
        )
        if st.button("Cancelar la eliminación de esta cuenta"):
            actions.run_action(
                lambda s2: accounts.cancel_deletion(s2, s2.get(User, user_id)),
                "Eliminación cancelada",
            )
    if not target.email_verified:
        st.info("Esta cuenta aún no activó su correo.", icon="📧")


def render() -> None:
    user = session.require_user()
    if not user.is_admin:
        st.error("No tienes permisos para ver esta página.")
        st.stop()
    st.title("🛡️ Panel de administrador")
    with session_scope() as s:
        pending = moderation.pending_reports_count(s)
    reports_label = f"Reportes ({pending})" if pending else "Reportes"
    tabs = st.tabs(["Resumen", "Estudiante", "Grupos", "Contenido", reports_label, "Usuarios"])
    with session_scope() as s:
        all_users = list(s.scalars(select(User).order_by(User.username)))
        with tabs[0]:
            _overview(s)
        with tabs[1]:
            _student_detail(s, all_users)
        with tabs[2]:
            _groups(s)
        with tabs[3]:
            _content(s, user)
        with tabs[4]:
            _reports(s, user)
        with tabs[5]:
            _users(s, user, all_users)
