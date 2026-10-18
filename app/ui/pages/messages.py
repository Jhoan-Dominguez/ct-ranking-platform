"""Bandeja de mensajes de apoyo."""

from __future__ import annotations

import streamlit as st

from app.database.session import session_scope
from app.services import social
from app.ui.components import formatting, session, widgets
from app.ui.components.moderation import actions_menu
from app.ui.pages.community import support_dialog


def render() -> None:
    user = session.require_user()
    st.title("💌 Mensajes de apoyo")
    st.caption("Un «¡vamos, tú puedes!» a tiempo hace la diferencia.")

    tab_in, tab_out = st.tabs(["Recibidos", "Enviados"])
    with session_scope() as s:
        unread = {m.id for m in social.inbox(s, user.id) if not m.is_read}
        with tab_in:
            messages = social.inbox(s, user.id)
            if not messages:
                st.info("Aún no has recibido mensajes de apoyo.")
            for m in messages:
                with st.container(border=True):
                    head, action, more = st.columns([5, 1, 0.8], vertical_alignment="center")
                    with head:
                        new = " 🆕" if m.id in unread else ""
                        widgets.user_chip(m.sender, 32, formatting.fmt_dt(m.created_at) + new)
                        st.markdown(f"> {m.message}")
                    if action.button("Responder", key=f"reply_{m.id}", icon="↩️"):
                        support_dialog(user.id, m.sender_id, m.sender.display_name)
                    with more:
                        actions_menu(user.id, m.sender_id, m.sender.display_name, f"msg_{m.id}")
        with tab_out:
            messages = social.sent(s, user.id)
            if not messages:
                st.info("No has enviado mensajes. Ve a **Personas** para animar a alguien.")
            for m in messages:
                with st.container(border=True):
                    widgets.user_chip(m.recipient, 32, f"para · {formatting.fmt_dt(m.created_at)}")
                    st.markdown(f"> {m.message}")
        if unread:
            social.mark_all_read(s, user.id)
