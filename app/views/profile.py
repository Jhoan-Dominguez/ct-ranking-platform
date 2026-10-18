"""Perfil personalizable: datos personales, foto, correo y contraseña."""

from __future__ import annotations

from datetime import date

import requests
import streamlit as st

from app.config import get_settings
from app.db.session import session_scope
from app.services import accounts, auth, social, users
from app.ui import common

CODE_SENT = "_deletion_code_sent"


def _otp_input(two_factor: bool, key: str) -> str:
    if not two_factor:
        return ""
    return st.text_input("Código de tu app autenticadora (2FA)", max_chars=6, key=key)


def _security_tab(user, two_factor: bool) -> None:
    st.text_input("Usuario", user.username, disabled=True)
    with st.form("email"):
        if user.is_admin:
            email_value = st.text_input("Correo electrónico", user.email)
        else:
            email_value = common.institutional_email_input("Correo institucional", user.email)
        if st.form_submit_button("Actualizar correo"):

            def _change(s):
                email = email_value if user.is_admin else auth.student_email(email_value)
                auth.change_email(s, s.merge(user), email)

            common.run_action(_change, "Correo actualizado")
    with st.form("password", clear_on_submit=True):
        st.markdown("**Cambiar contraseña**")
        current_pwd = st.text_input("Contraseña actual", type="password")
        new_pwd = st.text_input("Nueva contraseña", type="password")
        new_pwd2 = st.text_input("Repite la nueva contraseña", type="password")
        otp = _otp_input(two_factor, "pwd_otp")
        if st.form_submit_button("Cambiar contraseña"):
            if new_pwd != new_pwd2:
                st.error("Las contraseñas no coinciden.")
            else:
                common.run_action(
                    lambda s: auth.change_password(
                        s, s.merge(user), current_pwd, new_pwd, otp or None
                    ),
                    "Contraseña actualizada",
                )

    st.markdown("#### 🔐 Verificación en dos pasos (2FA)")
    if not auth.two_factor_supported():
        st.info("La verificación en dos pasos requiere Keycloak (`AUTH_PROVIDER=keycloak`).")
        return
    if two_factor:
        st.success("Activada: al iniciar sesión te pediremos el código de tu app autenticadora.")
        with st.expander("Desactivar 2FA"), st.form("disable_2fa", clear_on_submit=True):
            password = st.text_input("Contraseña", type="password")
            code = st.text_input("Código actual de tu app autenticadora", max_chars=6)
            if st.form_submit_button("Desactivar 2FA"):
                common.run_action(
                    lambda _s: auth.disable_two_factor(user, password, code),
                    "Verificación en dos pasos desactivada",
                )
        return
    st.write(
        "Protege tu cuenta con un código temporal de 6 dígitos que genera una app en tu celular "
        "(Google Authenticator, Microsoft Authenticator o FreeOTP)."
    )
    st.markdown(
        f"1. Pulsa **Enviar enlace de configuración**: llegará un correo a **{user.email}**.\n"
        "2. Abre el enlace: verás un **código QR**. Escanéalo con tu app autenticadora.\n"
        "3. Escribe en esa página el código que muestra la app para confirmar.\n"
        "4. Desde entonces, al iniciar sesión escribe también el código de la app."
    )
    if st.button("Enviar enlace de configuración", icon="📧", type="primary"):
        common.run_action(
            lambda _s: auth.request_two_factor_setup(user),
            f"Te enviamos el enlace a {user.email} (válido por {auth.TOTP_SETUP_LINK_HOURS} horas)",
        )


def _delete_tab(user, two_factor: bool) -> None:
    days = get_settings().account_deletion_days
    st.markdown("#### ⚠️ Eliminar mi cuenta")
    st.write(
        f"Tu cuenta quedará **desactivada** de inmediato y se eliminará definitivamente a los "
        f"**{days} días**, junto con tu perfil, plan académico, notas, publicaciones, comentarios, "
        "retos creados, participaciones, seguidores y mensajes. Durante ese plazo puedes "
        "cancelarlo iniciando sesión."
    )
    if not st.session_state.get(CODE_SENT):
        st.markdown("**Paso 1 de 2:** confirma que eres tú.")
        with st.form("delete_step1", clear_on_submit=True):
            password = st.text_input("Contraseña", type="password")
            otp = _otp_input(two_factor, "delete_otp")
            if st.form_submit_button("Enviarme el código de confirmación", icon="📧"):

                def _request(s):
                    accounts.request_deletion(s, s.merge(user), password, otp or None)
                    st.session_state[CODE_SENT] = True

                common.run_action(_request, f"Te enviamos un código a {user.email}")
        return

    st.markdown(f"**Paso 2 de 2:** escribe el código que enviamos a **{user.email}**.")
    with st.form("delete_step2"):
        code = st.text_input("Código de 6 dígitos", max_chars=6)
        confirm = st.checkbox(
            f"Entiendo que mi cuenta se eliminará definitivamente en {days} días."
        )
        if st.form_submit_button("Eliminar mi cuenta", type="primary", icon="🗑️"):
            if not confirm:
                st.error("Marca la casilla de confirmación.")
            else:
                when = common.run_action(
                    lambda s: accounts.confirm_deletion(s, s.merge(user), code), rerun=False
                )
                if when is not None:
                    common.logout()
                    common.flash(
                        f"Tu cuenta se eliminará el {common.fmt_dt(when)}. Inicia sesión antes "
                        "de esa fecha si quieres cancelarlo.",
                        "⚠️",
                    )
                    st.rerun()
    if st.button("Volver a empezar", icon="↩️"):
        st.session_state.pop(CODE_SENT, None)
        st.rerun()


