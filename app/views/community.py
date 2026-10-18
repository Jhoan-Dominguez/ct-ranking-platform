"""Personas: buscar, seguir, ver perfiles y enviar mensajes de apoyo."""

from __future__ import annotations

import streamlit as st

from app.db.session import session_scope
from app.services import challenges, social, users
from app.ui import common


@st.dialog("Enviar mensaje de apoyo")
def support_dialog(sender_id: int, recipient_id: int, recipient_name: str) -> None:
    st.markdown(f"Para **{recipient_name}**")

    def _use_template() -> None:
        st.session_state["support_msg"] = st.session_state.get("support_tpl") or ""

    st.pills(
        "Mensajes rápidos", social.SUPPORT_TEMPLATES, key="support_tpl", on_change=_use_template
    )
    message = st.text_area("Mensaje", max_chars=social.MAX_MESSAGE_LEN, key="support_msg")
    if st.button("Enviar 💌", type="primary"):
        common.run_action(
            lambda s: social.send_support(s, sender_id, recipient_id, message),
            f"Mensaje enviado a {recipient_name}",
        )


def _person_row(me, person, following: set[int], key: str) -> None:
    with st.container(border=True):
        info, b1, b2, b3 = st.columns([4, 1, 1, 1], vertical_alignment="center")
        with info:
            subtitle = " · ".join(
                x for x in (person.program, f"semestre {person.current_semester}") if x
            )
            common.user_chip(person, 40, subtitle)
        if person.id in following:
            if b1.button("Dejar de seguir", key=f"unf_{key}_{person.id}", width="stretch"):
                common.run_action(lambda s: social.unfollow(s, me.id, person.id))
        elif b1.button("Seguir", key=f"fol_{key}_{person.id}", type="primary", width="stretch"):
            common.run_action(
                lambda s: social.follow(s, me.id, person.id),
                f"Ahora sigues a {person.display_name}",
            )
        if b2.button("Apoyar", key=f"sup_{key}_{person.id}", icon="💌", width="stretch"):
            support_dialog(me.id, person.id, person.display_name)
        if b3.button("Perfil", key=f"prof_{key}_{person.id}", width="stretch"):
            st.session_state["profile_id"] = person.id
            st.rerun()


def _public_profile(me, person_id: int) -> None:
    if st.button("← Volver"):
        st.session_state.pop("profile_id", None)
        st.rerun()
    with session_scope() as s:
        person = users.get_user(s, person_id)
        if person is None:
            st.warning("Usuario no encontrado.")
            return
        n_followers, n_following = social.follow_counts(s, person.id)
        board = challenges.leaderboard(s, limit=10_000)
        score = next((e for e in board if e.user.id == person.id), None)

        left, right = st.columns([1, 3])
        left.markdown(common.avatar_html(person, 140), unsafe_allow_html=True)
        with right:
            st.title(person.display_name)
            st.caption(f"@{person.username} · {person.full_name}")
            if person.bio:
                st.write(person.bio)
            details = [
                ("🎓", person.program),
                ("🏫", person.university),
                ("📍", person.city),
                ("💡", person.interests),
            ]
            st.markdown("  \n".join(f"{i} {v}" for i, v in details if v))
            links = [x for x in (person.github_url, person.linkedin_url) if x]
            if links:
                st.markdown(" · ".join(f"[{x}]({x})" for x in links))

        cols = st.columns(5)
        cols[0].metric("Seguidores", n_followers)
        cols[1].metric("Siguiendo", n_following)
        cols[2].metric("Semestre", f"{person.current_semester}/{person.total_semesters}")
        cols[3].metric("Puntos en retos", score.score if score else 0)
        cols[4].metric("Retos completados", score.completed if score else 0)

        if person.id != me.id:
            following = social.following_ids(s, me.id)
            _person_row(me, person, following, "profile")

        st.subheader("🏅 Retos completados")
        done = challenges.completed_by(s, person.id)
        if not done:
            st.caption("Todavía no ha completado retos.")
        for part in done:
            st.markdown(
                f"- **{part.challenge.title}** · {part.challenge.points} pts · "
                f"{common.fmt_dt(part.completed_at)}"
            )


def render() -> None:
    me = common.require_user()
    profile_id = st.session_state.get("profile_id")
    if profile_id:
        _public_profile(me, profile_id)
        return

    st.title("👥 Personas")
    tab_explore, tab_followers, tab_following = st.tabs(["Explorar", "Seguidores", "Siguiendo"])
    with session_scope() as s:
        following = social.following_ids(s, me.id)
        with tab_explore:
            query = st.text_input("Buscar por nombre, alias, usuario o programa")
            people = users.search_users(s, query, exclude_id=me.id)
            if not people:
                st.info("No se encontraron personas.")
            for person in people:
                _person_row(me, person, following, "exp")
        with tab_followers:
            people = social.followers(s, me.id)
            if not people:
                st.info("Todavía nadie te sigue. ¡Participa en foros y retos para darte a conocer!")
            for person in people:
                _person_row(me, person, following, "fwr")
        with tab_following:
            people = social.following(s, me.id)
            if not people:
                st.info("Aún no sigues a nadie.")
            for person in people:
                _person_row(me, person, following, "fwg")
