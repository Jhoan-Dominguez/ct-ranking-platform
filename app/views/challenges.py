"""Retos dinámicos con banner de ranking a la derecha."""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.db.models import ChallengeKind, Difficulty, Visibility
from app.db.session import session_scope
from app.services import challenge_rules, challenges, social
from app.ui import common

DIFFICULTY_LABELS = {
    Difficulty.EASY: "🟢 Fácil",
    Difficulty.MEDIUM: "🟡 Media",
    Difficulty.HARD: "🔴 Difícil",
}
VISIBILITY_LABELS = {Visibility.PUBLIC: "🌎 Público", Visibility.FOLLOWERS: "👥 Sólo seguidores"}


@st.dialog("Crear reto", width="large")
def _create_dialog(user) -> None:
    with st.form("new_challenge"):
        title = st.text_input("Título")
        description = st.text_area("¿En qué consiste? ¿Cómo se demuestra que se cumplió?")
        c1, c2, c3 = st.columns(3)
        difficulty = c1.selectbox(
            "Dificultad", list(Difficulty), format_func=lambda d: DIFFICULTY_LABELS[d], index=1
        )
        points = c2.number_input("Puntos", 1, 100, 10)
        visibility = c3.selectbox(
            "Visibilidad", list(Visibility), format_func=lambda v: VISIBILITY_LABELS[v]
        )
        c4, c5 = st.columns(2)
        starts = c4.date_input("Inicio (opcional)", None)
        ends = c5.date_input("Cierre (opcional)", None, min_value=date.today())
        kind, rule = ChallengeKind.USER, None
        if user.is_admin:
            st.divider()
            st.caption("Opciones de administrador")
            if st.checkbox("Reto global (visible y el mismo para todos los estudiantes)"):
                kind = ChallengeKind.GLOBAL
            rule_code = st.selectbox(
                "Verificación automática",
                ["", *challenge_rules.RULES],
                format_func=lambda r: challenge_rules.RULES[r].label if r else "Manual (evidencia)",
            )
            rule = rule_code or None
        if st.form_submit_button("Crear reto", type="primary"):

            def _create(s):
                ch = challenges.create_challenge(
                    s,
                    s.merge(user),
                    title=title,
                    description=description,
                    difficulty=difficulty,
                    points=points,
                    visibility=visibility,
                    starts_at=starts,
                    ends_at=ends,
                    kind=kind,
                    rule=rule,
                )
                st.session_state["challenge_id"] = ch.id

            common.run_action(_create, "Reto creado")