def render() -> None:
    user = common.require_user()
    st.title("👤 Mi perfil")
    try:
        two_factor = auth.two_factor_enabled(user)
    except (auth.AuthError, requests.RequestException):
        two_factor = False
        st.warning("No fue posible consultar el estado del 2FA en Keycloak.", icon="⚠️")

    left, right = st.columns([1, 3])
    with left:
        st.markdown(common.avatar_html(user, 160), unsafe_allow_html=True)
        upload = st.file_uploader("Cambiar foto", type=["png", "jpg", "jpeg", "webp"])
        if upload is not None and st.button("Guardar foto", type="primary"):
            raw = upload.getvalue()
            common.run_action(lambda s: users.set_avatar(s.merge(user), raw), "Foto actualizada")
        if user.avatar and st.button("Quitar foto"):
            common.run_action(lambda s: users.set_avatar(s.merge(user), None), "Foto eliminada")
        st.caption(f"Miembro desde {common.fmt_dt(user.created_at, with_time=False)}")
        st.caption(f"Rol: {'administrador' if user.is_admin else 'estudiante'}")

    with right:
        tab_data, tab_academic, tab_security, tab_delete = st.tabs(
            ["Datos personales", "Datos académicos", "Cuenta y seguridad", "Eliminar cuenta"]
        )
        with tab_data, st.form("profile"):
            c1, c2, c3 = st.columns(3)
            first_name = c1.text_input("Nombre", user.first_name)
            last_name = c2.text_input("Apellido", user.last_name)
            alias = c3.text_input("Alias", user.alias, help="Así te verán los demás")
            bio = st.text_area("Biografía", user.bio, max_chars=1000)
            c4, c5, c6 = st.columns(3)
            phone = c4.text_input("Teléfono", user.phone)
            city = c5.text_input("Ciudad", user.city)
            birth = c6.date_input(
                "Fecha de nacimiento",
                user.birth_date,
                min_value=date(1940, 1, 1),
                max_value=date.today(),
                format="DD/MM/YYYY",
            )
            interests = st.text_input("Intereses", user.interests, placeholder="IA, música, …")
            c7, c8 = st.columns(2)
            github = c7.text_input("GitHub", user.github_url)
            linkedin = c8.text_input("LinkedIn", user.linkedin_url)
            if st.form_submit_button("Guardar cambios", type="primary"):

                def _save(s):
                    u = s.merge(user)
                    auth.change_names(s, u, first_name, last_name)
                    users.update_profile(
                        s,
                        u,
                        alias=alias,
                        bio=bio,
                        phone=phone,
                        city=city,
                        birth_date=birth,
                        interests=interests,
                        github_url=github,
                        linkedin_url=linkedin,
                    )

                common.run_action(_save, "Perfil actualizado")

        with tab_academic, st.form("academic"):
            c1, c2 = st.columns(2)
            university = c1.text_input("Universidad", user.university)
            code = c2.text_input("Código estudiantil", user.student_code)
            c3, c4 = st.columns(2)
            program = c3.text_input("Programa / carrera", user.program)
            plan = c4.text_input("Plan de estudios", user.study_plan)
            c5, c6 = st.columns(2)
            current = c5.number_input("Semestre actual", 1, 20, user.current_semester)
            total = c6.number_input("Total de semestres", 1, 20, user.total_semesters)
            if st.form_submit_button("Guardar", type="primary"):
                common.run_action(
                    lambda s: users.update_profile(
                        s,
                        s.merge(user),
                        university=university,
                        student_code=code,
                        program=program,
                        study_plan=plan,
                        current_semester=current,
                        total_semesters=total,
                    ),
                    "Datos académicos actualizados",
                )

        with tab_security:
            _security_tab(user, two_factor)
        with tab_delete:
            _delete_tab(user, two_factor)

    with session_scope() as s:
        n_followers, n_following = social.follow_counts(s, user.id)
    st.caption(f"👥 {n_followers} seguidores · {n_following} siguiendo")
