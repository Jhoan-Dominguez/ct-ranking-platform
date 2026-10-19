"""Ejecución de escrituras desde la UI y avisos (toasts) que sobreviven al rerun."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth
from app.auth.accounts import AccountError
from app.core.mailer import MailError
from app.database.session import session_scope
from app.services.academics import AcademicError
from app.services.admin import AdminError
from app.services.challenges import ChallengeError
from app.services.forum import ForumError
from app.services.moderation import ModerationError
from app.services.social import SocialError
from app.services.users import ProfileError

USER_ERRORS = (
    auth.AuthError,
    AccountError,
    AdminError,
    MailError,
    ModerationError,
    AcademicError,
    ChallengeError,
    ForumError,
    SocialError,
    ProfileError,
)


def flash(message: str, icon: str = "✅") -> None:
    st.session_state.setdefault("_flash", []).append((message, icon))


def show_flashes() -> None:
    for message, icon in st.session_state.pop("_flash", []):
        st.toast(message, icon=icon)


def run_action(fn: Callable[[Session], Any], success: str | None = None, rerun: bool = True):
    """Ejecuta una escritura en su propia transacción. Los errores de negocio se muestran como
    mensaje; si todo va bien se programa un aviso y se recarga la página."""
    try:
        with session_scope() as s:
            result = fn(s)
    except USER_ERRORS as exc:
        st.error(str(exc))
        return None
    except IntegrityError:
        # Dos clics seguidos (o dos pestañas) intentaron crear la misma fila: la restricción
        # única de la BD lo impidió. Se recarga para mostrar el estado real.
        flash("Esa acción ya se había realizado.", "ℹ️")
        st.rerun()
    if success:
        flash(success)
    if rerun:
        st.rerun()
    return result
