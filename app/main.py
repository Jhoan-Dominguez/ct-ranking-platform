"""Punto de entrada de Streamlit: ``streamlit run app/main.py`` (o ``make run``)."""

from __future__ import annotations

import sys
from pathlib import Path

# Permite `streamlit run app/main.py` sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from sqlalchemy.exc import OperationalError

from app.db.session import session_scope
from app.services import social
from app.ui import common
from app.views import (
    academics,
    admin,
    challenges,
    community,
    forum,
    home,
    login,
    messages,
    profile,
)

st.set_page_config(page_title="CT Ranking", page_icon="🎓", layout="wide")


def main() -> None:
    try:
        user = common.current_user()
    except OperationalError:
        st.error(
            "No hay conexión con la base de datos. Levanta los servicios con `make up` "
            "e inicialízala con `make init-db`."
        )
        st.stop()

    if user is None:
        st.navigation([st.Page(login.render, title="Ingresar", icon="🔐")], position="hidden").run()
        return

    with session_scope() as s:
        unread = social.unread_count(s, user.id)

    pages = {
        "Plataforma": [
            st.Page(home.render, title="Inicio", icon="🏠", url_path="inicio", default=True),
            st.Page(forum.render, title="Foros", icon="💬", url_path="foros"),
            st.Page(academics.render, title="Plan académico", icon="📚", url_path="academico"),
            st.Page(challenges.render, title="Retos", icon="🏆", url_path="retos"),
        ],
        "Comunidad": [
            st.Page(community.render, title="Personas", icon="👥", url_path="personas"),
            st.Page(
                messages.render,
                title=f"Mensajes de apoyo{f' ({unread})' if unread else ''}",
                icon="💌",
                url_path="mensajes",
            ),
            st.Page(profile.render, title="Mi perfil", icon="👤", url_path="perfil"),
        ],
    }
    if user.is_admin:
        pages["Administración"] = [
            st.Page(admin.render, title="Panel de administrador", icon="🛡️", url_path="admin")
        ]

    with st.sidebar:
        st.markdown(
            f'<div style="text-align:center">{common.avatar_html(user, 72)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"<center><b>{user.display_name}</b></center>", unsafe_allow_html=True)
        st.caption(
            f"<center>@{user.username} · {user.program or 'sin programa'}</center>",
            unsafe_allow_html=True,
        )
        if st.button("Cerrar sesión", icon="🚪", width="stretch"):
            common.logout()
            st.rerun()
        common.enable_sidebar_hover()

    common.show_flashes()
    st.navigation(pages).run()


main()
