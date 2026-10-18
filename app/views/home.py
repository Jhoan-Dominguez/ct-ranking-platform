"""Inicio: resumen personal, retos activos, actividad de quienes sigo y apoyos recibidos."""

from __future__ import annotations

import streamlit as st

from app.db.session import session_scope
from app.services import academics, accounts, challenge_rules, challenges, forum, moderation, social
from app.ui import common


def render() -> None:
    user = common.require_user()

    # Los retos automáticos se re-evalúan al entrar al inicio.
    with session_scope() as s:
        newly_done = challenges.refresh_automatic(s, user)
    for title in newly_done:
        st.toast(f"¡Completaste el reto «{title}»!", icon="🏆")
        st.balloons()

    st.title(f"Hola, {user.display_name} 👋")
    with session_scope() as s:
        summary = academics.user_summary(s, user.id, user.current_semester)
        n_followers, n_following = social.follow_counts(s, user.id)
        hidden = moderation.hidden_user_ids(s, user.id)
        board = challenges.leaderboard(
            s, limit=10_000, exclude_ids=accounts.pending_deletion_ids(s)
        )
        my_score = next((e for e in board if e.user.id == user.id), None)
        position = next((i for i, e in enumerate(board, 1) if e.user.id == user.id), None)

        cols = st.columns(5)
        cols[0].metric("Promedio general", common.fmt_grade(summary.general_average))
        cols[1].metric(
            f"Promedio semestre {user.current_semester}",
            common.fmt_grade(summary.current_semester_average),
        )
        cols[2].metric("Puntos en retos", my_score.score if my_score else 0)
        cols[3].metric("Posición", f"#{position}" if position else "—")
        cols[4].metric("Seguidores / seguidos", f"{n_followers} / {n_following}")

        left, right = st.columns([2, 1])
        with left:
            st.subheader("🏆 Mis retos en curso")
            rows = [
                r
                for r in challenges.list_challenges(s, user, scope="joined")
                if not r.done and challenges.is_open(r.challenge)
            ]
            if not rows:
                st.info("No tienes retos en curso. Visita **Retos** para unirte a uno.")
            for r in rows:
                with st.container(border=True):
                    st.markdown(f"**{r.challenge.title}** · {r.challenge.points} pts")
                    if r.challenge.rule:
                        current, target = challenge_rules.progress(s, r.challenge.rule, user.id)
                        st.progress(min(1.0, current / target), text=f"{current:g} / {target:g}")
                    else:
                        st.caption("Verificación manual: marca el reto como cumplido en Retos.")

            st.subheader("💬 Últimas discusiones")
            for row in forum.list_posts(s, limit=5, exclude_author_ids=hidden):
                st.markdown(
                    f"- **{row.post.title}** — {row.post.author.display_name} · "
                    f"{row.comments} 💬 · {row.likes} 👍"
                    + (" · ✅ resuelta" if row.post.is_solved else "")
                )

        with right:
            st.subheader("💌 Apoyos recibidos")
            inbox = social.inbox(s, user.id, limit=5)
            if not inbox:
                st.caption("Aún no has recibido mensajes de apoyo.")
            for m in inbox:
                with st.container(border=True):
                    common.user_chip(m.sender, 28, common.fmt_dt(m.created_at))
                    st.write(m.message)

            st.subheader("👀 Actividad de quienes sigues")
            activity = [
                a
                for a in challenges.following_activity(s, user, limit=8)
                if a.user.id not in hidden
            ]
            if not activity:
                st.caption("Sigue a otras personas para ver sus logros aquí.")
            for a in activity:
                common.user_chip(a.user, 28, f"completó «{a.challenge_title}»")
