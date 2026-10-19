"""Diálogo para enviar mensajes de apoyo (lo usan Personas y Mensajes de apoyo)."""

from __future__ import annotations

import streamlit as st

from app.services import social
from app.ui.components import actions


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
        actions.run_action(
            lambda s: social.send_support(s, sender_id, recipient_id, message),
            f"Mensaje enviado a {recipient_name}",
        )