def _challenge_card(s, user, row: challenges.ChallengeRow) -> None:
    ch = row.challenge
    is_open = challenges.is_open(ch)
    with st.container(border=True):
        kind = (
            ":violet-badge[Global]" if ch.kind == ChallengeKind.GLOBAL else ":blue-badge[Comunidad]"
        )
        badges = [
            kind,
            f":orange-badge[{ch.points} pts]",
            DIFFICULTY_LABELS[Difficulty(ch.difficulty)],
            "🤖 automático" if ch.rule else "📝 con evidencia",
        ]
        if ch.kind == ChallengeKind.USER:
            badges.append(VISIBILITY_LABELS[Visibility(ch.visibility)])
        if not is_open:
            badges.append(":red-badge[cerrado]")
        st.markdown(f"#### {'✅ ' if row.done else ''}{ch.title}\n" + " · ".join(badges))
        st.write(ch.description)
        dates = []
        if ch.starts_at:
            dates.append(f"desde {common.fmt_dt(ch.starts_at)}")
        if ch.ends_at:
            dates.append(f"hasta {common.fmt_dt(ch.ends_at)}")
        creator = ch.creator.display_name if ch.creator else "—"
        st.caption(
            f"Creado por {creator} · 👥 {row.participants} participantes · "
            f"🏁 {row.completed} completaron" + (f" · {' '.join(dates)}" if dates else "")
        )

        if ch.rule and row.joined and not row.done:
            current, target = challenge_rules.progress(s, ch.rule, user.id)
            st.progress(min(1.0, current / target), text=f"Progreso: {current:g} / {target:g}")
        if row.done:
            st.success(f"Completado el {common.fmt_dt(row.my_participation.completed_at)}")

        b = st.columns(4)
        if b[0].button("Ver ranking", key=f"rank_{ch.id}", icon="🏆", width="stretch"):
            st.session_state["challenge_id"] = ch.id
            st.rerun()
        if is_open and not row.joined:
            if b[1].button("Unirme", key=f"join_{ch.id}", type="primary", width="stretch"):
                st.session_state["challenge_id"] = ch.id
                common.run_action(
                    lambda s2: challenges.join(s2, user, ch.id), "¡Te uniste al reto!"
                )
        elif is_open and not row.done:
            if ch.rule:
                if b[1].button("Verificar", key=f"check_{ch.id}", type="primary", width="stretch"):
                    common.run_action(
                        lambda s2: challenges.complete(s2, user, ch.id), "¡Reto completado! 🎉"
                    )
            else:
                with b[1].popover("Cumplido", icon="🏁", width="stretch"):
                    evidence = st.text_area("Evidencia (enlace o descripción)", key=f"ev_{ch.id}")
                    if st.button("Enviar", key=f"done_{ch.id}", type="primary"):
                        common.run_action(
                            lambda s2: challenges.complete(s2, user, ch.id, evidence),
                            "¡Reto completado! 🎉",
                        )
            if b[2].button("Abandonar", key=f"leave_{ch.id}", width="stretch"):
                common.run_action(lambda s2: challenges.leave(s2, user, ch.id), "Saliste del reto")
        if user.is_admin or ch.creator_id == user.id:
            with b[3].popover("Gestionar", icon="⚙️", width="stretch"):
                label = "Cerrar reto" if ch.is_active else "Reabrir reto"
                if st.button(label, key=f"toggle_{ch.id}"):
                    common.run_action(
                        lambda s2: challenges.set_active(s2, user, ch.id, not ch.is_active),
                        "Reto actualizado",
                    )
                if st.button("Eliminar reto", key=f"delete_{ch.id}", icon="🗑️"):
                    st.session_state.pop("challenge_id", None)
                    common.run_action(
                        lambda s2: challenges.delete_challenge(s2, user, ch.id), "Reto eliminado"
                    )


def render() -> None:
    user = common.require_user()
    head, button = st.columns([4, 1], vertical_alignment="bottom")
    head.title("🏆 Retos dinámicos")
    if button.button("Crear reto", icon="➕", type="primary", width="stretch"):
        _create_dialog(user)
    st.caption(
        "Los retos **globales** son los mismos para todos los estudiantes (nuevos y antiguos) y se "
        "verifican automáticamente. Los retos de la **comunidad** los crean los estudiantes: "
        "únete, cúmplelos y compite por llegar primero."
    )

    f1, f2 = st.columns([3, 1], vertical_alignment="bottom")
    scope_label = f1.segmented_control(
        "Mostrar", list(challenges.SCOPES), default="Todos", label_visibility="collapsed"
    )
    only_open = f2.toggle("Sólo abiertos", value=True)

    with session_scope() as s:
        newly_done = challenges.refresh_automatic(s, user)
    for title in newly_done:
        st.toast(f"¡Completaste «{title}»!", icon="🏆")

    left, right = st.columns([2.2, 1], gap="large")
    with session_scope() as s:
        rows = challenges.list_challenges(
            s, user, scope=challenges.SCOPES[scope_label or "Todos"], only_open=only_open
        )
        with left:
            if not rows:
                st.info("No hay retos en esta vista.")
            for row in rows:
                _challenge_card(s, user, row)

        with right:
            selected = st.session_state.get("challenge_id")
            visible_ids = {r.challenge.id for r in rows}
            if selected not in visible_ids:
                selected = rows[0].challenge.id if rows else None
            if selected:
                common.challenge_ranking_banner(s, selected)
            ranking_scope = st.radio(
                "Ranking",
                ["Todos", "Personas que sigo"],
                horizontal=True,
                label_visibility="collapsed",
            )
            if ranking_scope == "Todos":
                common.leaderboard_banner(s)
            else:
                ids = social.following_ids(s, user.id) | {user.id}
                common.leaderboard_banner(s, "Ranking entre amigos", user_ids=ids)
