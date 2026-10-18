"""Pantalla única para una cuenta con eliminación programada: permite cancelarla."""

from __future__ import annotations

import streamlit as st

from app.auth import accounts
from app.ui.components import actions, formatting, session


def render(user) -> None:
    """Única pantalla disponible para una cuenta con eliminación programada."""
    _, center, _ = st.columns([1, 1.6, 1])
    with center:
        st.title("Tu cuenta será eliminada")
        when = formatting.fmt_dt(user.deletion_scheduled_for)
        st.warning(
            f"Solicitaste eliminar tu cuenta. Está **desactivada** y se borrará definitivamente "
            f"el **{when}**, junto con tu perfil, plan académico, publicaciones y demás datos.",
            icon="⚠️",
        )
        st.write("Mientras tanto nadie puede ver tu perfil ni tu contenido.")
        c1, c2 = st.columns(2)
        if c1.button("Cancelar eliminación", type="primary", icon="↩️", width="stretch"):

            def _cancel(s):
                accounts.cancel_deletion(s, s.merge(user))

            actions.run_action(_cancel, "¡Tu cuenta vuelve a estar activa!")
        if c2.button("Cerrar sesión", icon="🚪", width="stretch"):
            session.logout()
            st.rerun()
