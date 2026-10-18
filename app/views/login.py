"""Inicio de sesión y registro."""

from __future__ import annotations

import streamlit as st

from app.config import get_settings
from app.db.session import session_scope
from app.services import auth
from app.ui import common


def render() -> None:
    settings = get_settings()
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.title("🎓 CT Ranking")
        st.caption("Foros, plan académico, retos y una comunidad que te impulsa.")
        common.show_flashes()
        tab_login, tab_register = st.tabs(["Iniciar sesión", "Crear cuenta"])

        with tab_login, st.form("login"):
            username = st.text_input("Usuario o correo")
            password = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar", type="primary", width="stretch"):
                try:
                    with session_scope() as s:
                        user = auth.login(s, username, password)
                        user_id, name = user.id, user.display_name
                except auth.AuthError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["user_id"] = user_id
                    common.flash(f"¡Bienvenido, {name}!", "👋")
                    st.rerun()

        with tab_register, st.form("register", clear_on_submit=False):
            c1, c2 = st.columns(2)
            first_name = c1.text_input("Nombre")
            last_name = c2.text_input("Apellido")
            new_username = st.text_input(
                "Usuario", help="3 a 30 caracteres: letras, números, . - _"
            )
            email = st.text_input("Correo")
            c3, c4 = st.columns(2)
            pwd = c3.text_input("Contraseña", type="password", help="Mín. 8 con letras y números")
            pwd2 = c4.text_input("Repite la contraseña", type="password")
            if st.form_submit_button("Crear cuenta", type="primary", width="stretch"):
                if pwd != pwd2:
                    st.error("Las contraseñas no coinciden.")
                else:
                    try:
                        with session_scope() as s:
                            auth.register(
                                s,
                                username=new_username,
                                email=email,
                                password=pwd,
                                first_name=first_name,
                                last_name=last_name,
                            )
                    except auth.AuthError as exc:
                        st.error(str(exc))
                    else:
                        common.flash("Cuenta creada. Ya puedes iniciar sesión.", "🎉")
                        st.rerun()

        provider = "Keycloak" if settings.auth_provider == "keycloak" else "base de datos local"
        st.caption(f"🔒 Autenticación mediante {provider}.")
