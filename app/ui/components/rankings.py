"""Banners de ranking: por reto y general (leaderboard)."""

from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from app.auth import accounts
from app.database.models import Challenge
from app.services import challenges
from app.ui.components.formatting import fmt_dt
from app.ui.components.widgets import user_chip

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def challenge_ranking_banner(session: Session, challenge_id: int) -> None:
    challenge = session.get(Challenge, challenge_id)
    if challenge is None:
        return
    # Las cuentas en proceso de eliminación no se muestran (siguen contando en las métricas).
    hidden = accounts.pending_deletion_ids(session)
    entries = [e for e in challenges.ranking(session, challenge_id) if e.user.id not in hidden]
    stats = challenges.stats(session, challenge_id)
    first = next((e for e in entries if e.position), None)
    with st.container(border=True):
        st.markdown(f"#### 🏆 {challenge.title}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Participantes", stats.participants)
        c2.metric("Completado", stats.completed)
        c3.metric("Éxito", f"{stats.completion_rate:.0%}")
        if first:
            st.success(
                f"🚀 Primero en cumplirlo: **{first.user.display_name}** "
                f"({fmt_dt(first.completed_at)})"
            )
        if not entries:
            st.caption("Nadie se ha unido todavía. ¡Sé el primero!")
        for e in entries[:15]:
            if e.position:
                badge = MEDALS.get(e.position, f"#{e.position}")
                user_chip(e.user, 28, f"{badge} · {fmt_dt(e.completed_at)}")
            else:
                user_chip(e.user, 28, "⏳ en progreso")


def leaderboard_banner(session: Session, title: str = "Ranking general", **kwargs) -> None:
    kwargs.setdefault("exclude_ids", accounts.pending_deletion_ids(session))
    board = challenges.leaderboard(session, **kwargs)
    with st.container(border=True):
        st.markdown(f"#### 📊 {title}")
        st.caption("Puntos de retos completados (+50% para quien termina primero).")
        if not board:
            st.caption("Aún no hay retos completados.")
        for i, e in enumerate(board, start=1):
            user_chip(
                e.user,
                28,
                f"{MEDALS.get(i, f'#{i}')} {e.score} pts · {e.completed} retos · {e.firsts} 🚀",
            )
