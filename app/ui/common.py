"""Utilidades compartidas por las vistas de Streamlit."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any

import streamlit as st
from sqlalchemy.orm import Session

from app.db.models import Challenge, SubjectCategory, User
from app.db.session import session_scope
from app.services import accounts, auth, challenges
from app.services.academics import AcademicError
from app.services.accounts import AccountError
from app.services.challenges import ChallengeError
from app.services.forum import ForumError
from app.services.mailer import MailError
from app.services.moderation import ModerationError
from app.services.social import SocialError
from app.services.users import ProfileError

CATEGORY_LABELS = {
    SubjectCategory.SCIENCES: "🔬 Ciencias",
    SubjectCategory.HUMANITIES: "📜 Humanidades",
    SubjectCategory.TECHNOLOGY: "💻 Tecnología",
    SubjectCategory.LANGUAGES: "🌐 Idiomas",
}

USER_ERRORS = (
    auth.AuthError,
    AccountError,
    MailError,
    ModerationError,
    AcademicError,
    ChallengeError,
    ForumError,
    SocialError,
    ProfileError,
)

# --------------------------------------------------------------------------- sesión


def current_user() -> User | None:
    """Recarga el usuario autenticado desde la BD en cada ejecución (objeto desacoplado)."""
    user_id = st.session_state.get("user_id")
    if user_id is None:
        return None
    with session_scope() as s:
        user = s.get(User, user_id)
    if user is None or not user.is_active:
        st.session_state.pop("user_id", None)
        return None
    return user


def require_user() -> User:
    user = current_user()
    if user is None:
        st.stop()
    return user  # type: ignore[return-value]


def logout() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


@cache
def _sidebar_hover_script() -> str:
    return (Path(__file__).with_name("sidebar_hover.js")).read_text(encoding="utf-8")


def enable_sidebar_hover() -> None:
    """Expande la barra lateral oculta al pasar el mouse por el borde izquierdo
    (ver app/ui/sidebar_hover.js). Debe llamarse dentro de ``with st.sidebar``."""
    st.html(f"<script>{_sidebar_hover_script()}</script>", unsafe_allow_javascript=True)


# --------------------------------------------------------------------------- acciones


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
    if success:
        flash(success)
    if rerun:
        st.rerun()
    return result


# --------------------------------------------------------------------------- formato


def fmt_grade(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def fmt_dt(value: datetime | date | None, with_time: bool = True) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone()
        return value.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")
    return value.strftime("%d/%m/%Y")


def _initials_svg(user: User, size: int) -> str:
    initials = "".join(p[0] for p in (user.first_name, user.last_name) if p).upper() or "?"
    hue = int(hashlib.md5(user.username.encode()).hexdigest()[:2], 16) * 360 // 256
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">'
        f'<circle cx="50%" cy="50%" r="50%" fill="hsl({hue},55%,45%)"/>'
        f'<text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" '
        f'font-family="sans-serif" font-size="{size * 0.4:.0f}" fill="#fff">{initials}</text>'
        "</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def avatar_src(user: User, size: int = 48) -> str:
    if user.avatar:
        return (
            f"data:{user.avatar_mime or 'image/png'};base64,"
            + base64.b64encode(user.avatar).decode()
        )
    return _initials_svg(user, size)


def avatar_html(user: User, size: int = 40) -> str:
    return (
        f'<img src="{avatar_src(user, size)}" width="{size}" height="{size}" '
        f'style="border-radius:50%;object-fit:cover;vertical-align:middle" alt="">'
    )


def user_chip(user: User, size: int = 32, subtitle: str = "") -> None:
    sub = f'<br><span style="opacity:.65;font-size:.85em">{subtitle}</span>' if subtitle else ""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:.6rem">{avatar_html(user, size)}'
        f"<div><b>{_escape(user.display_name)}</b> "
        f'<span style="opacity:.6">@{_escape(user.username)}</span>{sub}</div></div>',
        unsafe_allow_html=True,
    )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------------------- banners de ranking

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
