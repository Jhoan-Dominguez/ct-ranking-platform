"""Perfil personalizable: datos personales, foto, correo y contraseña."""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.db.session import session_scope
from app.services import auth, social, users
from app.ui import common


def render() -> None:
    user = common.require_user()
    st.title("👤 Mi perfil")

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
        tab_data, tab_academic, tab_security = st.tabs(
            ["Datos personales", "Datos académicos", "Cuenta y seguridad"]
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
            st.text_input("Usuario", user.username, disabled=True)
            with st.form("email"):
                email = st.text_input("Correo electrónico", user.email)
                if st.form_submit_button("Actualizar correo"):
                    common.run_action(
                        lambda s: auth.change_email(s, s.merge(user), email), "Correo actualizado"
                    )
            with st.form("password", clear_on_submit=True):
                st.markdown("**Cambiar contraseña**")
                current_pwd = st.text_input("Contraseña actual", type="password")
                new_pwd = st.text_input("Nueva contraseña", type="password")
                new_pwd2 = st.text_input("Repite la nueva contraseña", type="password")
                if st.form_submit_button("Cambiar contraseña"):
                    if new_pwd != new_pwd2:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        common.run_action(
                            lambda s: auth.change_password(s, s.merge(user), current_pwd, new_pwd),
                            "Contraseña actualizada",
                        )

    with session_scope() as s:
        n_followers, n_following = social.follow_counts(s, user.id)
    st.caption(f"👥 {n_followers} seguidores · {n_following} siguiendo")
