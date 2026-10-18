"""Bandeja de mensajes de apoyo."""

from __future__ import annotations

import streamlit as st

from app.db.session import session_scope
from app.services import social
from app.ui import common
from app.views.community import support_dialog


def render() -> None:
    user = common.require_user()
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
                    head, action = st.columns([5, 1], vertical_alignment="center")
                    with head:
                        new = " 🆕" if m.id in unread else ""
                        common.user_chip(m.sender, 32, common.fmt_dt(m.created_at) + new)
                        st.markdown(f"> {m.message}")
                    if action.button("Responder", key=f"reply_{m.id}", icon="↩️"):
                        support_dialog(user.id, m.sender_id, m.sender.display_name)
        with tab_out:
            messages = social.sent(s, user.id)
            if not messages:
                st.info("No has enviado mensajes. Ve a **Personas** para animar a alguien.")
            for m in messages:
                with st.container(border=True):
                    common.user_chip(m.recipient, 32, f"para · {common.fmt_dt(m.created_at)}")
                    st.markdown(f"> {m.message}")
        if unread:
            social.mark_all_read(s, user.id)
